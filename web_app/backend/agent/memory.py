import os
import sqlite3
import json
import time
import uuid
from typing import Dict, Any, List, Optional

# Check if Firestore is available and enabled
USE_FIRESTORE = os.getenv("USE_FIRESTORE", "true").lower() in ("true", "1", "yes")
firestore_db = None

if USE_FIRESTORE:
    try:
        from google.cloud import firestore
        project_id = os.getenv("PROJECT_ID", "it-ai-briggs-agentspace")
        database_id = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
        firestore_db = firestore.Client(project=project_id, database=database_id)
        print(f"[MEMORY] Initialized Google Cloud Firestore (Project: {project_id}, Database: {database_id})")
    except Exception as e:
        print(f"[MEMORY WARNING] Could not initialize Firestore ({e}). Falling back to SQLite.")
        firestore_db = None

# SQLite Fallback Configuration
DB_DIR = os.getenv("SESSIONS_DB_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "sessions.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """)
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

init_db()

# --- PUBLIC MEMORY API ---

def get_user_sessions(user_id: str) -> List[Dict[str, Any]]:
    """Fetches all chat sessions for a specific user ID."""
    if firestore_db:
        try:
            docs = firestore_db.collection("user_sessions")\
                .where("user_id", "==", user_id)\
                .stream()
            
            sessions = []
            for doc in docs:
                data = doc.to_dict()
                sessions.append({
                    "session_id": doc.id,
                    "title": data.get("title", "Audit Thread"),
                    "created_at": data.get("created_at", 0),
                    "updated_at": data.get("updated_at", 0)
                })
            # Sort by updated_at descending
            sessions.sort(key=lambda x: x["updated_at"], reverse=True)
            return sessions
        except Exception as e:
            print(f"[MEMORY FIRESTORE ERROR] get_user_sessions: {e}")

    # SQLite Fallback
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT session_id, title, created_at, updated_at FROM user_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"session_id": r["session_id"], "title": r["title"], "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]

def create_user_session(user_id: str, title: str = "New Audit Thread") -> Dict[str, Any]:
    """Creates a new user chat session."""
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    now = time.time()
    
    if firestore_db:
        try:
            doc_ref = firestore_db.collection("user_sessions").document(session_id)
            doc_ref.set({
                "user_id": user_id,
                "title": title,
                "created_at": now,
                "updated_at": now
            })
            return {
                "session_id": session_id,
                "user_id": user_id,
                "title": title,
                "created_at": now,
                "updated_at": now
            }
        except Exception as e:
            print(f"[MEMORY FIRESTORE ERROR] create_user_session: {e}")

    # SQLite Fallback
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_sessions (session_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, title, now, now)
    )
    conn.commit()
    conn.close()
    return {"session_id": session_id, "user_id": user_id, "title": title, "created_at": now, "updated_at": now}

def get_session_messages(user_id: str, session_id: str) -> List[Dict[str, Any]]:
    """Fetches all messages in a chat thread."""
    if firestore_db:
        try:
            msg_docs = firestore_db.collection("user_sessions")\
                .document(session_id)\
                .collection("messages")\
                .stream()
            
            messages = []
            for doc in msg_docs:
                data = doc.to_dict()
                messages.append({
                    "role": data.get("role", "user"),
                    "content": data.get("content", ""),
                    "trajectory": data.get("trajectory", []),
                    "created_at": data.get("created_at", 0)
                })
            messages.sort(key=lambda x: x["created_at"])
            return messages
        except Exception as e:
            print(f"[MEMORY FIRESTORE ERROR] get_session_messages: {e}")

    # SQLite Fallback
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
    """Appends a user or assistant message to a session thread."""
    now = time.time()
    
    if firestore_db:
        try:
            session_ref = firestore_db.collection("user_sessions").document(session_id)
            session_snap = session_ref.get()
            
            if not session_snap.exists:
                session_ref.set({
                    "user_id": user_id,
                    "title": f"Audit {content[:20]}...",
                    "created_at": now,
                    "updated_at": now
                })
            else:
                session_ref.update({"updated_at": now})

            # Add message to subcollection
            msg_ref = session_ref.collection("messages").document()
            msg_ref.set({
                "user_id": user_id,
                "role": role,
                "content": content,
                "trajectory": trajectory or [],
                "created_at": now
            })
            return
        except Exception as e:
            print(f"[MEMORY FIRESTORE ERROR] add_session_message: {e}")

    # SQLite Fallback
    traj_str = json.dumps(trajectory) if trajectory else None
    conn = get_db()
    cursor = conn.cursor()
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
    """Deletes a chat session and its subcollection messages."""
    if firestore_db:
        try:
            session_ref = firestore_db.collection("user_sessions").document(session_id)
            # Delete messages subcollection docs
            msg_docs = session_ref.collection("messages").stream()
            for doc in msg_docs:
                doc.reference.delete()
            session_ref.delete()
            return
        except Exception as e:
            print(f"[MEMORY FIRESTORE ERROR] delete_user_session: {e}")

    # SQLite Fallback
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM session_messages WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    cursor.execute("DELETE FROM user_sessions WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    conn.commit()
    conn.close()
