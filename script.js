// State Management
const state = {
    user: null,
    view: 'login',
    sources: [],
    articles: [],
    bookmarks: [], // NEW: Store bookmark links for easy checking
    activeFilter: 'My Feed',
    searchQuery: '',
    categories: ['Politics', 'Sports', 'Technology', 'Business', 'Entertainment', 'Health', 'General'],
    theme: localStorage.getItem('theme') || 'light'
};

function initTheme() {
    if (state.theme === 'dark') {
        document.body.classList.add('dark-mode');
    }
}

window.toggleTheme = () => {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    if (state.theme === 'dark') {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    localStorage.setItem('theme', state.theme);
};

// --- UI HELPERS ---

// Debounce
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Toast Notification
window.showToast = (message, showUndo = false) => {
    // Remove existing toast
    const existing = document.querySelector('.toast-container');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.className = 'toast-container animate-fade-in';
    
    let html = `<span>${message}</span>`;
    if (showUndo) {
        html += `<button onclick="window.undoLastAction()" class="undo-btn">UNDO</button>`;
    }
    
    container.innerHTML = html;
    document.body.appendChild(container);

    // Auto hide after 4 seconds
    setTimeout(() => {
        if (container) {
            container.style.opacity = '0';
            setTimeout(() => container.remove(), 300);
        }
    }, 4000);
};

window.togglePassword = (inputId, iconElement) => {
    const input = document.getElementById(inputId);
    if (input.type === "password") {
        input.type = "text";
        iconElement.classList.replace("ph-eye", "ph-eye-slash");
    } else {
        input.type = "password";
        iconElement.classList.replace("ph-eye-slash", "ph-eye");
    }
};

window.toggleSidebar = () => {
    const sidebar = document.querySelector('.sidebar');
    const content = document.querySelector('.content');
    const overlay = document.getElementById('overlay');

    if (window.innerWidth < 768) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('active');
    } else {
        sidebar.classList.toggle('collapsed');
        content.classList.toggle('expanded');
    }
};

class UIFactory {
    static createNewsCard(article) {
        // Check if bookmarked
        const isBookmarked = state.bookmarks.includes(article.link);
        const heartIcon = isBookmarked ? 'ph-fill' : 'ph';
        const heartColor = isBookmarked ? 'color: #e11d48;' : '';

        const div = document.createElement('div');
        div.className = 'card';
        // Encode article data to pass to function
        const articleJson = encodeURIComponent(JSON.stringify(article));
        
        div.innerHTML = `
            <div class="card-img-wrapper">
                <i class="ph ph-newspaper"></i>
                <img src="${article.image}" 
                     onerror="this.style.display='none'; this.parentElement.classList.add('error');"
                     alt="News Image">
                <!-- Bookmark Button -->
                <button class="bookmark-btn" onclick="window.toggleBookmark(this, '${articleJson}')">
                    <i class="ph-heart ${heartIcon}" style="${heartColor}"></i>
                </button>
            </div>
            <div class="card-body">
                <div class="tag">${article.category} • ${article.source}</div>
                <h3 style="margin: 8px 0; font-size: 1.1rem; line-height: 1.4;">${article.title}</h3>
                <p style="font-size: 0.9rem; color: var(--text-light); flex: 1; line-height: 1.5;">${article.summary}</p>
                <a href="${article.link}" target="_blank" style="margin-top: 15px; color: var(--primary); text-decoration: none; font-weight: bold; display: flex; align-items: center; gap: 5px;">
                    Read Full Story <i class="ph ph-arrow-right"></i>
                </a>
            </div>
        `;
        return div;
    }
}

async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(`/api/${endpoint}`, options);
    return res.json();
}

// --- LOGIC ---

async function checkSession() {
    initTheme(); 
    try {
        const res = await apiCall('check_auth');
        if (res.authenticated) {
            state.user = res.user;
            await loadBookmarks(); // Load bookmarks first
            if (state.user.role === 'admin') {
                loadAdminDashboard();
            } else if (!state.user.preferences) {
                renderPreferences();
            } else {
                loadDashboard();
            }
        } else {
            renderLogin();
        }
    } catch (error) {
        console.error("Session check failed", error);
        renderLogin();
    }
}

async function loadBookmarks() {
    const bks = await apiCall('bookmarks');
    state.bookmarks = bks.map(b => b.link);
}

