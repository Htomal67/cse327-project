from flask import Flask, render_template, url_for, redirect, request, flash
from flask_login import login_user, LoginManager, login_required, logout_user, current_user
from tables import db, User, Article, NewsCategory, Bookmark
from form import FormFactory, bcrypt
import requests
import xml.etree.ElementTree as ET 
from datetime import datetime, timedelta
import urllib3
import re 

# Suppress InsecureRequestWarning from verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///dailydash.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'habijabi' 

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)

# Login Manager Configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

# --- API CONFIGURATION ---
NEWS_API_KEY = 'eeb2ea5807824ff3b5e877fb1767466c'

# --- CATEGORY CONFIGURATION ---
INTERNATIONAL_CATEGORIES = [
    NewsCategory.GENERAL.value,
    NewsCategory.TECHNOLOGY.value,
    NewsCategory.BUSINESS.value,
    NewsCategory.SCIENCE.value,
    NewsCategory.HEALTH.value,
    NewsCategory.SPORTS.value,
    NewsCategory.ENTERTAINMENT.value
]

LOCAL_CATEGORIES = INTERNATIONAL_CATEGORIES

# Define Sources for the toggle filter
LOCAL_SOURCES = [
    {'id': 'all', 'name': 'All Sources'},
    {'id': NewsCategory.PROTHOM_ALO.value, 'name': 'Prothom Alo'},
    {'id': NewsCategory.DAILY_STAR.value, 'name': 'The Daily Star'},
    {'id': NewsCategory.BBC_BENGALI.value, 'name': 'BBC Bengali'}
]

@login_manager.user_loader
def load_user(user_id): 
    return User.query.get(int(user_id)) 

