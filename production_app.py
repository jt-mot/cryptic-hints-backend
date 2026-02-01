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
import sqlite3
import json
from datetime import datetime, date
import os
import secrets

app = Flask(__name__, static_folder='static')
app.secret_key = secrets.token_hex(32)  # Generate secure secret key
CORS(app)

DATABASE = 'crosswords.db'
ADMIN_USERNAME = 'admin'  # Change this
ADMIN_PASSWORD_HASH = generate_password_hash('changeme123')  # CHANGE THIS PASSWORD!


def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    """Initialize database with schema"""
    db = get_db()
    
    db.executescript('''
        CREATE TABLE IF NOT EXISTS puzzles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publication TEXT NOT NULL,
            puzzle_number TEXT,
            setter TEXT,
            date DATE NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS clues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            hint_1_approved BOOLEAN DEFAULT 0,
            hint_2_approved BOOLEAN DEFAULT 0,
            hint_3_approved BOOLEAN DEFAULT 0,
            hint_4_approved BOOLEAN DEFAULT 0,
            hint_1_flagged BOOLEAN DEFAULT 0,
            hint_2_flagged BOOLEAN DEFAULT 0,
            hint_3_flagged BOOLEAN DEFAULT 0,
            hint_4_flagged BOOLEAN DEFAULT 0,
            FOREIGN KEY (puzzle_id) REFERENCES puzzles(id)
        );
        
        CREATE TABLE IF NOT EXISTS hint_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clue_id INTEGER NOT NULL,
            hint_level INTEGER NOT NULL,
            old_text TEXT,
            new_text TEXT,
            edited_by TEXT,
            edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clue_id) REFERENCES clues(id)
        );
        
        CREATE TABLE IF NOT EXISTS user_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            clue_id INTEGER NOT NULL,
            hints_viewed INTEGER DEFAULT 0,
            answered BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (clue_id) REFERENCES clues(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_puzzle_date ON puzzles(date);
        CREATE INDEX IF NOT EXISTS idx_puzzle_status ON puzzles(status);
        CREATE INDEX IF NOT EXISTS idx_clue_puzzle ON clues(puzzle_id);
    ''')
    
    db.commit()
    db.close()
    print("✓ Database initialized successfully!")


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
def index():
    """Serve the main page"""
    return send_from_directory('static', 'index.html')


@app.route('/api/puzzle/today')
def get_today_puzzle():
    """Get today's published puzzle"""
    db = get_db()
    
    # Get the most recent published puzzle
    puzzle = db.execute('''
        SELECT * FROM puzzles 
        WHERE status = 'published'
        AND date <= DATE('now')
        ORDER BY date DESC 
        LIMIT 1
    ''').fetchone()
    
    if not puzzle:
        return jsonify({'error': 'No puzzle available'}), 404
    
    # Get all clues for this puzzle
    clues = db.execute('''
        SELECT id, clue_number, direction, clue_text, enumeration
        FROM clues
        WHERE puzzle_id = ?
        ORDER BY 
            CASE WHEN direction = 'across' THEN 0 ELSE 1 END,
            CAST(clue_number AS INTEGER)
    ''', (puzzle['id'],)).fetchall()
    
    db.close()
    
    return jsonify({
        'id': puzzle['id'],
        'publication': puzzle['publication'],
        'puzzle_number': puzzle['puzzle_number'],
        'setter': puzzle['setter'],
        'date': puzzle['date'],
        'clues': [dict(clue) for clue in clues]
    })


@app.route('/api/clue/<int:clue_id>/hint/<int:level>')
def get_hint(clue_id, level):
    """Get a specific hint level for a clue"""
    if level not in [1, 2, 3, 4]:
        return jsonify({'error': 'Invalid hint level'}), 400
    
    db = get_db()
    
    clue = db.execute(f'''
        SELECT hint_level_{level} as hint_text,
               hint_{level}_approved as approved
        FROM clues
        WHERE id = ?
    ''', (clue_id,)).fetchone()
    
    db.close()
    
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
    
    db = get_db()
    
    clue = db.execute('''
        SELECT answer, clue_text
        FROM clues
        WHERE id = ?
    ''', (clue_id,)).fetchone()
    
    db.close()
    
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
                        window.location.href = '/admin/review';
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

@app.route('/admin/review')
@login_required
def admin_review():
    """Admin review interface"""
    return send_from_directory('static', 'admin-review.html')


@app.route('/admin/api/puzzles/pending')
@login_required
def get_pending_puzzles():
    """Get all puzzles awaiting review"""
    db = get_db()
    
    puzzles = db.execute('''
        SELECT p.*, 
               COUNT(DISTINCT c.id) as total_clues,
               SUM(CASE WHEN c.hint_1_flagged OR c.hint_2_flagged OR c.hint_3_flagged OR c.hint_4_flagged THEN 1 ELSE 0 END) as flagged_count,
               SUM(CASE WHEN c.hint_1_approved AND c.hint_2_approved AND c.hint_3_approved AND c.hint_4_approved THEN 1 ELSE 0 END) as approved_count
        FROM puzzles p
        LEFT JOIN clues c ON c.puzzle_id = p.id
        WHERE p.status = 'draft'
        GROUP BY p.id
        ORDER BY p.date DESC
    ''').fetchall()
    
    db.close()
    
    return jsonify({
        'puzzles': [dict(p) for p in puzzles]
    })


