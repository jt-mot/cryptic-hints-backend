"""
Cryptic Crossword Hint System - Production Backend
===================================================

Full-featured Flask application with:
- Admin authentication
- Hint review workflow
- Publishing system
- AI hint generation integration
- Database management

Run with: python production_app.py
"""

from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for, Response, make_response
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, date
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Session configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/crosswords_dev')
SITE_URL = os.environ.get('SITE_URL', 'https://www.cryptic-hints.com').rstrip('/')
GA_TRACKING_ID = os.environ.get('GA_TRACKING_ID', 'G-EN3G45Y8DB')
ADMIN_USERNAME = 'admin'  # Change this
ADMIN_PASSWORD_HASH = generate_password_hash('changeme123')  # CHANGE THIS PASSWORD!

# SMTP email settings (GoDaddy)
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtpout.secureserver.net')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USER = os.environ.get('SMTP_USER', '')  # e.g. info@cryptic-hints.com
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', '') or SMTP_USER


def _send_email(to_email, subject, html_body):
    """Send a single email via SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return False

    msg = MIMEMultipart('alternative')
    msg['From'] = EMAIL_FROM
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        app.logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def _build_puzzle_email(puzzle_number, setter):
    """Build the HTML email body for a new puzzle notification."""
    puzzle_url = f"{SITE_URL}/puzzle/{puzzle_number}"
    unsubscribe_url = f"{SITE_URL}"
    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px;">
  <h2 style="color: #1e293b; margin-bottom: 4px;">New Puzzle Available!</h2>
  <p style="color: #475569; font-size: 16px; line-height: 1.6;">
    Guardian Cryptic #{puzzle_number}{f' by {setter}' if setter and setter != 'Unknown' else ''} is now live on Cryptic Hints.
  </p>
  <a href="{puzzle_url}"
     style="display: inline-block; padding: 12px 28px; background: #2563eb; color: #fff;
            text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px; margin: 16px 0;">
    Solve Puzzle #{puzzle_number}
  </a>
  <p style="color: #94a3b8; font-size: 13px; margin-top: 32px;">
    You received this because you subscribed to puzzle notifications at
    <a href="{SITE_URL}" style="color: #94a3b8;">cryptic-hints.com</a>.<br>
    To unsubscribe, visit the site and use the unsubscribe option.
  </p>
</div>"""


def notify_subscribers(puzzle_number, setter):
    """Send new-puzzle emails to all active subscribers. Runs in a background thread."""
    if not SMTP_USER or not SMTP_PASSWORD:
        app.logger.info("SMTP not configured — skipping subscriber notifications")
        return

    def _send_all():
        try:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT email FROM subscribers
                WHERE unsubscribed_at IS NULL
            ''')
            subscribers = cursor.fetchall()
            cursor.close()
            conn.close()

            subject = f"New Puzzle: Guardian Cryptic #{puzzle_number}"
            body = _build_puzzle_email(puzzle_number, setter)

            sent = 0
            for sub in subscribers:
                if _send_email(sub['email'], subject, body):
                    sent += 1

            app.logger.info(f"Notified {sent}/{len(subscribers)} subscribers about puzzle #{puzzle_number}")
        except Exception as e:
            app.logger.error(f"Subscriber notification failed: {e}")

    thread = threading.Thread(target=_send_all, daemon=True)
    thread.start()


def get_db():
    """Get database connection"""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    """Initialize database with schema"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS puzzles (
            id SERIAL PRIMARY KEY,
            publication TEXT NOT NULL,
            puzzle_number TEXT,
            setter TEXT,
            date DATE NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clues (
            id SERIAL PRIMARY KEY,
            puzzle_id INTEGER NOT NULL,
            clue_number TEXT NOT NULL,
            direction TEXT NOT NULL,
            clue_text TEXT NOT NULL,
            enumeration TEXT,
            answer TEXT NOT NULL,
            hint_level_1 TEXT,
            hint_level_2 TEXT,
            hint_level_3 TEXT,
            hint_level_4 TEXT,
            hint_1_approved BOOLEAN DEFAULT FALSE,
            hint_2_approved BOOLEAN DEFAULT FALSE,
            hint_3_approved BOOLEAN DEFAULT FALSE,
            hint_4_approved BOOLEAN DEFAULT FALSE,
            hint_1_flagged BOOLEAN DEFAULT FALSE,
            hint_2_flagged BOOLEAN DEFAULT FALSE,
            hint_3_flagged BOOLEAN DEFAULT FALSE,
            hint_4_flagged BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (puzzle_id) REFERENCES puzzles(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hint_revisions (
            id SERIAL PRIMARY KEY,
            clue_id INTEGER NOT NULL,
            hint_level INTEGER NOT NULL,
            old_text TEXT,
            new_text TEXT,
            edited_by TEXT,
            edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clue_id) REFERENCES clues(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_progress (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            clue_id INTEGER NOT NULL,
            hints_viewed INTEGER DEFAULT 0,
            answered BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clue_id) REFERENCES clues(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id SERIAL PRIMARY KEY,
            puzzle_id INTEGER,
            puzzle_number TEXT,
            api_calls INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost_usd NUMERIC(10, 6) DEFAULT 0,
            model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (puzzle_id) REFERENCES puzzles(id) ON DELETE SET NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirmed BOOLEAN DEFAULT FALSE,
            unsubscribed_at TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_puzzle_date ON puzzles(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_puzzle_status ON puzzles(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_clue_puzzle ON clues(puzzle_id)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriber_email ON subscribers(email)')
    
    # Add grid_data column if it doesn't exist (migration)
    cursor.execute('''
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='puzzles' AND column_name='grid_data'
            ) THEN
                ALTER TABLE puzzles ADD COLUMN grid_data JSONB;
            END IF;
        END $$;
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✓ PostgreSQL database initialized successfully!")


