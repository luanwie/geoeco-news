from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import os

DATABASE_URL = "sqlite:///./news_alerts.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    hashed_password = Column(String(128), nullable=False)
    plan = Column(String(20), default="free")  # free, pro, pro_annual
    created_at = Column(DateTime, default=datetime.utcnow)
    trial_expires = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=2))
    stripe_customer_id = Column(String(100), nullable=True)
    
    # Relationships
    alerts = relationship("Alert", back_populates="user")
    categories = relationship("UserCategory", back_populates="user", uselist=False)

class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # economy, geopolitics, markets
    news_url = Column(String(500), nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="alerts")

class UserCategory(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    economy = Column(Boolean, default=True)
    geopolitics = Column(Boolean, default=True)
    markets = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="categories")

class NewsItem(Base):
    __tablename__ = "news_items"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    category = Column(String(50), nullable=False)
    source = Column(String(100), nullable=False)
    published_at = Column(DateTime, nullable=False)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    impact_score = Column(Integer, default=1)  # 1-5, based on source count
    processed = Column(Boolean, default=False)

# Create all tables
def create_tables():
    Base.metadata.create_all(bind=engine)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()