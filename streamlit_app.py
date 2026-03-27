from __future__ import annotations

from io import BytesIO
from typing import Any

import streamlit as st

from src.frontend_service import (
    authenticate_user,
    create_user_session,
    ensure_active_thread,
    get_session_label,
    get_user_profile,
    inject_app_styles,
    list_user_sessions,
    register_user,
    render_empty_state,
    render_hero,
    render_metric_grid,
    render_profile_card,
    render_section_intro,
    render_session_result_card,
    render_story_card,
    set_active_thread,
    touch_user_session,
)
from src.graph import build_graph
from src.session_service import (
    DEFAULT_MESSAGE,
    DEFAULT_USER_GOAL,
    build_config,
    get_session_values,
    get_state_history_rows,
    run_continue_analysis,
    run_new_analysis,
)
from src.utils import get_checkpoint_db_path, load_env, load_jobs, load_sample_resume


@st.cache_resource
def get_app():
    load_env()
    return build_graph()


@st.cache_data
def get_jobs() -> list[dict[str, Any]]:
    return load_jobs()


def load_resume_from_upload(uploaded_file) -> str:
    suffix = uploaded_file.name.lower().rsplit(".", 1)[-1]
    raw = uploaded_file.getvalue()

    if suffix in {"txt", "md"}:
        return raw.decode("utf-8").strip()

    if suffix == "pdf":
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise RuntimeError("当前环境缺少 pypdf，无法读取 PDF 简历。") from exc

        reader = PdfReader(BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise RuntimeError("PDF 已上传，但没有提取到可用文本。")
        return text

    raise RuntimeError("当前仅支持 txt / md / pdf 简历文件。")


def summarize_session(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_goal": values.get("user_goal", ""),
        "jobs_count": len(values.get("jobs", [])),
        "analyses_count": len(values.get("analyses", [])),
        "matches_count": len(values.get("matches", [])),
        "optimization_round": values.get("optimization_round", 0),
        "has_final_report": bool(values.get("final_report")),
        "shortlist": values.get("shortlist", []),
        "revision_notes": values.get("revision_notes", []),
    }


def get_active_matches(values: dict[str, Any]) -> list[dict[str, Any]]:
    current_round = values.get("optimization_round", 0)
    return [
        item
        for item in values.get("matches", [])
        if item.get("review_round", 0) == current_round
    ]


def init_page_state() -> None:
    defaults = {
        "user_account": None,
        "user_profile": None,
        "thread_id": "",
        "loaded_session": None,
        "last_result": None,
        "history_rows": [],
        "history_limit": 10,
        "form_user_goal": DEFAULT_USER_GOAL,
        "form_message": DEFAULT_MESSAGE,
        "form_max_rounds": 1,
        "resume_mode": "使用示例简历",
        "pasted_resume_text": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_logged_in_user(profile: dict[str, Any]) -> None:
    st.session_state.user_account = profile["account"]
    st.session_state.user_profile = profile
    st.session_state.thread_id = profile.get("active_thread_id") or ensure_active_thread(
        profile["account"]
    )
    st.session_state.loaded_session = None
    st.session_state.last_result = None
    st.session_state.history_rows = []


def logout() -> None:
    st.session_state.user_account = None
    st.session_state.user_profile = None
    st.session_state.thread_id = ""
    st.session_state.loaded_session = None
    st.session_state.last_result = None
    st.session_state.history_rows = []
    st.rerun()


def sync_user_profile() -> dict[str, Any] | None:
    account = st.session_state.user_account
    if not account:
        return None
    profile = get_user_profile(account)
    if not profile:
        logout()
        return None
    thread_id = profile.get("active_thread_id") or ensure_active_thread(account)
    if not profile.get("active_thread_id"):
        profile = get_user_profile(account)
    st.session_state.user_profile = profile
    if not st.session_state.thread_id:
        st.session_state.thread_id = thread_id
    return profile


def load_current_session(app, thread_id: str) -> dict[str, Any]:
    values = get_session_values(app, build_config(thread_id))
    st.session_state.loaded_session = values
    return values


def get_display_values() -> dict[str, Any]:
    if st.session_state.last_result:
        return st.session_state.last_result
    if st.session_state.loaded_session:
        return st.session_state.loaded_session
    return {}


def truncate_text(text: str, limit: int = 150) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def build_user_result_cards(app, account: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for session in list_user_sessions(account):
        values = get_session_values(app, build_config(session["thread_id"]))
        if not values:
            cards.append(
                {
                    "thread_id": session["thread_id"],
                    "label": session["label"],
                    "updated_at": session["updated_at"],
                    "status_text": "未开始",
                    "status_kind": "low",
                    "summary": "这个会话还没有保存分析结果，可以继续补充目标或简历后重新运行。",
                    "chips": ["尚无 final_report"],
                    "has_report": False,
                }
            )
            continue

        has_report = bool(values.get("final_report"))
        active_matches = get_active_matches(values)
        shortlist_count = len(values.get("shortlist", []))
        cards.append(
            {
                "thread_id": session["thread_id"],
                "label": session["label"],
                "updated_at": session["updated_at"],
                "status_text": "已有最终建议" if has_report else "分析进行中",
                "status_kind": "success" if has_report else "waiting",
                "summary": truncate_text(
                    values.get("final_report")
                    or values.get("user_goal")
                    or "当前会话已保存状态，但还没有生成最终建议。"
                ),
                "chips": [
                    f"岗位 {len(values.get('jobs', []))}",
                    f"分析 {len(values.get('analyses', []))}",
                    f"当前轮匹配 {len(active_matches)}",
                    f"shortlist {shortlist_count}",
                ],
                "has_report": has_report,
            }
        )

    return cards


def render_auth_page() -> None:
    render_hero(
        title="把实习求职流程，变成一张可回路的 Agent 图。",
        subtitle=(
            "先登录你的个人空间，再开始岗位分析、简历匹配、低分回路优化和最终建议生成。"
            "这一版界面更强调展示感，适合你后续面试演示。"
        ),
        kicker="Personalized Entry",
    )

    intro_col, auth_col = st.columns([1.05, 0.95], gap="large")

    with intro_col:
        with st.container(border=True):
            render_section_intro(
                "Workspace",
                "一个更像产品原型的求职助手",
                "登录后你会进入自己的分析空间。系统会维护个人会话列表，而不是让用户直接面对 thread_id。",
            )
            render_metric_grid(
                [
                    ("多智能体角色", "5"),
                    ("主图 + 子图", "3"),
                    ("支持会话恢复", "SQLite"),
                    ("前端形态", "Blog UI"),
                ]
            )
            render_story_card(
                "为什么先做登录层",
                "因为对普通用户来说，thread_id 是实现细节，不是产品入口。现在每个账号都会拥有自己的分析空间、会话列表和历史结果，展示体验会自然很多。",
                chips=["注册后自动创建空间", "昵称 + 账号展示", "会话与用户绑定"],
            )
            render_story_card(
                "页面风格方向",
                "整体采用更像知乎专栏、Medium 和博客产品的布局思路：卡片式内容承载、更多留白、更清晰的排版层级，以及更适合演示的结果展示页。",
                chips=["卡片阴影", "Hover 动画", "阅读型排版", "响应式布局"],
            )

    with auth_col:
        with st.container(border=True):
            render_section_intro(
                "Access",
                "登录你的工作台",
                "可以直接登录，也可以先注册一个新账号。账号数据会保存在本地 JSON 文件中，用于前端原型演示。",
            )
            login_tab, register_tab = st.tabs(["登录", "注册"])

            with login_tab:
                with st.form("login_form", clear_on_submit=False):
                    login_account = st.text_input("账号", placeholder="例如 lichunfeng")
                    login_password = st.text_input("密码", type="password")
                    login_submit = st.form_submit_button("进入工作台", use_container_width=True)
                if login_submit:
                    ok, message, profile = authenticate_user(login_account, login_password)
                    if ok and profile:
                        set_logged_in_user(profile)
                        st.toast(message)
                        st.rerun()
                    else:
                        st.error(message)

            with register_tab:
                with st.form("register_form", clear_on_submit=False):
                    register_account = st.text_input("新账号", placeholder="至少 3 个字符")
                    register_nickname = st.text_input("昵称", placeholder="页面里展示给你的称呼")
                    register_password = st.text_input("密码", type="password")
                    register_submit = st.form_submit_button("注册并创建空间", use_container_width=True)
                if register_submit:
                    ok, message, profile = register_user(
                        register_account,
                        register_nickname,
                        register_password,
                    )
                    if ok and profile:
                        set_logged_in_user(profile)
                        st.toast(message)
                        st.rerun()
                    else:
                        st.error(message)


def render_sidebar(profile: dict[str, Any], app, jobs: list[dict[str, Any]]) -> None:
    account = profile["account"]
    sessions = list_user_sessions(account)
    if not sessions:
        thread_id = ensure_active_thread(account)
        sessions = list_user_sessions(account)
        st.session_state.thread_id = thread_id

    session_map = {item["thread_id"]: item for item in sessions}
    if st.session_state.thread_id not in session_map:
        st.session_state.thread_id = profile.get("active_thread_id") or sessions[0]["thread_id"]

    with st.sidebar:
        render_profile_card(profile, get_session_label(account, st.session_state.thread_id))

        selected_thread = st.selectbox(
            "我的分析会话",
            options=[item["thread_id"] for item in sessions],
            index=[item["thread_id"] for item in sessions].index(st.session_state.thread_id),
            format_func=lambda thread_id: (
                f"{session_map[thread_id]['label']} · {session_map[thread_id]['updated_at']}"
            ),
        )
        if selected_thread != st.session_state.thread_id:
            st.session_state.thread_id = selected_thread
            set_active_thread(account, selected_thread)
            st.session_state.last_result = None
            load_current_session(app, selected_thread)
            st.rerun()

        top_left, top_right = st.columns(2)
        with top_left:
            if st.button("新建会话", use_container_width=True):
                st.session_state.thread_id = create_user_session(account)
                st.session_state.loaded_session = None
                st.session_state.last_result = None
                st.session_state.history_rows = []
                st.rerun()
        with top_right:
            current_values = get_display_values()
            if current_values.get("final_report") and st.button("结果页", use_container_width=True):
                st.switch_page("pages/01_Final_Report.py")

        history_limit = st.number_input(
            "历史快照数量",
            min_value=1,
            max_value=50,
            value=int(st.session_state.history_limit),
        )
        st.session_state.history_limit = int(history_limit)

        action_left, action_right = st.columns(2)
        with action_left:
            if st.button("读取会话", use_container_width=True):
                values = load_current_session(app, st.session_state.thread_id)
                if values:
                    st.success("已读取当前会话。")
                else:
                    st.warning("当前会话还没有保存内容。")
        with action_right:
            if st.button("读历史", use_container_width=True):
                st.session_state.history_rows = get_state_history_rows(
                    app,
                    build_config(st.session_state.thread_id),
                    st.session_state.history_limit,
                )
                if st.session_state.history_rows:
                    st.success("已读取历史快照。")
                else:
                    st.warning("当前会话没有历史快照。")

        with st.expander("查看会话技术细节", expanded=False):
            st.caption(f"thread_id: {st.session_state.thread_id}")
            st.caption(f"checkpoint_db: {get_checkpoint_db_path()}")

        st.caption(f"当前岗位数据量：{len(jobs)}")
        if st.button("退出登录", use_container_width=True):
            logout()


def render_run_tab(app, jobs: list[dict[str, Any]], profile: dict[str, Any]) -> None:
    account = profile["account"]
    active_values = get_display_values()
    result_cards = build_user_result_cards(app, account)
    completed_count = sum(1 for item in result_cards if item["has_report"])
    featured_result = next((item for item in result_cards if item["has_report"]), None)

    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        with st.container(border=True):
            render_section_intro(
                "Editor",
                "开始一次新的岗位分析",
                "填写你的求职目标、简历内容和用户消息。分析完成后，系统会直接跳转到单独的最终建议页。",
            )

            st.text_area("求职目标", key="form_user_goal", height=120)
            st.text_input("用户消息", key="form_message")
            st.number_input(
                "最大简历优化轮次",
                min_value=0,
                max_value=5,
                key="form_max_rounds",
            )

            st.radio(
                "简历输入方式",
                ["使用示例简历", "粘贴简历文本", "上传简历文件"],
                horizontal=True,
                key="resume_mode",
            )

            resume_text = ""
            if st.session_state.resume_mode == "使用示例简历":
                resume_text = load_sample_resume()
                st.text_area("示例简历预览", value=resume_text, height=260, disabled=True)
            elif st.session_state.resume_mode == "粘贴简历文本":
                resume_text = st.text_area(
                    "粘贴简历内容",
                    key="pasted_resume_text",
                    height=300,
                )
            else:
                uploaded_file = st.file_uploader(
                    "上传简历文件",
                    type=["txt", "md", "pdf"],
                    accept_multiple_files=False,
                )
                if uploaded_file is not None:
                    try:
                        resume_text = load_resume_from_upload(uploaded_file)
                        st.text_area("提取结果预览", value=resume_text, height=260, disabled=True)
                    except Exception as exc:
                        st.error(str(exc))

            action_left, action_right = st.columns(2)
            with action_left:
                if st.button("启动新分析", use_container_width=True):
                    if not resume_text.strip():
                        st.warning("请先提供简历内容。")
                    else:
                        try:
                            with st.spinner("岗位分析与匹配中，请稍等..."):
                                result = run_new_analysis(
                                    app,
                                    thread_id=st.session_state.thread_id,
                                    user_goal=st.session_state.form_user_goal.strip()
                                    or DEFAULT_USER_GOAL,
                                    resume_text=resume_text,
                                    jobs=jobs,
                                    message=st.session_state.form_message.strip() or DEFAULT_MESSAGE,
                                    max_optimization_rounds=int(st.session_state.form_max_rounds),
                                )
                            st.session_state.last_result = result
                            st.session_state.loaded_session = get_session_values(
                                app, build_config(st.session_state.thread_id)
                            )
                            touch_user_session(account, st.session_state.thread_id)
                            if result.get("final_report"):
                                st.toast("分析完成，正在进入最终建议页。")
                                st.switch_page("pages/01_Final_Report.py")
                            st.success("分析完成。")
                        except Exception as exc:
                            st.error(f"运行失败：{exc}")

            with action_right:
                if st.button("继续当前会话", use_container_width=True):
                    try:
                        with st.spinner("正在基于历史会话继续分析..."):
                            result = run_continue_analysis(
                                app,
                                thread_id=st.session_state.thread_id,
                                user_goal=st.session_state.form_user_goal.strip() or None,
                                resume_text=resume_text.strip() or None,
                                jobs=jobs,
                                message=st.session_state.form_message.strip() or DEFAULT_MESSAGE,
                                max_optimization_rounds=int(st.session_state.form_max_rounds),
                            )
                        if result is None:
                            st.warning("当前会话没有已保存内容，无法继续。")
                        else:
                            st.session_state.last_result = result
                            st.session_state.loaded_session = get_session_values(
                                app, build_config(st.session_state.thread_id)
                            )
                            touch_user_session(account, st.session_state.thread_id)
                            if result.get("final_report"):
                                st.toast("会话已续跑完成，正在进入最终建议页。")
                                st.switch_page("pages/01_Final_Report.py")
                            st.success("会话已继续完成。")
                    except Exception as exc:
                        st.error(f"继续会话失败：{exc}")

    with right:
        with st.container(border=True):
            render_section_intro(
                "Workspace",
                "当前分析空间",
                "这里不再直接显示最终建议，而是展示当前工作台的摘要。最终建议会进入专门的阅读页。",
            )
            render_metric_grid(
                [
                    ("当前会话", get_session_label(account, st.session_state.thread_id)),
                    ("岗位数量", str(len(active_values.get("jobs", jobs)))),
                    ("分析数", str(len(active_values.get("analyses", [])))),
                    ("当前轮匹配", str(len(get_active_matches(active_values)))),
                ]
            )
            if active_values.get("final_report"):
                render_story_card(
                    "已有结果可读",
                    "当前会话已经生成了最终建议。你可以点击左侧的“结果页”，进入更适合阅读和展示的单独页面。",
                    chips=[
                        f"shortlist {len(active_values.get('shortlist', []))}",
                        f"优化轮次 {active_values.get('optimization_round', 0)}",
                    ],
                )
            else:
                render_empty_state(
                    "这块区域现在只做工作台摘要。等你跑完一次完整分析后，最终建议会自动跳转到新的结果页里展示。"
                )

            if active_values.get("revision_notes"):
                render_story_card(
                    "最近一次简历优化",
                    active_values["revision_notes"][-1],
                    chips=[f"累计优化 {len(active_values['revision_notes'])} 次"],
                )

            if featured_result:
                render_story_card(
                    "精选历史结果",
                    featured_result["summary"],
                    chips=[
                        featured_result["label"],
                        featured_result["updated_at"],
                        "可直接进入结果页",
                    ],
                )

        with st.container(border=True):
            render_section_intro(
                "Library",
                "我的历史结果列表",
                "这里会聚合你账号下所有会话的结果状态。你可以把它理解成一个轻量的个人分析归档区。",
            )
            render_metric_grid(
                [
                    ("总会话数", str(len(result_cards))),
                    ("已出报告", str(completed_count)),
                    ("进行中", str(len(result_cards) - completed_count)),
                    ("当前查看", get_session_label(account, st.session_state.thread_id)),
                ]
            )
            if result_cards:
                for card in result_cards:
                    render_session_result_card(
                        title=card["label"],
                        session_label=card["label"],
                        updated_at=card["updated_at"],
                        status_text=card["status_text"],
                        status_kind=card["status_kind"],
                        summary=card["summary"],
                        chips=card["chips"],
                    )
                    action_left, action_right = st.columns([0.9, 1.1])
                    with action_left:
                        if st.button(
                            f"切换到 {card['label']}",
                            key=f"open-session-{card['thread_id']}",
                            use_container_width=True,
                        ):
                            st.session_state.thread_id = card["thread_id"]
                            set_active_thread(account, card["thread_id"])
                            st.session_state.last_result = None
                            load_current_session(app, card["thread_id"])
                            st.rerun()
                    with action_right:
                        if card["has_report"]:
                            if st.button(
                                f"查看 {card['label']} 的结果页",
                                key=f"open-report-{card['thread_id']}",
                                use_container_width=True,
                            ):
                                st.session_state.thread_id = card["thread_id"]
                                set_active_thread(account, card["thread_id"])
                                st.session_state.last_result = get_session_values(
                                    app, build_config(card["thread_id"])
                                )
                                st.switch_page("pages/01_Final_Report.py")
                        else:
                            st.caption("这个会话还没有生成最终建议。")


def render_session_tab(values: dict[str, Any]) -> None:
    if not values:
        render_empty_state("还没有读取到当前会话数据。你可以先运行分析，或者在左侧点击“读取会话”。")
        return

    summary = summarize_session(values)
    render_metric_grid(
        [
            ("岗位数", str(summary["jobs_count"])),
            ("分析数", str(summary["analyses_count"])),
            ("匹配数", str(summary["matches_count"])),
            ("优化轮次", str(summary["optimization_round"])),
        ]
    )

    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            render_section_intro(
                "Session",
                "当前会话摘要",
                "这里保留当前 thread 的关键运行状态，方便你调试图执行结果。",
            )
            st.json(summary, expanded=True)

    with right:
        with st.container(border=True):
            render_section_intro(
                "Preview",
                "结果概览",
                "如果当前会话已经生成最终建议，这里会显示摘要说明；完整内容请进入结果页查看。",
            )
            if values.get("final_report"):
                preview = values["final_report"][:260] + ("..." if len(values["final_report"]) > 260 else "")
                render_story_card(
                    "最终建议预览",
                    preview,
                    chips=[f"推荐岗位 {len(values.get('shortlist', []))} 个"],
                )
            else:
                render_empty_state("当前会话还没有 final_report。")

    analyses = values.get("analyses", [])
    if analyses:
        with st.container(border=True):
            render_section_intro("Analysis", "岗位分析结果", "以下是当前会话中已写入状态的岗位分析数据。")
            st.dataframe(analyses, use_container_width=True)

    matches = get_active_matches(values)
    if matches:
        with st.container(border=True):
            render_section_intro("Match", "当前轮匹配结果", "这里只展示当前 optimization_round 对应的匹配结果。")
            st.dataframe(matches, use_container_width=True)


def render_history_tab(history_rows: list[dict[str, Any]]) -> None:
    if not history_rows:
        render_empty_state("还没有历史快照数据。你可以在左侧点击“读历史”后回到这里查看。")
        return

    with st.container(border=True):
        render_section_intro(
            "History",
            "Checkpoint 时间线",
            "这里展示 SQLite checkpoint 保存下来的历史快照，适合你观察图的状态演进。",
        )
        st.dataframe(history_rows, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="LangGraph 求职助手",
        page_icon=":newspaper:",
        layout="wide",
    )
    inject_app_styles()
    init_page_state()

    if not st.session_state.user_account:
        render_auth_page()
        return

    profile = sync_user_profile()
    if not profile:
        return

    app = get_app()
    jobs = get_jobs()
    render_sidebar(profile, app, jobs)

    render_hero(
        title="基于 LangGraph 的轻量多智能体实习求职助手",
        subtitle=(
            f"欢迎回来，{profile['nickname']}。现在你看到的是个人工作台：左侧管理账号与会话，"
            "中间专注输入与运行，最终建议会进入单独页面阅读。"
        ),
        kicker="Personal Job Copilot",
    )

    active_values = get_display_values()
    render_metric_grid(
        [
            ("当前账号", profile["account"]),
            ("活跃会话", get_session_label(profile["account"], st.session_state.thread_id)),
            ("岗位数据", str(len(jobs))),
            ("Checkpoint", "SQLite"),
        ]
    )

    tab_run, tab_session, tab_history = st.tabs(["开始分析", "当前会话", "历史快照"])

    with tab_run:
        render_run_tab(app, jobs, profile)

    with tab_session:
        render_session_tab(active_values or st.session_state.loaded_session or {})

    with tab_history:
        render_history_tab(st.session_state.history_rows)


if __name__ == "__main__":
    main()
