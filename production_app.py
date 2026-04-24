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
import psycopg2.errors
from psycopg2.extras import RealDictCursor
import html as html_module
import json
from datetime import datetime, date, timedelta
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import threading
import uuid
import traceback as tb_module

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Session configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
CORS(app)

# In-memory store for background import tasks
_import_tasks = {}

# Auto-import scheduler state
_scheduler_state = {
    'enabled': os.environ.get('AUTO_IMPORT_ENABLED', 'true').lower() == 'true',
    'running': False,
    'last_check': None,
    'last_result': None,
    'next_check': None,
}

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


def notify_subscribers(puzzle_number, setter, puzzle_type='cryptic'):
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

            type_label = 'Quiptic' if puzzle_type == 'quiptic' else 'Cryptic'
            subject = f"New Puzzle: Guardian {type_label} #{puzzle_number}"
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


def save_puzzle_to_db(puzzle_data, puzzle_number, puzzle_type, auto_approve=False):
    """Save scraped puzzle data to the database.

    Returns (puzzle_id, clue_count) on success.
    Raises on failure (caller should handle).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO puzzles (publication, puzzle_type, puzzle_number, setter, date, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            puzzle_data.get('publication', 'Guardian'),
            puzzle_data.get('puzzle_type', puzzle_type),
            puzzle_data.get('puzzle_number', puzzle_number),
            puzzle_data.get('setter', 'Unknown'),
            puzzle_data.get('date', datetime.now().strftime('%Y-%m-%d')),
            'draft',
        ))
        puzzle_id = cursor.fetchone()[0]

        if puzzle_data.get('grid'):
            cursor.execute(
                "UPDATE puzzles SET grid_data = %s WHERE id = %s",
                (json.dumps(puzzle_data['grid']), puzzle_id),
            )

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

        clue_count = 0
        for clue_d in puzzle_data.get('clues', []):
            hints = clue_d.get('hints', ['', '', '', ''])
            cursor.execute('''
                INSERT INTO clues (
                    puzzle_id, clue_number, direction, clue_text,
                    answer, enumeration,
                    hint_level_1, hint_level_2, hint_level_3, hint_level_4,
                    hint_1_approved, hint_2_approved, hint_3_approved, hint_4_approved
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (
                puzzle_id,
                str(clue_d.get('clue_number', ''))[:10],
                str(clue_d.get('direction', 'across'))[:10],
                str(clue_d.get('clue_text', ''))[:500],
                str(clue_d.get('answer', ''))[:100],
                str(clue_d.get('enumeration', ''))[:20],
                (hints[0][:1000] if len(hints) > 0 else ''),
                (hints[1][:1000] if len(hints) > 1 else ''),
                (hints[2][:2000] if len(hints) > 2 else ''),
                (hints[3][:5000] if len(hints) > 3 else ''),
                auto_approve, auto_approve, auto_approve, auto_approve,
            ))
            clue_count += 1

        conn.commit()
        return puzzle_id, clue_count
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def init_db():
    """Initialize database with schema"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS puzzles (
            id SERIAL PRIMARY KEY,
            publication TEXT NOT NULL,
            puzzle_type TEXT DEFAULT 'cryptic',
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

    # Prevent duplicate puzzles (safe to run repeatedly - IF NOT EXISTS)
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_puzzles_number_type
        ON puzzles (puzzle_number, puzzle_type)
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            puzzle_number TEXT NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id SERIAL PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            meta_description TEXT,
            body TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_puzzle_date ON puzzles(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_puzzle_status ON puzzles(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_clue_puzzle ON clues(puzzle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_clue_lookup ON clues(puzzle_id, clue_number, direction)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriber_email ON subscribers(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_puzzle ON comments(puzzle_number)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_blog_slug ON blog_posts(slug)')
    
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

    # Add puzzle_type column if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='puzzles' AND column_name='puzzle_type'
            ) THEN
                ALTER TABLE puzzles ADD COLUMN puzzle_type TEXT DEFAULT 'cryptic';
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

def _serve_html(filename, extra=None, status=200):
    """Read an HTML file from static/ and inject config values."""
    filepath = os.path.join(app.static_folder, filename)
    with open(filepath, 'r') as f:
        html = f.read()
    html = html.replace('__SITE_URL__', SITE_URL)
    html = html.replace('__GA_TRACKING_ID__', GA_TRACKING_ID)
    if extra:
        for key, value in extra.items():
            html = html.replace(key, value)
    return Response(html, status=status, mimetype='text/html')


@app.route('/')
def homepage():
    """Serve the homepage with static puzzle fallback for no-JS"""
    # Fetch latest 10 puzzles for static rendering
    static_puzzles_html = ''
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT p.puzzle_type, p.puzzle_number, p.setter, p.date,
                   COUNT(c.id) as clue_count
            FROM puzzles p
            LEFT JOIN clues c ON c.puzzle_id = p.id
            WHERE p.status = 'published'
            GROUP BY p.id, p.puzzle_type, p.puzzle_number, p.setter, p.date
            ORDER BY p.date DESC
            LIMIT 10
        ''')
        puzzles = cursor.fetchall()
        cursor.close()
        conn.close()

        for p in puzzles:
            type_label = 'Quiptic' if p['puzzle_type'] == 'quiptic' else 'Cryptic'
            date_str = p['date'].strftime('%a, %d %b %Y') if p['date'] else 'Unknown date'
            clue_count = p['clue_count'] or '~28'
            static_puzzles_html += f'''
                <a href="/puzzle/{p['puzzle_number']}" class="puzzle-card">
                    <div class="puzzle-date">{date_str}</div>
                    <div class="puzzle-number">{type_label} #{p['puzzle_number']}</div>
                    <div class="puzzle-setter">by {p['setter']}</div>
                    <div class="puzzle-stats">
                        <div class="puzzle-stat">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="3" y="3" width="18" height="18" rx="2"/>
                                <path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>
                            </svg>
                            <strong>{clue_count}</strong> clues
                        </div>
                    </div>
                </a>'''
    except Exception:
        static_puzzles_html = '<div class="loading">Loading puzzles...</div>'

    return _serve_html('index.html', extra={'__STATIC_PUZZLES__': static_puzzles_html})


@app.route('/puzzle/<puzzle_number>')
def puzzle_page(puzzle_number):
    """Serve the puzzle solving page with server-side rendered clue list for SEO."""
    esc = html_module.escape
    puzzle_number = str(puzzle_number)

    # Default values
    ssr_content = ''
    puzzle_info = 'Loading...'
    page_title = f'Guardian Cryptic #{esc(puzzle_number)} - Hints &amp; Solutions | Cryptic Hints'
    page_desc = (f'Solve Guardian cryptic crossword #{esc(puzzle_number)} with progressive hints. '
                 'Get help from definition only to full explanation.')
    status = 200

    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute('''
            SELECT id, puzzle_type, puzzle_number, setter, date
            FROM puzzles WHERE puzzle_number = %s AND status = 'published' LIMIT 1
        ''', (puzzle_number,))
        puzzle = cursor.fetchone()

        if puzzle:
            cursor.execute('''
                SELECT clue_number, direction, clue_text, enumeration
                FROM clues WHERE puzzle_id = %s
                ORDER BY CASE WHEN direction = 'across' THEN 0 ELSE 1 END,
                         CAST(clue_number AS INTEGER)
            ''', (puzzle['id'],))
            clues = cursor.fetchall()

            ptype = 'Quiptic' if puzzle.get('puzzle_type') == 'quiptic' else 'Cryptic'
            setter = esc(puzzle['setter']) if puzzle.get('setter') else 'Unknown'
            puzzle_info = f'#{esc(puzzle_number)} by {setter} | {puzzle["date"]}'

            page_title = (f'Guardian {ptype} #{esc(puzzle_number)} by {setter} '
                          f'- Hints &amp; Solutions | Cryptic Hints')
            page_desc = (f'Solve Guardian {ptype.lower()} crossword #{esc(puzzle_number)} '
                         f'by {setter} with four levels of progressive hints.')

            # Build SSR clue list
            across_html = ''
            down_html = ''
            for clue in clues:
                enum = f' ({esc(clue["enumeration"])})' if clue.get('enumeration') else ''
                clue_html = (f'<p><strong>{esc(clue["clue_number"])}.</strong> '
                             f'{esc(clue["clue_text"])}{enum} '
                             f'<a href="/clue/{esc(puzzle_number)}/{esc(clue["clue_number"])}'
                             f'-{esc(clue["direction"])}">Hints</a></p>')
                if clue['direction'] == 'across':
                    across_html += clue_html
                else:
                    down_html += clue_html

            ssr_content = (
                '<div class="direction-section">'
                '<h2 class="direction-title">Across</h2>'
                f'{across_html}'
                '</div>'
                '<div class="direction-section">'
                '<h2 class="direction-title">Down</h2>'
                f'{down_html}'
                '</div>'
            )
        else:
            ssr_content = '<p>Puzzle not found.</p>'
            status = 404

        cursor.close()
        conn.close()
    except Exception:
        pass  # Fall back to empty SSR content

    return _serve_html('puzzle.html', extra={
        '__PUZZLE_NUMBER__': puzzle_number,
        '__PUZZLE_SSR_CONTENT__': ssr_content,
        '__PUZZLE_INFO__': puzzle_info,
        '__PUZZLE_PAGE_TITLE__': page_title,
        '__PUZZLE_PAGE_DESC__': page_desc,
    }, status=status)


@app.route('/guide')
def guide_page():
    """Serve the how-to-solve-cryptics guide"""
    return _serve_html('guide.html')


@app.route('/synonyms')
def synonyms_page():
    """Serve the public synonym database page"""
    return send_from_directory('static', 'synonym_database.html')


GUIDE_PAGES = ['anagrams', 'hidden-words', 'double-definitions', 'reversals', 'containers', 'homophones', 'deletions']


@app.route('/guide/<slug>')
def guide_subpage(slug):
    """Serve standalone guide pages for each clue type"""
    if slug not in GUIDE_PAGES:
        return _serve_html('guide.html')
    return send_from_directory('static/guide', f'{slug}.html')


@app.route('/blog')
def blog_listing():
    """Serve the blog listing page"""
    return _serve_html('blog.html')


@app.route('/blog/<slug>')
def blog_post_page(slug):
    """Serve an individual blog post page"""
    return _serve_html('blog-post.html', extra={'__BLOG_SLUG__': slug})


@app.route('/clue/<puzzle_number>/<clue_ref>')
def clue_page(puzzle_number, clue_ref):
    """Serve an individual clue page with server-side rendered content for SEO."""
    esc = html_module.escape
    puzzle_number = str(puzzle_number)
    clue_ref = str(clue_ref)

    # Default SSR values (used if DB query fails)
    ssr_content = '<div class="loading-state">Loading clue...</div>'
    page_title = f'Clue {esc(clue_ref)} - Guardian Cryptic #{esc(puzzle_number)} | Cryptic Hints'
    page_desc = (f'Hints for clue {esc(clue_ref)} from Guardian cryptic crossword '
                 f'#{esc(puzzle_number)}. Progressive hints from gentle nudge to full explanation.')
    clue_label = clue_ref
    status = 200

    # Try to fetch clue data from DB for server-side rendering
    parts = clue_ref.rsplit('-', 1)
    if len(parts) == 2 and parts[1] in ('across', 'down'):
        clue_number, direction = parts
        try:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT p.puzzle_number, p.setter, p.date, p.puzzle_type,
                       c.clue_number, c.direction, c.clue_text, c.enumeration,
                       c.hint_level_1, c.hint_level_2, c.hint_level_3, c.hint_level_4
                FROM clues c
                JOIN puzzles p ON c.puzzle_id = p.id
                WHERE p.puzzle_number = %s AND p.status = 'published'
                      AND c.clue_number = %s AND c.direction = %s
                LIMIT 1
            ''', (puzzle_number, clue_number, direction))
            row = cursor.fetchone()
            cursor.close()
            conn.close()

            if row:
                dir_label = direction.capitalize()
                label = f'{row["clue_number"]} {dir_label}'
                clue_label = label
                ptype = 'Quiptic' if row.get('puzzle_type') == 'quiptic' else 'Cryptic'
                setter_html = (f' by {esc(row["setter"])}' if row.get('setter')
                               and row['setter'] != 'Unknown' else '')
                enum_html = (f'<span class="clue-enum">({esc(row["enumeration"])})</span>'
                             if row.get('enumeration') else '')

                hints = [
                    row['hint_level_1'] or '',
                    row['hint_level_2'] or '',
                    row['hint_level_3'] or '',
                    row['hint_level_4'] or '',
                ]
                hint_labels = [
                    'Hint 1: Gentle nudge', 'Hint 2: More specific',
                    'Hint 3: Strong hint', 'Hint 4: Full explanation',
                ]
                hints_html = ''
                for i, hint in enumerate(hints):
                    if not hint:
                        continue
                    hints_html += (f'<button class="hint-btn" id="hint-btn-{i}" '
                                   f'onclick="toggleHint({i})">{hint_labels[i]}</button>')
                    hints_html += f'<div class="hint-text" id="hint-{i}">{esc(hint)}</div>'

                ssr_content = (
                    '<div class="clue-card">'
                    '<div class="clue-header">'
                    f'<span class="clue-number">{esc(label)}</span>'
                    f'{enum_html}'
                    '</div>'
                    f'<div class="clue-text">{esc(row["clue_text"])}</div>'
                    f'<div class="clue-meta">Guardian {ptype} #{esc(puzzle_number)}{setter_html}'
                    f' &middot; <a href="/puzzle/{esc(puzzle_number)}">View full puzzle</a></div>'
                    '<div class="hints-section">'
                    '<h2>Progressive Hints</h2>'
                    f'{hints_html}'
                    '</div>'
                    '</div>'
                    f'<a href="/puzzle/{esc(puzzle_number)}" class="full-puzzle-link">'
                    'Solve the full puzzle &rarr;</a>'
                )
                page_title = f'{label} - Guardian {ptype} #{puzzle_number} | Cryptic Hints'
                page_desc = (f'Hints for {label} from Guardian {ptype.lower()} '
                             f'#{puzzle_number}: \u201c{esc(row["clue_text"])}\u201d')
            else:
                ssr_content = (f'<div class="error-state">Clue not found. '
                               f'<a href="/puzzle/{esc(puzzle_number)}">View full puzzle</a></div>')
                status = 404
        except Exception:
            pass  # Fall back to default "Loading clue..." content

    return _serve_html('clue.html', extra={
        '__PUZZLE_NUMBER__': puzzle_number,
        '__CLUE_REF__': clue_ref,
        '__CLUE_SSR_CONTENT__': ssr_content,
        '__CLUE_PAGE_TITLE__': page_title,
        '__CLUE_PAGE_DESC__': page_desc,
        '__CLUE_LABEL__': clue_label,
    }, status=status)


@app.route('/api/clue/<puzzle_number>/<clue_ref>')
def get_clue_by_ref(puzzle_number, clue_ref):
    """Get a single clue by puzzle number and clue reference (e.g. 3-across)."""
    parts = clue_ref.rsplit('-', 1)
    if len(parts) != 2 or parts[1] not in ('across', 'down'):
        return jsonify({'error': 'Invalid clue reference. Use format: 3-across'}), 400

    clue_number, direction = parts

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
        SELECT p.puzzle_number, p.setter, p.date, p.puzzle_type,
               c.id, c.clue_number, c.direction, c.clue_text, c.enumeration, c.answer,
               c.hint_level_1, c.hint_level_2, c.hint_level_3, c.hint_level_4
        FROM clues c
        JOIN puzzles p ON c.puzzle_id = p.id
        WHERE p.puzzle_number = %s AND p.status = 'published'
              AND c.clue_number = %s AND c.direction = %s
        LIMIT 1
    ''', (puzzle_number, clue_number, direction))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return jsonify({'error': 'Clue not found'}), 404

    return jsonify({
        'puzzle_number': row['puzzle_number'],
        'setter': row['setter'],
        'date': str(row['date']),
        'puzzle_type': row.get('puzzle_type', 'cryptic'),
        'clue_id': row['id'],
        'clue_number': row['clue_number'],
        'direction': row['direction'],
        'clue_text': row['clue_text'],
        'enumeration': row['enumeration'],
        'answer': row['answer'],
        'hints': [
            row['hint_level_1'] or '',
            row['hint_level_2'] or '',
            row['hint_level_3'] or '',
            row['hint_level_4'] or '',
        ]
    })


@app.route('/api/blog/posts')
def get_blog_posts():
    """Get all published blog posts, newest first."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT id, slug, title, meta_description, published_at
        FROM blog_posts
        WHERE status = 'published'
        ORDER BY published_at DESC
    ''')
    posts = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{
        'id': p['id'],
        'slug': p['slug'],
        'title': p['title'],
        'meta_description': p['meta_description'],
        'published_at': p['published_at'].isoformat() if p['published_at'] else None,
    } for p in posts])