VALID_HINT_LEVELS = {1, 2, 3, 4}


def login_required(f):
    """Decorator to require login for admin routes"""
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


# ============================================================================
# PUBLIC ROUTES (Frontend)
# ============================================================================

def _serve_html(filename):
    """Read an HTML file from static/ and inject config values."""
    filepath = os.path.join(app.static_folder, filename)
    with open(filepath, 'r') as f:
        html = f.read()
    html = html.replace('__SITE_URL__', SITE_URL)
    html = html.replace('__GA_TRACKING_ID__', GA_TRACKING_ID)
    return Response(html, mimetype='text/html')


@app.route('/')
def homepage():
    """Serve the homepage"""
    return _serve_html('index.html')


@app.route('/puzzle/<puzzle_number>')
def puzzle_page(puzzle_number):
    """Serve the puzzle solving page"""
    return _serve_html('puzzle.html')


@app.route('/guide')
def guide_page():
    """Serve the how-to-solve-cryptics guide"""
    return _serve_html('guide.html')


@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt for search engine crawlers"""
    content = f"""User-agent: *
Allow: /
Allow: /puzzle/
Allow: /guide
Disallow: /admin/
Disallow: /api/

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    """Generate dynamic sitemap with all published puzzles"""
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT puzzle_number, published_at
            FROM puzzles
            WHERE status = 'published'
            ORDER BY published_at DESC
        """)
        puzzles = cursor.fetchall()
    except Exception:
        app.logger.exception("Failed to query puzzles for sitemap")
        puzzles = []

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # Homepage
    xml += '  <url>\n'
    xml += f'    <loc>{SITE_URL}/</loc>\n'
    xml += '    <changefreq>daily</changefreq>\n'
    xml += '    <priority>1.0</priority>\n'
    xml += '  </url>\n'

    # Guide page
    xml += '  <url>\n'
    xml += f'    <loc>{SITE_URL}/guide</loc>\n'
    xml += '    <changefreq>monthly</changefreq>\n'
    xml += '    <priority>0.9</priority>\n'
    xml += '  </url>\n'

    # Individual puzzle pages
    for puzzle in puzzles:
        lastmod = ''
        pub_date = puzzle.get('published_at')
        if pub_date:
            try:
                if hasattr(pub_date, 'strftime'):
                    lastmod = f'    <lastmod>{pub_date.strftime("%Y-%m-%d")}</lastmod>\n'
                else:
                    lastmod = f'    <lastmod>{str(pub_date)[:10]}</lastmod>\n'
            except Exception:
                pass
        xml += '  <url>\n'
        xml += f'    <loc>{SITE_URL}/puzzle/{puzzle["puzzle_number"]}</loc>\n'
        xml += lastmod
        xml += '    <changefreq>monthly</changefreq>\n'
        xml += '    <priority>0.8</priority>\n'
        xml += '  </url>\n'

    xml += '</urlset>'

    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


@app.route('/api/puzzle/today')
def get_today_puzzle():
    """Get today's published puzzle"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get the most recent published puzzle
    cursor.execute('''
        SELECT id, publication, puzzle_number, setter, date, grid_data
        FROM puzzles 
        WHERE status = 'published'
        AND date <= CURRENT_DATE
        ORDER BY date DESC 
        LIMIT 1
    ''')
    puzzle = cursor.fetchone()
    
    if not puzzle:
        return jsonify({'error': 'No puzzle available'}), 404
    
    # Get all clues for this puzzle
    cursor.execute('''
        SELECT id, clue_number, direction, clue_text, enumeration, answer
        FROM clues
        WHERE puzzle_id = %s
        ORDER BY 
            CASE WHEN direction = 'across' THEN 0 ELSE 1 END,
            CAST(clue_number AS INTEGER)
    ''', (puzzle['id'],))
    clues = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'id': puzzle['id'],
        'publication': puzzle['publication'],
        'puzzle_number': puzzle['puzzle_number'],
        'setter': puzzle['setter'],
        'date': puzzle['date'],
        'grid': puzzle.get('grid_data'),
        'clues': [dict(clue) for clue in clues]
    })


