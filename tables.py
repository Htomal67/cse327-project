from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import enum

db = SQLAlchemy()

# 1. Define the categories here as the "Single Source of Truth"
class NewsCategory(enum.Enum):
    # International Categories
    GENERAL = "general"
    TECHNOLOGY = "technology"
    BUSINESS = "business"
    SCIENCE = "science"
    HEALTH = "health"
    SPORTS = "sports"
    ENTERTAINMENT = "entertainment"
    
    # Local Sources (Bangladesh)
    PROTHOM_ALO = "prothom_alo" 
    DAILY_STAR = "daily_star"
    BBC_BENGALI = "bbc_bengali"

    @classmethod
    def list(cls):
        return [c.value for c in cls]

class User(db.Model, UserMixin): 
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True) 
    password = db.Column(db.String(80), nullable=False)
    # Relationship to access bookmarks easily
    bookmarks = db.relationship('Bookmark', backref='user', lazy=True)

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    urlToImage = db.Column(db.String(255))
    source_name = db.Column(db.String(100))
    description = db.Column(db.Text)
    published_at = db.Column(db.String(50))
    
    # Use the Enum value for the default
    category = db.Column(db.String(50), default=NewsCategory.PROTHOM_ALO.value) 
    
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to get article details
    article = db.relationship('Article')