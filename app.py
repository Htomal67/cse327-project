import sqlite3
import feedparser
from flask import Flask, render_template, request, jsonify, g, session
from functools import wraps
import time
from datetime import datetime
import threading
import copy

app = Flask(__name__)
app.secret_key = 'super_secret_dailydash_key'
DATABASE = 'dailydash.db'

# ==========================================
# PATTERN 1: SINGLETON PATTERN
# ==========================================
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                category TEXT NOT NULL
            )
        ''')
        
        cursor.execute("SELECT * FROM users WHERE email = 'admin@dailydash.com'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (email, password, name, role) VALUES (?, ?, ?, ?)",
                           ('admin@dailydash.com', 'admin123', 'System Admin', 'admin'))
        
        cursor.execute("SELECT * FROM sources")
        if not cursor.fetchall():
            default_sources = [
                ('NYT World', 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml', 'Politics'),
                ('BBC Tech', 'http://feeds.bbci.co.uk/news/technology/rss.xml', 'Technology'),
                ('ESPN Top', 'https://www.espn.com/espn/rss/news', 'Sports')
            ]
            cursor.executemany("INSERT INTO sources (name, url, category) VALUES (?, ?, ?)", default_sources)
        
        db.commit()

# ==========================================
# PATTERN 2: DECORATOR PATTERN
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# PATTERN 3: ADAPTER PATTERN
# ==========================================
class RSSAdapter:
    @staticmethod
    def adapt(entry, source_name, source_category):
        image = 'https://via.placeholder.com/300?text=News'
        if 'media_content' in entry:
            image = entry.media_content[0]['url']
        elif 'media_thumbnail' in entry:
            image = entry.media_thumbnail[0]['url']
        elif 'links' in entry:
            for link in entry.links:
                if link.type.startswith('image/'):
                    image = link.href
                    break
        
        timestamp = 0
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            timestamp = time.mktime(entry.published_parsed)
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            timestamp = time.mktime(entry.updated_parsed)
            
        return {
            'title': entry.get('title', 'No Title'),
            'summary': entry.get('summary', 'No summary available.')[:200] + '...',
            'link': entry.get('link', '#'),
            'date': entry.get('published', ''),
            'timestamp': timestamp,
            'source': source_name,
            'category': source_category,
            'image': image
        }

# ==========================================
# BACKGROUND NEWS FETCHER (Proxy/Singleton)
# ==========================================
class NewsFetcher:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NewsFetcher, cls).__new__(cls)
            cls._instance.articles = []
            cls._instance.lock = threading.Lock()
            cls._instance.start_background_thread()
        return cls._instance

    def start_background_thread(self):
        thread = threading.Thread(target=self.update_loop, daemon=True)
        thread.start()

    def update_loop(self):
        self.fetch_all_sources()
        while True:
            time.sleep(300)
            self.fetch_all_sources()

    def fetch_all_sources(self):
        print("--- [Background] Fetching News Sources... ---")
        try:
            with sqlite3.connect(DATABASE) as conn:
                conn.row_factory = sqlite3.Row
                sources = conn.execute("SELECT * FROM sources").fetchall()
                
                new_articles = []
                for source in sources:
                    try:
                        feed = feedparser.parse(source['url'])
                        for entry in feed.entries:
                            new_articles.append(RSSAdapter.adapt(entry, source['name'], source['category']))
                    except Exception as e:
                        print(f"Error fetching {source['name']}: {e}")
                
                new_articles.sort(key=lambda x: x['timestamp'], reverse=True)
                
                with self.lock:
                    self.articles = new_articles
                print(f"--- [Background] Updated {len(new_articles)} articles ---")
                
        except Exception as e:
            print(f"Background Fetch Error: {e}")

    def get_cached_articles(self):
        with self.lock:
            return copy.deepcopy(self.articles)

    def refresh_now(self):
        threading.Thread(target=self.fetch_all_sources, daemon=True).start()

news_fetcher = NewsFetcher()

# ==========================================
# PATTERN 4: STRATEGY PATTERN
# ==========================================
class CategoryStrategy:
    def filter(self, articles, category):
        if category == 'All':
            return articles
        return [a for a in articles if a['category'].lower() == category.lower()]

class PreferenceStrategy:
    def filter(self, articles, user_prefs):
        if not user_prefs:
            return articles
        prefs_list = [p.strip().lower() for p in user_prefs.split(',')]
        return [a for a in articles if a['category'].lower() in prefs_list]

# NEW: Search Strategy
class SearchStrategy:
    def filter(self, articles, query):
        if not query:
            return articles
        q = query.lower()
        # Search in Title OR Summary
        return [a for a in articles if q in a['title'].lower() or q in a['summary'].lower()]

# --- ROUTES ---

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        db = db_instance.get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        if user:
            return jsonify({
                'authenticated': True,
                'user': {'id': user['id'], 'name': user['name'], 'role': user['role'], 'preferences': user['preferences']}
            })
    return jsonify({'authenticated': False})

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

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    db = db_instance.get_db()
    cursor = db.cursor()
    try:
        role = data.get('role', 'reader')
        if role not in ['reader', 'admin']: role = 'reader'
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
        if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
        data = request.json
        db.execute("INSERT INTO sources (name, url, category) VALUES (?, ?, ?)", 
                   (data['name'], data['url'], data['category']))
        db.commit()
        news_fetcher.refresh_now()
        return jsonify({'success': True})

    if request.method == 'DELETE':
        if session.get('role') != 'admin': return jsonify({'error': 'Forbidden'}), 403
        source_id = request.args.get('id')
        db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/news', methods=['GET'])
def get_news():
    # 1. Fetch from Memory
    all_articles = news_fetcher.get_cached_articles()
    filtered = all_articles
    
    # 2. Apply Category/Preference Filters (Primary Filter)
    filter_type = request.args.get('filter_type', 'All')
    filter_value = request.args.get('filter_value', '')
    
    if filter_type == 'Category':
        strategy = CategoryStrategy()
        filtered = strategy.filter(filtered, filter_value)
    elif filter_type == 'Preferences':
        if 'user_id' in session:
            db = db_instance.get_db()
            user = db.execute("SELECT preferences FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            if user and user['preferences']:
                strategy = PreferenceStrategy()
                filtered = strategy.filter(filtered, user['preferences'])

    # 3. Apply Search Filter (Secondary Filter)
    search_query = request.args.get('search', '').strip()
    if search_query:
        search_strategy = SearchStrategy()
        filtered = search_strategy.filter(filtered, search_query)

    return jsonify(filtered)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)