@app.route('/api/puzzles/published')
def get_published_puzzles():
    """Get all published puzzles for listing"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT p.id, p.publication, p.puzzle_number, p.setter, p.date,
               COUNT(c.id) as clue_count
        FROM puzzles p
        LEFT JOIN clues c ON c.puzzle_id = p.id
        WHERE p.status = 'published'
        GROUP BY p.id, p.publication, p.puzzle_number, p.setter, p.date
        ORDER BY p.date DESC
    ''')
    puzzles = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify([dict(p) for p in puzzles])


@app.route('/api/puzzle/<puzzle_number>')
def get_puzzle_by_number(puzzle_number):
    """Get a specific puzzle by its number"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get puzzle
    cursor.execute('''
        SELECT id, publication, puzzle_number, setter, date, status, grid_data
        FROM puzzles 
        WHERE puzzle_number = %s
        AND status = 'published'
        LIMIT 1
    ''', (puzzle_number,))
    puzzle = cursor.fetchone()
    
    if not puzzle:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Puzzle not found'}), 404
    
    # Get clues with hints included
    cursor.execute('''
        SELECT id, clue_number, direction, clue_text, enumeration, answer,
               hint_level_1, hint_level_2, hint_level_3, hint_level_4
        FROM clues
        WHERE puzzle_id = %s
        ORDER BY
            CASE WHEN direction = 'across' THEN 0 ELSE 1 END,
            CAST(clue_number AS INTEGER)
    ''', (puzzle['id'],))
    clues = cursor.fetchall()

    # Format clues with hints array
    formatted_clues = []
    for clue in clues:
        formatted_clues.append({
            'id': clue['id'],
            'clue_number': clue['clue_number'],
            'direction': clue['direction'],
            'clue_text': clue['clue_text'],
            'enumeration': clue['enumeration'],
            'answer': clue['answer'],
            'hints': [
                clue['hint_level_1'] or '',
                clue['hint_level_2'] or '',
                clue['hint_level_3'] or '',
                clue['hint_level_4'] or ''
            ]
        })

    cursor.close()
    conn.close()

    return jsonify({
        'id': puzzle['id'],
        'publication': puzzle['publication'],
        'puzzle_number': puzzle['puzzle_number'],
        'setter': puzzle['setter'],
        'date': str(puzzle['date']),
        'grid': puzzle.get('grid_data'),
        'clues': formatted_clues
    })


