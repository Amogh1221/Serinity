import uuid
from typing import Optional
from datetime import datetime, timezone
from persistence.sqlite_memory_store import SQLiteBaseStore

class SQLiteUserStore(SQLiteBaseStore):
    """Concrete implementation for User authentication persistence using SQLite."""

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        nationality: Optional[str] = None,
        emergency_contact_name: Optional[str] = None,
        emergency_contact_phone: Optional[str] = None
    ) -> str:
        user_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO users(id, username, email, password_hash, nationality, emergency_contact_name, emergency_contact_phone, created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (user_id, username, email, password_hash, nationality, emergency_contact_name, emergency_contact_phone, self._now())
            )
        return user_id

    def get_user_by_username(self, username: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username=?",
                (username,)
            ).fetchone()
        return dict(row) if row else None
        
    def get_user_by_email(self, email: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email=?",
                (email,)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id=?",
                (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_password(self, email: str, new_password_hash: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE users SET password_hash=? WHERE email=?",
                (new_password_hash, email)
            )

    def delete_user(self, user_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))

    # OTP Token Management
    def store_otp(self, email: str, otp_code: str, expires_at: datetime) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO otp_tokens(email, otp_code, expires_at)
                VALUES(?,?,?)
                ON CONFLICT(email) DO UPDATE SET
                    otp_code=excluded.otp_code,
                    expires_at=excluded.expires_at
                """,
                (email, otp_code, expires_at.isoformat())
            )

    def get_otp(self, email: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM otp_tokens WHERE email=?",
                (email,)
            ).fetchone()
        return dict(row) if row else None

    def delete_otp(self, email: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM otp_tokens WHERE email=?", (email,))
