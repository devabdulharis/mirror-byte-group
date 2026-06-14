from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import Config

Base = declarative_base()
engine = create_engine(Config.DATABASE_URL)
Session = sessionmaker(bind=engine)

class DownloadTask(Base):
    __tablename__ = "download_tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    chat_id = Column(BigInteger)
    url = Column(Text)
    platform = Column(String(50))
    status = Column(String(20), default="pending")  # pending, downloading, completed, failed
    file_path = Column(Text, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    mirrors = Column(Text, nullable=True)  # JSON string of mirror links
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_msg = Column(Text, nullable=True)

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True)
    username = Column(String(100), nullable=True)
    total_downloads = Column(Integer, default=0)
    total_size = Column(BigInteger, default=0)
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

class MirrorTask(Base):
    __tablename__ = "mirror_tasks"

    id = Column(Integer, primary_key=True)
    download_id = Column(Integer)
    platform = Column(String(50))
    link = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(engine)

def get_session():
    return Session()
