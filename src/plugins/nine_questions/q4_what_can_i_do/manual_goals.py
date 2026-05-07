from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
)
from zentex.common.storage_paths import get_storage_paths

Q4_SNAPSHOT_TABLE = "nine_question_q4_snapshots"

ManualTaskGoalLane = Literal["internal", "external", "hybrid"]
ManualTaskGoalPreferredLane = Literal["internal", "external", "both"]


class ManualTaskGoalLaneAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    lane_classification: ManualTaskGoalLane
    internal_task_analysis: str
    external_task_analysis: str
    internal_external_comparison: str
    preferred_q4_lane: ManualTaskGoalPreferredLane
    rationale: str

    @field_validator(
        "goal",
        "internal_task_analysis",
        "external_task_analysis",
        "internal_external_comparison",
        "rationale",
    )
    @classmethod
    def _non_empty_text(cls, value: str, info: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{info.field_name}_empty")
        return text

    @model_validator(mode="after")
    def _validate_comparison_content(self) -> ManualTaskGoalLaneAnalysis:
        comparison = self.internal_external_comparison
        if "内部" not in comparison or "外部" not in comparison:
            raise ValueError("internal_external_comparison_must_compare_both_lanes")
        return self


class ManualTaskGoalLaneAnalysisSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ManualTaskGoalLaneAnalysisSet"]
    manual_task_goals: list[ManualTaskGoalLaneAnalysis] = Field(default_factory=list)


def _q4_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _q4_text(item))]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [item_text for item in parsed if (item_text := _q4_text(item))]
        return [
            cleaned
            for line in text.splitlines()
            if (cleaned := re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip())
        ]
    return []


def _q4_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("goal", "title", "name", "description", "content"):
            text = _q4_text(value.get(key))
            if text:
                return text
        return ""
    return str(value).strip()


def resolve_workspace_task_goals(context: dict[str, Any]) -> list[str]:
    direct = _q4_string_list(
        context.get("workspace_task_goals")
        or context.get("settings_task_goals")
        or context.get("task_goals")
    )
    if direct:
        return list(dict.fromkeys(direct))

    workspace_store = context.get("workspace_store")
    if workspace_store is None:
        return []

    workspace = None
    get_by_path = getattr(workspace_store, "get_workspace_by_path", None)
    if callable(get_by_path):
        for key in ("workspace_path", "workspace"):
            workspace_path = _q4_text(context.get(key))
            if not workspace_path:
                continue
            workspace = get_by_path(workspace_path)
            if workspace is not None:
                break

    if workspace is None:
        get_default = getattr(workspace_store, "get_default_workspace", None)
        if callable(get_default):
            workspace = get_default()

    if workspace is None:
        return []
    return list(dict.fromkeys(_q4_string_list(getattr(workspace, "task_goals", None))))


def empty_manual_task_goal_lane_analysis() -> dict[str, Any]:
    return {
        "type": "ManualTaskGoalLaneAnalysisSet",
        "manual_task_goals": [],
    }


def validate_manual_task_goal_lane_analysis_set(
    raw_output: dict[str, Any],
    *,
    expected_goals: list[str],
) -> dict[str, Any]:
    try:
        validated = ManualTaskGoalLaneAnalysisSet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q4_manual_task_goal_lane_analysis_validation_failed:{exc}") from exc

    payload = validated.model_dump(mode="json")
    analyzed_goals = [str(item.get("goal") or "").strip() for item in payload["manual_task_goals"]]
    missing = [goal for goal in expected_goals if goal not in analyzed_goals]
    if missing:
        raise RuntimeError(f"q4_manual_task_goal_lane_analysis_missing_goals:{missing}")
    if len(analyzed_goals) != len(set(analyzed_goals)):
        raise RuntimeError("q4_manual_task_goal_lane_analysis_duplicate_goals")
    return payload


def build_manual_task_goal_lane_analysis_prompt(*, goals: list[str]) -> str:
    goals_json = json.dumps(goals, ensure_ascii=False, indent=2)
    return f"""### Zentex Q4 用户手动任务目标 Lane Analysis LLM 提示词

你是一个纯粹的数据分类与比较函数，必须直接输出标准 JSON，禁止输出自然语言解释。

【任务】
用户在设置页手动添加了任务目标。你必须逐条判断每个目标更适合 Q4 内部认知轨、Q4 外部执行轨，还是两者都需要，并为每个目标写出内部任务分析、外部任务分析、内部与外部比较、推荐进入的 Q4 轨道。

【分类标准】
- internal：目标主要指向记忆治理、反思、学习、价值提示、策略补丁、影子测试、自我进化等脑内维护。
- external：目标主要指向文件、浏览器、CLI、MCP、Connector、Agent、外部服务、外部信息获取或业务执行。
- hybrid：目标同时需要内部认知整理和外部执行能力。

【用户手动任务目标】
```json
{goals_json}
```

【强制输出 JSON Schema】
```json
{{
  "type": "ManualTaskGoalLaneAnalysisSet",
  "manual_task_goals": [
    {{
      "goal": "必须原样填写用户手动任务目标文本",
      "lane_classification": "enum: [internal, external, hybrid]",
      "internal_task_analysis": "该目标若进入内部认知轨，需要解决什么脑内问题或形成什么认知目标",
      "external_task_analysis": "该目标若进入外部执行轨，需要解决什么业务问题或形成什么外部目标",
      "internal_external_comparison": "必须明确比较内部与外部两种处理方式的差异",
      "preferred_q4_lane": "enum: [internal, external, both]",
      "rationale": "一句话说明分类依据"
    }}
  ]
}}
```
"""


