from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from src.session_service import generate_thread_id
from src.utils import DATA_DIR


USER_STORE_PATH = DATA_DIR / "app_users.json"


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #f6f3ee;
            --surface: rgba(255, 255, 255, 0.94);
            --surface-soft: rgba(255, 255, 255, 0.74);
            --ink: #202124;
            --muted: #6b7280;
            --line: #e7dfd4;
            --accent: #0f766e;
            --accent-soft: #dff5f2;
            --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
            --shadow-hover: 0 28px 60px rgba(15, 23, 42, 0.14);
            --radius: 24px;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(15, 118, 110, 0.08), transparent 30%),
                radial-gradient(circle at top right, rgba(217, 119, 6, 0.08), transparent 26%),
                linear-gradient(180deg, #f8f5ef 0%, #f5f2ec 100%);
            color: var(--ink);
        }

        .block-container {
            max-width: 1320px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3 {
            font-family: Georgia, "Times New Roman", serif;
            letter-spacing: -0.02em;
            color: #1f2937;
        }

        p, li, label, div, span {
            color: var(--ink);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(250,248,243,0.92));
            border-right: 1px solid rgba(231, 223, 212, 0.9);
        }

        [data-testid="stSidebar"] .block-container {
            padding-top: 1.4rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid rgba(231, 223, 212, 0.9);
            background: var(--surface);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
            backdrop-filter: blur(12px);
        }

        div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            transform: translateY(-3px);
            box-shadow: var(--shadow-hover);
            border-color: rgba(15, 118, 110, 0.28);
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="select"] > div,
        .stNumberInput div[data-baseweb="input"] > div {
            background: rgba(250, 248, 243, 0.92);
            border-radius: 18px;
            border: 1px solid rgba(226, 232, 240, 0.95);
        }

        .stTextInput input,
        .stTextArea textarea,
        .stNumberInput input {
            font-size: 1rem;
        }

        .stButton > button, .stDownloadButton > button {
            border-radius: 999px;
            border: 1px solid rgba(15, 118, 110, 0.14);
            background: linear-gradient(180deg, #ffffff, #f9fafb);
            color: #111827;
            padding: 0.7rem 1.1rem;
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.05);
        }

        .stButton > button:hover, .stDownloadButton > button:hover {
            transform: translateY(-2px);
            border-color: rgba(15, 118, 110, 0.35);
            box-shadow: 0 18px 35px rgba(15, 23, 42, 0.09);
            color: #0f766e;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 1rem;
            border-bottom: 1px solid rgba(231, 223, 212, 0.95);
        }

        .stTabs [data-baseweb="tab"] {
            height: 3rem;
            border-radius: 999px 999px 0 0;
            padding: 0 0.1rem;
        }

        .hero-panel {
            padding: 1.8rem 2rem;
            border-radius: 30px;
            background:
                linear-gradient(140deg, rgba(255, 255, 255, 0.95), rgba(248, 250, 252, 0.78)),
                linear-gradient(135deg, rgba(15, 118, 110, 0.05), rgba(217, 119, 6, 0.05));
            border: 1px solid rgba(231, 223, 212, 0.9);
            box-shadow: var(--shadow);
            margin-bottom: 1.25rem;
        }

        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            background: var(--accent-soft);
            color: var(--accent);
            font-size: 0.88rem;
            font-weight: 600;
            margin-bottom: 0.9rem;
        }

        .hero-title {
            font-size: clamp(2rem, 4vw, 3.6rem);
            line-height: 1.08;
            margin: 0 0 0.9rem 0;
        }

        .hero-subtitle {
            color: var(--muted);
            font-size: 1.02rem;
            line-height: 1.8;
            max-width: 860px;
        }

        .profile-card {
            padding: 1rem 1.1rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(247,244,238,0.98));
            border: 1px solid rgba(231, 223, 212, 0.88);
            box-shadow: 0 18px 36px rgba(15, 23, 42, 0.07);
            margin-bottom: 1rem;
        }

        .profile-tag {
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            background: rgba(15, 118, 110, 0.1);
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 600;
            margin-bottom: 0.65rem;
        }

        .profile-name {
            font-size: 1.28rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }

        .profile-meta {
            color: var(--muted);
            font-size: 0.93rem;
            line-height: 1.7;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin: 1rem 0 1.4rem;
        }

        .metric-card {
            padding: 1.05rem 1.1rem;
            border-radius: 22px;
            background: rgba(255,255,255,0.92);
            border: 1px solid rgba(231, 223, 212, 0.95);
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.05);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .metric-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 22px 42px rgba(15, 23, 42, 0.1);
        }

        .metric-label {
            color: var(--muted);
            font-size: 0.88rem;
            margin-bottom: 0.4rem;
        }

        .metric-value {
            font-size: 1.55rem;
            font-weight: 700;
            color: #111827;
        }

        .section-kicker {
            color: var(--accent);
            font-size: 0.9rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .section-title {
            margin: 0;
            font-size: 2rem;
        }

        .section-subtitle {
            color: var(--muted);
            margin-top: 0.4rem;
            line-height: 1.8;
        }

        .story-card {
            padding: 1.35rem 1.5rem;
            border-radius: 24px;
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(231, 223, 212, 0.95);
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .story-card:hover {
            transform: translateY(-3px);
            box-shadow: var(--shadow-hover);
        }

        .story-title {
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 0.55rem;
        }

        .story-body {
            color: var(--muted);
            line-height: 1.85;
        }

        .chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.8rem;
        }

        .chip {
            padding: 0.38rem 0.72rem;
            border-radius: 999px;
            font-size: 0.84rem;
            border: 1px solid rgba(15, 118, 110, 0.18);
            background: rgba(15, 118, 110, 0.08);
            color: var(--accent);
        }

        .empty-state {
            padding: 1.4rem 1.5rem;
            border-radius: 24px;
            background: rgba(255,255,255,0.86);
            border: 1px dashed rgba(148, 163, 184, 0.5);
            color: var(--muted);
        }

        .article-job-card {
            position: relative;
            padding: 1.45rem 1.5rem 1.3rem;
            border-radius: 26px;
            background:
                linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94));
            border: 1px solid rgba(231, 223, 212, 0.95);
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.07);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
            overflow: hidden;
            margin-bottom: 1rem;
        }

        .article-job-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 26px 54px rgba(15, 23, 42, 0.12);
            border-color: rgba(15, 118, 110, 0.24);
        }

        .article-job-card::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 6px;
            background: linear-gradient(180deg, #0f766e, #14b8a6);
        }

        .article-job-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.8rem;
        }

        .article-job-kicker {
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 0.45rem;
        }

        .article-job-title {
            font-size: 1.2rem;
            font-weight: 700;
            line-height: 1.5;
            color: #111827;
        }

        .article-job-score {
            min-width: 86px;
            padding: 0.72rem 0.85rem;
            border-radius: 20px;
            background: rgba(15, 118, 110, 0.08);
            border: 1px solid rgba(15, 118, 110, 0.14);
            text-align: center;
        }

        .article-job-score-value {
            font-size: 1.5rem;
            font-weight: 700;
            color: #0f766e;
            line-height: 1;
        }

        .article-job-score-label {
            margin-top: 0.28rem;
            color: var(--muted);
            font-size: 0.75rem;
        }

        .meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin: 0.7rem 0 1rem;
        }

        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            background: rgba(15, 23, 42, 0.05);
            color: #374151;
            font-size: 0.82rem;
            border: 1px solid rgba(226, 232, 240, 0.88);
        }

        .article-job-body {
            color: var(--muted);
            line-height: 1.85;
            margin-bottom: 0.9rem;
        }

        .article-job-split {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.85rem;
            margin-bottom: 1rem;
        }

        .mini-panel {
            padding: 0.95rem 1rem;
            border-radius: 18px;
            background: rgba(248, 250, 252, 0.88);
            border: 1px solid rgba(226, 232, 240, 0.9);
        }

        .mini-panel-title {
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--accent);
            margin-bottom: 0.45rem;
        }

        .mini-panel-body {
            color: #4b5563;
            line-height: 1.7;
            font-size: 0.92rem;
        }

        .session-result-card {
            padding: 1.2rem 1.3rem;
            border-radius: 24px;
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(231, 223, 212, 0.95);
            box-shadow: 0 16px 35px rgba(15, 23, 42, 0.06);
            margin-bottom: 0.9rem;
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .session-result-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.1);
        }

        .session-result-top {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
            margin-bottom: 0.7rem;
        }

        .session-result-title {
            font-size: 1.08rem;
            font-weight: 700;
            color: #111827;
            margin-bottom: 0.28rem;
        }

        .session-result-meta {
            font-size: 0.86rem;
            color: var(--muted);
            line-height: 1.7;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            border: 1px solid transparent;
        }

        .status-success {
            background: rgba(15, 118, 110, 0.1);
            color: #0f766e;
            border-color: rgba(15, 118, 110, 0.14);
        }

        .status-waiting {
            background: rgba(217, 119, 6, 0.1);
            color: #b45309;
            border-color: rgba(217, 119, 6, 0.16);
        }

        .status-low {
            background: rgba(107, 114, 128, 0.1);
            color: #4b5563;
            border-color: rgba(107, 114, 128, 0.16);
        }

        @media (max-width: 900px) {
            .block-container {
                padding-top: 1.2rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }

            .hero-panel {
                padding: 1.3rem 1.2rem;
            }

            .article-job-head,
            .session-result-top {
                flex-direction: column;
            }

            .article-job-split {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(title: str, subtitle: str, kicker: str) -> None:
    st.markdown(
        f"""
        <section class="hero-panel">
            <div class="hero-kicker">{kicker}</div>
            <h1 class="hero-title">{title}</h1>
            <div class="hero-subtitle">{subtitle}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_intro(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-kicker">{kicker}</div>
        <h2 class="section-title">{title}</h2>
        <p class="section-subtitle">{subtitle}</p>
        """,
        unsafe_allow_html=True,
    )


def render_metric_grid(items: list[tuple[str, str]]) -> None:
    cards = []
    for label, value in items:
        cards.append(
            (
                '<div class="metric-card">'
                f'<div class="metric-label">{html.escape(str(label))}</div>'
                f'<div class="metric-value">{html.escape(str(value))}</div>'
                "</div>"
            )
        )
    st.markdown(
        '<div class="metric-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def render_profile_card(profile: dict[str, Any], session_label: str | None = None) -> None:
    session_text = f"当前会话：{session_label}" if session_label else "当前会话：未命名"
    st.markdown(
        f"""
        <div class="profile-card">
            <div class="profile-tag">Personal Workspace</div>
            <div class="profile-name">{html.escape(str(profile.get("nickname", "")))}</div>
            <div class="profile-meta">
                账号：{html.escape(str(profile.get("account", "")))}<br/>
                {html.escape(session_text)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_story_card(title: str, body: str, chips: list[str] | None = None) -> None:
    chip_html = ""
    if chips:
        chip_html = '<div class="chip-row">' + "".join(
            f'<span class="chip">{html.escape(str(chip))}</span>' for chip in chips
        ) + "</div>"
    st.markdown(
        f"""
        <article class="story-card">
            <div class="story-title">{html.escape(str(title))}</div>
            <div class="story-body">{html.escape(str(body))}</div>
            {chip_html}
        </article>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(text: str) -> None:
    st.markdown(
        f'<div class="empty-state">{html.escape(str(text))}</div>',
        unsafe_allow_html=True,
    )


def render_job_article_card(
    *,
    title: str,
    city: str,
    score: str,
    verdict: str,
    strategy: str,
    reason: str,
    skill_tags: list[str] | None = None,
    gap_tags: list[str] | None = None,
    job_id: str = "",
) -> None:
    skill_tags = skill_tags or []
    gap_tags = gap_tags or []
    meta_pills = [
        f'<span class="meta-pill">城市 · {html.escape(city)}</span>',
        f'<span class="meta-pill">结论 · {html.escape(verdict)}</span>',
        f'<span class="meta-pill">策略 · {html.escape(strategy)}</span>',
    ]
    if job_id:
        meta_pills.append(f'<span class="meta-pill">岗位ID · {html.escape(job_id)}</span>')

    def build_tags(tags: list[str], fallback: str) -> str:
        if not tags:
            return fallback
        return "".join(
            f'<span class="chip">{html.escape(tag)}</span>'
            for tag in tags[:6]
        )

    st.markdown(
        f"""
        <article class="article-job-card">
            <div class="article-job-head">
                <div>
                    <div class="article-job-kicker">Priority Opportunity</div>
                    <div class="article-job-title">{html.escape(title)}</div>
                </div>
                <div class="article-job-score">
                    <div class="article-job-score-value">{html.escape(score)}</div>
                    <div class="article-job-score-label">Match Score</div>
                </div>
            </div>
            <div class="meta-row">{"".join(meta_pills)}</div>
            <div class="article-job-body">{html.escape(reason)}</div>
            <div class="article-job-split">
                <div class="mini-panel">
                    <div class="mini-panel-title">技能标签</div>
                    <div class="chip-row">{build_tags(skill_tags, '<span class="meta-pill">暂无技能标签</span>')}</div>
                </div>
                <div class="mini-panel">
                    <div class="mini-panel-title">补足重点</div>
                    <div class="chip-row">{build_tags(gap_tags, '<span class="meta-pill">当前没有明显短板</span>')}</div>
                </div>
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def render_session_result_card(
    *,
    title: str,
    session_label: str,
    updated_at: str,
    status_text: str,
    status_kind: str,
    summary: str,
    chips: list[str] | None = None,
) -> None:
    chips = chips or []
    chip_html = ""
    if chips:
        chip_html = '<div class="chip-row">' + "".join(
            f'<span class="chip">{html.escape(chip)}</span>'
            for chip in chips
        ) + "</div>"

    status_class = {
        "success": "status-success",
        "waiting": "status-waiting",
        "low": "status-low",
    }.get(status_kind, "status-low")

    st.markdown(
        f"""
        <article class="session-result-card">
            <div class="session-result-top">
                <div>
                    <div class="session-result-title">{html.escape(title)}</div>
                    <div class="session-result-meta">
                        会话：{html.escape(session_label)}<br/>
                        更新时间：{html.escape(updated_at)}
                    </div>
                </div>
                <span class="status-badge {status_class}">{html.escape(status_text)}</span>
            </div>
            <div class="story-body">{html.escape(summary)}</div>
            {chip_html}
        </article>
        """,
        unsafe_allow_html=True,
    )


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalize_account(account: str) -> str:
    return account.strip().lower()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


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
    return sorted(
        sessions,
        key=lambda item: item.get("updated_at", ""),
        reverse=True,
    )


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