@app.route('/api/blog/posts/<slug>')
def get_blog_post(slug):
    """Get a single published blog post by slug."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT id, slug, title, meta_description, body, published_at
        FROM blog_posts
        WHERE slug = %s AND status = 'published'
    ''', (slug,))
    post = cursor.fetchone()
    cursor.close()
    conn.close()
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    return jsonify({
        'id': post['id'],
        'slug': post['slug'],
        'title': post['title'],
        'meta_description': post['meta_description'],
        'body': post['body'],
        'published_at': post['published_at'].isoformat() if post['published_at'] else None,
    })


@app.route('/robots.txt')
def robots_txt():
    """Serve robots.txt for search engine crawlers"""
    content = f"""User-agent: *
Allow: /
Allow: /puzzle/
Allow: /guide
Allow: /guide/
Allow: /blog
Allow: /clue/
Disallow: /admin/
Disallow: /api/

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(content, mimetype='text/plain')


def _sitemap_lastmod(pub_date):
    """Format a date for sitemap <lastmod>."""
    if not pub_date:
        return ''
    try:
        if hasattr(pub_date, 'strftime'):
            return f'    <lastmod>{pub_date.strftime("%Y-%m-%d")}</lastmod>\n'
        return f'    <lastmod>{str(pub_date)[:10]}</lastmod>\n'
    except Exception:
        return ''


