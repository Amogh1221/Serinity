import os
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Any
from core.ports import LLM2Output, LLMProvider

class SQLiteBaseStore:
    """Base class for SQLite stores providing connection and initialization."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """
        Yields a short-lived SQLite connection wrapped in a transaction block.
        Ensures the connection is properly closed to prevent file descriptor/memory leaks.
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            # The inner 'with conn:' handles committing or rolling back the transaction
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS patients (
                    patient_id      TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    age             INTEGER,
                    gender          TEXT,
                    occupation      TEXT,
                    primary_concern TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id      TEXT PRIMARY KEY,
                    patient_id      TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active       INTEGER DEFAULT 1,
                    rolling_summary TEXT DEFAULT '',
                    summarized_msg_count INTEGER DEFAULT 0,
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
                    long_term_memory_json TEXT NOT NULL DEFAULT '{}',
                    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, id);
            """)

            # Safe migrations
            try:
                conn.execute("ALTER TABLE patients ADD COLUMN gender TEXT")
                conn.execute("ALTER TABLE patients ADD COLUMN occupation TEXT")
                conn.execute("ALTER TABLE patients ADD COLUMN primary_concern TEXT")
            except sqlite3.OperationalError:
                pass 
                
            try:
                conn.execute("ALTER TABLE patient_profile ADD COLUMN long_term_memory_json TEXT NOT NULL DEFAULT '{}'")
            except sqlite3.OperationalError:
                pass 
                
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN summarized_msg_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass 
                
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN is_active INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass 

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class SQLiteProfileStore(SQLiteBaseStore):
    """Concrete implementation of ProfileStore using SQLite."""

    def create_patient(
        self, 
        name: str, 
        age: Optional[int] = None, 
        gender: Optional[str] = None, 
        occupation: Optional[str] = None, 
        primary_concern: Optional[str] = None
    ) -> str:
        patient_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO patients(patient_id, name, age, gender, occupation, primary_concern) VALUES(?,?,?,?,?,?)",
                (patient_id, name, age, gender, occupation, primary_concern),
            )
        return patient_id

    def list_patients(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT patient_id, name, age, gender, occupation, primary_concern, created_at FROM patients ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_patient(self, patient_id: str) -> dict:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT patient_id, name, age, gender, occupation, primary_concern, created_at FROM patients WHERE patient_id=?",
                (patient_id,),
            ).fetchone()
        return dict(row) if row else {}

    def get_patient_profile(self, patient_id: str) -> dict:
        with self._get_conn() as conn:
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

    def get_long_term_memory(self, patient_id: str) -> dict:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT long_term_memory_json FROM patient_profile WHERE patient_id=?",
                (patient_id,),
            ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["long_term_memory_json"])
        except Exception:
            return {}

    def update_long_term_memory(self, patient_id: str, llm_output: Any) -> None:
        memory = self.get_long_term_memory(patient_id)
        list_fields = [
            "emotional_themes", "thinking_patterns", "behavioral_patterns", 
            "interpersonal_dynamics", "stressors", "unclear_areas", "protective_factors"
        ]

        for field in list_fields:
            if hasattr(llm_output, field):
                memory[field] = getattr(llm_output, field)

        if hasattr(llm_output, "risk_assessment"):
            memory["risk_assessment"] = getattr(llm_output, "risk_assessment")
            
        memory["last_analyzed"] = self._now()

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO patient_profile(patient_id, long_term_memory_json, updated_at)
                VALUES(?,?,?)
                ON CONFLICT(patient_id) DO UPDATE SET
                    long_term_memory_json=excluded.long_term_memory_json,
                    updated_at=excluded.updated_at
                """,
                (patient_id, json.dumps(memory), self._now()),
            )

    def update_patient_profile(self, patient_id: str, llm_output: Any) -> None:
        profile = self.get_patient_profile(patient_id)
        list_fields = [
            "emotional_themes", "thinking_patterns", "behavioral_patterns", 
            "interpersonal_dynamics", "stressors", "unclear_areas", "protective_factors"
        ]

        for field in list_fields:
            if hasattr(llm_output, field):
                profile[field] = getattr(llm_output, field)

        if hasattr(llm_output, "risk_assessment"):
            profile["risk_assessment"] = getattr(llm_output, "risk_assessment")
        if hasattr(llm_output, "session_summary"):
            profile["last_session_summary"] = getattr(llm_output, "session_summary")
            
        profile["last_analyzed"] = self._now()

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO patient_profile(patient_id, profile_json, updated_at)
                VALUES(?,?,?)
                ON CONFLICT(patient_id) DO UPDATE SET
                    profile_json=excluded.profile_json,
                    updated_at=excluded.updated_at
                """,
                (patient_id, json.dumps(profile), self._now()),
            )

    def get_patient_sessions(self, patient_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, created_at, last_active_at, rolling_summary, is_active FROM sessions WHERE patient_id=? ORDER BY created_at DESC",
                (patient_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def build_profile_recap(self, patient_id: str) -> Optional[str]:
        memory = self.get_long_term_memory(patient_id)
        if not memory:
            memory = self.get_patient_profile(patient_id)
            if not memory:
                return None

        lines = ["[Returning patient — prior session context (not to be quoted back verbatim)]:"]

        recap = memory.get("last_session_summary")
        if recap:
            lines.append(f"Last session summary: {recap}")
        if memory.get("emotional_themes"):
            lines.append(f"Emotional themes: {'; '.join(memory['emotional_themes'][:4])}")
        if memory.get("stressors"):
            lines.append(f"Key stressors: {'; '.join(memory['stressors'][:4])}")
        if memory.get("risk_assessment") and memory["risk_assessment"] != "Not yet assessed":
            lines.append(f"Last risk status: {memory['risk_assessment'][:120]}")
        if memory.get("protective_factors"):
            lines.append(f"Protective factors: {'; '.join(memory['protective_factors'][:3])}")
        if memory.get("last_analyzed"):
            lines.append(f"Last analyzed: {memory['last_analyzed']}")

        return "\n".join(lines)

    def reset_patient_data(self, patient_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id IN (SELECT session_id FROM sessions WHERE patient_id = ?)", (patient_id,))
            conn.execute("DELETE FROM sessions WHERE patient_id = ?", (patient_id,))
            conn.execute(
                "UPDATE patient_profile SET profile_json = '{}', updated_at = ? WHERE patient_id = ?",
                (self._now(), patient_id)
            )

    def delete_patient(self, patient_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id IN (SELECT session_id FROM sessions WHERE patient_id = ?)", (patient_id,))
            conn.execute("DELETE FROM sessions WHERE patient_id = ?", (patient_id,))
            conn.execute("DELETE FROM patient_profile WHERE patient_id = ?", (patient_id,))
            conn.execute("DELETE FROM patients WHERE patient_id = ?", (patient_id,))


class SQLiteSessionStore(SQLiteBaseStore):
    """Concrete implementation of SessionStore using SQLite."""

    def __init__(self, db_path: str, working_memory_turns: int):
        super().__init__(db_path)
        self.working_memory_turns = working_memory_turns

    def create_session(self, patient_id: Optional[str] = None) -> str:
        session_id = str(uuid.uuid4())
        if patient_id is None:
            patient_id = str(uuid.uuid4())
        
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM patients WHERE patient_id=?", (patient_id,)
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO patients(patient_id, name, age) VALUES(?,?,?)",
                    (patient_id, "Guest Patient", None),
                )
        
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, patient_id, is_active, created_at, last_active_at) VALUES(?,?,1,?,?)",
                (session_id, patient_id, self._now(), self._now()),
            )
        return session_id

    def end_session(self, session_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET last_active_at=?, is_active=0 WHERE session_id=?",
                (self._now(), session_id),
            )
            
    def get_abandoned_sessions(self, timeout_minutes: int) -> list[str]:
        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT session_id FROM sessions WHERE is_active=1 AND last_active_at < datetime('now', '-{timeout_minutes} minutes')"
            ).fetchall()
        return [r["session_id"] for r in rows]

    def session_exists(self, session_id: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return row is not None

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
                (session_id, role, content, self._now()),
            )
            conn.execute(
                "UPDATE sessions SET last_active_at=? WHERE session_id=?",
                (self._now(), session_id),
            )

    def get_active_session(self, patient_id: str) -> Optional[str]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE patient_id=? AND is_active=1 ORDER BY created_at DESC LIMIT 1",
                (patient_id,)
            ).fetchone()
        return row["session_id"] if row else None

    def end_session(self, session_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET is_active=0 WHERE session_id=?",
                (session_id,)
            )

    def get_all_messages(self, session_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def _get_rolling_summary(self, session_id: str) -> tuple[str, int]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT rolling_summary, summarized_msg_count FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        if not row:
            return "", 0
        return (row["rolling_summary"] or ""), (row["summarized_msg_count"] or 0)

    def _set_rolling_summary(self, session_id: str, summary: str, count: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET rolling_summary=?, summarized_msg_count=? WHERE session_id=?",
                (summary, count, session_id),
            )

    def get_working_context(self, session_id: str, llm_engine: Optional[LLMProvider] = None) -> list:
        all_msgs = self.get_all_messages(session_id)
        if len(all_msgs) <= self.working_memory_turns:
            return all_msgs

        tail = all_msgs[-self.working_memory_turns:]
        summary, _ = self._get_rolling_summary(session_id)

        context = []
        if summary:
            context.append({
                "role": "system",
                "content": f"[Earlier session summary — do not quote back to patient]: {summary}",
            })
        context.extend(tail)
        return context

    def get_patient_id(self, session_id: str) -> Optional[str]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT patient_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return row["patient_id"] if row else None

    def get_session_count(self, patient_id: str) -> int:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE patient_id=?", (patient_id,)
            ).fetchone()
        return row[0]

    def save_session_summary(self, session_id: str, summary: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET rolling_summary = ? WHERE session_id = ?",
                (summary, session_id)
            )
