from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import settings
from core.utils import read_json, write_json


class AuthService:
    SESSION_TTL_HOURS = 72

    @classmethod
    def _users_path(cls):
        return settings.storage_root / "users.json"

    @classmethod
    def _sessions_path(cls):
        return settings.storage_root / "sessions.json"

    @classmethod
    def _ownership_path(cls):
        return settings.storage_root / "report_ownership.json"

    @classmethod
    def _load_users(cls) -> dict[str, Any]:
        path = cls._users_path()
        if not path.exists():
            return {"users": {}}
        return read_json(path)

    @classmethod
    def _save_users(cls, data: dict[str, Any]) -> None:
        write_json(cls._users_path(), data)

    @classmethod
    def _load_sessions(cls) -> dict[str, Any]:
        path = cls._sessions_path()
        if not path.exists():
            return {"sessions": {}}
        return read_json(path)

    @classmethod
    def _save_sessions(cls, data: dict[str, Any]) -> None:
        write_json(cls._sessions_path(), data)

    @classmethod
    def _load_ownership(cls) -> dict[str, str]:
        path = cls._ownership_path()
        if not path.exists():
            return {}
        return read_json(path)

    @classmethod
    def _save_ownership(cls, data: dict[str, str]) -> None:
        write_json(cls._ownership_path(), data)

    @classmethod
    def ensure_demo_user(cls) -> None:
        data = cls._load_users()
        users = data.setdefault("users", {})
        demo_hash = cls._hash_password("demo123")
        existing = next((u for u in users.values() if u.get("username") == "demo"), None)
        if existing:
            existing["password_hash"] = demo_hash
        else:
            users["user_demo"] = {
                "user_id": "user_demo",
                "username": "demo",
                "password_hash": demo_hash,
                "created_at": datetime.now(UTC).isoformat(),
            }
        cls._save_users(data)

    @classmethod
    def register(cls, username: str, password: str) -> dict[str, Any]:
        username = username.strip().lower()
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        data = cls._load_users()
        if any(user["username"] == username for user in data["users"].values()):
            raise ValueError("Username already exists")

        user_id = f"user_{secrets.token_hex(8)}"
        data["users"][user_id] = {
            "user_id": user_id,
            "username": username,
            "password_hash": cls._hash_password(password),
            "created_at": datetime.now(UTC).isoformat(),
        }
        cls._save_users(data)
        return {"user_id": user_id, "username": username}

    @classmethod
    def login(cls, username: str, password: str) -> dict[str, Any]:
        username = username.strip().lower()
        data = cls._load_users()
        user = next((u for u in data["users"].values() if u["username"] == username), None)
        if user is None or not cls._verify_password(password, user["password_hash"]):
            raise ValueError("Invalid username or password")

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=cls.SESSION_TTL_HOURS)
        sessions = cls._load_sessions()
        sessions["sessions"][token] = {
            "user_id": user["user_id"],
            "username": user["username"],
            "expires_at": expires_at.isoformat(),
        }
        cls._save_sessions(sessions)
        return {"token": token, "user_id": user["user_id"], "username": user["username"], "expires_at": expires_at.isoformat()}

    @classmethod
    def resolve_user(cls, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        sessions = cls._load_sessions()
        session = sessions["sessions"].get(token)
        if not session:
            return None
        expires_at = datetime.fromisoformat(session["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            sessions["sessions"].pop(token, None)
            cls._save_sessions(sessions)
            return None
        return {"user_id": session["user_id"], "username": session["username"]}

    @classmethod
    def assign_report(cls, report_id: str, user_id: str) -> None:
        ownership = cls._load_ownership()
        ownership[report_id] = user_id
        cls._save_ownership(ownership)

    @classmethod
    def report_owner(cls, report_id: str) -> str | None:
        return cls._load_ownership().get(report_id)

    @classmethod
    def can_delete(cls, report_id: str, user_id: str) -> bool:
        owner = cls.report_owner(report_id)
        if owner is None:
            return False
        return owner == user_id

    @classmethod
    def remove_report_ownership(cls, report_id: str) -> None:
        ownership = cls._load_ownership()
        ownership.pop(report_id, None)
        cls._save_ownership(ownership)

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return f"pbkdf2_sha256${salt}${digest}"

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            scheme, salt, digest = encoded.split("$", 2)
        except ValueError:
            return False
        if scheme != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return secrets.compare_digest(check, digest)
