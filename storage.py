import datetime
from sqlalchemy import (create_engine, Column, Integer, String, Float, DateTime, JSON, Index, Text)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class PricePoint(Base):
    __tablename__ = "price_points"
    id = Column(Integer, primary_key=True)
    card_id = Column(String, index=True)
    platform = Column(String, index=True)
    price = Column(Float)
    extra = Column(JSON, nullable=True)
    ts = Column(DateTime, default=datetime.datetime.utcnow, index=True)

Index('ix_card_ts', PricePoint.card_id, PricePoint.ts.desc())

class TrackedCard(Base):
    __tablename__ = "tracked_cards"
    id = Column(Integer, primary_key=True)
    card_id = Column(String, unique=True, index=True)
    name = Column(String)
    futbin_url = Column(String)
    platform = Column(String)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    meta = Column(JSON, nullable=True)

class HypeEvent(Base):
    __tablename__ = "hype_events"
    id = Column(Integer, primary_key=True)
    card_id = Column(String, index=True)
    source = Column(String)
    score = Column(Float)
    text = Column(Text)
    ts = Column(DateTime, default=datetime.datetime.utcnow, index=True)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    card_id = Column(String, index=True)
    message = Column(Text)
    sent_to = Column(String)
    ts = Column(DateTime, default=datetime.datetime.utcnow, index=True)


def init_db(db_url):
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(db_url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
