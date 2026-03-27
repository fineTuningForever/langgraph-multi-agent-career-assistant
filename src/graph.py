from __future__ import annotations

import sqlite3
from functools import lru_cache
from statistics import mean
from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import Command, Send

from src.agents import (
    coach_report,
    extract_job_requirements,
    optimize_resume,
    position_job_for_candidate,
    score_match,
    supervisor_decide,
)
from src.models import InternshipAgentState, SingleJobAnalysisState, SingleMatchState
from src.utils import get_checkpoint_db_path


@lru_cache(maxsize=1)
def build_sqlite_checkpointer() -> SqliteSaver:
    # 第二版升级后的默认 checkpoint 实现：
    # 使用 SQLite 持久化图状态，而不是仅保存在进程内存中。
    #
    # 这里用缓存确保整个进程里只复用一份连接，
    # 避免多次 build_graph() 时重复打开数据库连接。
    conn = sqlite3.connect(get_checkpoint_db_path(), check_same_thread=False)
    return SqliteSaver(conn)


def _get_active_matches(state: InternshipAgentState) -> list[dict]:
    # matches 会保留历史轮次的结果。
    # 第二版加入低分回路后，必须只筛出“当前轮”的匹配结果参与决策。
    current_round = state.get("optimization_round", 0)
    return [
        item
        for item in state.get("matches", [])
        if item.get("review_round", 0) == current_round
    ]


def _build_supervisor_payload(state: InternshipAgentState) -> str:
    # 给 Supervisor 的不是整份原始状态，而是浓缩后的关键指标。
    # 这样更像给它一个“决策面板”，能减少无关信息干扰。
    matches = _get_active_matches(state)
    scores = [item["score"] for item in matches]
    high_count = sum(1 for item in matches if item["verdict"] == "high")
    average_score = round(mean(scores), 2) if scores else 0

    return f"""
用户求职目标：
{state['user_goal']}

当前状态摘要：
- jobs_count: {len(state.get('jobs', []))}
- analyses_count: {len(state.get('analyses', []))}
- matches_count: {len(matches)}
- high_match_count: {high_count}
- average_score: {average_score}
- optimization_round: {state.get('optimization_round', 0)}
- max_optimization_rounds: {state.get('max_optimization_rounds', 1)}
- has_final_report: {bool(state.get('final_report'))}

请基于上面信息决定下一步动作。
"""


def _fallback_supervisor_step(state: InternshipAgentState) -> tuple[str, str]:
    # 这是 Supervisor 的代码级兜底策略。
    # 就算模型输出异常，图也能按稳定逻辑继续走。
    matches = _get_active_matches(state)
    scores = [item["score"] for item in matches]
    high_count = sum(1 for item in matches if item["verdict"] == "high")
    average_score = mean(scores) if scores else 0

    if state.get("final_report"):
        return "finish", "最终报告已经生成，流程可以结束。"
    if not state.get("analyses"):
        return "analyze_jobs", "当前没有岗位分析结果，先分析岗位。"
    if not matches:
        return "review_matches", "岗位分析已完成，但还没有匹配结果，先进行简历匹配。"
    if high_count == 0 and average_score < 75 and state.get("optimization_round", 0) < state.get("max_optimization_rounds", 1):
        return "optimize_resume", "当前整体匹配度偏低，先优化简历再重新评估。"
    return "coach", "当前已有可用的岗位分析与匹配结果，进入求职建议阶段。"


def _is_step_allowed(state: InternshipAgentState, step: str) -> bool:
    # 即使模型给出了某个 next_step，我们也要检查当前状态是否允许这样跳。
    # 这是为了防止“连续优化”“提前 finish”等非法或无效决策。
    active_matches = _get_active_matches(state)
    has_analyses = bool(state.get("analyses"))
    has_report = bool(state.get("final_report"))
    rounds_left = state.get("optimization_round", 0) < state.get("max_optimization_rounds", 1)

    if step == "analyze_jobs":
        return not has_analyses
    if step == "review_matches":
        return has_analyses and not active_matches
    if step == "optimize_resume":
        return bool(active_matches) and rounds_left
    if step == "coach":
        return bool(active_matches)
    if step == "finish":
        return has_report
    return False


