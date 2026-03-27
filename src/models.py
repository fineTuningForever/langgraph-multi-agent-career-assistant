from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.graph import add_messages


# 原始岗位信息。
# 这类对象通常来自本地 JSON、数据库或招聘网站抓取结果，
# 代表“模型尚未处理过的输入数据”。
class JobPosting(TypedDict):
    job_id: str
    company: str
    title: str
    city: str
    description: str


# 岗位分析子图第一阶段的产物。
# 这一层尽量只抽取事实，不急着做“适不适合投”的解释。
class JobRequirementsDraft(TypedDict):
    summary: str
    core_skills: list[str]
    bonus_skills: list[str]


# 单岗位分析完成后的最终结果。
# 相比 JobRequirementsDraft，这里额外加入了 recommendation_reason，
# 用来表达“这个岗位为什么值得当前用户关注”。
class JobAnalysis(TypedDict):
    job_id: str
    summary: str
    core_skills: list[str]
    bonus_skills: list[str]
    city: str
    recommendation_reason: str


# 岗位与简历匹配结果。
# review_round 很关键：第二版加入了低分回路，
# 所以需要用轮次区分“第几轮匹配结果”，否则历史结果会混在一起。
class MatchResult(TypedDict):
    job_id: str
    review_round: int
    score: int
    strengths: list[str]
    gaps: list[str]
    verdict: Literal["high", "medium", "low"]
    application_strategy: Literal["apply_now", "prepare_then_apply", "stretch"]


# 单岗位分析子图的局部状态。
# 这里故意使用 goal_context，而不是继续沿用父图里的 user_goal，
# 是为了避免并行子图运行时和父图状态字段发生冲突。
class SingleJobAnalysisState(TypedDict, total=False):
    job: JobPosting
    goal_context: str
    job_requirements: JobRequirementsDraft
    # analyses 是并行聚合字段。
    # 多个岗位分析子图结束后，各自返回一条结果，LangGraph 会自动把它们拼接起来。
    analyses: Annotated[list[JobAnalysis], add]


# 单岗位匹配子图的局部状态。
# 这部分状态只服务于“某一个岗位、某一轮简历”的匹配过程。
class SingleMatchState(TypedDict, total=False):
    job: JobPosting
    analysis_snapshot: JobAnalysis
    resume_snapshot: str
    review_round: int
    match_result: MatchResult
    # matches 同样是并行聚合字段，
    # 允许多个匹配子图把结果汇总回父图。
    matches: Annotated[list[MatchResult], add]


# 实习求职多智能体系统的全局状态。
# 你可以把它理解成：整张主图在运行过程中共享的一份“总上下文”。
class InternshipAgentState(TypedDict, total=False):
    # 消息通道，保留每一步的调度痕迹和系统反馈。
    messages: Annotated[list, add_messages]
    # 用户的求职目标，例如目标城市、岗位方向、技术关键词等。
    user_goal: str
    # 当前正在使用的简历文本。
    # 如果触发简历优化回路，这个字段会被优化后的版本覆盖。
    resume_text: str
    # 本次求职分析要处理的岗位列表。
    jobs: list[JobPosting]
    # 所有岗位分析结果，支持并行聚合。
    analyses: Annotated[list[JobAnalysis], add]
    # 所有匹配结果，包含历史轮次结果，当前轮结果需要结合 review_round 过滤。
    matches: Annotated[list[MatchResult], add]
    # 最终推荐投递的岗位 ID。
    shortlist: list[str]
    # 求职教练输出的最终报告。
    final_report: str
    # Supervisor 当前选择的下一步策略。
    next_step: Literal[
        "analyze_jobs",
        "review_matches",
        "optimize_resume",
        "coach",
        "finish",
    ]
    # 记录 Supervisor 给出的中文决策理由，便于调试和学习。
    strategy_reason: str
    # 当前已经做了多少轮“简历优化 -> 重新匹配”。
    optimization_round: int
    # 限制最大优化轮次，防止图无限循环。
    max_optimization_rounds: int
    # 保存每轮简历优化的说明，最终会提供给 Career Coach 生成更完整的报告。
    revision_notes: Annotated[list[str], add]
