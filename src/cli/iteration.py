"""iteration CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.iteration import EvaluationSampleResult, ModelEvaluation, get_iteration_runtime


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器."""
    parser = argparse.ArgumentParser(description="Manage iteration jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enqueue_parser = subparsers.add_parser("enqueue")
    enqueue_parser.add_argument("--request-file", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--job-id", required=True)

    worker_parser = subparsers.add_parser("worker")
    worker_parser.add_argument("--once", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime = get_iteration_runtime()

    if args.command == "enqueue":
        return _handle_enqueue(Path(args.request_file))
    if args.command == "status":
        return _handle_status(args.job_id)
    if args.command == "worker":
        return _handle_worker_once() if args.once else _handle_worker_drain()

    parser.error(f"unsupported command: {args.command}")
    return 1


def _handle_enqueue(request_file: Path) -> int:
    runtime = get_iteration_runtime()
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    job = _run_async(
        runtime.service.enqueue_job(
            action_id=payload["action_id"],
            baseline=_payload_to_model_evaluation(payload["baseline"]),
            candidate=_payload_to_model_evaluation(payload["candidate"]),
            trigger_reason=payload.get("trigger_reason", "manual"),
        )
    )
    print(f"job_id={job.job_id}")
    return 0


def _handle_status(job_id: str) -> int:
    runtime = get_iteration_runtime()
    job = runtime.service.get_job(job_id)
    if job is None:
        print("迭代任务不存在", file=__import__("sys").stderr)
        return 1

    print(json.dumps(job.to_dict(), ensure_ascii=False))
    return 0


def _handle_worker_once() -> int:
    runtime = get_iteration_runtime()
    _run_async(runtime.service.run_once())
    return 0


def _handle_worker_drain() -> int:
    runtime = get_iteration_runtime()
    _run_async(runtime.worker.run_until_empty())
    return 0


def _payload_to_model_evaluation(payload: dict[str, object]) -> ModelEvaluation:
    return ModelEvaluation(
        version_id=payload["version_id"],
        action_id=payload["action_id"],
        overall_score=payload["overall_score"],
        metric_scores=payload["metric_scores"],
        sample_results=[
            EvaluationSampleResult.from_dict(item)
            for item in payload.get("sample_results", [])
        ],
        dataset_version=payload["dataset_version"],
        config_version=payload["config_version"],
    )


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    raise SystemExit(main())