def supervisor_node(
    state: InternshipAgentState,
) -> Command[Literal["job_analysis_flow", "match_flow", "resume_optimizer", "career_coach", "finish_node"]]:
    # Supervisor 是第二版的核心节点。
    # 它不再只是补理由，而是会：
    # 1. 先根据代码规则得到保底策略
    # 2. 再让模型做更灵活的策略判断
    # 3. 最后用状态约束过滤非法跳转
    fallback_step, fallback_reason = _fallback_supervisor_step(state)

    try:
        decision = supervisor_decide(_build_supervisor_payload(state))
        next_step = decision.get("next_step", fallback_step)
        reason = decision.get("reason", fallback_reason)
    except Exception:
        next_step = fallback_step
        reason = fallback_reason

    allowed_steps = {"analyze_jobs", "review_matches", "optimize_resume", "coach", "finish"}
    if next_step not in allowed_steps:
        next_step = fallback_step
        reason = fallback_reason

    if not _is_step_allowed(state, next_step):
        next_step = fallback_step
        reason = fallback_reason

    if state.get("final_report"):
        next_step = "finish"

    if next_step == "analyze_jobs":
        # 岗位分析阶段使用 Send 并行分发到单岗位分析子图。
        goto = [
            Send(
                "job_analysis_flow",
                {
                    "job": job,
                    "goal_context": state["user_goal"],
                },
            )
            for job in state.get("jobs", [])
        ]
    elif next_step == "review_matches":
        # 匹配阶段也采用 Send，并把当前轮次带入每个匹配子图。
        analysis_map = {item["job_id"]: item for item in state.get("analyses", [])}
        goto = [
            Send(
                "match_flow",
                {
                    "job": job,
                    "analysis_snapshot": analysis_map[job["job_id"]],
                    "resume_snapshot": state["resume_text"],
                    "review_round": state.get("optimization_round", 0),
                },
            )
            for job in state.get("jobs", [])
            if job["job_id"] in analysis_map
        ]
    elif next_step == "optimize_resume":
        goto = "resume_optimizer"
    elif next_step == "coach":
        goto = "career_coach"
    else:
        goto = "finish_node"

    return Command(
        # Command 的价值在于“更新状态 + 指定跳转目标”一次完成。
        # 这比第一版那种“先写 next_step，再靠条件边路由”更像真正的图式控制。
        update={
            "next_step": next_step,
            "strategy_reason": reason,
            "messages": [AIMessage(content=f"Supervisor 决策：{next_step}。原因：{reason}")],
        },
        goto=goto,
    )


def extract_requirements_node(
    state: SingleJobAnalysisState,
) -> Command[Literal["position_job_node"]]:
    # 岗位分析子图第 1 步：
    # 先提取岗位要求，再显式跳转到下一步定位节点。
    requirements = extract_job_requirements(state["job"], state["goal_context"])
    return Command(update={"job_requirements": requirements}, goto="position_job_node")


def position_job_node(state: SingleJobAnalysisState) -> dict:
    # 岗位分析子图第 2 步：
    # 在事实提取结果基础上，补上对当前候选人的解释性结论。
    positioning = position_job_for_candidate(
        job=state["job"],
        user_goal=state["goal_context"],
        job_requirements=state["job_requirements"],
    )
    return {
        "analyses": [
            {
                "job_id": state["job"]["job_id"],
                "city": state["job"]["city"],
                **state["job_requirements"],
                **positioning,
            }
        ]
    }


def score_match_node(state: SingleMatchState) -> dict:
    # 匹配子图第 1 步：针对单个岗位给出分数、优势、短板和投递策略。
    result = score_match(
        job=state["job"],
        analysis=state["analysis_snapshot"],
        resume_text=state["resume_snapshot"],
    )
    return {
        "match_result": {
            "job_id": state["job"]["job_id"],
            "review_round": state["review_round"],
            **result,
        }
    }