# --- Helper Function ---
def get_news_headlines(category, region='international', source='all', search_date=None):
    local_source_names = ['Prothom Alo', 'The Daily Star', 'BBC Bengali']
    
    # RSS URL Mappings
    PA_URLS = {
        'general': "https://www.prothomalo.com/feed",
        'technology': "https://www.prothomalo.com/feed/technology",
        'business': "https://www.prothomalo.com/feed/business",
        'sports': "https://www.prothomalo.com/feed/sports",
        'entertainment': "https://www.prothomalo.com/feed/entertainment",
        'science': "https://www.prothomalo.com/feed/technology", 
        'health': "https://www.prothomalo.com/feed/lifestyle"
    }

    DS_URLS = {
        'general': "https://www.thedailystar.net/frontpage/rss.xml",
        'business': "https://www.thedailystar.net/business/rss.xml",
        'sports': "https://www.thedailystar.net/sports/rss.xml",
        'entertainment': "https://www.thedailystar.net/entertainment/rss.xml",
        'technology': "https://www.thedailystar.net/tech-startup/rss.xml", 
        'science': "https://www.thedailystar.net/tech-startup/rss.xml",
        'health': "https://www.thedailystar.net/health/rss.xml"
    }

    BBC_URLS = {
        'general': "https://feeds.bbci.co.uk/bengali/rss.xml",
        'technology': None, 
        'business': None,
        'sports': None,
        'entertainment': None,
        'science': None,
        'health': None
    }

    # 1. Build Query for Cache/Retrieval
    query = Article.query
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    is_today_search = (not search_date) or (search_date == today_str)

    # Apply Date Filter
    if search_date:
        try:
            start_of_day = datetime.strptime(search_date, "%Y-%m-%d")
            end_of_day = start_of_day + timedelta(days=1)
            query = query.filter(Article.fetched_at >= start_of_day, Article.fetched_at < end_of_day)
        except ValueError:
            pass 

    if region == 'local':
        if source == NewsCategory.PROTHOM_ALO.value:
            query = query.filter(Article.source_name == 'Prothom Alo')
        elif source == NewsCategory.DAILY_STAR.value:
            query = query.filter(Article.source_name == 'The Daily Star')
        elif source == NewsCategory.BBC_BENGALI.value:
            query = query.filter(Article.source_name == 'BBC Bengali')
        else:
            query = query.filter(Article.source_name.in_(local_source_names))
        
        query = query.filter_by(category=category)

    else:
        query = query.filter_by(category=category).filter(Article.source_name.notin_(local_source_names))

    # 2. Check Validity
    should_fetch = False
    
    if is_today_search:
        last_article = query.order_by(Article.fetched_at.desc()).first()
        if not last_article or (datetime.now() - last_article.fetched_at) > timedelta(hours=6):
            should_fetch = True

    # 3. Fetch Fresh News
    if should_fetch:
        print(f"Fetching fresh {category} ({region}, Source: {source})...")
        fresh_articles = []
        
        # --- FETCH LOGIC ---
        def fetch_rss(url, source_name, static_image, save_as_category):
            if not url: return
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Referer': 'https://www.google.com/'
                }
                response = requests.get(url, headers=headers, timeout=15, verify=False)
                
                if response.status_code == 200:
                    try:
                        root = ET.fromstring(response.content)
                    except ET.ParseError:
                        root = ET.fromstring(response.content.decode('utf-8', errors='ignore'))

                    items = []
                    for child in root.iter():
                        if child.tag.endswith('item') or child.tag.endswith('entry'):
                            items.append(child)

                    for item in items:
                        def get_text_safe(elem, tag_ends_with):
                            for child in elem:
                                if child.tag.endswith(tag_ends_with) and child.text:
                                    return child.text.strip()
                            return None

                        title = get_text_safe(item, 'title') or 'No Title'
                        link = get_text_safe(item, 'link') or '#'
                        
                        if link == '#':
                            for child in item:
                                if child.tag.endswith('link') and child.get('href'):
                                    link = child.get('href')
                                    break

                        description = get_text_safe(item, 'description') or get_text_safe(item, 'summary') or ''
                        
                        image_url = None
                        if description:
                            img_match = re.search(r'src=["\']([^"\']+)["\']', description)
                            if img_match: image_url = img_match.group(1)
                        if not image_url:
                            for child in item.iter():
                                if ('content' in child.tag or 'enclosure' in child.tag or 'thumbnail' in child.tag) and child.get('url'):
                                    image_url = child.get('url'); break
                        
                        if not image_url: image_url = url_for('static', filename=static_image)
                        if description: description = re.sub('<[^<]+?>', '', description)
                        
                        if title != 'No Title':
                            fresh_articles.append({
                                'title': title,
                                'url': link,
                                'urlToImage': image_url,
                                'description': description,
                                'source': {'name': source_name},
                                'publishedAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                                '_internal_category': save_as_category 
                            })
            except Exception as e:
                print(f"Error fetching {source_name}: {e}")

        # --- EXECUTE FETCH ---
        if region == 'local':
            pa_link = PA_URLS.get(category, PA_URLS['general'])
            ds_link = DS_URLS.get(category, DS_URLS['general'])
            bbc_link = BBC_URLS.get(category)

            if source == 'all':
                fetch_rss(pa_link, 'Prothom Alo', 'prothom_alo.png', category)
                fetch_rss(ds_link, 'The Daily Star', 'daily_star.png', category)
                if bbc_link: fetch_rss(bbc_link, 'BBC Bengali', 'bbc_bengali.png', category)

            elif source == NewsCategory.PROTHOM_ALO.value:
                fetch_rss(pa_link, 'Prothom Alo', 'prothom_alo.png', category)
            elif source == NewsCategory.DAILY_STAR.value:
                fetch_rss(ds_link, 'The Daily Star', 'daily_star.png', category)
            elif source == NewsCategory.BBC_BENGALI.value:
                if bbc_link: fetch_rss(bbc_link, 'BBC Bengali', 'bbc_bengali.png', category)

        else:
            # International (NewsAPI)
            url = f"https://newsapi.org/v2/top-headlines?country=us&category={category}&apiKey={NEWS_API_KEY}"
            try:
                response = requests.get(url)
                data = response.json()
                if data.get('status') == 'ok':
                    fresh_articles = data.get('articles', [])
                    for art in fresh_articles: art['_internal_category'] = category
            except Exception as e:
                print("Request failed:", e)

        # 4. Save to Database
        if fresh_articles:
            try:
                new_count = 0
                updated_count = 0
                
                for art in fresh_articles:
                    if art.get('title') and art.get('url'): 
                        exists = Article.query.filter_by(url=art.get('url')).first()
                        
                        if exists:
                            exists.fetched_at = datetime.now()
                            exists.title = art.get('title')
                            exists.urlToImage = art.get('urlToImage')
                            updated_count += 1
                        else:
                            save_category = art.get('_internal_category', category)
                            new_article = Article(
                                title=art.get('title'),
                                url=art.get('url'),
                                urlToImage=art.get('urlToImage'),
                                source_name=art.get('source', {}).get('name', 'Unknown'),
                                description=art.get('description'),
                                published_at=art.get('publishedAt'),
                                category=save_category,
                                fetched_at=datetime.now()
                            )
                            db.session.add(new_article)
                            new_count += 1
                            
                db.session.commit()
                print(f"Fetch complete. Added {new_count} new, Updated {updated_count} existing.")
            except Exception as e:
                db.session.rollback()
                print("Error saving news:", e)

    # 5. Return All Articles from DB
    db_articles = query.order_by(Article.fetched_at.desc()).limit(150).all() 
    
    articles_formatted = []
    
    # Pre-fetch bookmarked IDs for the current user
    bookmarked_ids = [b.article_id for b in current_user.bookmarks]

    for a in db_articles:
        fetched_date_obj = a.fetched_at
        display_date = fetched_date_obj.strftime("%d %B, %Y")
        
        if fetched_date_obj.date() == datetime.now().date():
            display_date = "Today"
        elif fetched_date_obj.date() == (datetime.now() - timedelta(days=1)).date():
            display_date = "Yesterday"

        articles_formatted.append({
            'id': a.id, # Need ID for bookmarking
            'title': a.title,
            'url': a.url,
            'urlToImage': a.urlToImage,
            'description': a.description,
            'source': {'name': a.source_name}, 
            'publishedAt': a.published_at,
            'display_date': display_date,
            'is_bookmarked': a.id in bookmarked_ids
        })
        
    return articles_formatted

