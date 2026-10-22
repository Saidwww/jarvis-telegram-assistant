import sqlite3
import datetime
from config import DATABASE_PATH

def get_connection():
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_PATH)
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if tables do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Create habits table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        );
        """)
        
        # Create habit_logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            habit_id INTEGER NOT NULL,
            date TEXT NOT NULL, -- Format: YYYY-MM-DD
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE,
            UNIQUE(user_id, habit_id, date)
        );
        """)
        
        # Create sleep_logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sleep_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL, -- Format: YYYY-MM-DD
            hours REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        );
        """)
        
        # Create conversation_history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL, -- 'user' or 'assistant'
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()

# --- Habits functions ---

def add_habit(user_id, name):
    """Adds a new habit to track. Returns True if added, False if duplicate."""
    name = name.strip()
    if not name:
        return False
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO habits (user_id, name) VALUES (?, ?);",
                (user_id, name)
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def delete_habit(user_id, name):
    """Deletes a habit and all associated logs. Returns True if deleted."""
    name = name.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM habits WHERE user_id = ? AND name = ?;",
            (user_id, name)
        )
        conn.commit()
        return cursor.rowcount > 0

def get_habits(user_id):
    """Retrieves all active habits for a user."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM habits WHERE user_id = ? ORDER BY name ASC;",
            (user_id,)
        )
        return [row["name"] for row in cursor.fetchall()]

def log_habit(user_id, name, date_str=None):
    """Logs completion of a habit on a specific date (default today YYYY-MM-DD)."""
    if not date_str:
        date_str = datetime.date.today().isoformat()
    
    name = name.strip()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            # Find the habit id
            cursor.execute(
                "SELECT id FROM habits WHERE user_id = ? AND name = ?;",
                (user_id, name)
            )
            row = cursor.fetchone()
            if not row:
                return False  # Habit does not exist
            
            habit_id = row["id"]
            cursor.execute(
                "INSERT INTO habit_logs (user_id, habit_id, date) VALUES (?, ?, ?);",
                (user_id, habit_id, date_str)
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False  # Already logged for this date

def unlog_habit(user_id, name, date_str=None):
    """Removes a habit log for a specific date (default today YYYY-MM-DD)."""
    if not date_str:
        date_str = datetime.date.today().isoformat()
    
    name = name.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM habit_logs 
            WHERE user_id = ? AND date = ? AND habit_id = (
                SELECT id FROM habits WHERE user_id = ? AND name = ?
            );
            """,
            (user_id, date_str, user_id, name)
        )
        conn.commit()
        return cursor.rowcount > 0

def get_habit_logs_for_date(user_id, date_str=None):
    """Retrieves all habits completed on a specific date."""
    if not date_str:
        date_str = datetime.date.today().isoformat()
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT h.name FROM habit_logs hl
            JOIN habits h ON hl.habit_id = h.id
            WHERE hl.user_id = ? AND hl.date = ?;
            """,
            (user_id, date_str)
        )
        return [row["name"] for row in cursor.fetchall()]

# --- Sleep functions ---

def log_sleep(user_id, hours, date_str=None):
    """Logs sleep hours for a specific date (default today YYYY-MM-DD). Updates if exists."""
    if not date_str:
        date_str = datetime.date.today().isoformat()
    
    # Validation
    try:
        hours = float(hours)
        if hours < 0 or hours > 24:
            return False
    except ValueError:
        return False
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sleep_logs (user_id, date, hours) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) 
            DO UPDATE SET hours = excluded.hours;
            """,
            (user_id, date_str, hours)
        )
        conn.commit()
        return True

def get_sleep_for_date(user_id, date_str=None):
    """Retrieves sleep hours for a specific date."""
    if not date_str:
        date_str = datetime.date.today().isoformat()
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hours FROM sleep_logs WHERE user_id = ? AND date = ?;",
            (user_id, date_str)
        )
        row = cursor.fetchone()
        return row["hours"] if row else None

# --- Chat history functions ---

def save_chat_message(user_id, role, content):
    """Saves a user or assistant message to the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversation_history (user_id, role, content) VALUES (?, ?, ?);",
            (user_id, role, content)
        )
        conn.commit()

def get_chat_history(user_id, limit=20):
    """Retrieves the last N messages for context."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content FROM conversation_history 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?;
            """,
            (user_id, limit)
        )
        # We fetch in descending order of time, so reverse it to keep chronological order
        rows = cursor.fetchall()
        messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return messages

def clear_chat_history(user_id):
    """Clears all conversation history for the user."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM conversation_history WHERE user_id = ?;",
            (user_id,)
        )
        conn.commit()

# --- Statistical reporting data queries ---

def get_habit_stats(user_id, start_date, end_date):
    """Retrieves habit completion counts between start_date and end_date (inclusive)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT h.name, COUNT(hl.id) as completion_count
            FROM habits h
            LEFT JOIN habit_logs hl ON h.id = hl.habit_id AND hl.date BETWEEN ? AND ?
            WHERE h.user_id = ?
            GROUP BY h.name;
            """,
            (start_date, end_date, user_id)
        )
        return {row["name"]: row["completion_count"] for row in cursor.fetchall()}

def get_sleep_stats(user_id, start_date, end_date):
    """Retrieves date-to-hours dictionary for sleep between start_date and end_date (inclusive)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, hours 
            FROM sleep_logs 
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC;
            """,
            (user_id, start_date, end_date)
        )
        return {row["date"]: row["hours"] for row in cursor.fetchall()}
