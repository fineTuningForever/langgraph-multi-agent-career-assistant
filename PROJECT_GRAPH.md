# 项目 Graph 结构图

下面这张图对应当前项目里的实际 LangGraph 结构，重点标出了：

- 主图与两个子图的关系
- `Command` 如何同时完成状态更新和节点跳转
- `Send` 如何并行分发单岗位任务，并在结束后自动汇总回主图
- 低分回路在什么条件下触发

```mermaid
flowchart TD
    classDef note fill:#FFF7E6,stroke:#D48806,color:#613400
    classDef graph fill:#F6FFED,stroke:#389E0D,color:#135200
    classDef node fill:#E6F4FF,stroke:#1677FF,color:#10239E
    classDef state fill:#F9F0FF,stroke:#722ED1,color:#391085

    START([START]):::graph --> SUP[supervisor_node]:::node
    FIN[finish_node]:::node --> END([END]):::graph

    subgraph MAIN[主图 Main Graph]
        SUP -->|"Command.update<br/>next_step<br/>strategy_reason<br/>messages += Supervisor 决策消息"| DECIDE{{Supervisor 决策后选择 goto}}:::node

        DECIDE -->|"next_step = analyze_jobs<br/>条件：当前还没有 analyses"| SEND_JOBS[[Send 并行分发<br/>job_analysis_flow x N]]:::graph
        DECIDE -->|"next_step = review_matches<br/>条件：已有 analyses 且当前轮没有 active_matches"| SEND_MATCH[[Send 并行分发<br/>match_flow x N]]:::graph
        DECIDE -->|"next_step = optimize_resume<br/>条件：触发低分回路"| OPT[resume_optimizer_node]:::node
        DECIDE -->|"next_step = coach<br/>条件：当前轮已有可用匹配结果"| COACH[career_coach_node]:::node
        DECIDE -->|"next_step = finish<br/>条件：final_report 已存在"| FIN

        OPT -->|"Command.update<br/>resume_text = optimized_resume<br/>optimization_round += 1<br/>shortlist = []<br/>revision_notes += revision_note<br/>messages += 优化完成消息<br/>goto supervisor"| SUP

        COACH -->|"Command.update<br/>shortlist = Top 3(score >= 70)<br/>final_report = coach_report(...active_matches...)<br/>messages += 报告完成消息<br/>goto supervisor"| SUP
    end

    subgraph JOB_SUB[子图 job_analysis_flow]
        JA1[extract_requirements_node]:::node -->|"Command.update<br/>job_requirements = extract_job_requirements(...)<br/>goto position_job_node"| JA2[position_job_node]:::node
        JA2 -->|"return<br/>analyses += [JobAnalysis]"| JA_OUT[[并行汇总回主图 analyses]]:::state
    end

    subgraph MATCH_SUB[子图 match_flow]
        MA1[score_match_node]:::node -->|"return<br/>match_result = score_match(...)"| MA2[finalize_match_node]:::node
        MA2 -->|"return<br/>matches += [MatchResult(review_round=当前 optimization_round)]"| MA_OUT[[并行汇总回主图 matches]]:::state
    end

    SEND_JOBS -->|"每个岗位发送 1 条 Send<br/>{ job, goal_context }"| JA1
    JA_OUT -->|"所有并行岗位分析结束后回到主图"| SUP

    SEND_MATCH -->|"每个已分析岗位发送 1 条 Send<br/>{ job, analysis_snapshot, resume_snapshot, review_round }"| MA1
    MA_OUT -->|"所有并行岗位匹配结束后回到主图"| SUP

    ACTIVE["active_matches = 仅筛选<br/>review_round == optimization_round 的匹配结果"]:::note
    LOW_LOOP["低分回路触发条件：<br/>high_count == 0<br/>AND average_score < 75<br/>AND optimization_round < max_optimization_rounds"]:::note
    GUARD["Supervisor 实际决策机制：<br/>1. 先走 fallback 代码兜底<br/>2. 再参考 LLM 决策<br/>3. 最后经过 _is_step_allowed 合法性校验"]:::note

    ACTIVE -.-> SEND_MATCH
    ACTIVE -.-> COACH
    LOW_LOOP -.-> OPT
    GUARD -.-> SUP
```

## 图中对应的核心语义

- `supervisor_node` 不是单纯路由器，它会先得到一个保底策略，再结合 LLM 决策，最后再做一步合法性校验，防止提前结束或重复优化。
- `job_analysis_flow` 是“单岗位分析子图”，由“提取岗位要求”与“岗位定位”两步组成；主图通过 `Send` 把多个岗位拆成多个并行任务。
- `match_flow` 是“单岗位匹配子图”，由“单岗位评分”与“结果标准化回写”两步组成；多个岗位匹配结果会自动聚合回主图的 `matches`。
- `resume_optimizer_node` 只在低分回路条件满足时执行，并且会把优化后的简历覆盖回 `resume_text`，再回到 `supervisor_node` 发起下一轮匹配。
- `career_coach_node` 只看当前轮 `active_matches`，避免旧轮次的匹配结果污染最终建议。

## 实际运行顺序

### 正常链路

`START -> supervisor -> Send(job_analysis_flow x N) -> supervisor -> Send(match_flow x N) -> supervisor -> career_coach -> supervisor -> finish_node -> END`

### 低分回路链路

`START -> supervisor -> Send(job_analysis_flow x N) -> supervisor -> Send(match_flow x N) -> supervisor -> resume_optimizer -> supervisor -> Send(match_flow x N) -> supervisor -> career_coach -> supervisor -> finish_node -> END`