@app.route('/api/puzzle/<int:puzzle_id>/grid')
def get_puzzle_grid(puzzle_id):
    """Get grid data for a puzzle"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT grid_data 
        FROM puzzles 
        WHERE id = %s
    ''', (puzzle_id,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not result or not result.get('grid_data'):
        return jsonify({'error': 'Grid not found'}), 404
    
    return jsonify(result['grid_data'])


@app.route('/api/clue/<int:clue_id>/hints')
def get_clue_hints(clue_id):
    """Get all hints for a clue"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT hint_level_1, hint_level_2, hint_level_3, hint_level_4
        FROM clues
        WHERE id = %s
    ''', (clue_id,))
    
    clue = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not clue:
        return jsonify({'error': 'Clue not found'}), 404
    
    return jsonify({
        'clue_id': clue_id,
        'hints': [
            clue['hint_level_1'] or '',
            clue['hint_level_2'] or '',
            clue['hint_level_3'] or '',
            clue['hint_level_4'] or ''
        ]
    })


@app.route('/api/clue/<int:clue_id>/hint/<int:level>')
def get_hint(clue_id, level):
    """Get a specific hint level for a clue"""
    if level not in [1, 2, 3, 4]:
        return jsonify({'error': 'Invalid hint level'}), 400
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute(f'''
        SELECT hint_level_{level} as hint_text,
               hint_{level}_approved as approved
        FROM clues
        WHERE id = %s
    ''', (clue_id,))
    clue = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not clue:
        return jsonify({'error': 'Clue not found'}), 404
    
    return jsonify({
        'clue_id': clue_id,
        'hint_level': level,
        'hint_text': clue['hint_text'],
        'can_request_next': level < 4
    })


@app.route('/api/clue/<int:clue_id>/check', methods=['POST'])
def check_answer(clue_id):
    """Check if an answer is correct"""
    data = request.get_json()
    user_answer = data.get('answer', '').strip().upper()
    
    if not user_answer:
        return jsonify({'error': 'No answer provided'}), 400
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT answer, clue_text
        FROM clues
        WHERE id = %s
    ''', (clue_id,))
    clue = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not clue:
        return jsonify({'error': 'Clue not found'}), 404
    
    # Remove spaces and hyphens for comparison
    correct_answer = clue['answer'].upper().replace(' ', '').replace('-', '')
    user_answer_cleaned = user_answer.replace(' ', '').replace('-', '')
    
    correct = user_answer_cleaned == correct_answer
    
    return jsonify({
        'correct': correct,
        'message': '🎉 Correct! Well done!' if correct else '❌ Not quite - try again or check the hints',
        'clue_text': clue['clue_text']
    })


# ============================================================================
# EMAIL SUBSCRIPTION
# ============================================================================

@app.route('/api/subscribe', methods=['POST'])
def subscribe_email():
    """Subscribe an email to puzzle notifications"""
    import re
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()

    if not email or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'success': False, 'message': 'Please enter a valid email address'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Re-subscribe if previously unsubscribed, otherwise insert
        cursor.execute('''
            INSERT INTO subscribers (email, confirmed)
            VALUES (%s, FALSE)
            ON CONFLICT (email)
            DO UPDATE SET unsubscribed_at = NULL, subscribed_at = CURRENT_TIMESTAMP
        ''', (email,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Unable to subscribe. Please try again.'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({'success': True, 'message': 'Thanks for subscribing! You\'ll be notified when new puzzles are published.'})