# --- Routes ---
@app.route("/", methods=['GET','POST'])
def hello_world():
    return render_template('index.html')

@app.route("/dashboard", methods=['GET', 'POST'])
@login_required
def dashboard():
    selected_region = request.args.get('region', 'local')
    selected_category = request.args.get('category')
    selected_source = request.args.get('source', 'all')
    selected_date = request.args.get('date') 
    
    display_categories = []
    
    if selected_region == 'local':
        if not selected_category:
            selected_category = NewsCategory.GENERAL.value
        display_categories = LOCAL_CATEGORIES
    else: 
        if not selected_category or selected_category not in INTERNATIONAL_CATEGORIES:
            selected_category = INTERNATIONAL_CATEGORIES[0]
        display_categories = INTERNATIONAL_CATEGORIES

    articles = get_news_headlines(selected_category, region=selected_region, source=selected_source, search_date=selected_date)
    
    return render_template('dashboard.html', 
                           articles=articles, 
                           current_region=selected_region,
                           current_category=selected_category, 
                           current_source=selected_source,
                           current_date=selected_date,
                           categories=display_categories,
                           local_sources=LOCAL_SOURCES)

@app.route('/bookmark/<int:article_id>', methods=['POST'])
@login_required
def toggle_bookmark(article_id):
    bookmark = Bookmark.query.filter_by(user_id=current_user.id, article_id=article_id).first()
    
    if bookmark:
        db.session.delete(bookmark)
        db.session.commit()
    else:
        new_bookmark = Bookmark(user_id=current_user.id, article_id=article_id)
        db.session.add(new_bookmark)
        db.session.commit()
        
    # Redirect back to the referring page (dashboard or bookmarks page)
    return redirect(request.referrer)

@app.route('/bookmarks')
@login_required
def bookmarks():
    # Fetch user's bookmarks
    user_bookmarks = Bookmark.query.filter_by(user_id=current_user.id).order_by(Bookmark.saved_at.desc()).all()
    
    articles = []
    for b in user_bookmarks:
        a = b.article
        articles.append({
            'id': a.id,
            'title': a.title,
            'url': a.url,
            'urlToImage': a.urlToImage,
            'description': a.description,
            'source': {'name': a.source_name}, 
            'publishedAt': a.published_at,
            'is_bookmarked': True
        })
        
    return render_template('bookmarks.html', articles=articles)

@app.route("/signup", methods=['GET', 'POST'])
def signup():
    form_factory = FormFactory()
    form = form_factory.create_form('signup')

    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        new_user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('signup.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form_factory = FormFactory()
    form = form_factory.create_form('login')
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        login_user(user)
        return redirect(url_for('dashboard'))
        
    return render_template('login.html', form=form)

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)