from __future__ import annotations

from uuid import uuid4


async def run_q1(runtime, timeout_seconds: float = 90.0) -> None:
    """通过真实九问服务执行 Q1。"""
    await runtime.nine_question_service.run_single("q1", timeout_seconds=timeout_seconds)


def unique_suffix() -> str:
    return uuid4().hex[:10]


def task_payload(*, suffix: str, title_prefix: str = "real-ci-task", source_module: str = "ci_real_tasks") -> dict:
    return {
        "title": f"{title_prefix}-{suffix}",
        "task_type": "system_action",
        "originator_id": "ci_real_modules",
        "idempotency_key": f"{title_prefix}-{suffix}",
        "metadata": {"source_module": source_module},
    }