// NEW: Toggle Bookmark
window.toggleBookmark = async (btn, articleJson) => {
    // Prevent bubbling if clicking button
    if(event) event.stopPropagation();
    
    const article = JSON.parse(decodeURIComponent(articleJson));
    const icon = btn.querySelector('i');
    
    // Optimistic UI update
    const isAdding = !icon.classList.contains('ph-fill');
    
    if (isAdding) {
        icon.classList.add('ph-fill');
        icon.style.color = '#e11d48';
        state.bookmarks.push(article.link);
        await apiCall('bookmarks', 'POST', { article });
        showToast('Added to Read Later', true);
    } else {
        icon.classList.remove('ph-fill');
        icon.style.color = '';
        state.bookmarks = state.bookmarks.filter(l => l !== article.link);
        await apiCall('bookmarks', 'DELETE', { article });
        showToast('Removed from Read Later', true);
        
        // If we are currently viewing Read Later, remove card immediately
        if (state.activeFilter === 'Read Later') {
            loadDashboard(false);
        }
    }
};

// NEW: Undo Action
window.undoLastAction = async () => {
    const res = await apiCall('undo', 'POST');
    if (res.success) {
        showToast('Action undone');
        await loadBookmarks(); // Refresh list
        loadDashboard(false); // Refresh UI
    } else {
        showToast('Nothing to undo');
    }
};

// ... Render Login/Preferences logic remains same ...
function renderLogin() {
    const app = document.getElementById('app');
    app.innerHTML = `
        <div class="auth-wrapper animate-fade-in">
            <div class="auth-container">
                <div style="margin-bottom: 2rem;">
                    <i class="ph ph-newspaper" style="font-size: 3rem; color: var(--primary);"></i>
                    <h1 style="color: var(--primary); margin: 0.5rem 0;">DailyDash</h1>
                    <p style="color: var(--text-light);">Your personalized news aggregator</p>
                </div>
                <div class="auth-tabs">
                    <button class="auth-tab active" onclick="switchAuthMode('login')">Login</button>
                    <button class="auth-tab" onclick="switchAuthMode('signup')">Sign Up</button>
                </div>
                <form id="authForm" onsubmit="handleAuth(event)">
                    <div id="signupFields" style="display: none;">
                        <div class="input-group">
                            <input type="text" name="name" placeholder="Full Name">
                        </div>
                        <div class="input-group">
                            <select name="role">
                                <option value="reader">Reader Account</option>
                                <option value="admin">Admin Account</option>
                            </select>
                        </div>
                    </div>
                    <div class="input-group">
                        <input type="email" name="email" placeholder="Email Address" required>
                    </div>
                    <div class="input-group">
                        <input type="password" name="password" id="authPassword" placeholder="Password" required>
                        <i class="ph ph-eye password-toggle" onclick="togglePassword('authPassword', this)"></i>
                    </div>
                    <button type="submit" class="primary">Continue</button>
                </form>
            </div>
        </div>
    `;
}

function switchAuthMode(mode) {
    const signupFields = document.getElementById('signupFields');
    const tabs = document.querySelectorAll('.auth-tab');
    if (mode === 'signup') {
        signupFields.style.display = 'block';
        signupFields.classList.add('animate-fade-in'); 
        tabs[0].classList.remove('active');
        tabs[1].classList.add('active');
        document.getElementById('authForm').dataset.mode = 'signup';
    } else {
        signupFields.style.display = 'none';
        tabs[1].classList.remove('active');
        tabs[0].classList.add('active');
        document.getElementById('authForm').dataset.mode = 'login';
    }
}

async function handleAuth(e) {
    e.preventDefault();
    const mode = e.target.dataset.mode || 'login';
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData.entries());
    const res = await apiCall(mode, 'POST', data);
    
    if (res.success) {
        if (mode === 'login') {
            state.user = res.user;
            await loadBookmarks();
            if (state.user.role === 'admin') {
                loadAdminDashboard();
            } else if (!state.user.preferences) {
                renderPreferences();
            } else {
                loadDashboard();
            }
        } else {
            alert('Account created! Please login.');
            switchAuthMode('login');
        }
    } else {
        alert(res.message || 'Error occurred');
    }
}

