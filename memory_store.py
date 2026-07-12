"""
memory_store.py — Persistent memory for Serinity (Phase 5).

SQLite-backed storage with three layers:
  1. Persisted raw messages (all turns, never lost across restarts)
  2. Working memory (last WORKING_MEMORY_TURNS raw turns in active context)
  3. Long-term patient profile (merged from LLM2Output after each ANALYZE)

PRIVACY NOTE: Conversation data is stored in plaintext SQLite at MEMORY_DB_PATH.
Field-level encryption (e.g. Fernet) is a stretch goal noted in changes.txt §8.5.
If this is deployed outside a personal laptop, encrypt the database or at minimum
the messages and profile_json columns before shipping.

Schema:
  sessions(session_id, patient_id, created_at, last_active_at)
  messages(id, session_id, role, content, created_at)
  patient_profile(patient_id, profile_json, updated_at)
"""

import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

MEMORY_DB_PATH       = os.getenv("MEMORY_DB_PATH",        "./data/serinity.db")
WORKING_MEMORY_TURNS = int(os.getenv("WORKING_MEMORY_TURNS", "20"))

# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(MEMORY_DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                age        INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id      TEXT PRIMARY KEY,
                patient_id      TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rolling_summary TEXT DEFAULT '',
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS patient_profile (
                patient_id   TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL DEFAULT '{}',
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, id);
        """)
    print(f"[MEMORY] SQLite DB ready at {MEMORY_DB_PATH}")


# ---------------------------------------------------------------------------
# Patient profiles CRUD
# ---------------------------------------------------------------------------

def create_patient(name: str, age: Optional[int] = None) -> str:
    """Create a new patient entry and return its patient_id."""
    patient_id = str(uuid.uuid4())
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO patients(patient_id, name, age) VALUES(?,?,?)",
            (patient_id, name, age),
        )
    return patient_id


def list_patients() -> list[dict]:
    """Retrieve all patients sorted by name."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT patient_id, name, age, created_at FROM patients ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_patient(patient_id: str) -> Optional[dict]:
    """Retrieve a single patient by ID."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT patient_id, name, age, created_at FROM patients WHERE patient_id=?",
            (patient_id,),
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def create_session(patient_id: Optional[str] = None) -> str:
    """Create a new session row and return the new session_id."""
    session_id = str(uuid.uuid4())
    if patient_id is None:
        patient_id = str(uuid.uuid4())  # anonymous local patient ID
    
    # Ensure patient actually exists in the patients table
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM patients WHERE patient_id=?", (patient_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO patients(patient_id, name, age) VALUES(?,?,?)",
                (patient_id, "Guest Patient", None),
            )
            
    now = _now()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions(session_id, patient_id, created_at, last_active_at) VALUES(?,?,?,?)",
            (session_id, patient_id, now, now),
        )
    return session_id


def get_patient_id(session_id: str) -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT patient_id FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    return row["patient_id"] if row else None


def touch_session(session_id: str):
    """Update last_active_at timestamp."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET last_active_at=? WHERE session_id=?",
            (_now(), session_id),
        )


def session_exists(session_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    return row is not None


def get_patient_sessions(patient_id: str) -> list[dict]:
    """Retrieve all sessions for a specific patient, ordered by creation date."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT session_id, created_at, last_active_at, rolling_summary FROM sessions WHERE patient_id=? ORDER BY created_at DESC",
            (patient_id,)
        ).fetchall()
    return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------

def append_message(session_id: str, role: str, content: str):
    """Save a single message turn to the DB."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
            (session_id, role, content, _now()),
        )
    touch_session(session_id)


