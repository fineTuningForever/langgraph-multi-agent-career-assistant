from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth_service import (
    authenticate_user,
    create_access_token,
    create_user_session,
    ensure_active_thread,
    get_session_label,
    get_user_profile,
    list_user_sessions,
    register_user,
    set_active_thread,
    touch_user_session,
    user_owns_thread,
    verify_access_token,
)
from src.graph import build_graph
from src.resume_parser import parse_resume_file
from src.session_service import (
    DEFAULT_MESSAGE,
    DEFAULT_USER_GOAL,
    build_config,
    get_session_values,
    get_state_history_rows,
    run_continue_analysis,
    run_new_analysis,
)
from src.utils import load_env, load_jobs, load_sample_resume

from .schemas import (
    ActivateSessionResponse,
    AnalysisResponse,
    AuthResponse,
    AuthRequest,
    HistoryItem,
    JobListResponse,
    RegisterRequest,
    SessionListResponse,
    SessionStateResponse,
    SessionSummary,
    UserProfile,
)


load_env()

app = FastAPI(
    title="LangGraph Internship Assistant API",
    version="1.0.0",
    description="Vue + FastAPI backend for the LangGraph multi-agent internship assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_graph_app():
    return build_graph()


def summarize_session(values: dict[str, Any]) -> SessionSummary:
    return SessionSummary(
        user_goal=values.get("user_goal", ""),
        jobs_count=len(values.get("jobs", [])),
        analyses_count=len(values.get("analyses", [])),
        matches_count=len(values.get("matches", [])),
        optimization_round=values.get("optimization_round", 0),
        has_final_report=bool(values.get("final_report")),
        shortlist=values.get("shortlist", []),
        revision_notes=values.get("revision_notes", []),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录。")

    account = verify_access_token(credentials.credentials)
    if not account:
        raise HTTPException(status_code=401, detail="登录状态无效或已过期。")

    profile = get_user_profile(account)
    if not profile:
        raise HTTPException(status_code=401, detail="当前用户不存在。")
    return profile


def ensure_thread_owner(account: str, thread_id: str) -> None:
    if not user_owns_thread(account, thread_id):
        raise HTTPException(status_code=404, detail="当前会话不存在或不属于你。")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=AuthResponse)
def api_register(payload: RegisterRequest) -> AuthResponse:
    ok, message, profile = register_user(
        payload.account,
        payload.nickname,
        payload.password,
    )
    token = create_access_token(profile["account"]) if ok and profile else None
    return AuthResponse(
        ok=ok,
        message=message,
        token=token,
        profile=UserProfile(**profile) if profile else None,
    )


@app.post("/api/auth/login", response_model=AuthResponse)
def api_login(payload: AuthRequest) -> AuthResponse:
    ok, message, profile = authenticate_user(payload.account, payload.password)
    token = create_access_token(profile["account"]) if ok and profile else None
    return AuthResponse(
        ok=ok,
        message=message,
        token=token,
        profile=UserProfile(**profile) if profile else None,
    )


@app.get("/api/auth/me", response_model=UserProfile)
def api_me(current_user: dict[str, Any] = Depends(get_current_user)) -> UserProfile:
    return UserProfile(**current_user)


@app.get("/api/jobs", response_model=JobListResponse)
def api_jobs(current_user: dict[str, Any] = Depends(get_current_user)) -> JobListResponse:
    jobs = load_jobs()
    return JobListResponse(total=len(jobs), jobs=jobs)


@app.get("/api/sessions", response_model=SessionListResponse)
def api_sessions(current_user: dict[str, Any] = Depends(get_current_user)) -> SessionListResponse:
    return SessionListResponse(
        active_thread_id=current_user.get("active_thread_id", ""),
        sessions=list_user_sessions(current_user["account"]),
    )


@app.post("/api/sessions", response_model=ActivateSessionResponse)
def api_create_session(current_user: dict[str, Any] = Depends(get_current_user)) -> ActivateSessionResponse:
    thread_id = create_user_session(current_user["account"])
    return ActivateSessionResponse(ok=True, active_thread_id=thread_id)


@app.post("/api/sessions/{thread_id}/activate", response_model=ActivateSessionResponse)
def api_activate_session(
    thread_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ActivateSessionResponse:
    ensure_thread_owner(current_user["account"], thread_id)
    set_active_thread(current_user["account"], thread_id)
    return ActivateSessionResponse(ok=True, active_thread_id=thread_id)


@app.get("/api/sessions/{thread_id}", response_model=SessionStateResponse)
def api_session_state(
    thread_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SessionStateResponse:
    ensure_thread_owner(current_user["account"], thread_id)
    values = get_session_values(get_graph_app(), build_config(thread_id))
    return SessionStateResponse(
        thread_id=thread_id,
        values=values,
        summary=summarize_session(values),
    )


@app.get("/api/sessions/{thread_id}/history", response_model=list[HistoryItem])
def api_session_history(
    thread_id: str,
    limit: int = 10,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[HistoryItem]:
    ensure_thread_owner(current_user["account"], thread_id)
    rows = get_state_history_rows(get_graph_app(), build_config(thread_id), limit=limit)
    return [HistoryItem(**row) for row in rows]


@app.get("/api/sessions/{thread_id}/label")
def api_session_label(
    thread_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    ensure_thread_owner(current_user["account"], thread_id)
    return {"label": get_session_label(current_user["account"], thread_id)}


@app.post("/api/analysis/run", response_model=AnalysisResponse)
async def api_run_analysis(
    thread_id: str = Form(...),
    continue_session: bool = Form(False),
    user_goal: str | None = Form(None),
    message: str = Form(DEFAULT_MESSAGE),
    resume_text: str | None = Form(None),
    max_optimization_rounds: int = Form(1),
    resume_file: UploadFile | None = File(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AnalysisResponse:
    ensure_thread_owner(current_user["account"], thread_id)

    resolved_resume_text = resume_text.strip() if resume_text else None
    if resume_file is not None:
        raw = await resume_file.read()
        resolved_resume_text = parse_resume_file(resume_file.filename, raw)

    app_graph = get_graph_app()
    if continue_session:
        result = run_continue_analysis(
            app_graph,
            thread_id=thread_id,
            user_goal=(user_goal or "").strip() or None,
            resume_text=resolved_resume_text or None,
            jobs=load_jobs(),
            message=(message or DEFAULT_MESSAGE).strip() or DEFAULT_MESSAGE,
            max_optimization_rounds=max_optimization_rounds,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="当前会话没有已保存状态，无法继续。")
    else:
        result = run_new_analysis(
            app_graph,
            thread_id=thread_id,
            user_goal=(user_goal or "").strip() or DEFAULT_USER_GOAL,
            resume_text=resolved_resume_text or load_sample_resume(),
            jobs=load_jobs(),
            message=(message or DEFAULT_MESSAGE).strip() or DEFAULT_MESSAGE,
            max_optimization_rounds=max_optimization_rounds,
        )

    touch_user_session(current_user["account"], thread_id)
    values = get_session_values(app_graph, build_config(thread_id))
    return AnalysisResponse(
        thread_id=thread_id,
        result=result,
        summary=summarize_session(values),
    )
