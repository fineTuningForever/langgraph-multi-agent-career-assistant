from __future__ import annotations

import argparse

from src.graph import build_graph
from src.session_service import (
    DEFAULT_MESSAGE,
    DEFAULT_USER_GOAL,
    build_config,
    build_fresh_input,
    generate_thread_id,
    get_session_values,
    get_state_history_rows,
    resolve_resume_text,
)
from src.utils import get_checkpoint_db_path, load_env, load_jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="基于 LangGraph 的轻量多智能体实习求职助手"
    )
    parser.add_argument(
        "--thread-id",
        help="指定会话 thread_id。不传则自动生成一个新的会话 ID。",
    )
    parser.add_argument(
        "--message",
        default=DEFAULT_MESSAGE,
        help="本次运行的用户请求消息。",
    )
    parser.add_argument(
        "--user-goal",
        help="覆盖默认求职目标。",
    )
    parser.add_argument(
        "--resume-path",
        help="从指定文件读取简历内容，支持 txt / md 等文本格式。",
    )
    parser.add_argument(
        "--resume-text",
        help="直接在命令行中传入简历文本。",
    )
    parser.add_argument(
        "--max-optimization-rounds",
        type=int,
        default=1,
        help="最多允许多少轮简历优化回路。",
    )

    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--show-session",
        action="store_true",
        help="只读取并展示当前 thread_id 对应的最新会话状态，不重新运行图。",
    )
    action_group.add_argument(
        "--show-history",
        action="store_true",
        help="展示当前 thread_id 的历史 checkpoint 快照。",
    )
    action_group.add_argument(
        "--continue-session",
        action="store_true",
        help="基于指定 thread_id 的已保存状态继续分析。",
    )

    parser.add_argument(
        "--history-limit",
        type=int,
        default=10,
        help="查看历史快照时最多输出多少条。",
    )
    return parser.parse_args()
def resolve_thread_id(args: argparse.Namespace) -> str:
    if args.thread_id:
        return args.thread_id
    return generate_thread_id()


def print_session_summary(thread_id: str, values: dict[str, Any]) -> None:
    print(f"checkpoint_db: {get_checkpoint_db_path()}")
    print(f"thread_id: {thread_id}")
    print("=" * 60)
    print("会话摘要")
    print("=" * 60)
    if not values:
        print("当前 thread_id 还没有保存的会话状态。")
        return

    print(f"user_goal: {values.get('user_goal', '')}")
    print(f"jobs_count: {len(values.get('jobs', []))}")
    print(f"analyses_count: {len(values.get('analyses', []))}")
    print(f"matches_count: {len(values.get('matches', []))}")
    print(f"optimization_round: {values.get('optimization_round', 0)}")
    print(f"has_final_report: {bool(values.get('final_report'))}")
    print(f"shortlist: {values.get('shortlist', [])}")
    print(f"revision_notes: {values.get('revision_notes', [])}")


def print_state_history(app, config: dict[str, Any], limit: int) -> None:
    snapshots = get_state_history_rows(app, config, limit)
    print(f"checkpoint_db: {get_checkpoint_db_path()}")
    print(f"thread_id: {config['configurable']['thread_id']}")
    print("=" * 60)
    print("历史快照")
    print("=" * 60)
    if not snapshots:
        print("当前 thread_id 没有历史快照。")
        return

    for index, snapshot in enumerate(snapshots, start=1):
        print(f"{index}. created_at={snapshot['created_at']}")
        print(f"   next={tuple(snapshot['next'])}")
        print(f"   step={snapshot['step']}, source={snapshot['source']}")
        print(
            "   analyses={analyses}, matches={matches}, has_report={report}, round={round}".format(
                analyses=snapshot["analyses_count"],
                matches=snapshot["matches_count"],
                report=snapshot["has_final_report"],
                round=snapshot["optimization_round"],
            )
        )


def print_result(thread_id: str, result: dict[str, Any]) -> None:
    print(f"checkpoint_db: {get_checkpoint_db_path()}")
    print(f"thread_id: {thread_id}")
    print("=" * 60)
    print("最终投递建议")
    print("=" * 60)
    print(result.get("final_report", "未生成 final_report，请检查图流程或模型返回。"))
    print("\n" + "=" * 60)
    print("推荐岗位 ID")
    print("=" * 60)
    print(result.get("shortlist", []))
    print("\n" + "=" * 60)
    print("简历优化记录")
    print("=" * 60)
    print(result.get("revision_notes", []))


def main() -> None:
    # 1. 加载环境变量、解析参数并构建图实例。
    load_env()
    args = parse_args()
    app = build_graph()

    thread_id = resolve_thread_id(args)
    config = build_config(thread_id)

    # 2. 支持直接查看某个 thread_id 对应的最新会话状态。
    if args.show_session:
        values = get_session_values(app, config)
        print_session_summary(thread_id, values)
        return

    # 3. 支持查看某个 thread_id 的历史 checkpoint 快照。
    if args.show_history:
        print_state_history(app, config, args.history_limit)
        return

    # 4. 继续历史会话时，会先读取保存状态。
    #    如果已有状态，则默认沿用之前的 user_goal / resume / jobs；
    #    如果命令行传了新值，则优先使用新值，并在同一个 thread_id 下重新跑一轮。
    if args.continue_session:
        saved_values = get_session_values(app, config)
        if not saved_values:
            print(f"thread_id={thread_id} 当前没有已保存会话，无法继续。")
            return

        user_goal = args.user_goal or saved_values.get("user_goal") or DEFAULT_USER_GOAL
        resume_text = resolve_resume_text(
            resume_text=args.resume_text,
            resume_path=args.resume_path,
            fallback=saved_values.get("resume_text"),
        )
        jobs = saved_values.get("jobs") or load_jobs()
        result = app.invoke(
            build_fresh_input(
                user_goal=user_goal,
                resume_text=resume_text,
                jobs=jobs,
                message=args.message,
                max_optimization_rounds=args.max_optimization_rounds,
            ),
            config=config,
        )
        print_result(thread_id, result)
        return

    # 5. 默认模式：启动一条新分析。
    user_goal = args.user_goal or DEFAULT_USER_GOAL
    resume_text = resolve_resume_text(
        resume_text=args.resume_text,
        resume_path=args.resume_path,
    )
    jobs = load_jobs()
    result = app.invoke(
        build_fresh_input(
            user_goal=user_goal,
            resume_text=resume_text,
            jobs=jobs,
            message=args.message,
            max_optimization_rounds=args.max_optimization_rounds,
        ),
        config=config,
    )
    print_result(thread_id, result)


if __name__ == "__main__":
    main()
