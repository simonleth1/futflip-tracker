import os
import logging
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
import yaml
from storage import init_db, PricePoint, TrackedCard, HypeEvent, Alert
from futbin_fetcher import FutbinFetcher
from trend_detector import compute_rolling_signals, score_flip
from datetime import datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from leak_listener_reddit import RedditListener
from alerting import send_telegram, send_discord_webhook

load_dotenv()
app = Flask(__name__, static_folder='static', static_url_path='/static')

# Load config
cfg_path = os.environ.get('FUTFLIP_CONFIG', 'config.yaml')
if not os.path.exists(cfg_path):
    cfg_path = 'config.example.yaml'
with open(cfg_path) as f:
    cfg = yaml.safe_load(f)

DB_URL = os.getenv('DATABASE_URL', cfg['database']['url'])
SessionMaker = init_db(DB_URL)

fetcher_cfg = cfg['sources']['futbin']
fetcher = FutbinFetcher(fetcher_cfg['base_url'], fetcher_cfg['price_selector'], user_agent=fetcher_cfg.get('user_agent'))

scheduler = BackgroundScheduler()
JOB_IDS = {
    'poller': 'poller_job',
    'evaluator': 'eval_job',
    'reddit': 'reddit_job'
}

# Helper functions
def poll_all_cards():
    session = SessionMaker()
    cards = session.query(TrackedCard).all()
    for card in cards:
        try:
            res = fetcher.fetch_card_price(card.futbin_url, platform=card.platform)
            if res and 'price' in res:
                p = PricePoint(card_id=card.card_id, platform=card.platform, price=res['price'], extra={'raw': res.get('raw'), 'source': res.get('source')})
                session.add(p)
                session.commit()
                app.logger.info('Polled %s -> %s', card.card_id, res['price'])
        except Exception:
            app.logger.exception('Poll failed for %s', card.card_id)
    session.close()

def evaluate_and_alert():
    session = SessionMaker()
    cards = session.query(TrackedCard).all()
    for card in cards:
        q = session.query(PricePoint).filter(PricePoint.card_id == card.card_id).order_by(PricePoint.ts.desc()).limit(720)
        rows = list(q)
        if not rows:
            continue
        df = pd.DataFrame([{'ts': r.ts, 'price': r.price} for r in rows])
        df = df.sort_values('ts')
        sig = compute_rolling_signals(df, short_minutes=cfg['signals']['short_window_minutes'], long_minutes=cfg['signals']['long_window_minutes'])
        if not sig:
            continue
        # compute a naive hype_score from recent HypeEvents
        recent = session.query(HypeEvent).filter(HypeEvent.card_id==card.card_id).order_by(HypeEvent.ts.desc()).limit(20)
        hype_score = 0.0
        for h in recent:
            # simple decay weighting
            delta = (datetime.utcnow() - h.ts).total_seconds()/3600.0
            weight = max(0.0, 1.0 - delta/24.0)
            hype_score += (h.score or 0.0) * weight
        hype_score = min(max(hype_score/5.0, 0.0), 1.0)
        flip_score = score_flip(sig['latest'], sig['momentum'], sig['zscore'], hype_score, fee_pct=cfg['signals']['market_fee_pct'])
        app.logger.debug('Eval %s z=%.2f mom=%.3f hype=%.2f score=%.3f', card.card_id, sig['zscore'] or 0.0, sig['momentum'] or 0.0, hype_score, flip_score)
        if sig.get('zscore') and sig['zscore'] > cfg['signals']['zscore_threshold'] and flip_score > 0.02:
            msg = f"FLIP ALERT: {card.name} ({card.card_id}) latest={sig['latest']:.0f} z={sig['zscore']:.2f} mom={sig['momentum']:.3f} hype={hype_score:.2f} score={flip_score:.3f}"
            sent = []
            if cfg['alerting'].get('telegram_enabled'):
                if send_telegram(msg):
                    sent.append('telegram')
            if cfg['alerting'].get('discord_enabled'):
                if send_discord_webhook(msg):
                    sent.append('discord')
            a = Alert(card_id=card.card_id, message=msg, sent_to=','.join(sent))
            session.add(a)
            session.commit()
    session.close()

# Reddit leak poller job
def reddit_poll_job():
    reddit_cfg = cfg.get('reddit')
    if not reddit_cfg or not reddit_cfg.get('enabled'):
        return
    client_id = os.getenv('REDDIT_CLIENT_ID')
    client_secret = os.getenv('REDDIT_CLIENT_SECRET')
    user_agent = reddit_cfg.get('user_agent','futflip-reddit-listener')

    listener = RedditListener(client_id, client_secret, user_agent, reddit_cfg.get('subreddits',[]), reddit_cfg.get('keywords',None))
    session = SessionMaker()
    candidates = [c.name for c in session.query(TrackedCard).all()]
    for post in listener.poll_new_posts(limit=50):
        mentions = listener.extract_player_mentions(post['text'], candidates, limit=5)
        for name, score in mentions:
            # map name to card_id(s)
            card = session.query(TrackedCard).filter(TrackedCard.name==name).first()
            if card:
                he = HypeEvent(card_id=card.card_id, source='reddit', score=score/100.0, text=post['text'], ts=post['created_utc'])
                session.add(he)
                session.commit()
                app.logger.info('HypeEvent for %s score=%.2f', card.card_id, score/100.0)
    session.close()

