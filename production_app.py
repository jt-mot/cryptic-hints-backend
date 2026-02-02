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

from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, date
import os
import secrets

app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(32)  # Generate secure secret key
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/crosswords_dev')
ADMIN_USERNAME = 'admin'  # Change this
ADMIN_PASSWORD_HASH = generate_password_hash('changeme123')  # CHANGE THIS PASSWORD!


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
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_puzzle_date ON puzzles(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_puzzle_status ON puzzles(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_clue_puzzle ON clues(puzzle_id)')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✓ PostgreSQL database initialized successfully!")


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

@app.route('/')
def homepage():
    """Serve the homepage with puzzle list"""
    return send_from_directory('static', 'home.html')


@app.route('/puzzle/<puzzle_number>')
def puzzle_page(puzzle_number):
    """Serve the puzzle solving page"""
    return send_from_directory('static', 'puzzle.html')


@app.route('/api/puzzle/today')
def get_today_puzzle():
    """Get today's published puzzle"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get the most recent published puzzle
    cursor.execute('''
        SELECT * FROM puzzles 
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
        SELECT * FROM puzzles 
        WHERE puzzle_number = %s
        AND status = 'published'
        LIMIT 1
    ''', (puzzle_number,))
    puzzle = cursor.fetchone()
    
    if not puzzle:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Puzzle not found'}), 404
    
    # Get clues
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
        'date': str(puzzle['date']),
        'clues': [dict(clue) for clue in clues]
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


@app.route('/admin/quick-import')
@login_required  
def admin_quick_import():
    """Quick import page for puzzle JSON"""
    return send_from_directory('static', 'quick-import.html')


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
    ''', (puzzle_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Puzzle published successfully!'})


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
