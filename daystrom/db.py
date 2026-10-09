"""Daystrom database connection and session helpers."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


def get_engine():
    url = os.getenv('DAYSTROM_DATABASE_URL')
    if not url:
        raise RuntimeError('DAYSTROM_DATABASE_URL is not configured')
    return create_engine(url, pool_pre_ping=True)


def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