def _xml_response(xml):
    """Return an XML response."""
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml'
    return response


@app.route('/sitemap.xml')
def sitemap_index():
    """Sitemap index pointing to sub-sitemaps for better crawlability."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for name in ['pages', 'puzzles', 'blog', 'clues']:
        xml += '  <sitemap>\n'
        xml += f'    <loc>{SITE_URL}/sitemap-{name}.xml</loc>\n'
        xml += '  </sitemap>\n'
    xml += '</sitemapindex>'
    return _xml_response(xml)


@app.route('/sitemap-pages.xml')
def sitemap_pages():
    """Static pages sitemap."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '  <url>\n'
    xml += f'    <loc>{SITE_URL}/</loc>\n'
    xml += '    <changefreq>daily</changefreq>\n'
    xml += '    <priority>1.0</priority>\n'
    xml += '  </url>\n'
    xml += '  <url>\n'
    xml += f'    <loc>{SITE_URL}/guide</loc>\n'
    xml += '    <changefreq>monthly</changefreq>\n'
    xml += '    <priority>0.9</priority>\n'
    xml += '  </url>\n'
    for slug in GUIDE_PAGES:
        xml += '  <url>\n'
        xml += f'    <loc>{SITE_URL}/guide/{slug}</loc>\n'
        xml += '    <changefreq>monthly</changefreq>\n'
        xml += '    <priority>0.8</priority>\n'
        xml += '  </url>\n'
    xml += '  <url>\n'
    xml += f'    <loc>{SITE_URL}/blog</loc>\n'
    xml += '    <changefreq>weekly</changefreq>\n'
    xml += '    <priority>0.8</priority>\n'
    xml += '  </url>\n'
    xml += '</urlset>'
    return _xml_response(xml)


