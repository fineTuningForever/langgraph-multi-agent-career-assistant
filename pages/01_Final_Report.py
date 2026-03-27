from __future__ import annotations

from typing import Any

import streamlit as st

from src.frontend_service import (
    get_session_label,
    get_user_profile,
    inject_app_styles,
    render_empty_state,
    render_hero,
    render_job_article_card,
    render_metric_grid,
    render_profile_card,
    render_section_intro,
    render_story_card,
)
from src.graph import build_graph
from src.session_service import build_config, get_session_values
from src.utils import load_env


@st.cache_resource
def get_app():
    load_env()
    return build_graph()


def get_active_matches(values: dict[str, Any]) -> list[dict[str, Any]]:
    current_round = values.get("optimization_round", 0)
    return [
        item
        for item in values.get("matches", [])
        if item.get("review_round", 0) == current_round
    ]


def logout() -> None:
    st.session_state.user_account = None
    st.session_state.user_profile = None
    st.session_state.thread_id = ""
    st.session_state.loaded_session = None
    st.session_state.last_result = None
    st.session_state.history_rows = []
    st.switch_page("streamlit_app.py")


def get_report_values() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    account = st.session_state.get("user_account")
    if not account:
        return None, None

    profile = get_user_profile(account)
    if not profile:
        return None, None

    thread_id = st.session_state.get("thread_id") or profile.get("active_thread_id")
    st.session_state.thread_id = thread_id
    app = get_app()

    values = st.session_state.get("last_result")
    if not values or not values.get("final_report"):
        values = get_session_values(app, build_config(thread_id))
        st.session_state.loaded_session = values

    return profile, values


def build_shortlist_cards(values: dict[str, Any]) -> list[dict[str, Any]]:
    analyses_map = {item["job_id"]: item for item in values.get("analyses", [])}
    matches_map = {item["job_id"]: item for item in get_active_matches(values)}
    jobs_map = {item["job_id"]: item for item in values.get("jobs", [])}
    cards = []
    for job_id in values.get("shortlist", []):
        analysis = analyses_map.get(job_id, {})
        match = matches_map.get(job_id, {})
        job = jobs_map.get(job_id, {})
        title = job.get("title") or analysis.get("summary") or job_id
        cards.append(
            {
                "job_id": job_id,
                "title": title,
                "company": job.get("company", "未知公司"),
                "city": analysis.get("city", "未知"),
                "score": str(match.get("score", "-")),
                "verdict": match.get("verdict", "unknown"),
                "strategy": match.get("application_strategy", "待补充"),
                "reason": analysis.get("recommendation_reason", "当前没有生成额外推荐理由。"),
                "skills": analysis.get("core_skills", []) + analysis.get("bonus_skills", []),
                "gaps": match.get("gaps", []),
            }
        )
    return cards


def main() -> None:
    st.set_page_config(
        page_title="最终建议页",
        page_icon=":bookmark_tabs:",
        layout="wide",
    )
    inject_app_styles()

    profile, values = get_report_values()
    if not profile:
        st.warning("还没有登录，正在返回首页。")
        if st.button("返回首页", use_container_width=True):
            st.switch_page("streamlit_app.py")
        return

    with st.sidebar:
        render_profile_card(profile, get_session_label(profile["account"], st.session_state.thread_id))
        if st.button("返回工作台", use_container_width=True):
            st.switch_page("streamlit_app.py")
        if st.button("刷新结果", use_container_width=True):
            st.session_state.last_result = None
            st.rerun()
        if st.button("退出登录", use_container_width=True):
            logout()
        with st.expander("当前会话", expanded=False):
            st.caption(f"thread_id: {st.session_state.thread_id}")

    if not values or not values.get("final_report"):
        render_hero(
            title="最终建议还没有准备好",
            subtitle="当前会话还没有生成 final_report。你可以先回到工作台运行一次完整分析，再进入这个页面阅读结果。",
            kicker="Report Pending",
        )
        render_empty_state("现在还没有可展示的最终建议。")
        if st.button("回到工作台继续分析", use_container_width=False):
            st.switch_page("streamlit_app.py")
        return

    shortlist_cards = build_shortlist_cards(values)
    active_matches = get_active_matches(values)

    render_hero(
        title="最终建议",
        subtitle=(
            "这是独立的阅读页。它更像博客或专栏页，不再和表单挤在同一屏里，"
            "适合你做项目演示、截图或者直接放到 README 中展示。"
        ),
        kicker="Final Report",
    )

    render_metric_grid(
        [
            ("推荐岗位", str(len(values.get("shortlist", [])))),
            ("当前轮匹配", str(len(active_matches))),
            ("优化轮次", str(values.get("optimization_round", 0))),
            ("会话标签", get_session_label(profile["account"], st.session_state.thread_id)),
        ]
    )

    main_col, side_col = st.columns([1.35, 0.75], gap="large")

    with main_col:
        with st.container(border=True):
            render_section_intro(
                "Article",
                "求职建议正文",
                "这里保留自然语言报告本身，尽量让阅读体验更接近博客正文，而不是控制台输出。",
            )
            st.markdown(values.get("final_report", "未生成最终建议。"))

        with st.container(border=True):
            render_section_intro(
                "Recommendation",
                "优先投递岗位",
                "下面这组卡片更偏博客式阅读体验，会把公司、城市、匹配分、投递策略、技能标签和短板放在一起。",
            )
            if shortlist_cards:
                cols = st.columns(2, gap="large")
                for idx, card in enumerate(shortlist_cards):
                    with cols[idx % 2]:
                        render_job_article_card(
                            title=f"{card['title']} · {card['company']}",
                            city=card["city"],
                            score=card["score"],
                            verdict=card["verdict"],
                            strategy=card["strategy"],
                            reason=card["reason"],
                            skill_tags=card["skills"],
                            gap_tags=card["gaps"],
                            job_id=card["job_id"],
                        )
            else:
                render_empty_state("当前没有 shortlist，可回到工作台重新调整目标或简历。")

    with side_col:
        with st.container(border=True):
            render_section_intro(
                "Snapshot",
                "会话快照",
                "把这次分析最关键的状态压缩成一眼能扫完的摘要，方便演示时快速讲清楚。",
            )
            render_story_card(
                "当前目标",
                values.get("user_goal", "未记录求职目标。"),
                chips=[
                    f"analyses {len(values.get('analyses', []))}",
                    f"matches {len(values.get('matches', []))}",
                ],
            )

        with st.container(border=True):
            render_section_intro(
                "Revision",
                "简历优化记录",
                "如果低分回路触发过，这里会按时间顺序保留每轮优化说明。",
            )
            revision_notes = values.get("revision_notes", [])
            if revision_notes:
                for idx, note in enumerate(revision_notes, start=1):
                    render_story_card(f"第 {idx} 轮优化", note)
            else:
                render_empty_state("当前会话没有发生简历优化。")

    with st.container(border=True):
        render_section_intro(
            "Data",
            "结构化明细",
            "如果你要调试状态流转或给面试官看结构化结果，这一层会更直接。",
        )
        detail_tab1, detail_tab2 = st.tabs(["岗位分析", "当前轮匹配"])
        with detail_tab1:
            if values.get("analyses"):
                st.dataframe(values["analyses"], use_container_width=True)
            else:
                render_empty_state("当前还没有岗位分析结果。")
        with detail_tab2:
            if active_matches:
                st.dataframe(active_matches, use_container_width=True)
            else:
                render_empty_state("当前还没有当前轮匹配结果。")


if __name__ == "__main__":
    main()
