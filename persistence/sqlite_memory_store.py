import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional
from core.ports import LLM2Output, LLMProvider

class SQLiteMemoryStore:
    """
    Concrete implementation of ProfileStore, SessionStore, and AnalysisJobStore using SQLite.
    Provides durable, local storage for patients, conversational context, and background job state.
    """
    def __init__(self, db_path: str, working_memory_turns: int):
        self.db_path = db_path
        self.working_memory_turns = working_memory_turns
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

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

                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id       TEXT PRIMARY KEY,
                    session_id   TEXT NOT NULL,
                    patient_id   TEXT NOT NULL,
                    status       TEXT NOT NULL CHECK(status IN ('queued', 'in_progress', 'completed', 'failed')),
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, id);
            """)

            # Safe migration for existing DB
            try:
                conn.execute("ALTER TABLE patients ADD COLUMN gender TEXT")
                conn.execute("ALTER TABLE patients ADD COLUMN occupation TEXT")
                conn.execute("ALTER TABLE patients ADD COLUMN primary_concern TEXT")
            except sqlite3.OperationalError:
                pass # Columns already exist
                
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN summarized_msg_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass # Column already exists

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # --- ProfileStore Implementation ---

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

    def update_patient_profile(self, patient_id: str, llm2_output: LLM2Output) -> None:
        profile = self.get_patient_profile(patient_id)

        # Dynamically process all list-based fields to adhere to OCP
        list_fields = [
            field for field, field_info in LLM2Output.model_fields.items()
            if field != "risk_assessment"
        ]

        for field in list_fields:
            existing = profile.get(field, [])
            new_items = getattr(llm2_output, field, [])
            existing_lower = {x.lower() for x in existing}
            for item in new_items:
                if item.lower() not in existing_lower:
                    existing.append(item)
                    existing_lower.add(item.lower())
            profile[field] = existing

        profile["risk_assessment"] = getattr(llm2_output, "risk_assessment", "Not yet assessed")
        profile["last_analyzed"]   = self._now()

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
                "SELECT session_id, created_at, last_active_at, rolling_summary FROM sessions WHERE patient_id=? ORDER BY created_at DESC",
                (patient_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def build_profile_recap(self, patient_id: str) -> Optional[str]:
        profile = self.get_patient_profile(patient_id)
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

    def get_patient_id(self, session_id: str) -> Optional[str]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT patient_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return row["patient_id"] if row else None

    def reset_patient_data(self, patient_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM analysis_jobs WHERE patient_id = ?", (patient_id,))
            conn.execute("DELETE FROM messages WHERE session_id IN (SELECT session_id FROM sessions WHERE patient_id = ?)", (patient_id,))
            conn.execute("DELETE FROM sessions WHERE patient_id = ?", (patient_id,))
            conn.execute(
                "UPDATE patient_profile SET profile_json = '{}', updated_at = ? WHERE patient_id = ?",
                (self._now(), patient_id)
            )

    def delete_patient(self, patient_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM analysis_jobs WHERE patient_id = ?", (patient_id,))
            conn.execute("DELETE FROM messages WHERE session_id IN (SELECT session_id FROM sessions WHERE patient_id = ?)", (patient_id,))
            conn.execute("DELETE FROM sessions WHERE patient_id = ?", (patient_id,))
            conn.execute("DELETE FROM patient_profile WHERE patient_id = ?", (patient_id,))
            conn.execute("DELETE FROM patients WHERE patient_id = ?", (patient_id,))


    # --- SessionStore Implementation ---

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
                
        now = self._now()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, patient_id, created_at, last_active_at) VALUES(?,?,?,?)",
                (session_id, patient_id, now, now),
            )
        return session_id

    def end_session(self, session_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET last_active_at=? WHERE session_id=?",
                (self._now(), session_id),
            )
        
    # --- Background Job Management ---
    def queue_analysis_job(self, session_id: str, patient_id: str) -> str:
        job_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO analysis_jobs (job_id, session_id, patient_id, status) VALUES (?, ?, ?, 'queued')",
                (job_id, session_id, patient_id)
            )
        return job_id

    def acquire_analysis_job(self, job_id: str, patient_id: str) -> bool:
        """Atomically acquires a job if no other job for this patient is in progress."""
        with self._get_conn() as conn:
            cur = conn.execute("""
                UPDATE analysis_jobs 
                SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP 
                WHERE job_id = ? AND status = 'queued'
                AND NOT EXISTS (
                    SELECT 1 FROM analysis_jobs 
                    WHERE patient_id = ? AND status = 'in_progress'
                )
            """, (job_id, patient_id))
            return cur.rowcount > 0

    def complete_analysis_job(self, job_id: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (job_id,)
            )

    def fail_analysis_job(self, job_id: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (job_id,)
            )

    def recover_orphaned_jobs(self):
        """Called on startup to reset jobs stuck in_progress due to server crash."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET status = 'queued', updated_at = CURRENT_TIMESTAMP WHERE status = 'in_progress'"
            )

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

    def _get_all_messages(self, session_id: str) -> list[dict]:
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
        all_msgs = self._get_all_messages(session_id)
        if len(all_msgs) <= self.working_memory_turns:
            return all_msgs

        overflow = all_msgs[:-self.working_memory_turns]
        tail     = all_msgs[-self.working_memory_turns:]

        summary, summarized_count = self._get_rolling_summary(session_id)
        
        if len(overflow) > summarized_count and llm_engine is not None:
            new_overflow = overflow[summarized_count:]
            
            if summary:
                turns_to_summarize = [{"role": "system", "content": f"Previous summary: {summary}"}] + new_overflow
            else:
                turns_to_summarize = new_overflow
                
            summary = llm_engine.summarize_history(turns_to_summarize)
            self._set_rolling_summary(session_id, summary, len(overflow))

        context = []
        if summary:
            context.append({
                "role": "system",
                "content": f"[Earlier session summary — do not quote back to patient]: {summary}",
            })
        context.extend(tail)
        return context

    def save_session_summary(self, session_id: str, summary: str) -> None:
        patient_id = self.get_patient_id(session_id)
        if not patient_id:
            return
        
        profile = self.get_patient_profile(patient_id)
        profile["last_session_summary"] = summary
        profile["last_session_at"] = self._now()
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