@app.route('/sitemap-puzzles.xml')
def sitemap_puzzles():
    """Puzzle pages sitemap."""
    puzzles = []
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

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for puzzle in puzzles:
        xml += '  <url>\n'
        xml += f'    <loc>{SITE_URL}/puzzle/{puzzle["puzzle_number"]}</loc>\n'
        xml += _sitemap_lastmod(puzzle.get('published_at'))
        xml += '    <changefreq>monthly</changefreq>\n'
        xml += '    <priority>0.8</priority>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    return _xml_response(xml)


@app.route('/sitemap-blog.xml')
def sitemap_blog():
    """Blog posts sitemap."""
    blog_posts = []
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT slug, published_at
            FROM blog_posts
            WHERE status = 'published'
            ORDER BY published_at DESC
        """)
        blog_posts = cursor.fetchall()
    except Exception:
        app.logger.exception("Failed to query blog posts for sitemap")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for post in blog_posts:
        xml += '  <url>\n'
        xml += f'    <loc>{SITE_URL}/blog/{post["slug"]}</loc>\n'
        xml += _sitemap_lastmod(post.get('published_at'))
        xml += '    <changefreq>monthly</changefreq>\n'
        xml += '    <priority>0.7</priority>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    return _xml_response(xml)


@app.route('/sitemap-clues.xml')
def sitemap_clues():
    """Individual clue pages sitemap."""
    clues = []
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT p.puzzle_number, c.clue_number, c.direction, p.published_at
            FROM clues c
            JOIN puzzles p ON c.puzzle_id = p.id
            WHERE p.status = 'published'
            ORDER BY p.puzzle_number DESC, c.direction, CAST(c.clue_number AS INTEGER)
        """)
        clues = cursor.fetchall()
    except Exception:
        app.logger.exception("Failed to query clues for sitemap")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for clue in clues:
        ref = f'{clue["clue_number"]}-{clue["direction"]}'
        xml += '  <url>\n'
        xml += f'    <loc>{SITE_URL}/clue/{clue["puzzle_number"]}/{ref}</loc>\n'
        xml += _sitemap_lastmod(clue.get('published_at'))
        xml += '    <changefreq>monthly</changefreq>\n'
        xml += '    <priority>0.5</priority>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    return _xml_response(xml)


def _rss_date(dt):
    """Format a datetime for RSS <pubDate> (RFC 822)."""
    if dt is None:
        return ''
    if hasattr(dt, 'strftime'):
        return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
    return str(dt)


@app.route('/feed/puzzles')
def rss_puzzles():
    """RSS feed of published puzzles."""
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT puzzle_number, setter, puzzle_type, published_at
            FROM puzzles
            WHERE status = 'published'
            ORDER BY published_at DESC
            LIMIT 30
        """)
        puzzles = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception:
        puzzles = []

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
    xml += '<channel>\n'
    xml += f'  <title>Cryptic Hints - New Puzzles</title>\n'
    xml += f'  <link>{SITE_URL}/</link>\n'
    xml += f'  <description>Latest Guardian cryptic crosswords with progressive hints</description>\n'
    xml += f'  <atom:link href="{SITE_URL}/feed/puzzles" rel="self" type="application/rss+xml"/>\n'

    for p in puzzles:
        ptype = 'Quiptic' if p.get('puzzle_type') == 'quiptic' else 'Cryptic'
        setter_str = f' by {p["setter"]}' if p.get('setter') and p['setter'] != 'Unknown' else ''
        xml += '  <item>\n'
        xml += f'    <title>Guardian {ptype} #{p["puzzle_number"]}{setter_str}</title>\n'
        xml += f'    <link>{SITE_URL}/puzzle/{p["puzzle_number"]}</link>\n'
        xml += f'    <guid>{SITE_URL}/puzzle/{p["puzzle_number"]}</guid>\n'
        xml += f'    <description>Solve Guardian {ptype} #{p["puzzle_number"]}{setter_str} with four levels of progressive hints.</description>\n'
        if p.get('published_at'):
            xml += f'    <pubDate>{_rss_date(p["published_at"])}</pubDate>\n'
        xml += '  </item>\n'

    xml += '</channel>\n</rss>'
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/rss+xml'
    return response


@app.route('/feed/blog')
def rss_blog():
    """RSS feed of published blog posts."""
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT slug, title, meta_description, published_at
            FROM blog_posts
            WHERE status = 'published'
            ORDER BY published_at DESC
            LIMIT 30
        """)
        posts = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception:
        posts = []

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
    xml += '<channel>\n'
    xml += f'  <title>Cryptic Hints Blog</title>\n'
    xml += f'  <link>{SITE_URL}/blog</link>\n'
    xml += f'  <description>Tips, guides, and insights about cryptic crosswords</description>\n'
    xml += f'  <atom:link href="{SITE_URL}/feed/blog" rel="self" type="application/rss+xml"/>\n'

    for p in posts:
        xml += '  <item>\n'
        xml += f'    <title>{p["title"]}</title>\n'
        xml += f'    <link>{SITE_URL}/blog/{p["slug"]}</link>\n'
        xml += f'    <guid>{SITE_URL}/blog/{p["slug"]}</guid>\n'
        if p.get('meta_description'):
            xml += f'    <description>{p["meta_description"]}</description>\n'
        if p.get('published_at'):
            xml += f'    <pubDate>{_rss_date(p["published_at"])}</pubDate>\n'
        xml += '  </item>\n'

    xml += '</channel>\n</rss>'
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/rss+xml'
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
        SELECT p.id, p.publication, p.puzzle_type, p.puzzle_number, p.setter, p.date,
               COUNT(c.id) as clue_count
        FROM puzzles p
        LEFT JOIN clues c ON c.puzzle_id = p.id
        WHERE p.status = 'published'
        GROUP BY p.id, p.publication, p.puzzle_type, p.puzzle_number, p.setter, p.date
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
        SELECT id, publication, puzzle_type, puzzle_number, setter, date, status, grid_data
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
        'puzzle_type': puzzle.get('puzzle_type', 'cryptic'),
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
# COMMENTS
# ============================================================================

