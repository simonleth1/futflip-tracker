# futflip-tracker

Prototype FUT Flip Tracker with a small web UI (Flask + Chart.js).

This update adds:
- Background scheduler to auto-poll tracked cards
- CSV import to seed tracked cards
- Reddit leak listener (PRAW) that stores hype events
- Signal evaluation job that can send alerts via Telegram/Discord

Quickstart (macOS)

1) Clone the repo and enter folder:

   git clone https://github.com/simonleth1/futflip-tracker
   cd futflip-tracker

2) Create and activate virtualenv:

   python3 -m venv venv
   source venv/bin/activate

3) Install dependencies:

   pip install -r requirements.txt

   Note: If you plan to use Playwright for JS-heavy scraping, install it and browsers:
   pip install playwright
   playwright install

4) Create config and env files:

   cp .env.example .env
   cp config.example.yaml config.yaml

   Edit .env to set DATABASE_URL (or leave default sqlite), and set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET if you want reddit listener. Also add TELEGRAM/ DISCORD webhooks if desired.

5) Edit config.yaml:

   - Add any seed tracked cards under tracking.cards or import a CSV in the UI.
   - Set monitor.auto_start: true if you want the scheduler to begin automatically.
   - Configure reddit section (subreddits and poll interval) if you will use Reddit.

6) Run the app:

   python app.py

7) Open http://localhost:5000 in your browser.

Using the UI

- Add cards manually or import a CSV with columns: card_id,name,futbin_url,platform.
- Click Select on a card to view its price chart.
- Use Refresh Price Now to fetch current price and store in DB.
- Start Auto Poll to begin background polling and reddit leak scanning.

Reddit leaks

- To enable reddit leaks, create a Reddit app (script) at https://www.reddit.com/prefs/apps and set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in your .env.
- Add a reddit section to config.yaml:

reddit:
  enabled: true
  subreddits: ["FUTMobile","FIFA"]
  poll_interval_seconds: 300
  user_agent: "futflip-reddit-listener"

- The listener looks for configured keywords and fuzzy-matches post titles/text to tracked player names and stores HypeEvent entries.

Notes & next steps

- Price site scraping is fragile; if pages are JS-rendered you may need Playwright.
- Respect Terms of Service for all sites. Use partner APIs where available.
- For production, use Postgres/TimescaleDB, gunicorn, and a reverse proxy.

If you want, I can:
- Add Playwright scrapers and a Docker Compose file.
- Add Twitter/X and Discord real-time listeners (requires API tokens/permissions).
- Build an authenticated UI and add historical charts and filters.

