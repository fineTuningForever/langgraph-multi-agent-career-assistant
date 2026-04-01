from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from src.session_service import generate_thread_id
from src.utils import DATA_DIR


USER_STORE_PATH = DATA_DIR / "app_users.json"
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalize_account(account: str) -> str:
    return account.strip().lower()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _token_secret() -> str:
    return os.getenv("APP_AUTH_SECRET", "langgraph-job-assistant-dev-secret")


def _empty_store() -> dict[str, Any]:
    return {"users": {}}


def get_user_store_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USER_STORE_PATH.exists():
        USER_STORE_PATH.write_text(
            json.dumps(_empty_store(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return USER_STORE_PATH


def _load_store() -> dict[str, Any]:
    path = get_user_store_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        store = _empty_store()
        path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
        return store


def _save_store(store: dict[str, Any]) -> None:
    get_user_store_path().write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "account": user["account"],
        "nickname": user["nickname"],
        "created_at": user["created_at"],
        "last_login_at": user.get("last_login_at", ""),
        "active_thread_id": user.get("active_thread_id", ""),
        "sessions": user.get("sessions", []),
    }


def create_access_token(account: str) -> str:
    normalized = _normalize_account(account)
    timestamp = str(int(datetime.now().timestamp()))
    payload = f"{normalized}:{timestamp}"
    signature = hmac.new(
        _token_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def verify_access_token(token: str, max_age_seconds: int = TOKEN_MAX_AGE_SECONDS) -> str | None:
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(
            _token_secret().encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        account, timestamp_text = payload.split(":", 1)
        issued_at = int(timestamp_text)
        if int(datetime.now().timestamp()) - issued_at > max_age_seconds:
            return None
        if not get_user_profile(account):
            return None
        return account
    except Exception:
        return None


def get_user_profile(account: str) -> dict[str, Any] | None:
    normalized = _normalize_account(account)
    if not normalized:
        return None
    store = _load_store()
    user = store["users"].get(normalized)
    if not user:
        return None
    return _serialize_user(user)


def register_user(account: str, nickname: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
    normalized = _normalize_account(account)
    nickname = nickname.strip()
    password = password.strip()

    if not normalized:
        return False, "请输入账号。", None
    if len(normalized) < 3:
        return False, "账号至少需要 3 个字符。", None
    if not nickname:
        return False, "请输入昵称。", None
    if len(password) < 6:
        return False, "密码至少需要 6 个字符。", None

    store = _load_store()
    if normalized in store["users"]:
        return False, "该账号已经存在，请直接登录。", None

    now = _now_text()
    thread_id = generate_thread_id()
    session = {
        "thread_id": thread_id,
        "label": "分析会话 1",
        "created_at": now,
        "updated_at": now,
    }
    user = {
        "account": normalized,
        "nickname": nickname,
        "password_hash": _hash_password(password),
        "created_at": now,
        "last_login_at": now,
        "active_thread_id": thread_id,
        "sessions": [session],
    }
    store["users"][normalized] = user
    _save_store(store)
    return True, "注册成功，已为你创建默认分析空间。", _serialize_user(user)


def authenticate_user(account: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
    normalized = _normalize_account(account)
    password = password.strip()
    store = _load_store()
    user = store["users"].get(normalized)
    if not user:
        return False, "账号不存在，请先注册。", None
    if user.get("password_hash") != _hash_password(password):
        return False, "密码不正确，请重新输入。", None

    user["last_login_at"] = _now_text()
    if not user.get("sessions"):
        user["sessions"] = [
            {
                "thread_id": generate_thread_id(),
                "label": "分析会话 1",
                "created_at": _now_text(),
                "updated_at": _now_text(),
            }
        ]
        user["active_thread_id"] = user["sessions"][0]["thread_id"]
    _save_store(store)
    return True, "登录成功。", _serialize_user(user)


def list_user_sessions(account: str) -> list[dict[str, Any]]:
    profile = get_user_profile(account)
    if not profile:
        return []
    sessions = profile.get("sessions", [])
    return sorted(sessions, key=lambda item: item.get("updated_at", ""), reverse=True)


def ensure_active_thread(account: str) -> str:
    normalized = _normalize_account(account)
    store = _load_store()
    user = store["users"].get(normalized)
    if not user:
        raise ValueError("用户不存在，无法创建会话。")

    sessions = user.setdefault("sessions", [])
    if sessions and user.get("active_thread_id"):
        return user["active_thread_id"]

    now = _now_text()
    thread_id = generate_thread_id()
    sessions.append(
        {
            "thread_id": thread_id,
            "label": f"分析会话 {len(sessions) + 1}",
            "created_at": now,
            "updated_at": now,
        }
    )
    user["active_thread_id"] = thread_id
    _save_store(store)
    return thread_id


def create_user_session(account: str) -> str:
    normalized = _normalize_account(account)
    store = _load_store()
    user = store["users"].get(normalized)
    if not user:
        raise ValueError("用户不存在，无法创建新会话。")

    sessions = user.setdefault("sessions", [])
    now = _now_text()
    thread_id = generate_thread_id()
    sessions.append(
        {
            "thread_id": thread_id,
            "label": f"分析会话 {len(sessions) + 1}",
            "created_at": now,
            "updated_at": now,
        }
    )
    user["active_thread_id"] = thread_id
    _save_store(store)
    return thread_id


def set_active_thread(account: str, thread_id: str) -> None:
    normalized = _normalize_account(account)
    store = _load_store()
    user = store["users"].get(normalized)
    if not user:
        return

    for session in user.get("sessions", []):
        if session.get("thread_id") == thread_id:
            user["active_thread_id"] = thread_id
            session["updated_at"] = _now_text()
            _save_store(store)
            return


def touch_user_session(account: str, thread_id: str) -> None:
    normalized = _normalize_account(account)
    store = _load_store()
    user = store["users"].get(normalized)
    if not user:
        return

    updated = False
    for session in user.get("sessions", []):
        if session.get("thread_id") == thread_id:
            session["updated_at"] = _now_text()
            updated = True
            break
    if updated:
        user["active_thread_id"] = thread_id
        _save_store(store)


def get_session_label(account: str, thread_id: str) -> str:
    for session in list_user_sessions(account):
        if session.get("thread_id") == thread_id:
            return session.get("label", thread_id)
    return thread_id


def user_owns_thread(account: str, thread_id: str) -> bool:
    return any(session.get("thread_id") == thread_id for session in list_user_sessions(account))