@app.route('/api/unsubscribe', methods=['POST'])
def unsubscribe_email():
    """Unsubscribe an email from puzzle notifications"""
    data = request.get_json()
    email = (data.get('email') or '').strip().lower()

    if not email:
        return jsonify({'success': False, 'message': 'Email required'}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE subscribers
        SET unsubscribed_at = CURRENT_TIMESTAMP
        WHERE email = %s AND unsubscribed_at IS NULL
    ''', (email,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'success': True, 'message': 'You have been unsubscribed.'})


# ============================================================================
# ADMIN AUTHENTICATION
# ============================================================================

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard landing page"""
    return send_from_directory('static', 'admin-dashboard.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '')
        password = data.get('password', '')
        
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            session['username'] = username
            return jsonify({'success': True, 'message': 'Login successful'})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    
    # Return login page HTML
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f0f0f0; }
            .login-box { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
            h2 { margin-top: 0; }
            input { width: 100%; padding: 0.75rem; margin: 0.5rem 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            button { width: 100%; padding: 0.75rem; background: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
            button:hover { background: #1d4ed8; }
            .error { color: red; margin-top: 0.5rem; display: none; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>Admin Login</h2>
            <input type="text" id="username" placeholder="Username" />
            <input type="password" id="password" placeholder="Password" />
            <button onclick="login()">Login</button>
            <div class="error" id="error">Invalid credentials</div>
        </div>
        <script>
            function login() {
                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                
                fetch('/admin/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        window.location.href = '/admin';
                    } else {
                        document.getElementById('error').style.display = 'block';
                    }
                });
            }
            
            document.getElementById('password').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') login();
            });
        </script>
    </body>
    </html>
    '''


@app.route('/admin/logout')
def admin_logout():
    """Logout"""
    session.clear()
    return redirect(url_for('admin_login'))


# ============================================================================
# ADMIN ROUTES (Hint Review & Publishing)
# ============================================================================

@app.route('/admin/puzzles')
@login_required
def admin_puzzles():
    """Admin puzzle management page"""
    return send_from_directory('static', 'admin-puzzles.html')


@app.route('/admin/review')
@login_required
def admin_review():
    """Admin review interface"""
    return send_from_directory('static', 'admin-review.html')


@app.route('/admin/api/scrape-and-import', methods=['POST'])
@login_required
def scrape_and_import():
    """Scrape puzzle from Guardian and fifteensquared, then import"""
    data = request.json
    puzzle_number = data.get('puzzle_number')
    
    if not puzzle_number:
        return jsonify({'success': False, 'message': 'Puzzle number required'})
    
    try:
        # Import the scraper
        from puzzle_scraper import PuzzleScraper
        
        # Scrape the puzzle
        scraper = PuzzleScraper()
        
        try:
            puzzle_data = scraper.scrape_puzzle(puzzle_number)
        except Exception as scrape_error:
            print(f"Scraping error: {scrape_error}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'message': f'Scraping failed: {str(scrape_error)}',
                'details': 'Error while fetching puzzle data'
            })
        
        if 'error' in puzzle_data:
            return jsonify({
                'success': False, 
                'message': puzzle_data['error'],
                'details': 'Could not fetch puzzle from Guardian'
            })
        
        # Check hint coverage
        clues_with_hints = len([c for c in puzzle_data.get('clues', []) if any(c.get('hints', []))])
        
        # Import into database
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            # Insert puzzle
            cursor.execute('''
                INSERT INTO puzzles (publication, puzzle_number, setter, date, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                puzzle_data.get('publication', 'Guardian'),
                puzzle_data.get('puzzle_number', puzzle_number),
                puzzle_data.get('setter', 'Unknown'),
                puzzle_data.get('date', datetime.now().strftime('%Y-%m-%d')),
                'draft'
            ))
            
            puzzle_id = cursor.fetchone()[0]
            
            # Store grid data if available
            if puzzle_data.get('grid'):
                cursor.execute('''
                    UPDATE puzzles
                    SET grid_data = %s
                    WHERE id = %s
                ''', (json.dumps(puzzle_data['grid']), puzzle_id))

            # Store API usage stats
            api_usage = puzzle_data.get('api_usage', {})
            if api_usage.get('api_calls', 0) > 0:
                cursor.execute('''
                    INSERT INTO api_usage (
                        puzzle_id, puzzle_number, api_calls,
                        input_tokens, output_tokens,
                        estimated_cost_usd, model
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    puzzle_id,
                    puzzle_data.get('puzzle_number', puzzle_number),
                    api_usage.get('api_calls', 0),
                    api_usage.get('input_tokens', 0),
                    api_usage.get('output_tokens', 0),
                    api_usage.get('estimated_cost_usd', 0),
                    api_usage.get('model', ''),
                ))
            
            # Insert clues with hints
            clue_count = 0
            for clue_data in puzzle_data.get('clues', []):
                hints = clue_data.get('hints', ['', '', '', ''])
                
                # Validate data
                clue_number = str(clue_data.get('clue_number', ''))[:10]
                direction = str(clue_data.get('direction', 'across'))[:10]
                clue_text = str(clue_data.get('clue_text', ''))[:500]
                answer = str(clue_data.get('answer', ''))[:100]
                enumeration = str(clue_data.get('enumeration', ''))[:20]
                
                # Truncate hints if too long
                hint1 = hints[0][:1000] if len(hints) > 0 else ''
                hint2 = hints[1][:1000] if len(hints) > 1 else ''
                hint3 = hints[2][:2000] if len(hints) > 2 else ''
                hint4 = hints[3][:5000] if len(hints) > 3 else ''
                
                cursor.execute('''
                    INSERT INTO clues (
                        puzzle_id, clue_number, direction, clue_text, 
                        answer, enumeration,
                        hint_level_1, hint_level_2, hint_level_3, hint_level_4,
                        hint_1_approved, hint_2_approved, hint_3_approved, hint_4_approved
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    puzzle_id,
                    clue_number,
                    direction,
                    clue_text,
                    answer,
                    enumeration,
                    hint1, hint2, hint3, hint4,
                    False, False, False, False
                ))
                clue_count += 1
            
            print(f"Inserted {clue_count} clues into database")
            conn.commit()
            
        except Exception as db_error:
            conn.rollback()
            raise db_error
        finally:
            cursor.close()
            conn.close()
        
        # Build response message
        message = f"Successfully imported puzzle {puzzle_number}"
        if clues_with_hints == 0:
            message += " (No hints found - you'll need to write hints manually)"
        elif clues_with_hints < len(puzzle_data.get('clues', [])):
            message += f" ({clues_with_hints}/{len(puzzle_data['clues'])} clues have hints)"

        api_usage = puzzle_data.get('api_usage', {})
        if api_usage.get('api_calls', 0) > 0:
            message += f" | API cost: ${api_usage['estimated_cost_usd']:.4f}"

        return jsonify({
            'success': True,
            'puzzle_id': puzzle_id,
            'puzzle_number': puzzle_data.get('puzzle_number', puzzle_number),
            'setter': puzzle_data.get('setter', 'Unknown'),
            'clue_count': len(puzzle_data.get('clues', [])),
            'hints_found': clues_with_hints,
            'api_usage': api_usage,
            'message': message
        })
        
    except Exception as e:
        print(f"Error in scrape_and_import: {e}")
        import traceback
        error_details = traceback.format_exc()
        print(error_details)
        return jsonify({
            'success': False, 
            'message': str(e),
            'details': error_details[:500]  # First 500 chars of traceback
        })


@app.route('/admin/quick-import')
@login_required  
def admin_quick_import():
    """Auto-import page for Guardian puzzles"""
    return send_from_directory('static', 'admin-import-auto.html')


@app.route('/admin/init-db')
@login_required
def admin_init_db():
    """Initialize the database (creates tables)"""
    try:
        init_db()
        return jsonify({
            'success': True,
            'message': 'Database initialized successfully!'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/admin/api/puzzles/all')
@login_required
def get_all_puzzles_admin():
    """Get all puzzles (any status) for admin"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT p.*, 
               COUNT(DISTINCT c.id) as total_clues
        FROM puzzles p
        LEFT JOIN clues c ON c.puzzle_id = p.id
        GROUP BY p.id
        ORDER BY p.date DESC, p.id DESC
    ''')
    puzzles = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'puzzles': [dict(p) for p in puzzles]
    })