function renderPreferences() {
    let selected = [];
    const app = document.getElementById('app');
    const toggle = (cat) => {
        if (selected.includes(cat)) selected = selected.filter(c => c !== cat);
        else if (selected.length < 5) selected.push(cat);
        render();
    };
    const render = () => {
        app.innerHTML = `
            <div class="auth-wrapper animate-fade-in">
                <div class="auth-container" style="max-width: 600px;">
                    <h2 style="color: var(--primary);">Welcome, ${state.user.name}!</h2>
                    <p style="color: var(--text-light); margin-bottom: 2rem;">Select up to 5 topics to personalize your feed.</p>
                    <div class="pref-grid">
                        ${state.categories.map(cat => `
                            <div class="pref-item ${selected.includes(cat) ? 'selected' : ''}" 
                                 onclick="window.togglePref('${cat}')">
                                ${cat}
                            </div>
                        `).join('')}
                    </div>
                    <button class="primary" onclick="window.savePrefs()" ${selected.length === 0 ? 'disabled style="opacity: 0.5;"' : ''}>
                        Get Started
                    </button>
                </div>
            </div>
        `;
    };
    window.togglePref = toggle;
    window.savePrefs = async () => {
        await apiCall('preferences', 'POST', { preferences: selected });
        state.user.preferences = selected.join(',');
        loadDashboard();
    };
    render();
}

// Search
const performSearch = debounce(() => {
    loadDashboard(false); 
}, 300);

window.handleSearch = (e) => {
    state.searchQuery = e.target.value;
    performSearch();
};

async function loadDashboard(renderShell = true) {
    state.view = 'dashboard';
    
    // Logic for deciding what to fetch
    if (state.activeFilter === 'Read Later') {
        state.articles = await apiCall('bookmarks');
    } else {
        let query = '';
        if (state.activeFilter === 'My Feed') {
            query = '?filter_type=Preferences';
        } else if (state.activeFilter !== 'All') {
            query = `?filter_type=Category&filter_value=${state.activeFilter}`;
        } else {
            query = '?filter_type=All';
        }

        if (state.searchQuery) {
            query += `&search=${encodeURIComponent(state.searchQuery)}`;
        }
        state.articles = await apiCall(`news${query}`);
    }
    
    const app = document.getElementById('app');
    const dashboardExists = app.querySelector('.dashboard') && !app.querySelector('.settings-container');

    if (renderShell && !dashboardExists) {
        renderDashboardStructure();
    }
    updateDashboardContent();
}

function renderDashboardStructure() {
    const app = document.getElementById('app');
    
    app.innerHTML = `
        <div class="dashboard">
            <div class="sidebar">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
                    <h2 style="color: var(--primary); margin:0; display: flex; align-items: center; gap: 10px;">
                        <i class="ph ph-newspaper-clipping"></i> DailyDash
                    </h2>
                    <button class="menu-btn" onclick="toggleSidebar()" style="font-size: 1.2rem; display: none;">
                        <i class="ph ph-x"></i>
                    </button>
                </div>

                <div id="sidebar-cats" style="display: flex; flex-direction: column; gap: 5px; flex: 1;">
                    <button class="cat-btn" data-cat="My Feed" onclick="setFilter('My Feed')">
                        <i class="ph ph-star" style="color: gold;"></i> For You
                    </button>
                    <button class="cat-btn" data-cat="All" onclick="setFilter('All')">
                        <i class="ph ph-squares-four"></i> All News
                    </button>
                    <!-- NEW: Read Later Button -->
                    <button class="cat-btn" data-cat="Read Later" onclick="setFilter('Read Later')">
                        <i class="ph ph-bookmark-simple"></i> Read Later
                    </button>

                    <div style="margin: 1rem 0; font-size: 0.75rem; color: var(--text-light); font-weight: bold; text-transform: uppercase; padding-left: 12px;">Categories</div>
                    ${state.categories.map(cat => `
                        <button class="cat-btn" data-cat="${cat}" onclick="setFilter('${cat}')">
                            ${cat}
                        </button>
                    `).join('')}
                </div>

                <div style="border-top: 1px solid var(--border); padding-top: 1rem; margin-top: auto;">
                    <button class="cat-btn" onclick="loadSettings()">
                        <i class="ph ph-gear"></i> Settings
                    </button>
                </div>
            </div>
            
            <div class="content animate-fade-in">
                <div class="header">
                    <div style="display: flex; align-items: center; gap: 1rem; flex: 1;">
                        <button class="menu-btn" onclick="toggleSidebar()">
                            <i class="ph ph-list"></i>
                        </button>
                        <div class="search-bar-container">
                            <i class="ph ph-magnifying-glass search-icon"></i>
                            <input type="text" class="search-input" 
                                   placeholder="Search news..." 
                                   value="${state.searchQuery}"
                                   oninput="window.handleSearch(event)">
                        </div>
                    </div>
                    
                    <div style="display: flex; align-items: center; gap: 1rem; margin-left: 1rem;">
                        <span style="font-weight: 600; display: none; margin-right: 10px; @media(min-width: 768px){display:inline;}">
                            ${state.user.name}
                        </span>
                        <button onclick="logout()" style="width: auto; padding: 8px 16px; border: 1px solid var(--border); color: var(--text-light);">
                            <i class="ph ph-sign-out"></i> Logout
                        </button>
                    </div>
                </div>
                
                <div class="dashboard-title-area" style="margin-bottom: 2rem;">
                    <h2 id="page-title" style="margin: 0;">Your Personal Feed</h2>
                    <span id="page-date" style="font-size: 0.85rem; color: var(--text-light);"></span>
                </div>

                <div class="news-grid" id="newsGrid"></div>
            </div>
        </div>
    `;
}

