from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.prompts import (
    CAREER_COACH_PROMPT,
    JOB_POSITIONING_PROMPT,
    JOB_REQUIREMENTS_PROMPT,
    MATCH_SCORING_PROMPT,
    RESUME_OPTIMIZER_PROMPT,
    SUPERVISOR_PROMPT,
)
from src.utils import get_base_url, get_model_name


# 角色到环境变量的映射表。
# 这样我们可以让不同智能体使用不同模型，而不是所有节点都共用一个模型。
ROLE_MODEL_ENV = {
    "supervisor": "SUPERVISOR_MODEL",
    "analyst": "ANALYST_MODEL",
    "reviewer": "REVIEWER_MODEL",
    "optimizer": "OPTIMIZER_MODEL",
    "coach": "COACH_MODEL",
}


def build_llm(role: str, temperature: float = 0.2) -> ChatOpenAI:
    # 根据角色选择模型，是第二版“按任务分配模型成本”的核心入口。
    # 例如抽取类任务可以用更便宜的模型，最终报告可以使用更强模型。
    kwargs: dict[str, Any] = {
        "model": get_model_name(ROLE_MODEL_ENV.get(role)),
        "temperature": temperature,
    }
    base_url = get_base_url()
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _parse_json_content(content: str) -> dict[str, Any]:
    # 大模型并不总是严格返回纯 JSON。
    # 这里依次兼容：
    # 1. 纯 JSON
    # 2. ```json 代码块
    # 3. 包裹在自然语言里的 JSON 对象
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        fenced_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if fenced_match:
            return json.loads(fenced_match.group(1).strip())

        generic_match = re.search(r"\{.*\}", content, re.DOTALL)
        if generic_match:
            return json.loads(generic_match.group(0).strip())

        raise ValueError(f"模型没有返回可解析的 JSON。原始内容：{content}")


def _invoke_json(role: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    # 统一封装“结构化输出”的模型调用逻辑，
    # 让各个专家函数只关心自己的输入和输出语义。
    llm = build_llm(role=role)
    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    return _parse_json_content(response.content)


def supervisor_decide(payload: str) -> dict[str, Any]:
    # Supervisor 负责策略决策，因此它产出的结构是 next_step + reason。
    return _invoke_json(
        role="supervisor",
        system_prompt=SUPERVISOR_PROMPT,
        user_prompt=payload,
    )


def extract_job_requirements(job: dict[str, Any], user_goal: str) -> dict[str, Any]:
    # 岗位分析子图第 1 步：先尽可能抽取客观事实。
    prompt = f"""
用户求职目标：
{user_goal}

岗位信息：
{json.dumps(job, ensure_ascii=False, indent=2)}
"""
    return _invoke_json("analyst", JOB_REQUIREMENTS_PROMPT, prompt)


def position_job_for_candidate(
    job: dict[str, Any],
    user_goal: str,
    job_requirements: dict[str, Any],
) -> dict[str, Any]:
    # 岗位分析子图第 2 步：在已有事实基础上，生成面向候选人的解释。
    prompt = f"""
用户求职目标：
{user_goal}

岗位信息：
{json.dumps(job, ensure_ascii=False, indent=2)}

岗位要求提取结果：
{json.dumps(job_requirements, ensure_ascii=False, indent=2)}
"""
    return _invoke_json("analyst", JOB_POSITIONING_PROMPT, prompt)


def score_match(job: dict[str, Any], analysis: dict[str, Any], resume_text: str) -> dict[str, Any]:
    # 匹配专家同时参考岗位原文、岗位分析结果和简历，
    # 这样比只看单侧信息更稳定。
    prompt = f"""
候选人简历：
{resume_text}

岗位信息：
{json.dumps(job, ensure_ascii=False, indent=2)}

岗位分析：
{json.dumps(analysis, ensure_ascii=False, indent=2)}
"""
    return _invoke_json("reviewer", MATCH_SCORING_PROMPT, prompt)


def optimize_resume(
    user_goal: str,
    resume_text: str,
    matches: list[dict[str, Any]],
    optimization_round: int,
) -> dict[str, Any]:
    # 低分回路的核心函数：
    # 根据上一轮匹配结果里的短板，重新组织简历表达，而不是虚构项目经历。
    prompt = f"""
用户求职目标：
{user_goal}

当前简历：
{resume_text}

当前匹配结果：
{json.dumps(matches, ensure_ascii=False, indent=2)}

当前是第 {optimization_round + 1} 轮优化。
"""
    return _invoke_json("optimizer", RESUME_OPTIMIZER_PROMPT, prompt)


def coach_report(
    user_goal: str,
    analyses: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    # 带上简历优化历史，是为了让最终报告更像一个完整求职过程，而不是单次评分。
    revision_notes: list[str],
) -> str:
    # 最终报告偏自然语言生成，因此这里不要求 JSON，直接返回文本。
    llm = build_llm(role="coach", temperature=0.4)
    prompt = f"""
用户求职目标：
{user_goal}

岗位分析结果：
{json.dumps(analyses, ensure_ascii=False, indent=2)}

匹配结果：
{json.dumps(matches, ensure_ascii=False, indent=2)}

简历优化历史：
{json.dumps(revision_notes, ensure_ascii=False, indent=2)}
"""
    response = llm.invoke(
        [
            SystemMessage(content=CAREER_COACH_PROMPT),
            HumanMessage(content=prompt),
        ]
    )
    return response.content