def get_all_messages(session_id: str) -> list[dict]:
    """Return all messages for a session ordered by insertion."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ---------------------------------------------------------------------------
# Working memory — last N turns + optional rolling summary prefix
# ---------------------------------------------------------------------------

def get_working_context(session_id: str, llm_engine=None) -> list[dict]:
    """
    Return the active context to pass to LLM1:
      - If total turns <= WORKING_MEMORY_TURNS: return all raw turns.
      - If total turns > WORKING_MEMORY_TURNS: return rolling_summary as a
        synthetic 'system' message + the last WORKING_MEMORY_TURNS raw turns.
        If no summary exists yet, generate one with LLM1 and persist it.

    Args:
        session_id:  The current session.
        llm_engine:  The LLMEngine instance (needed for summarization). Pass
                     None to skip summarization (returns raw tail only).
    """
    all_msgs = get_all_messages(session_id)
    if len(all_msgs) <= WORKING_MEMORY_TURNS:
        return all_msgs

    overflow = all_msgs[:-WORKING_MEMORY_TURNS]
    tail     = all_msgs[-WORKING_MEMORY_TURNS:]

    # Get or generate rolling summary
    summary = _get_rolling_summary(session_id)
    if not summary and llm_engine is not None:
        summary = llm_engine.summarize_history(overflow)
        _set_rolling_summary(session_id, summary)

    context = []
    if summary:
        context.append({
            "role": "system",
            "content": f"[Earlier session summary — do not quote back to patient]: {summary}",
        })
    context.extend(tail)
    return context


def _get_rolling_summary(session_id: str) -> str:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT rolling_summary FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    return (row["rolling_summary"] or "") if row else ""


def _set_rolling_summary(session_id: str, summary: str):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET rolling_summary=? WHERE session_id=?",
            (summary, session_id),
        )


# ---------------------------------------------------------------------------
# Patient profile — long-term memory
# ---------------------------------------------------------------------------

def get_patient_profile(patient_id: str) -> dict:
    """Return the stored profile dict, or {} if none exists yet."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT profile_json FROM patient_profile WHERE patient_id=?",
            (patient_id,),
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["profile_json"])
    except Exception:
        return {}


def update_patient_profile(patient_id: str, llm2_output):
    """
    Merge a new LLM2Output into the stored patient profile.
    Strategy:
      - List fields (emotional_themes, thinking_patterns, etc.): append new
        items, deduplicate at string level (simple but cheap).
      - risk_assessment: replace with the latest value (don't accumulate old ones).
      - protective_factors: same merge+dedupe as list fields.
    """
    profile = get_patient_profile(patient_id)

    LIST_FIELDS = [
        "emotional_themes",
        "thinking_patterns",
        "behavioral_patterns",
        "interpersonal_dynamics",
        "stressors",
        "unclear_areas",
        "protective_factors",
    ]

    for field in LIST_FIELDS:
        existing = profile.get(field, [])
        new_items = getattr(llm2_output, field, [])
        # Simple string-level dedupe: normalize to lowercase for comparison
        existing_lower = {x.lower() for x in existing}
        for item in new_items:
            if item.lower() not in existing_lower:
                existing.append(item)
                existing_lower.add(item.lower())
        profile[field] = existing

    # Always replace risk_assessment with the latest
    profile["risk_assessment"] = getattr(llm2_output, "risk_assessment", "Not yet assessed")
    profile["last_analyzed"]   = _now()

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO patient_profile(patient_id, profile_json, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(patient_id) DO UPDATE SET
                profile_json=excluded.profile_json,
                updated_at=excluded.updated_at
            """,
            (patient_id, json.dumps(profile), _now()),
        )


def build_profile_recap(patient_id: str) -> Optional[str]:
    """
    Build a short text recap of the patient profile for LLM1's opening context.
    Returns None if no profile exists (first-ever session).
    """
    profile = get_patient_profile(patient_id)
    if not profile:
        return None

    lines = ["[Returning patient — prior session context (not to be quoted back verbatim)]:"]

    recap = profile.get("last_session_summary")
    if recap:
        lines.append(f"Last session summary: {recap}")
    if profile.get("emotional_themes"):
        lines.append(f"Emotional themes: {'; '.join(profile['emotional_themes'][:4])}")
    if profile.get("stressors"):
        lines.append(f"Key stressors: {'; '.join(profile['stressors'][:4])}")
    if profile.get("risk_assessment") and profile["risk_assessment"] != "Not yet assessed":
        lines.append(f"Last risk status: {profile['risk_assessment'][:120]}")
    if profile.get("protective_factors"):
        lines.append(f"Protective factors: {'; '.join(profile['protective_factors'][:3])}")
    if profile.get("last_analyzed"):
        lines.append(f"Last analyzed: {profile['last_analyzed']}")

    return "\n".join(lines)


def save_session_summary(patient_id: str, summary: str):
    """
    Persist the end-of-session summary into the patient profile so LLM1
    can use it as warm-start context next session.
    """
    profile = get_patient_profile(patient_id)
    profile["last_session_summary"] = summary
    profile["last_session_at"] = _now()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO patient_profile(patient_id, profile_json, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(patient_id) DO UPDATE SET
                profile_json=excluded.profile_json,
                updated_at=excluded.updated_at
            """,
            (patient_id, json.dumps(profile), _now()),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Initialize DB on import
init_db()