@app.route('/admin/api/puzzle/<int:puzzle_id>', methods=['DELETE'])
@login_required
def delete_puzzle(puzzle_id):
    """Delete a puzzle and all its clues"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Delete clues first (cascade should handle this but be explicit)
    cursor.execute('DELETE FROM clues WHERE puzzle_id = %s', (puzzle_id,))
    
    # Delete puzzle
    cursor.execute('DELETE FROM puzzles WHERE id = %s', (puzzle_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Puzzle deleted'})


@app.route('/admin/api/puzzles/pending')
@login_required
def get_pending_puzzles():
    """Get all puzzles awaiting review"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT p.*, 
               COUNT(DISTINCT c.id) as total_clues,
               SUM(CASE WHEN c.hint_1_flagged OR c.hint_2_flagged OR c.hint_3_flagged OR c.hint_4_flagged THEN 1 ELSE 0 END) as flagged_count,
               SUM(CASE WHEN c.hint_1_approved AND c.hint_2_approved AND c.hint_3_approved AND c.hint_4_approved THEN 1 ELSE 0 END) as approved_count
        FROM puzzles p
        LEFT JOIN clues c ON c.puzzle_id = p.id
        WHERE p.status = 'draft'
        GROUP BY p.id
        ORDER BY p.date DESC
    ''')
    puzzles = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'puzzles': [dict(p) for p in puzzles]
    })


@app.route('/admin/api/puzzle/<int:puzzle_id>/clues')
@login_required
def get_puzzle_clues_for_review(puzzle_id):
    """Get all clues for a puzzle with review status"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        SELECT * FROM clues
        WHERE puzzle_id = %s
        ORDER BY 
            CASE WHEN direction = 'across' THEN 0 ELSE 1 END,
            CAST(clue_number AS INTEGER)
    ''', (puzzle_id,))
    clues = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'clues': [dict(c) for c in clues]
    })