def finalize_match_node(state: SingleMatchState) -> dict:
    # 匹配子图第 2 步：把单岗位结果包装成可汇总回父图的结构。
    return {"matches": [state["match_result"]]}


def resume_optimizer_node(
    state: InternshipAgentState,
) -> Command[Literal["supervisor"]]:
    # 低分回路节点：
    # 当当前轮整体匹配偏低时，先优化简历表达，再回到 Supervisor 重新触发匹配。
    optimized = optimize_resume(
        user_goal=state["user_goal"],
        resume_text=state["resume_text"],
        matches=state.get("matches", []),
        optimization_round=state.get("optimization_round", 0),
    )
    next_round = state.get("optimization_round", 0) + 1
    note = optimized.get("revision_note", f"完成第 {next_round} 轮简历优化。")

    return Command(
        update={
            # 后续节点直接使用优化后的简历版本。
            "resume_text": optimized["optimized_resume"],
            "optimization_round": next_round,
            "shortlist": [],
            "revision_notes": [note],
            "messages": [AIMessage(content=f"Resume Optimizer 已完成第 {next_round} 轮简历优化。")],
        },
        goto="supervisor",
    )


def career_coach_node(
    state: InternshipAgentState,
) -> Command[Literal["supervisor"]]:
    # 最终报告节点只看“当前轮”匹配结果，
    # 避免历史轮次的旧结果干扰最终建议。
    matches = _get_active_matches(state)
    shortlist = [
        match["job_id"]
        for match in sorted(matches, key=lambda item: item["score"], reverse=True)
        if match["score"] >= 70
    ][:3]

    report = coach_report(
        user_goal=state["user_goal"],
        analyses=state.get("analyses", []),
        matches=matches,
        revision_notes=state.get("revision_notes", []),
    )
    return Command(
        update={
            "shortlist": shortlist,
            "final_report": report,
            "messages": [AIMessage(content="Career Coach 已生成求职建议报告。")],
        },
        goto="supervisor",
    )


def finish_node(state: InternshipAgentState) -> dict:
    # 结束节点本身不做复杂业务，只作为整张图的显式终点。
    return {
        "messages": [AIMessage(content="流程结束，最终状态已准备完毕。")]
    }


def build_job_analysis_subgraph():
    # 真正的岗位分析子图：先抽取岗位要求，再做岗位定位。
    graph = StateGraph(SingleJobAnalysisState)
    graph.add_node("extract_requirements_node", extract_requirements_node)
    graph.add_node("position_job_node", position_job_node)
    graph.add_edge(START, "extract_requirements_node")
    graph.add_edge("position_job_node", END)
    return graph.compile()


def build_match_subgraph():
    # 真正的匹配子图：先评分，再标准化回写。
    graph = StateGraph(SingleMatchState)
    graph.add_node("score_match_node", score_match_node)
    graph.add_node("finalize_match_node", finalize_match_node)
    graph.add_edge(START, "score_match_node")
    graph.add_edge("score_match_node", "finalize_match_node")
    graph.add_edge("finalize_match_node", END)
    return graph.compile()


def build_graph():
    # 主图只保留“策略调度”和“阶段节点”，
    # 单岗位分析、单岗位匹配这些细粒度工作交给子图处理。
    graph = StateGraph(InternshipAgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("job_analysis_flow", build_job_analysis_subgraph())
    graph.add_node("match_flow", build_match_subgraph())
    graph.add_node("resume_optimizer", resume_optimizer_node)
    graph.add_node("career_coach", career_coach_node)
    graph.add_node("finish_node", finish_node)

    graph.add_edge(START, "supervisor")
    graph.add_edge("job_analysis_flow", "supervisor")
    graph.add_edge("match_flow", "supervisor")
    graph.add_edge("finish_node", END)

    # 当前版本默认使用 SQLite checkpoint。
    # 这意味着图状态会持久化到磁盘，下次运行时只要 thread_id 一样，就能恢复同一条会话。
    return graph.compile(checkpointer=build_sqlite_checkpointer())
