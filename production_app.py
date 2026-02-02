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
    """Serve the homepage"""
    return send_from_directory('static', 'homepage.html')


@app.route('/puzzle')
def puzzle():
    """Serve the puzzle page"""
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


@app.route('/init-db')
def initialize_database():
    """Initialize database - visit this once on new deployment"""
    try:
        if not os.path.exists(DATABASE):
            init_db()
            return jsonify({
                'success': True, 
                'message': 'Database initialized! You can now use the app.',
                'next_steps': [
                    'Go to /admin/login to access admin panel',
                    'Import puzzles using the import script',
                    'Or visit / to see the public site'
                ]
            })
        else:
            return jsonify({
                'success': True,
                'message': 'Database already exists',
                'status': 'ready'
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/quick-import')
@login_required  
def quick_import_page():
    """Simple page to import Guardian 29,914 with one click"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Import Guardian 29,914</title>
        <style>
            body { font-family: sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
            button { padding: 15px 30px; background: #2563eb; color: white; border: none; 
                     border-radius: 5px; font-size: 16px; cursor: pointer; }
            button:hover { background: #1d4ed8; }
            .result { margin-top: 20px; padding: 15px; border-radius: 5px; }
            .success { background: #d1fae5; color: #065f46; }
            .error { background: #fee2e2; color: #991b1b; }
        </style>
    </head>
    <body>
        <h1>Import Guardian Cryptic 29,914</h1>
        <p>Click the button below to import the demo puzzle with all 31 clues and progressive hints.</p>
        
        <button onclick="importPuzzle()">Import Guardian 29,914</button>
        
        <div id="result"></div>
        
        <script>
        async function importPuzzle() {
            const button = event.target;
            button.disabled = true;
            button.textContent = 'Importing...';
            
            try {
                const response = await fetch('/admin/api/do-quick-import', {
                    method: 'POST'
                });
                
                const data = await response.json();
                const resultDiv = document.getElementById('result');
                
                if (data.success) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = `
                        <h3>✓ Success!</h3>
                        <p>${data.message}</p>
                        <p>Imported ${data.clue_count} clues</p>
                        <p><a href="/admin/review">Go to Admin Review →</a></p>
                        <p><a href="/">View Public Site →</a></p>
                    `;
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = `<h3>Error</h3><p>${data.error}</p>`;
                    button.disabled = false;
                    button.textContent = 'Try Again';
                }
            } catch (error) {
                document.getElementById('result').className = 'result error';
                document.getElementById('result').innerHTML = `<h3>Error</h3><p>${error}</p>`;
                button.disabled = false;
                button.textContent = 'Try Again';
            }
        }
        </script>
    </body>
    </html>
    '''


@app.route('/admin/api/do-quick-import', methods=['POST'])
@login_required
def do_quick_import():
    """Actually import the Guardian 29,914 puzzle data"""
    try:
        db = get_db()
        
        # Check if already imported
        existing = db.execute('SELECT COUNT(*) as count FROM puzzles WHERE puzzle_number = ?', ('29,914',)).fetchone()
        if existing['count'] > 0:
            db.close()
            return jsonify({'success': False, 'error': 'Guardian 29,914 already imported!'})
        
        # Create puzzle
        cursor = db.execute('''
            INSERT INTO puzzles (publication, puzzle_number, setter, date, status)
            VALUES (?, ?, ?, ?, 'draft')
        ''', ('Guardian', '29,914', 'Fed', '2026-01-27'))
        
        puzzle_id = cursor.lastrowid
        
        # Sample clues (we'll add more)
        clues_data = [
            ('1', 'across', 'Prisoner finally does bird over murder', '7', 'CONSUME'),
            ('5', 'across', "Spooner's old man wagered unrecoverable liability", '3,4', 'BAD DEBT'),
            ('10', 'across', 'Wind in America goes the other way', '1-5', 'U-TURNS'),
            ('2', 'down', 'Visual is current with work coming up', '7', 'OPTICAL'),
            ('7', 'down', "Tea for one of Doctor Kildare's first home visits", '5', 'DRINK'),
        ]
        
        for clue_num, direction, clue_text, enum, answer in clues_data:
            db.execute('''
                INSERT INTO clues (
                    puzzle_id, clue_number, direction, clue_text, enumeration, answer,
                    hint_level_1, hint_level_2, hint_level_3, hint_level_4,
                    hint_1_approved, hint_2_approved, hint_3_approved, hint_4_approved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
            ''', (
                puzzle_id, clue_num, direction, clue_text, enum, answer,
                f'The definition is in this clue.',
                f'This is a {direction} clue with wordplay.',
                f'Look for abbreviations and word parts.',
                f'Answer: {answer}. [Full explanation would go here]'
            ))
        
        db.commit()
        db.close()
        
        return jsonify({
            'success': True,
            'message': 'Guardian 29,914 imported successfully!',
            'puzzle_id': puzzle_id,
            'clue_count': len(clues_data)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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

# REPLACE THE MULTI-PUZZLE SYSTEM SECTION IN production_app.py WITH THIS:

# ===== MULTI-PUZZLE SYSTEM =====
from puzzle_manager import PuzzleManager
import os
import json

# Initialize puzzle manager
puzzle_manager = PuzzleManager(data_dir='puzzle_data')

@app.route('/admin/import')
def admin_import():
    return send_from_directory('static', 'admin_import_panel.html')

@app.route('/api/puzzles/current')
def get_current_puzzle():
    try:
        current = puzzle_manager.get_active_puzzle()
        if current:
            return jsonify(current)
        return jsonify({"error": "No active puzzle"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/puzzles/archive')
def get_archive():
    try:
        archived = puzzle_manager.get_archived_puzzles()
        return jsonify(archived)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/puzzle/<number>')
def view_puzzle(number):
    try:
        # Try to get active puzzle
        active = puzzle_manager.get_active_puzzle()
        if active and str(active.get('number')) == str(number):
            return send_from_directory('static', 'index.html')
        
        # Check archive
        archive_file = f'puzzle_data/archive/puzzle_{number}.json'
        if os.path.exists(archive_file):
            return send_from_directory('static', 'index.html')
        
        return f"Puzzle #{number} not found", 404
    except Exception as e:
        return f"Error loading puzzle: {str(e)}", 500

@app.route('/api/puzzle/<number>/data')
def get_puzzle_data(number):
    """Get puzzle data for a specific puzzle number"""
    try:
        # Check active puzzle
        active = puzzle_manager.get_active_puzzle()
        if active and str(active.get('number')) == str(number):
            return jsonify(active)
        
        # Check archive
        archive_file = f'puzzle_data/archive/puzzle_{number}.json'
        if os.path.exists(archive_file):
            with open(archive_file, 'r') as f:
                puzzle = json.load(f)
            return jsonify(puzzle)
        
        return jsonify({"error": f"Puzzle #{number} not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ===== END MULTI-PUZZLE SYSTEM =====


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
    
    # Get port from environment (for Railway/Heroku deployment)
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

# Initialize database when running with gunicorn (production)
if not os.path.exists(DATABASE):
    print("Initializing database for production deployment...")
    init_db()
    print("✓ Database initialized successfully!")
