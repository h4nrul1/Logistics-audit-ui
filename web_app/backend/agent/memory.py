import os
import sqlite3
import json
import time
import uuid
from typing import Dict, Any, List, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "sessions.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """)
    
    # Messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS session_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        trajectory TEXT,
        created_at REAL NOT NULL,
        FOREIGN KEY (session_id) REFERENCES user_sessions(session_id) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    conn.close()

# Initialize DB on module load
init_db()

def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT session_id, title, created_at, updated_at FROM user_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    sessions = []
    for r in rows:
        sessions.append({
            "session_id": r["session_id"],
            "title": r["title"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        })
    return sessions

def create_user_session(user_id: str, title: str = "New Audit Thread") -> Dict[str, Any]:
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    now = time.time()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_sessions (session_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, title, now, now)
    )
    conn.commit()
    conn.close()
    
    return {
        "session_id": session_id,
        "user_id": user_id,
        "title": title,
        "created_at": now,
        "updated_at": now
    }

def get_session_messages(user_id: str, session_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, trajectory, created_at FROM session_messages WHERE user_id = ? AND session_id = ? ORDER BY id ASC",
        (user_id, session_id)
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for r in rows:
        trajectory = []
        if r["trajectory"]:
            try:
                trajectory = json.loads(r["trajectory"])
            except Exception:
                trajectory = []
        messages.append({
            "role": r["role"],
            "content": r["content"],
            "trajectory": trajectory,
            "created_at": r["created_at"]
        })
    return messages

def add_session_message(user_id: str, session_id: str, role: str, content: str, trajectory: Optional[List[Dict[str, Any]]] = None) -> None:
    now = time.time()
    traj_str = json.dumps(trajectory) if trajectory else None
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Ensure session exists
    cursor.execute("SELECT session_id FROM user_sessions WHERE session_id = ?", (session_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO user_sessions (session_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, f"Audit {content[:20]}...", now, now)
        )
        
    cursor.execute(
        "INSERT INTO session_messages (session_id, user_id, role, content, trajectory, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, role, content, traj_str, now)
    )
    cursor.execute(
        "UPDATE user_sessions SET updated_at = ? WHERE session_id = ?",
        (now, session_id)
    )
    conn.commit()
    conn.close()

def delete_user_session(user_id: str, session_id: str) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM session_messages WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    cursor.execute("DELETE FROM user_sessions WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    conn.commit()
    conn.close()