@app.route('/admin/api/puzzle/<int:puzzle_id>/clues')
@login_required
def get_puzzle_clues_for_review(puzzle_id):
    """Get all clues for a puzzle with review status"""
    db = get_db()
    
    clues = db.execute('''
        SELECT * FROM clues
        WHERE puzzle_id = ?
        ORDER BY 
            CASE WHEN direction = 'across' THEN 0 ELSE 1 END,
            CAST(clue_number AS INTEGER)
    ''', (puzzle_id,)).fetchall()
    
    db.close()
    
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
    
    db = get_db()
    
    # Get old text for revision history
    old_text = db.execute(f'''
        SELECT hint_level_{hint_level} as old_text
        FROM clues WHERE id = ?
    ''', (clue_id,)).fetchone()['old_text']
    
    # Update hint
    db.execute(f'''
        UPDATE clues 
        SET hint_level_{hint_level} = ?,
            hint_{hint_level}_flagged = 0
        WHERE id = ?
    ''', (new_text, clue_id))
    
    # Save revision
    db.execute('''
        INSERT INTO hint_revisions (clue_id, hint_level, old_text, new_text, edited_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (clue_id, hint_level, old_text, new_text, session.get('username')))
    
    db.commit()
    db.close()
    
    return jsonify({'success': True})


@app.route('/admin/api/hint/approve', methods=['POST'])
@login_required
def approve_hint():
    """Approve a hint"""
    data = request.get_json()
    clue_id = data.get('clue_id')
    hint_level = data.get('hint_level')
    
    db = get_db()
    
    db.execute(f'''
        UPDATE clues 
        SET hint_{hint_level}_approved = 1,
            hint_{hint_level}_flagged = 0
        WHERE id = ?
    ''', (clue_id,))
    
    db.commit()
    db.close()
    
    return jsonify({'success': True})


@app.route('/admin/api/hint/flag', methods=['POST'])
@login_required
def flag_hint():
    """Flag a hint for review"""
    data = request.get_json()
    clue_id = data.get('clue_id')
    hint_level = data.get('hint_level')
    
    db = get_db()
    
    db.execute(f'''
        UPDATE clues 
        SET hint_{hint_level}_flagged = 1,
            hint_{hint_level}_approved = 0
        WHERE id = ?
    ''', (clue_id,))
    
    db.commit()
    db.close()
    
    return jsonify({'success': True})


@app.route('/admin/api/puzzle/<int:puzzle_id>/publish', methods=['POST'])
@login_required
def publish_puzzle(puzzle_id):
    """Publish a puzzle (make it live)"""
    db = get_db()
    
    # Check all hints are approved
    unapproved = db.execute('''
        SELECT COUNT(*) as count FROM clues
        WHERE puzzle_id = ?
        AND (hint_1_approved = 0 OR hint_2_approved = 0 OR hint_3_approved = 0 OR hint_4_approved = 0)
    ''', (puzzle_id,)).fetchone()['count']
    
    if unapproved > 0:
        db.close()
        return jsonify({'success': False, 'message': f'{unapproved} hints still need approval'}), 400
    
    # Publish
    db.execute('''
        UPDATE puzzles 
        SET status = 'published',
            published_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (puzzle_id,))
    
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Puzzle published successfully!'})


@app.route('/admin/api/puzzle/<int:puzzle_id>/unpublish', methods=['POST'])
@login_required
def unpublish_puzzle(puzzle_id):
    """Unpublish a puzzle (take it offline)"""
    db = get_db()
    
    db.execute('''
        UPDATE puzzles 
        SET status = 'draft'
        WHERE id = ?
    ''', (puzzle_id,))
    
    db.commit()
    db.close()
    
    return jsonify({'success': True, 'message': 'Puzzle unpublished'})


# ============================================================================
# IMPORT/SCRAPING ROUTES
# ============================================================================

@app.route('/admin/api/import-puzzle', methods=['POST'])
@login_required
def import_puzzle():
    """Import a puzzle with clues and AI-generated hints"""
    data = request.get_json()
    
    db = get_db()
    
    # Create puzzle
    cursor = db.execute('''
        INSERT INTO puzzles (publication, puzzle_number, setter, date, status)
        VALUES (?, ?, ?, ?, 'draft')
    ''', (
        data['publication'],
        data['puzzle_number'],
        data['setter'],
        data['date']
    ))
    
    puzzle_id = cursor.lastrowid
    
    # Add clues with hints
    for clue_data in data['clues']:
        db.execute('''
            INSERT INTO clues (
                puzzle_id, clue_number, direction, clue_text, 
                enumeration, answer, 
                hint_level_1, hint_level_2, hint_level_3, hint_level_4,
                hint_1_flagged, hint_2_flagged, hint_3_flagged, hint_4_flagged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    
    db.commit()
    db.close()
    
    return jsonify({
        'success': True,
        'puzzle_id': puzzle_id,
        'message': f'Imported puzzle {data["puzzle_number"]} with {len(data["clues"])} clues'
    })


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