@app.route('/api/puzzle/<puzzle_number>/comments')
def get_comments(puzzle_number):
    """Get comments for a puzzle, newest first."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
        SELECT id, author, body, created_at
        FROM comments
        WHERE puzzle_number = %s
        ORDER BY created_at DESC
    ''', (puzzle_number,))
    comments = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify([{
        'id': c['id'],
        'author': c['author'],
        'body': c['body'],
        'created_at': c['created_at'].isoformat() if c['created_at'] else None,
    } for c in comments])


@app.route('/api/puzzle/<puzzle_number>/comments', methods=['POST'])
def post_comment(puzzle_number):
    """Add a comment to a puzzle."""
    data = request.get_json() or {}
    author = (data.get('author') or '').strip()
    body = (data.get('body') or '').strip()

    if not author or not body:
        return jsonify({'error': 'Author and comment are required'}), 400

    if len(author) > 50:
        return jsonify({'error': 'Name is too long (max 50 characters)'}), 400

    if len(body) > 2000:
        return jsonify({'error': 'Comment is too long (max 2000 characters)'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute('''
            INSERT INTO comments (puzzle_number, author, body)
            VALUES (%s, %s, %s)
            RETURNING id, author, body, created_at
        ''', (puzzle_number, author, body))
        comment = cursor.fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        return jsonify({'error': 'Unable to save comment'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        'id': comment['id'],
        'author': comment['author'],
        'body': comment['body'],
        'created_at': comment['created_at'].isoformat() if comment['created_at'] else None,
    }), 201


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
    """Start async puzzle import - returns task_id for polling"""
    data = request.json
    puzzle_number = data.get('puzzle_number')
    puzzle_type = data.get('puzzle_type', 'cryptic')  # 'cryptic' or 'quiptic'

    if not puzzle_number:
        return jsonify({'success': False, 'message': 'Puzzle number required'})

    if puzzle_type not in ('cryptic', 'quiptic'):
        return jsonify({'success': False, 'message': 'Invalid puzzle type'})

    task_id = str(uuid.uuid4())
    _import_tasks[task_id] = {
        'status': 'running',
        'step': 'Starting import...',
        'puzzle_number': puzzle_number,
        'puzzle_type': puzzle_type,
        '_ts': time.time(),
    }

    thread = threading.Thread(
        target=_run_import_task,
        args=(task_id, puzzle_number, puzzle_type),
        daemon=True,
    )
    thread.start()

    return jsonify({'success': True, 'task_id': task_id})


@app.route('/admin/api/import-status/<task_id>')
@login_required
def import_status(task_id):
    """Poll import task status"""
    # Evict finished tasks older than 1 hour to prevent memory leak
    now = time.time()
    stale = [k for k, v in _import_tasks.items()
             if v.get('status') != 'running' and now - v.get('_ts', now) > 3600]
    for k in stale:
        _import_tasks.pop(k, None)

    task = _import_tasks.get(task_id)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify(task)


def _run_import_task(task_id, puzzle_number, puzzle_type):
    """Background worker that scrapes and imports a puzzle"""
    task = _import_tasks[task_id]
    try:
        from puzzle_scraper import PuzzleScraper

        task['step'] = 'Fetching puzzle from Guardian...'
        scraper = PuzzleScraper()

        try:
            puzzle_data = scraper.scrape_puzzle(puzzle_number, puzzle_type)
        except Exception as scrape_error:
            print(f"Scraping error: {scrape_error}")
            tb_module.print_exc()
            task.update({'status': 'error', 'message': f'Scraping failed: {scrape_error}',
                         'details': 'Error while fetching puzzle data'})
            return

        if 'error' in puzzle_data:
            task.update({'status': 'error', 'message': puzzle_data['error'],
                         'details': 'Could not fetch puzzle from Guardian'})
            return

        task['step'] = 'Saving to database...'
        puzzle_id, clue_count = save_puzzle_to_db(puzzle_data, puzzle_number, puzzle_type)

        clues_with_hints = len([c for c in puzzle_data.get('clues', []) if any(c.get('hints', []))])
        message = f"Successfully imported puzzle {puzzle_number}"
        if clues_with_hints == 0:
            message += " (No hints found - you'll need to write hints manually)"
        elif clues_with_hints < len(puzzle_data.get('clues', [])):
            message += f" ({clues_with_hints}/{len(puzzle_data['clues'])} clues have hints)"
        api_usage = puzzle_data.get('api_usage', {})
        if api_usage.get('api_calls', 0) > 0:
            message += f" | API cost: ${api_usage['estimated_cost_usd']:.4f}"

        task.update({
            'status': 'complete', 'success': True,
            'puzzle_id': puzzle_id,
            'puzzle_number': puzzle_data.get('puzzle_number', puzzle_number),
            'setter': puzzle_data.get('setter', 'Unknown'),
            'clue_count': clue_count,
            'hints_found': clues_with_hints,
            'api_usage': api_usage,
            'message': message,
        })

    except Exception as e:
        print(f"Error in import task: {e}")
        error_details = tb_module.format_exc()
        print(error_details)
        task.update({'status': 'error', 'message': str(e),
                     'details': error_details[:500]})


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
        RETURNING puzzle_number, setter, puzzle_type
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
        p_type = published.get('puzzle_type', 'cryptic') if published else 'cryptic'
        if SMTP_USER and SMTP_PASSWORD:
            notify_subscribers(puzzle_num, setter_name, p_type)
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
# SYNONYM DATABASE
# ============================================================================

@app.route('/synonyms')
def public_synonyms():
    """Public read-only synonym database page"""
    return send_from_directory('static', 'synonym_database.html')


@app.route('/periodic-table')
def public_periodic_table():
    """Public periodic table reference page"""
    return send_from_directory('static', 'periodic-table.html')


@app.route('/times-checker')
def times_checker():
    """Times crossword checker tool"""
    return send_from_directory('static', 'times-checker.html')


def _lookup_cryptics_dataset(req, clue, answer_len):
    """Search the cryptics.georgeho.org dataset (660K+ cryptic clues) for matching answers."""
    try:
        # Full-text search on the clue text
        resp = req.get(
            'https://cryptics.georgeho.org/data/clues.json',
            params={'_search': clue, '_size': 20, '_shape': 'array'},
            headers={'Accept': 'application/json'},
            timeout=8,
        )
        if resp.status_code != 200:
            return set()
        rows = resp.json()
        answers = set()
        for row in rows:
            ans = (row.get('answer') or '').upper().replace(' ', '')
            if ans.isalpha() and len(ans) == answer_len:
                answers.add(ans)
        return answers
    except Exception:
        return set()


def _lookup_danword(req, clue, answer_len):
    """Try to look up answers on danword.com."""
    try:
        from bs4 import BeautifulSoup
        clue_slug = '_'.join(w.capitalize() for w in clue.split())
        clue_slug = ''.join(c for c in clue_slug if c.isalnum() or c == '_')
        resp = req.get(
            f'https://www.danword.com/crossword/{clue_slug}',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html',
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return set()
        soup = BeautifulSoup(resp.text, 'html.parser')
        answers = set()
        for el in soup.find_all(['a', 'span', 'td', 'strong', 'b']):
            text = el.get_text(strip=True).upper().replace(' ', '')
            if text.isalpha() and len(text) == answer_len:
                answers.add(text)
        return answers
    except Exception:
        return set()


def _solve_with_claude(req, api_key, clue, answer_len):
    """Ask Claude to solve the cryptic clue. Returns a list of candidate answers."""
    prompt = (
        'You are an expert cryptic crossword solver. '
        f'Solve this cryptic crossword clue: "{clue}"\n'
        f'The answer has {answer_len} letters.\n\n'
        'Break down the wordplay mentally, then give your top 3 most likely answers '
        'in order of confidence. '
        'Return ONLY a JSON array of uppercase strings, no explanation, no markdown.\n'
        'Example: ["FIRST", "SECOND", "THIRD"]'
    )
    try:
        resp = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            json={
                'model': 'claude-sonnet-4-6-20250514',
                'max_tokens': 200,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        raw = ''.join(b.get('text', '') for b in result.get('content', []))
        raw = raw.replace('```json', '').replace('```', '').strip()
        candidates = json.loads(raw)
        if not isinstance(candidates, list):
            return []
        candidates = [c.upper().replace(' ', '') for c in candidates if isinstance(c, str)]
        return [c for c in candidates if len(c) == answer_len]
    except Exception:
        return []


@app.route('/api/check-clue', methods=['POST'])
def check_clue():
    """Solve a crossword clue using Claude + verification sources, then check user's guess."""
    import requests as req

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'message': 'ANTHROPIC_API_KEY not configured on server'}), 500

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    clue = (data.get('clue') or '').strip()
    guess = (data.get('guess') or '').strip().upper().replace(' ', '')

    if not clue or not guess:
        return jsonify({'success': False, 'message': 'Clue text and guess are required'}), 400

    guess_len = len(guess)

    # Step 1: Ask Claude to solve the clue
    claude_answers = _solve_with_claude(req, api_key, clue, guess_len)

    # Step 2: Look up verification sources in parallel-ish (sequential but fast)
    dataset_answers = _lookup_cryptics_dataset(req, clue, guess_len)
    danword_answers = _lookup_danword(req, clue, guess_len)

    # Step 3: Build a scored set of all candidate answers
    # Answers confirmed by multiple sources get higher confidence
    all_candidates = {}
    for ans in claude_answers:
        all_candidates[ans] = all_candidates.get(ans, 0) + 1
    for ans in dataset_answers:
        all_candidates[ans] = all_candidates.get(ans, 0) + 2  # dataset is authoritative
    for ans in danword_answers:
        all_candidates[ans] = all_candidates.get(ans, 0) + 2

    if not all_candidates:
        return jsonify({'success': False, 'message': 'Could not determine an answer. Try including the letter count, e.g. (5).'})

    # Step 4: Check if the user's guess appears in any source
    if guess in all_candidates:
        return jsonify({
            'success': True,
            'correct': True,
            'confidence': 'high' if all_candidates[guess] >= 2 else 'medium'
        })

    # Step 5: Find the best answer (highest confidence) to compare against
    best = max(all_candidates, key=all_candidates.get)
    confidence = all_candidates[best]

    wrong_positions = [i for i in range(guess_len) if i < len(best) and guess[i] != best[i]]

    return jsonify({
        'success': True,
        'correct': False,
        'wrong_count': len(wrong_positions),
        'wrong_positions': wrong_positions,
        'confidence': 'high' if confidence >= 2 else 'medium',
        'sources': (
            ('Verified across multiple sources' if confidence >= 3
             else 'Verified against crossword database' if dataset_answers or danword_answers
             else 'Based on Claude analysis only')
        )
    })


