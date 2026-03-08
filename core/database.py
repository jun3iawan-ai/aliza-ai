import psycopg2
from psycopg2.extras import RealDictCursor

# =========================
# CONNECT POSTGRESQL
# =========================

conn = psycopg2.connect(
    host="localhost",
    database="aliza",
    user="aliza_user",
    password="Junjun!99!"
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

# =========================
# USERS TABLE
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# =========================
# CHAT HISTORY
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS chats (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    channel TEXT DEFAULT 'web',
    message TEXT,
    response TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

# =========================
# USAGE TRACKING
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS usage (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    tokens INTEGER,
    endpoint TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

# =========================
# DOCUMENTS (RAG FILES)
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    filename TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

# =========================
# COMMIT
# =========================

conn.commit()