# Routes
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/cards', methods=['GET'])
def api_cards():
    session = SessionMaker()
    cards = session.query(TrackedCard).all()
    out = []
    for c in cards:
        # compute simple recent hype
        recent = session.query(HypeEvent).filter(HypeEvent.card_id==c.card_id).order_by(HypeEvent.ts.desc()).limit(5)
        hype = sum((h.score or 0.0) for h in recent)
        out.append({'card_id': c.card_id, 'name': c.name, 'futbin_url': c.futbin_url, 'platform': c.platform, 'hype_score': round(hype,3)})
    session.close()
    return jsonify(out)

@app.route('/api/cards', methods=['POST'])
def api_add_card():
    data = request.get_json()
    required = ['card_id','name','futbin_url']
    if not all(k in data for k in required):
        return jsonify({'error':'missing fields'}), 400
    session = SessionMaker()
    existing = session.query(TrackedCard).filter(TrackedCard.card_id == data['card_id']).first()
    if existing:
        session.close()
        return jsonify({'error':'card exists'}), 400
    c = TrackedCard(card_id=data['card_id'], name=data['name'], futbin_url=data['futbin_url'], platform=data.get('platform','ps'))
    session.add(c)
    session.commit()
    session.close()
    return jsonify({'ok':True})

@app.route('/api/import_csv', methods=['POST'])
def api_import_csv():
    if 'file' not in request.files:
        return jsonify({'error':'no file'}), 400
    f = request.files['file']
    content = f.read().decode('utf-8')
    import csv
    reader = csv.DictReader(content.splitlines())
    session = SessionMaker()
    added = 0
    for row in reader:
        if not row.get('card_id') or not row.get('name') or not row.get('futbin_url'):
            continue
        exists = session.query(TrackedCard).filter(TrackedCard.card_id==row['card_id']).first()
        if exists:
            continue
        c = TrackedCard(card_id=row['card_id'], name=row['name'], futbin_url=row['futbin_url'], platform=row.get('platform','ps'))
        session.add(c)
        added += 1
    session.commit()
    session.close()
    return jsonify({'ok':True, 'added':added})

@app.route('/api/prices/<card_id>', methods=['GET'])
def api_prices(card_id):
    session = SessionMaker()
    q = session.query(PricePoint).filter(PricePoint.card_id == card_id).order_by(PricePoint.ts.asc()).all()
    out = [{'ts': p.ts.isoformat(), 'price': p.price} for p in q]
    session.close()
    return jsonify(out)

@app.route('/api/refresh/<card_id>', methods=['POST'])
def api_refresh(card_id):
    session = SessionMaker()
    card = session.query(TrackedCard).filter(TrackedCard.card_id == card_id).first()
    if not card:
        session.close()
        return jsonify({'error':'not found'}), 404
    res = fetcher.fetch_card_price(card.futbin_url, platform=card.platform)
    if not res:
        session.close()
        return jsonify({'error':'fetch failed'}), 500
    p = PricePoint(card_id=card.card_id, platform=card.platform, price=res['price'], extra={'raw': res.get('raw')})
    session.add(p)
    session.commit()
    session.close()
    return jsonify({'ok':True, 'price': res['price']})

@app.route('/api/signals/<card_id>', methods=['GET'])
def api_signals(card_id):
    session = SessionMaker()
    q = session.query(PricePoint).filter(PricePoint.card_id == card_id).order_by(PricePoint.ts.desc()).limit(720)
    rows = list(q)
    session.close()
    if not rows:
        return jsonify({'error':'no data'}), 404
    df = pd.DataFrame([{'ts': r.ts, 'price': r.price} for r in rows])
    df = df.sort_values('ts')
    sig = compute_rolling_signals(df, short_minutes=cfg['signals']['short_window_minutes'], long_minutes=cfg['signals']['long_window_minutes'])
    return jsonify(sig or {})

@app.route('/api/auto_poll/start', methods=['POST'])
def api_start_poll():
    # start scheduler jobs if not running
    if not scheduler.get_job(JOB_IDS['poller']):
        scheduler.add_job(poll_all_cards, 'interval', seconds=cfg['monitor']['default_poll_interval_seconds'], id=JOB_IDS['poller'])
    if not scheduler.get_job(JOB_IDS['evaluator']):
        scheduler.add_job(evaluate_and_alert, 'interval', seconds=cfg['monitor']['default_poll_interval_seconds'], id=JOB_IDS['evaluator'])
    # reddit
    reddit_cfg = cfg.get('reddit')
    if reddit_cfg and reddit_cfg.get('enabled') and not scheduler.get_job(JOB_IDS['reddit']):
        scheduler.add_job(reddit_poll_job, 'interval', seconds=reddit_cfg.get('poll_interval_seconds',300), id=JOB_IDS['reddit'])
    return jsonify({'ok':True})

@app.route('/api/auto_poll/stop', methods=['POST'])
def api_stop_poll():
    for jid in JOB_IDS.values():
        job = scheduler.get_job(jid)
        if job:
            scheduler.remove_job(jid)
    return jsonify({'ok':True})

@app.route('/api/scheduler/status', methods=['GET'])
def api_scheduler_status():
    jobs = scheduler.get_jobs()
    return jsonify({'jobs':[j.id for j in jobs]})

# Start scheduler if configured
if cfg.get('monitor',{}).get('auto_start', False):
    scheduler.start()
else:
    # always start scheduler but without jobs so UI can start/stop
    scheduler.start()

if __name__ == '__main__':
    # start default jobs if auto_start true
    if cfg.get('monitor',{}).get('auto_start', False):
        api_start_poll()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=(os.getenv('LOGLEVEL','INFO')=='DEBUG'))
