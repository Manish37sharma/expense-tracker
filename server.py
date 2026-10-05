from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, os, datetime, hashlib, jwt



app = Flask(__name__, static_folder='Frontend', static_url_path='')
CORS(app)

@app.route('/')
def home():
    return send_from_directory(FRONTEND_DIR, 'login.html')
    
DB_PATH = os.path.join(os.path.dirname(__file__), 'Database', 'expenses.db')
SECRET  = 'expense_tracker_secret'

def get_db():
    os.makedirs(DATABASE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL,
                email    TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER REFERENCES users(id),
                title    TEXT NOT NULL,
                amount   REAL NOT NULL,
                category TEXT NOT NULL,
                type     TEXT NOT NULL,
                date     TEXT NOT NULL,
                note     TEXT
            );
        ''')
        # migrate old db that has no user_id column
        cols = [r[1] for r in conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if 'user_id' not in cols:
            conn.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER")

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def make_token(user_id, name):
    payload = {
        'id':   user_id,
        'name': name,
        'exp':  datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET, algorithm='HS256')

def get_user():
    auth  = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '')
    try:
        return jwt.decode(token, SECRET, algorithms=['HS256'])
    except:
        return None

# ── Auth ──────────────────────────────────────────────────────
@app.route('/')
def home():
    return send_from_directory('Frontend', 'login.html')
    
@app.route('/register', methods=['POST'])
def register():
    d = request.get_json()
    if not d.get('name') or not d.get('email') or not d.get('password'):
        return jsonify({'error': 'All fields required'}), 400
    try:
        with get_db() as conn:
            cur = conn.execute(
                'INSERT INTO users (name, email, password) VALUES (?,?,?)',
                (d['name'], d['email'], hash_pw(d['password']))
            )
        token = make_token(cur.lastrowid, d['name'])
        return jsonify({'token': token, 'name': d['name']})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Email already registered'}), 400

@app.route('/login', methods=['POST'])
def login():
    d = request.get_json()
    with get_db() as conn:
        user = conn.execute(
            'SELECT * FROM users WHERE email=? AND password=?',
            (d.get('email',''), hash_pw(d.get('password','')))
        ).fetchone()
    if not user:
        return jsonify({'error': 'Invalid email or password'}), 401
    return jsonify({'token': make_token(user['id'], user['name']), 'name': user['name']})

# ── Expenses ──────────────────────────────────────────────────
@app.route('/expenses', methods=['GET'])
def get_expenses():
    user = get_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    month = request.args.get('month', '')
    with get_db() as conn:
        if month:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE user_id=? AND date LIKE ? ORDER BY date DESC",
                (user['id'], f'{month}%')
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE user_id=? ORDER BY date DESC",
                (user['id'],)
            ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/expenses', methods=['POST'])
def add_expense():
    user = get_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    d = request.get_json()
    with get_db() as conn:
        conn.execute(
            'INSERT INTO expenses (user_id,title,amount,category,type,date,note) VALUES (?,?,?,?,?,?,?)',
            (user['id'], d['title'], d['amount'], d['category'], d['type'], d['date'], d.get('note',''))
        )
    return jsonify({'message': 'Added'})

@app.route('/expenses/<int:eid>', methods=['DELETE'])
def delete_expense(eid):
    user = get_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    with get_db() as conn:
        conn.execute('DELETE FROM expenses WHERE id=? AND user_id=?', (eid, user['id']))
    return jsonify({'message': 'Deleted'})

@app.route('/summary', methods=['GET'])
def summary():
    user = get_user()
    if not user: return jsonify({'error': 'Unauthorized'}), 401
    month = request.args.get('month', datetime.date.today().strftime('%Y-%m'))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id=? AND date LIKE ?",
            (user['id'], f'{month}%')
        ).fetchall()
    data    = [dict(r) for r in rows]
    income  = sum(r['amount'] for r in data if r['type'] == 'income')
    expense = sum(r['amount'] for r in data if r['type'] == 'expense')
    by_cat  = {}
    for r in data:
        if r['type'] == 'expense':
            by_cat[r['category']] = by_cat.get(r['category'], 0) + r['amount']
    return jsonify({'income': income, 'expense': expense,
                    'balance': income - expense, 'by_category': by_cat})

if __name__ == '__main__':
    init_db()
    if __name__ == '__main__':
            app.run(debug=True, port=5000)