@app.route('/admin/api/hint/update', methods=['POST'])
@login_required
def update_hint():
    """Update a hint text"""
    data = request.get_json()
    clue_id = data.get('clue_id')
    hint_level = data.get('hint_level')
    new_text = data.get('new_text')

    if hint_level not in VALID_HINT_LEVELS:
        return jsonify({'error': 'Invalid hint level'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get old text for revision history
    cursor.execute(f'''
        SELECT hint_level_{hint_level} as old_text
        FROM clues WHERE id = %s
    ''', (clue_id,))
    old_text = cursor.fetchone()['old_text']

    # Update hint
    cursor.execute(f'''
        UPDATE clues
        SET hint_level_{hint_level} = %s,
            hint_{hint_level}_flagged = FALSE
        WHERE id = %s
    ''', (new_text, clue_id))

    # Save revision
    cursor.execute('''
        INSERT INTO hint_revisions (clue_id, hint_level, old_text, new_text, edited_by)
        VALUES (%s, %s, %s, %s, %s)
    ''', (clue_id, hint_level, old_text, new_text, session.get('username')))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'success': True})


@app.route('/admin/api/hint/approve', methods=['POST'])
@login_required
def approve_hint():
    """Approve a hint"""
    data = request.get_json()
    clue_id = data.get('clue_id')
    hint_level = data.get('hint_level')

    if hint_level not in VALID_HINT_LEVELS:
        return jsonify({'error': 'Invalid hint level'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(f'''
        UPDATE clues
        SET hint_{hint_level}_approved = TRUE,
            hint_{hint_level}_flagged = FALSE
        WHERE id = %s
    ''', (clue_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True})


@app.route('/admin/api/hint/flag', methods=['POST'])
@login_required
def flag_hint():
    """Flag a hint for review"""
    data = request.get_json()
    clue_id = data.get('clue_id')
    hint_level = data.get('hint_level')

    if hint_level not in VALID_HINT_LEVELS:
        return jsonify({'error': 'Invalid hint level'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(f'''
        UPDATE clues
        SET hint_{hint_level}_flagged = TRUE,
            hint_{hint_level}_approved = FALSE
        WHERE id = %s
    ''', (clue_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True})


@app.route('/admin/api/puzzle/<int:puzzle_id>/publish', methods=['POST'])
@login_required
def publish_puzzle(puzzle_id):
    """Publish a puzzle (make it live)"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check all hints are approved
    cursor.execute('''
        SELECT COUNT(*) as count FROM clues
        WHERE puzzle_id = %s
        AND (hint_1_approved = FALSE OR hint_2_approved = FALSE OR hint_3_approved = FALSE OR hint_4_approved = FALSE)
    ''', (puzzle_id,))
    unapproved = cursor.fetchone()['count']
    
    if unapproved > 0:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': f'{unapproved} hints still need approval'}), 400
    
    # Publish
    cursor.execute('''
        UPDATE puzzles
        SET status = 'published',
            published_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING puzzle_number, setter
    ''', (puzzle_id,))
    published = cursor.fetchone()

    # Count active subscribers (for the response message)
    cursor.execute('''
        SELECT COUNT(*) as count FROM subscribers
        WHERE unsubscribed_at IS NULL
    ''')
    sub_count = cursor.fetchone()['count']

    conn.commit()
    cursor.close()
    conn.close()

    # Send email notifications in the background
    notify_msg = ''
    if sub_count > 0:
        puzzle_num = published['puzzle_number'] if published else str(puzzle_id)
        setter_name = published['setter'] if published else 'Unknown'
        if SMTP_USER and SMTP_PASSWORD:
            notify_subscribers(puzzle_num, setter_name)
            notify_msg = f' (notifying {sub_count} subscriber{"s" if sub_count != 1 else ""})'
        else:
            notify_msg = f' ({sub_count} subscriber{"s" if sub_count != 1 else ""} — SMTP not configured)'

    return jsonify({
        'success': True,
        'message': f'Puzzle published successfully!{notify_msg}'
    })


@app.route('/admin/api/puzzle/<int:puzzle_id>/unpublish', methods=['POST'])
@login_required
def unpublish_puzzle(puzzle_id):
    """Unpublish a puzzle (take it offline)"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('''
        UPDATE puzzles 
        SET status = 'draft'
        WHERE id = %s
    ''', (puzzle_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Puzzle unpublished'})


@app.route('/admin/api/usage')
@login_required
def get_api_usage():
    """Get API usage stats for the admin dashboard"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Per-import breakdown (most recent first)
    cursor.execute('''
        SELECT id, puzzle_number, api_calls, input_tokens, output_tokens,
               (input_tokens + output_tokens) as total_tokens,
               estimated_cost_usd, model, created_at
        FROM api_usage
        ORDER BY created_at DESC
    ''')
    imports = cursor.fetchall()

    # Running totals
    cursor.execute('''
        SELECT COALESCE(SUM(api_calls), 0) as total_calls,
               COALESCE(SUM(input_tokens), 0) as total_input_tokens,
               COALESCE(SUM(output_tokens), 0) as total_output_tokens,
               COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
               COALESCE(SUM(estimated_cost_usd), 0) as total_cost_usd,
               COUNT(*) as total_imports
        FROM api_usage
    ''')
    totals = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify({
        'imports': [dict(r) for r in imports],
        'totals': dict(totals),
    })


@app.route('/admin/usage')
@login_required
def admin_usage():
    """Admin API usage page"""
    return send_from_directory('static', 'admin-usage.html')


@app.route('/admin/api/subscribers')
@login_required
def get_subscribers():
    """Get all subscribers for the admin dashboard"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
        SELECT id, email, subscribed_at, confirmed, unsubscribed_at
        FROM subscribers
        ORDER BY subscribed_at DESC
    ''')
    subscribers = cursor.fetchall()

    # Counts
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE unsubscribed_at IS NULL) as active,
            COUNT(*) FILTER (WHERE unsubscribed_at IS NOT NULL) as unsubscribed
        FROM subscribers
    ''')
    counts = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify({
        'subscribers': [dict(s) for s in subscribers],
        'counts': dict(counts),
    })


@app.route('/admin/api/subscriber/<int:subscriber_id>', methods=['DELETE'])
@login_required
def delete_subscriber(subscriber_id):
    """Delete a subscriber"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscribers WHERE id = %s', (subscriber_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})


@app.route('/admin/subscribers')
@login_required
def admin_subscribers():
    """Admin subscribers page"""
    return send_from_directory('static', 'admin-subscribers.html')


# ============================================================================
# IMPORT/SCRAPING ROUTES
# ============================================================================

@app.route('/admin/api/import-puzzle', methods=['POST'])
@login_required
def import_puzzle():
    """Import a puzzle with clues and AI-generated hints"""
    data = request.get_json()
    
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create puzzle
    cursor.execute('''
        INSERT INTO puzzles (publication, puzzle_number, setter, date, status)
        VALUES (%s, %s, %s, %s, 'draft')
        RETURNING id
    ''', (
        data['publication'],
        data['puzzle_number'],
        data['setter'],
        data['date']
    ))
    
    puzzle_id = cursor.fetchone()['id']
    
    # Add clues with hints
    for clue_data in data['clues']:
        cursor.execute('''
            INSERT INTO clues (
                puzzle_id, clue_number, direction, clue_text, 
                enumeration, answer, 
                hint_level_1, hint_level_2, hint_level_3, hint_level_4,
                hint_1_flagged, hint_2_flagged, hint_3_flagged, hint_4_flagged
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            puzzle_id,
            clue_data['clue_number'],
            clue_data['direction'],
            clue_data['clue_text'],
            clue_data['enumeration'],
            clue_data['answer'],
            clue_data['hints'][0],
            clue_data['hints'][1],
            clue_data['hints'][2],
            clue_data['hints'][3],
            clue_data.get('flagged', [False, False, False, False])[0],
            clue_data.get('flagged', [False, False, False, False])[1],
            clue_data.get('flagged', [False, False, False, False])[2],
            clue_data.get('flagged', [False, False, False, False])[3]
        ))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({
        'success': True,
        'puzzle_id': puzzle_id,
        'message': f'Imported puzzle {data["puzzle_number"]} with {len(data["clues"])} clues'
    })


# Initialize database when running with gunicorn (production)
# This runs on module import, before any requests
try:
    db_test = get_db()
    db_test.execute("SELECT 1 FROM puzzles LIMIT 1")
    db_test.close()
    print("✓ Database tables exist")
except:
    print("Database tables don't exist, initializing...")
    init_db()
    print("✓ Database initialized successfully!")


if __name__ == '__main__':
    # Initialize database on first run
    if not os.path.exists(DATABASE):
        print("Creating database...")
        init_db()
    
    print("\n" + "="*70)
    print("🧩 CRYPTIC CROSSWORD HINT SYSTEM - PRODUCTION")
    print("="*70)
    print("\nServer starting...")
    print("Public site: http://localhost:5000")
    print("Admin login: http://localhost:5000/admin/login")
    print("\nDefault admin credentials:")
    print("  Username: admin")
    print("  Password: changeme123")
    print("\n⚠️  CHANGE THE PASSWORD IN production_app.py BEFORE DEPLOYING!")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(debug=True, port=5000)