function updateDashboardContent() {
    const titleEl = document.getElementById('page-title');
    const dateEl = document.getElementById('page-date');
    
    if (titleEl) {
        if(state.activeFilter === 'Read Later') titleEl.textContent = 'Saved Articles';
        else titleEl.textContent = state.activeFilter === 'My Feed' ? 'Your Personal Feed' : state.activeFilter;
        
        if (state.searchQuery) titleEl.textContent = `Results for "${state.searchQuery}"`;
    }
    if (dateEl) {
        dateEl.textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    }

    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.cat === state.activeFilter) btn.classList.add('active');
    });

    const grid = document.getElementById('newsGrid');
    if (!grid) return;
    
    grid.innerHTML = '';
    if (state.articles.length === 0) {
        grid.innerHTML = `
            <div style="text-align: center; grid-column: 1/-1; padding: 4rem; color: var(--text-light);">
                <i class="ph ph-magnifying-glass" style="font-size: 3rem; margin-bottom: 1rem; display: block; opacity: 0.5;"></i>
                <p>No news found.</p>
            </div>
        `;
    } else {
        state.articles.forEach(article => {
            grid.appendChild(UIFactory.createNewsCard(article));
        });
    }
}

window.setFilter = (filter) => {
    state.activeFilter = filter;
    state.searchQuery = ''; 
    const searchInput = document.querySelector('.search-input');
    if (searchInput) searchInput.value = '';

    if (window.innerWidth < 768) {
        toggleSidebar();
    }
    loadDashboard();
};

function loadSettings() {
    state.view = 'settings';
    renderSettings();
}

