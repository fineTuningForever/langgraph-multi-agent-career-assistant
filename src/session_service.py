from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from src.utils import load_jobs, load_sample_resume, read_text


DEFAULT_USER_GOAL = (
    "我想找上海或杭州的 Java 后端 / AI 应用开发实习，"
    "希望岗位和 LangGraph、多智能体、后端开发有一定关联。"
)
DEFAULT_MESSAGE = "请帮我分析这些岗位，并给出投递建议。"


def generate_thread_id() -> str:
    return f"internship-session-{uuid.uuid4()}"


def build_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def resolve_resume_text(
    *,
    resume_text: str | None = None,
    resume_path: str | None = None,
    fallback: str | None = None,
) -> str:
    if resume_text:
        return resume_text.strip()
    if resume_path:
        return read_text(Path(resume_path))
    if fallback:
        return fallback
    return load_sample_resume()


def build_fresh_input(
    *,
    user_goal: str,
    resume_text: str,
    jobs: list[dict[str, Any]] | None = None,
    message: str = DEFAULT_MESSAGE,
    max_optimization_rounds: int = 1,
) -> dict[str, Any]:
    # 这里显式重置 final_report / next_step / strategy_reason，
    # 是为了避免同一个 thread_id 下重复运行时，
    # 旧会话的最终报告残留在 checkpoint 里，导致 Supervisor 直接 finish。
    return {
        "messages": [HumanMessage(content=message)],
        "user_goal": user_goal,
        "resume_text": resume_text,
        "jobs": jobs or load_jobs(),
        "analyses": [],
        "matches": [],
        "shortlist": [],
        "final_report": "",
        "next_step": "analyze_jobs",
        "strategy_reason": "",
        "optimization_round": 0,
        "max_optimization_rounds": max_optimization_rounds,
        "revision_notes": [],
    }


def get_session_values(app, config: dict[str, Any]) -> dict[str, Any]:
    snapshot = app.get_state(config)
    return dict(snapshot.values or {})


def get_state_history_rows(
    app,
    config: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snapshot in app.get_state_history(config, limit=limit):
        values = dict(snapshot.values or {})
        metadata = getattr(snapshot, "metadata", {}) or {}
        rows.append(
            {
                "created_at": getattr(snapshot, "created_at", ""),
                "next": list(getattr(snapshot, "next", ()) or ()),
                "step": metadata.get("step"),
                "source": metadata.get("source"),
                "analyses_count": len(values.get("analyses", [])),
                "matches_count": len(values.get("matches", [])),
                "optimization_round": values.get("optimization_round", 0),
                "has_final_report": bool(values.get("final_report")),
                "checkpoint_id": snapshot.config["configurable"].get("checkpoint_id", ""),
            }
        )
    return rows


def run_new_analysis(
    app,
    *,
    thread_id: str,
    user_goal: str,
    resume_text: str,
    jobs: list[dict[str, Any]] | None = None,
    message: str = DEFAULT_MESSAGE,
    max_optimization_rounds: int = 1,
) -> dict[str, Any]:
    return app.invoke(
        build_fresh_input(
            user_goal=user_goal,
            resume_text=resume_text,
            jobs=jobs,
            message=message,
            max_optimization_rounds=max_optimization_rounds,
        ),
        config=build_config(thread_id),
    )


def run_continue_analysis(
    app,
    *,
    thread_id: str,
    user_goal: str | None = None,
    resume_text: str | None = None,
    jobs: list[dict[str, Any]] | None = None,
    message: str = DEFAULT_MESSAGE,
    max_optimization_rounds: int = 1,
) -> dict[str, Any] | None:
    config = build_config(thread_id)
    saved_values = get_session_values(app, config)
    if not saved_values:
        return None

    return app.invoke(
        build_fresh_input(
            user_goal=user_goal or saved_values.get("user_goal") or DEFAULT_USER_GOAL,
            resume_text=resume_text or saved_values.get("resume_text") or load_sample_resume(),
            jobs=jobs or saved_values.get("jobs") or load_jobs(),
            message=message,
            max_optimization_rounds=max_optimization_rounds,
        ),
        config=config,
    )
