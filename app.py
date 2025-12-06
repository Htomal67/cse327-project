import sqlite3
import feedparser
from flask import Flask, render_template, request, jsonify, g, session
from functools import wraps
import hashlib
import os

app = Flask(__name__)
app.secret_key = 'super_secret_dailydash_key'
DATABASE = 'dailydash.db'


# PATTERN 1: SINGLETON PATTERN
# Purpose: Ensure only one Database connection helper exists

class DBConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBConnection, cls).__new__(cls)
        return cls._instance

    def get_db(self):
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row
        return db

db_instance = DBConnection()

def init_db():
    with app.app_context():
        db = db_instance.get_db()
        cursor = db.cursor()
        # Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT,
                role TEXT NOT NULL,
                preferences TEXT
            )
        ''')
        # Sources Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                category TEXT NOT NULL
            )
        ''')
        
        # Seed Admin
        cursor.execute("SELECT * FROM users WHERE email = 'admin@dailydash.com'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)",
                           ('admin@dailydash.com', 'admin123', 'System Admin', 'admin'))
        
        # Seed Sources
        cursor.execute("SELECT * FROM sources")
        if not cursor.fetchall():
            default_sources = [
                ('NYT World', 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'Politics'),
                ('BBC Tech', 'http://feeds.bbci.co.uk/news/technology/rss.xml', 'Technology'),
                ('ESPN Top', 'https://www.espn.com/espn/rss/news', 'Sports')
            ]
            cursor.executemany("INSERT INTO sources (name, url, category) VALUES (?, ?, ?)", default_sources)
        
        db.commit()


# PATTERN 2: DECORATOR PATTERN
# Purpose: Protect routes that require specific roles (Admin/User)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({'error': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated_function


# PATTERN 3: ADAPTER PATTERN
# Purpose: Convert raw RSS feed items into our standard JSON structure

class RSSAdapter:
    @staticmethod
    def adapt(entry, source_name, source_category):
        # Extract image if available (Media RSS or Enclosure)
        image = 'https://via.placeholder.com/150'
        if 'media_content' in entry:
            image = entry.media_content[0]['url']
        elif 'media_thumbnail' in entry:
            image = entry.media_thumbnail[0]['url']
        
        return {
            'title': entry.get('title', 'No Title'),
            'summary': entry.get('summary', 'No summary available.')[:200] + '...',
            'link': entry.get('link', '#'),
            'date': entry.get('published', ''),
            'source': source_name,
            'category': source_category,
            'image': image
        }


# PATTERN 4: STRATEGY PATTERN
# Purpose: Encapsulate filtering logic

class NewsFilterStrategy:
    def filter(self, articles, criteria):
        pass

class CategoryStrategy(NewsFilterStrategy):
    def filter(self, articles, category):
        if category == 'All':
            return articles
        return [a for a in articles if a['category'].lower() == category.lower()]

class PreferenceStrategy(NewsFilterStrategy):
    def filter(self, articles, user_prefs):
        if not user_prefs:
            return articles
        prefs_list = user_prefs.split(',')
        return [a for a in articles if a['category'] in prefs_list]

# --- ROUTES ---

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    db = db_instance.get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? AND password = ?", (data['email'], data['password']))
    user = cursor.fetchone()
    
    if user:
        session['user_id'] = user['id']
        session['role'] = user['role']
        return jsonify({
            'success': True,
            'user': {'id': user['id'], 'name': user['name'], 'role': user['role'], 'preferences': user['preferences']}
        })
    return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    db = db_instance.get_db()
    cursor = db.cursor()
    try:
        # Simple Logic: First user created is admin, else reader
        role = 'reader' 
        cursor.execute("INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)",
                       (data['email'], data['password'], data['name'], role))
        db.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already exists'})

@app.route('/api/preferences', methods=['POST'])
@login_required
def save_preferences():
    data = request.json
    prefs_string = ",".join(data['preferences'])
    db = db_instance.get_db()
    db.execute("UPDATE users SET preferences = ? WHERE id = ?", (prefs_string, session['user_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/sources', methods=['GET', 'POST', 'DELETE'])
def manage_sources():
    db = db_instance.get_db()
    
    if request.method == 'GET':
        cur = db.execute("SELECT * FROM sources")
        return jsonify([dict(row) for row in cur.fetchall()])
    
    if request.method == 'POST':
        # @admin_required check manually applied here for brevity in demo
        if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
        data = request.json
        db.execute("INSERT INTO sources (name, url, category) VALUES (?, ?, ?)", 
                   (data['name'], data['url'], data['category']))
        db.commit()
        return jsonify({'success': True})

    if request.method == 'DELETE':
        if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
        source_id = request.args.get('id')
        db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/news', methods=['GET'])
def get_news():
    db = db_instance.get_db()
    sources = db.execute("SELECT * FROM sources").fetchall()
    
    all_articles = []
    
    # RSS Fetching
    for source in sources:
        feed = feedparser.parse(source['url'])
        for entry in feed.entries:
            all_articles.append(RSSAdapter.adapt(entry, source['name'], source['category']))
    
    # Filtering Strategy Execution
    filter_type = request.args.get('filter_type', 'All')
    filter_value = request.args.get('filter_value', '')
    
    filtered = all_articles
    if filter_type == 'Category':
        strategy = CategoryStrategy()
        filtered = strategy.filter(all_articles, filter_value)
    elif filter_type == 'Preferences':
        # Fetch current user prefs
        if 'user_id' in session:
            user = db.execute("SELECT preferences FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            if user and user['preferences']:
                strategy = PreferenceStrategy()
                filtered = strategy.filter(all_articles, user['preferences'])

    return jsonify(filtered)

if __name__ == '__main__':
    init_db()

    app.run(debug=True)