function renderSettings() {
    const app = document.getElementById('app');
    let selected = state.user.preferences ? state.user.preferences.split(',') : [];

    window.toggleSettingPref = (cat) => {
        if (selected.includes(cat)) selected = selected.filter(c => c !== cat);
        else if (selected.length < 5) selected.push(cat);
        renderSettingsUI(); 
    };

    window.saveNewSettings = async () => {
        await apiCall('preferences', 'POST', { preferences: selected });
        state.user.preferences = selected.join(',');
        alert('Preferences updated!');
        loadDashboard();
    };

    const renderSettingsUI = () => {
        app.innerHTML = `
            <div class="dashboard">
                <div class="sidebar">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
                        <h2 style="color: var(--primary); margin:0; display: flex; align-items: center; gap: 10px;">
                            <i class="ph ph-newspaper-clipping"></i> DailyDash
                        </h2>
                        <button class="menu-btn" onclick="toggleSidebar()" style="font-size: 1.2rem; display: none;">
                            <i class="ph ph-x"></i>
                        </button>
                    </div>
                    <button class="cat-btn" onclick="loadDashboard()">
                        <i class="ph ph-arrow-left"></i> Back to News
                    </button>
                </div>
                
                <div class="content animate-fade-in">
                    <div class="header">
                        <div style="display: flex; align-items: center;">
                             <button class="menu-btn" onclick="toggleSidebar()"><i class="ph ph-list"></i></button>
                             <h2>Profile Settings</h2>
                        </div>
                    </div>

                    <div class="settings-container">
                        <div class="settings-section">
                            <h3 style="margin-top: 0;">Appearance</h3>
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <div>
                                    <div style="font-weight: 600;">Dark Mode</div>
                                    <div style="font-size: 0.9rem; color: var(--text-light);">Switch between light and dark themes</div>
                                </div>
                                <label class="switch">
                                    <input type="checkbox" ${state.theme === 'dark' ? 'checked' : ''} onchange="toggleTheme()">
                                    <span class="slider"></span>
                                </label>
                            </div>
                        </div>

                        <div class="settings-section">
                             <h3>Account Information</h3>
                             <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                                 <div>
                                     <label style="font-size: 0.8rem; color: var(--text-light); font-weight: bold;">Full Name</label>
                                     <div style="padding: 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px;">${state.user.name}</div>
                                 </div>
                                 <div>
                                     <label style="font-size: 0.8rem; color: var(--text-light); font-weight: bold;">Email</label>
                                     <div style="padding: 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px;">${state.user.email}</div>
                                 </div>
                             </div>
                        </div>

                        <div class="settings-section" style="border-bottom: none;">
                            <h3>News Preferences</h3>
                            <p style="color: var(--text-light);">Update your favorite topics (Select up to 5)</p>
                            <div class="pref-grid">
                                ${state.categories.map(cat => `
                                    <div class="pref-item ${selected.includes(cat) ? 'selected' : ''}" 
                                         onclick="window.toggleSettingPref('${cat}')">
                                        ${cat}
                                    </div>
                                `).join('')}
                            </div>
                            <button class="primary" onclick="window.saveNewSettings()" style="width: auto; padding-left: 2rem; padding-right: 2rem;">
                                Save Changes
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    };
    renderSettingsUI();
}

window.logout = async () => {
    await apiCall('logout', 'POST');
    state.user = null;
    renderLogin();
};

async function loadAdminDashboard() {
    const sources = await apiCall('sources');
    const app = document.getElementById('app');
    
    const renderSources = () => sources.map(s => `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 1rem; background: var(--white); margin-bottom: 10px; border-radius: 8px; border: 1px solid var(--border);">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <div style="background: #e0f2fe; color: var(--primary); padding: 8px; border-radius: 6px;">
                    <i class="ph ph-rss"></i>
                </div>
                <div>
                    <div style="font-weight: 600;">${s.name}</div>
                    <div style="font-size: 0.85rem; color: var(--text-light);">${s.category}</div>
                </div>
            </div>
            <button onclick="window.deleteSource(${s.id})" style="width: auto; background: #fee2e2; color: #dc2626; border: none; padding: 8px; border-radius: 6px; cursor: pointer;">
                <i class="ph ph-trash"></i>
            </button>
        </div>
    `).join('');

    app.innerHTML = `
        <div class="dashboard">
            <div class="content animate-fade-in" style="margin-left: 0; max-width: 800px; margin: 0 auto; width: 100%;">
                <div class="header">
                    <h2>Admin Dashboard</h2>
                    <button onclick="logout()" style="width: auto; padding: 8px 16px;">Logout</button>
                </div>
                
                <div style="background: var(--white); padding: 2rem; border-radius: var(--radius); box-shadow: var(--shadow); margin-bottom: 2rem;">
                    <h3 style="margin-top: 0; color: var(--primary);">Add New Source</h3>
                    <form onsubmit="window.addSource(event)" style="display: grid; gap: 1rem;">
                        <input type="text" name="name" placeholder="Source Name (e.g. Wired)" required>
                        <input type="url" name="url" placeholder="RSS Feed URL" required>
                        <select name="category" style="background: white;">
                            ${state.categories.map(c => `<option>${c}</option>`).join('')}
                        </select>
                        <button type="submit" class="primary" style="margin-top: 0;">
                            <i class="ph ph-plus"></i> Add Source
                        </button>
                    </form>
                </div>

                <h3>Active Sources</h3>
                <div id="sourceList">${renderSources()}</div>
            </div>
        </div>
    `;
    
    window.addSource = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        await apiCall('sources', 'POST', Object.fromEntries(formData.entries()));
        loadAdminDashboard();
    };

    window.deleteSource = async (id) => {
        if(confirm('Delete this source?')) {
            await apiCall(`sources?id=${id}`, 'DELETE');
            loadAdminDashboard();
        }
    };
}

checkSession();