@app.route('/admin/synonyms')
@login_required
def admin_synonyms():
    """Admin synonym database page"""
    return send_from_directory('static', 'synonym_database.html')


@app.route('/admin/api/synonyms/extract', methods=['POST'])
@login_required
def extract_synonyms():
    """Proxy endpoint for Claude API to extract synonyms from clue text."""
    import requests as req

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'message': 'ANTHROPIC_API_KEY not configured on server'}), 500

    data = request.get_json()
    text = (data or {}).get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'No text provided'}), 400

    prompt = (
        'Extract cryptic crossword wordplay synonyms from this text. '
        'Look for patterns like "WORD (clue word)" where clue word is the synonym for WORD in the crossword. '
        'Return ONLY a JSON array: [{"key":"clue word","val":"crossword code","cat":"CATEGORY"}] '
        'where CATEGORY is one of: CRICKET, WORKERS, LETTERS, NUMBERS, PEOPLE, MUSIC, SPORTS, GEOGRAPHY, TIME, MONEY, MISC. '
        'No markdown, no extra text.\n\n' + text
    )

    try:
        resp = req.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            json={
                'model': 'claude-sonnet-4-6-20250514',
                'max_tokens': 1000,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        raw = ''.join(b.get('text', '') for b in result.get('content', []))
        raw = raw.replace('```json', '').replace('```', '').strip()
        synonyms = json.loads(raw)
        return jsonify({'success': True, 'synonyms': synonyms})
    except req.RequestException as e:
        return jsonify({'success': False, 'message': f'API request failed: {e}'}), 502
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({'success': False, 'message': f'Failed to parse API response: {e}'}), 500


# ============================================================================
# BLOG ADMIN
# ============================================================================

@app.route('/admin/blog')
@login_required
def admin_blog():
    """Admin blog management page"""
    return send_from_directory('static', 'admin-blog.html')


@app.route('/admin/api/blog/posts')
@login_required
def admin_get_blog_posts():
    """Get all blog posts (including drafts) for admin."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT id, slug, title, meta_description, body, status, created_at, published_at
        FROM blog_posts
        ORDER BY created_at DESC
    ''')
    posts = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{
        'id': p['id'],
        'slug': p['slug'],
        'title': p['title'],
        'meta_description': p['meta_description'],
        'body': p['body'],
        'status': p['status'],
        'created_at': p['created_at'].isoformat() if p['created_at'] else None,
        'published_at': p['published_at'].isoformat() if p['published_at'] else None,
    } for p in posts])


@app.route('/admin/api/blog/posts', methods=['POST'])
@login_required
def admin_create_blog_post():
    """Create a new blog post."""
    import re
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    slug = (data.get('slug') or '').strip()
    meta_description = (data.get('meta_description') or '').strip()
    body = (data.get('body') or '').strip()

    if not title or not body:
        return jsonify({'error': 'Title and body are required'}), 400

    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', slug) and len(slug) > 1:
        return jsonify({'error': 'Slug must contain only lowercase letters, numbers, and hyphens'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute('''
            INSERT INTO blog_posts (slug, title, meta_description, body)
            VALUES (%s, %s, %s, %s)
            RETURNING id, slug, title, meta_description, body, status, created_at, published_at
        ''', (slug, title, meta_description, body))
        post = cursor.fetchone()
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({'error': 'A post with that slug already exists'}), 409
    except Exception:
        conn.rollback()
        return jsonify({'error': 'Failed to create post'}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        'id': post['id'],
        'slug': post['slug'],
        'title': post['title'],
        'meta_description': post['meta_description'],
        'body': post['body'],
        'status': post['status'],
        'created_at': post['created_at'].isoformat() if post['created_at'] else None,
        'published_at': post['published_at'].isoformat() if post['published_at'] else None,
    }), 201


@app.route('/admin/api/blog/posts/<int:post_id>', methods=['PUT'])
@login_required
def admin_update_blog_post(post_id):
    """Update an existing blog post."""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    meta_description = (data.get('meta_description') or '').strip()
    body = (data.get('body') or '').strip()

    if not title or not body:
        return jsonify({'error': 'Title and body are required'}), 400

    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        UPDATE blog_posts
        SET title = %s, meta_description = %s, body = %s
        WHERE id = %s
        RETURNING id, slug, title, status
    ''', (title, meta_description, body, post_id))
    post = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()

    if not post:
        return jsonify({'error': 'Post not found'}), 404
    return jsonify({'success': True, 'post': dict(post)})


@app.route('/admin/api/blog/posts/<int:post_id>/publish', methods=['POST'])
@login_required
def admin_publish_blog_post(post_id):
    """Publish a blog post."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        UPDATE blog_posts
        SET status = 'published', published_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING id, slug, title, status, published_at
    ''', (post_id,))
    post = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()

    if not post:
        return jsonify({'error': 'Post not found'}), 404
    return jsonify({'success': True, 'post': dict(post)})


@app.route('/admin/api/blog/posts/<int:post_id>/unpublish', methods=['POST'])
@login_required
def admin_unpublish_blog_post(post_id):
    """Unpublish a blog post (back to draft)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE blog_posts
        SET status = 'draft', published_at = NULL
        WHERE id = %s
    ''', (post_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})