def run_q4_manual_task_goal_lane_analysis_and_save(context: dict[str, Any]) -> dict[str, Any]:
    goals = resolve_workspace_task_goals(context)
    if not goals:
        result = empty_manual_task_goal_lane_analysis()
        return {"manual_task_goals": [], "result": result}

    session_id = str(context.get("session_id") or "unknown-session")
    trace_id = f"{context.get('trace_id') or 'q4'}:manual-task-goals"
    decision_id = f"q4-manual-task-goals:{uuid4().hex}"
    provider = require_model_provider(context)
    require_transcript_store(context)
    prompt = build_manual_task_goal_lane_analysis_prompt(goals=goals)
    llm_input = {"prompt": prompt}
    _save_q4_manual_task_goal_lane_analysis_io(session_id=session_id, llm_input=llm_input)
    raw_output = provider.generate_json(
        prompt=prompt,
        context={},
        caller_context=build_caller_context(
            source_module=__name__,
            invocation_phase="nine_question_q4_manual_task_goal_lane_analysis",
            question_ref="q4:manual-task-goals",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        ),
        metadata={
            "question_id": "q4",
            "scope": "manual_task_goals",
            "output_schema": "ManualTaskGoalLaneAnalysisSet",
            "max_json_repair_attempts": 0,
            "output_truncation_forbidden": True,
        },
    )
    llm_output_raw = raw_output if isinstance(raw_output, dict) else {}
    if not llm_output_raw:
        raise RuntimeError("q4_manual_task_goal_lane_analysis_llm_output_empty")
    llm_output = validate_manual_task_goal_lane_analysis_set(llm_output_raw, expected_goals=goals)
    _save_q4_manual_task_goal_lane_analysis_io(
        session_id=session_id,
        llm_input=llm_input,
        llm_output=llm_output,
    )
    persist_question_module_output(
        context,
        question_id="q4",
        module_id="q4_manual_task_goal_lane_analysis_llm",
        payload={
            "q4_manual_task_goal_analysis_llm_input": llm_input,
            "q4_manual_task_goal_analysis_llm_output": llm_output,
        },
        status="completed",
        output_kind="inference",
        trace_id=trace_id,
    )
    return {
        "manual_task_goals": goals,
        "llm_input": llm_input,
        "llm_output": llm_output,
        "result": llm_output,
    }


def _save_q4_manual_task_goal_lane_analysis_io(
    *,
    session_id: str,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db_path = get_storage_paths().session_db
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            f"SELECT llm_output_json, created_at FROM {Q4_SNAPSHOT_TABLE} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        payload: dict[str, Any] = {}
        created_at = now
        if row is not None:
            created_at = str(row["created_at"] or now)
            try:
                loaded = json.loads(str(row["llm_output_json"] or "{}"))
            except json.JSONDecodeError as exc:
                raise RuntimeError("q4_llm_output_json_invalid") from exc
            if isinstance(loaded, dict):
                payload = loaded
        payload["q4_manual_task_goal_analysis_llm_input"] = json_safe_payload(llm_input)
        if llm_output is None:
            payload.pop("q4_manual_task_goal_analysis_llm_output", None)
        else:
            payload["q4_manual_task_goal_analysis_llm_output"] = json_safe_payload(llm_output)
        conn.execute(
            f"""
            INSERT INTO {Q4_SNAPSHOT_TABLE}
                (session_id, schema_version, record_version, snapshot_schema_version,
                 snapshot_json, llm_output_json, llm_trace_json, result_json,
                 context_updates_json, created_at, updated_at)
            VALUES (?, 3, 1, 3, ?, ?, '{{}}', '{{}}', '{{}}', ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                record_version = record_version + 1,
                llm_output_json = excluded.llm_output_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                json.dumps({"question_id": "q4"}, ensure_ascii=False, separators=(",", ":")),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                created_at,
                now,
            ),
        )