@app.route('/admin/api/blog/posts/<int:post_id>', methods=['DELETE'])
@login_required
def admin_delete_blog_post(post_id):
    """Delete a blog post."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM blog_posts WHERE id = %s', (post_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})


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


# ---------------------------------------------------------------------------
# Auto-import scheduler
# ---------------------------------------------------------------------------

def _discover_latest_puzzle_number(puzzle_type='cryptic'):
    """Fetch the Guardian crosswords series page and find the latest puzzle number."""
    import requests as req
    series = 'quiptic' if puzzle_type == 'quiptic' else 'cryptic'
    url = f'https://www.theguardian.com/crosswords/series/{series}'
    try:
        resp = req.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        resp.raise_for_status()
        # Links look like /crosswords/cryptic/29940
        import re as _re
        pattern = rf'/crosswords/{series}/(\d+)'
        numbers = [int(m) for m in _re.findall(pattern, resp.text)]
        if numbers:
            return str(max(numbers))
    except Exception as e:
        print(f"[auto-import] Failed to discover latest puzzle number: {e}")
    return None


def _auto_import_once(puzzle_type='cryptic'):
    """Run one auto-import cycle. Returns a status message string."""

    # Discover the latest puzzle number from Guardian
    latest_num = _discover_latest_puzzle_number(puzzle_type)
    if not latest_num:
        return "Could not determine latest puzzle number from Guardian"

    # Check if already imported (unique index prevents duplicates even in a race)
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM puzzles WHERE puzzle_number = %s AND puzzle_type = %s",
            (latest_num, puzzle_type),
        )
        existing = cursor.fetchone()
        cursor.close()
        conn.close()
        if existing:
            return f"Puzzle {latest_num} already imported"
    except Exception as e:
        return f"DB check failed: {e}"

    # Check if fifteensquared has the analysis yet
    from puzzle_scraper import FifteensquaredScraper
    fs = FifteensquaredScraper()
    post_url = fs.find_puzzle_post(latest_num, puzzle_type)
    if not post_url:
        return f"Puzzle {latest_num} not on fifteensquared yet"

    # Run the full import
    print(f"[auto-import] Importing puzzle {latest_num}...")
    from puzzle_scraper import PuzzleScraper
    scraper = PuzzleScraper()
    try:
        puzzle_data = scraper.scrape_puzzle(latest_num, puzzle_type)
    except Exception as e:
        return f"Scrape failed: {e}"

    if 'error' in puzzle_data:
        return f"Scrape error: {puzzle_data['error']}"

    # Save to database with auto-approve
    try:
        puzzle_id, clue_count = save_puzzle_to_db(
            puzzle_data, latest_num, puzzle_type, auto_approve=True)
        print(f"[auto-import] Saved {clue_count} clues")
    except psycopg2.errors.UniqueViolation:
        return f"Puzzle {latest_num} already imported (race)"
    except Exception as e:
        return f"DB save failed: {e}"

    # Publish the puzzle
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE puzzles
            SET status = 'published', published_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (puzzle_id,))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[auto-import] Published puzzle {latest_num}")
    except Exception as e:
        return f"Publish failed: {e}"

    # Notify subscribers in background
    setter_name = puzzle_data.get('setter', 'Unknown')
    if SMTP_USER and SMTP_PASSWORD:
        notify_subscribers(latest_num, setter_name, puzzle_type)

    api_usage = puzzle_data.get('api_usage', {})
    cost_str = ''
    if api_usage.get('api_calls', 0) > 0:
        cost_str = f", API cost: ${api_usage['estimated_cost_usd']:.4f}"
    return f"Imported, approved, and published puzzle {latest_num} by {setter_name} ({clue_count} clues{cost_str})"


def _scheduler_loop():
    """Background loop: check hourly 9am-6pm Mon-Fri (UK time)."""
    import time as _time
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
    uk_tz = ZoneInfo('Europe/London')

    while True:
        try:
            now = datetime.now(uk_tz)
            _scheduler_state['next_check'] = None

            # Only Mon(0)-Fri(4), 9am-6pm UK time
            if _scheduler_state['enabled'] and now.weekday() < 5 and 9 <= now.hour < 18:
                _scheduler_state['running'] = True
                _scheduler_state['last_check'] = now.isoformat()
                print(f"\n[auto-import] Running check at {now.strftime('%Y-%m-%d %H:%M')} UK")
                result = _auto_import_once('cryptic')
                _scheduler_state['last_result'] = result
                _scheduler_state['running'] = False
                print(f"[auto-import] Result: {result}")
            else:
                _scheduler_state['running'] = False

            # Sleep until the next hour boundary + 5 minutes
            now2 = datetime.now(uk_tz)
            minutes_to_next = 60 - now2.minute + 5
            _scheduler_state['next_check'] = (
                now2.replace(second=0, microsecond=0)
                + timedelta(minutes=minutes_to_next)
            ).isoformat()
            _time.sleep(minutes_to_next * 60)

        except Exception as e:
            print(f"[auto-import] Scheduler error: {e}")
            _scheduler_state['running'] = False
            _scheduler_state['last_result'] = f"Error: {e}"
            _time.sleep(300)  # Retry in 5 minutes on error


def start_scheduler():
    """Start the auto-import scheduler in a background thread."""
    t = threading.Thread(target=_scheduler_loop, daemon=True, name='auto-import')
    t.start()
    print("[auto-import] Scheduler started (Mon-Fri 9am-6pm UK, hourly)")


@app.route('/admin/api/auto-import/status')
@login_required
def auto_import_status():
    """Get auto-import scheduler status"""
    return jsonify(_scheduler_state)


@app.route('/admin/api/auto-import/toggle', methods=['POST'])
@login_required
def auto_import_toggle():
    """Enable or disable the auto-import scheduler"""
    _scheduler_state['enabled'] = not _scheduler_state['enabled']
    status = 'enabled' if _scheduler_state['enabled'] else 'disabled'
    print(f"[auto-import] Scheduler {status}")
    return jsonify({'success': True, 'enabled': _scheduler_state['enabled']})


@app.route('/admin/api/auto-import/run-now', methods=['POST'])
@login_required
def auto_import_run_now():
    """Trigger an immediate auto-import check"""
    if _scheduler_state['running']:
        return jsonify({'success': False, 'message': 'Import already running'})

    task_id = str(uuid.uuid4())
    _import_tasks[task_id] = {
        'status': 'running',
        'step': 'Running auto-import...',
        '_ts': time.time(),
    }

    def _run():
        try:
            _scheduler_state['running'] = True
            _scheduler_state['last_check'] = datetime.now().isoformat()
            result = _auto_import_once('cryptic')
            _scheduler_state['last_result'] = result
            _scheduler_state['running'] = False

            is_success = result.startswith('Imported')
            _import_tasks[task_id].update({
                'status': 'complete' if is_success else 'error',
                'message': result,
                'success': is_success,
            })
        except Exception as e:
            _scheduler_state['running'] = False
            _import_tasks[task_id].update({
                'status': 'error',
                'message': str(e),
            })

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'success': True, 'task_id': task_id})


# Initialize database when running with gunicorn (production)
# This runs on module import, before any requests
try:
    db_test = get_db()
    db_test.execute("SELECT 1 FROM puzzles LIMIT 1")
    db_test.close()
    print("✓ Database tables exist")
except Exception:
    print("Database tables don't exist, initializing...")
    init_db()
    print("✓ Database initialized successfully!")

# Start the auto-import scheduler (skip during tests)
if not os.environ.get('TESTING'):
    start_scheduler()


if __name__ == '__main__':
    # Initialize database on first run
    try:
        init_db()
    except Exception:
        pass
    
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
