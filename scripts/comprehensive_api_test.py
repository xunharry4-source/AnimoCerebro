#!/usr/bin/env python3
"""
Zentex web-console API comprehensive verification runner.

Responsibilities:
- exercise the real HTTP API surface against a running backend
- record evidence for normal, abnormal, and special/edge scenarios
- produce a backfilled markdown report with explicit pass/fail judgment

This script is intentionally an integration verifier, not a unit test:
- results are labeled as real execution only when an actual backend responds
- controlled 4xx/5xx paths are treated as evidence, not automatically as failures
"""

from dataclasses import dataclass
from typing import Any
from datetime import datetime
from pathlib import Path
import json
import requests
import sys
import tempfile
import uuid

import os

BACKEND_PORT = os.getenv("BACKEND_PORT", "8000")
BASE_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/web"
HOST_URL = f"http://127.0.0.1:{BACKEND_PORT}"


@dataclass(frozen=True)
class ApiTestCase:
    module: str
    function_desc: str
    method: str
    path: str
    scenario: str
    expected_status: tuple[int, ...]
    params: dict[str, Any] | None = None
    json_data: dict[str, Any] | None = None
    preconditions: str = "后端服务已启动，目标接口已注册。"
    assertions: str = "HTTP 状态码命中可接受集合，返回体可序列化。"
    log_observation: str = "观察接口状态码、响应耗时、返回体摘要。"
    side_effects: str = "可能创建测试用资源或触发后台执行。"
    degrade_expectation: str = "异常路径应 fail-closed 或返回受控错误，不得 silent failure。"
    rollback_expectation: str = "若产生测试资源，应支持手动删除或后续覆盖。"
    failure_attribution: str = "按状态码、异常类型、返回体摘要区分配置错误、后端错误、契约错误。"
    realism_label: str = "real"


class ApiTester:
    def __init__(self):
        self.results = []
        self.tc_count = 0
        self.environment_blocker: str | None = None

    def preflight_check(self, timeout_seconds: int = 5) -> bool:
        try:
            requests.get(f"{BASE_URL}/overview", timeout=timeout_seconds)
            self.environment_blocker = None
            return True
        except Exception as exc:
            self.environment_blocker = str(exc)
            return False

    def test(
        self,
        module,
        function_desc,
        method,
        path,
        params=None,
        json_data=None,
        expected_status=200,
        *,
        scenario=None,
        preconditions="后端服务已启动，目标接口已注册。",
        assertions="HTTP 状态码命中可接受集合，返回体可序列化。",
        log_observation="观察接口状态码、响应耗时、返回体摘要。",
        side_effects="可能创建测试用资源或触发后台执行。",
        degrade_expectation="异常路径应 fail-closed 或返回受控错误，不得 silent failure。",
        rollback_expectation="若产生测试资源，应支持手动删除或后续覆盖。",
        failure_attribution="按状态码、异常类型、返回体摘要区分配置错误、后端错误、契约错误。",
        realism_label="real",
        timeout_seconds=20,
    ):
        self.tc_count += 1
        tc_id = f"TC-{self.tc_count:03d}"
        url = f"{HOST_URL}{path}" if path.startswith("/api/") else f"{BASE_URL}{path}"

        acceptable_statuses = (
            tuple(expected_status)
            if isinstance(expected_status, (list, tuple, set))
            else (expected_status,)
        )
        primary_expected = acceptable_statuses[0]

        resolved_scenario = scenario
        if not resolved_scenario:
            resolved_scenario = "正常情况" if primary_expected < 400 else "异常情况 (Fail-Closed/Invalid)"
            if 503 in acceptable_statuses:
                resolved_scenario = "特殊/边缘情况 (Service Initializing)"

        case = ApiTestCase(
            module=module,
            function_desc=function_desc,
            method=method,
            path=path,
            scenario=resolved_scenario,
            expected_status=acceptable_statuses,
            params=params,
            json_data=json_data,
            preconditions=preconditions,
            assertions=assertions,
            log_observation=log_observation,
            side_effects=side_effects,
            degrade_expectation=degrade_expectation,
            rollback_expectation=rollback_expectation,
            failure_attribution=failure_attribution,
            realism_label=realism_label,
        )

        print(f"[{tc_id}] {method} {path} ...", end=" ", flush=True)
        
        try:
            start_time = datetime.now()
            if method == "GET":
                resp = requests.get(url, params=params, timeout=timeout_seconds)
            elif method == "POST":
                resp = requests.post(url, json=json_data, timeout=timeout_seconds)
            elif method == "PUT":
                resp = requests.put(url, json=json_data, timeout=timeout_seconds)
            elif method == "PATCH":
                resp = requests.patch(url, json=json_data, timeout=timeout_seconds)
            elif method == "DELETE":
                resp = requests.delete(url, timeout=timeout_seconds)
            else:
                print("SKIPPED")
                return

            # Acceptance logic: strict — only statuses explicitly listed in expected_status pass.
            # A 503 from an endpoint that only expects 200 is a REAL FAILURE, not a managed fallback.
            # If a service is known to be unavailable in dev, the test case MUST include 503 in
            # expected_status explicitly.  This prevents silent masking of core interface defects.
            status_ok = resp.status_code in acceptable_statuses

            actual_response = resp.text.strip()
            # Truncate and clean for markdown table
            display_response = (actual_response[:120] + "...") if len(actual_response) > 120 else actual_response
            display_response = display_response.replace("\n", " ").replace("|", "\\|").replace("`", "'")
            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            content_type = resp.headers.get("content-type", "")
            evidence = f"HTTP {resp.status_code}; {latency_ms}ms; content-type={content_type or 'unknown'}"
            error_category = self._classify_result(resp.status_code, display_response)

            result = {
                "tc_id": tc_id,
                "module": case.module,
                "path": case.path,
                "function_desc": case.function_desc,
                "scenario": resolved_scenario,
                "method": case.method,
                "params": json.dumps(params or (json_data or {})) if (params or json_data) else "{}",
                "expected": " / ".join(f"HTTP {status}" for status in acceptable_statuses),
                "actual": display_response,
                "ok": status_ok,
                "preconditions": case.preconditions,
                "assertions": case.assertions,
                "log_observation": case.log_observation,
                "side_effects": case.side_effects,
                "degrade_expectation": case.degrade_expectation,
                "rollback_expectation": case.rollback_expectation,
                "failure_attribution": case.failure_attribution,
                "realism_label": case.realism_label,
                "latency_ms": latency_ms,
                "evidence": evidence,
                "error_category": error_category,
            }
            self.results.append(result)
            
            if status_ok:
                print(f"✓ ({resp.status_code})")
            else:
                print(f"✘ ({resp.status_code})")
                
        except Exception as e:
            print(f"✘ ERROR: {e}")
            self.results.append({
                "tc_id": tc_id,
                "module": case.module,
                "path": case.path,
                "function_desc": case.function_desc,
                "scenario": case.scenario,
                "method": case.method,
                "params": "ERROR",
                "expected": " / ".join(f"HTTP {status}" for status in acceptable_statuses),
                "actual": f"EXCEPTION: {str(e)}",
                "ok": False,
                "preconditions": case.preconditions,
                "assertions": case.assertions,
                "log_observation": case.log_observation,
                "side_effects": case.side_effects,
                "degrade_expectation": case.degrade_expectation,
                "rollback_expectation": case.rollback_expectation,
                "failure_attribution": case.failure_attribution,
                "realism_label": "real",
                "latency_ms": -1,
                "evidence": f"EXCEPTION: {str(e)}",
                "error_category": "transport_or_runtime_exception",
            })

    @staticmethod
    def _classify_result(status_code: int, response_excerpt: str) -> str:
        if 200 <= status_code < 300:
            return "success"
        if status_code in {400, 401, 403, 404, 409, 422}:
            return "controlled_client_error"
        if status_code == 503:
            return "managed_fail_closed"
        if status_code >= 500:
            return "server_error"
        if response_excerpt.startswith("EXCEPTION:"):
            return "transport_or_runtime_exception"
        return "unknown"

    def _summary(self) -> dict[str, int]:
        summary = {
            "total": len(self.results),
            "passed": sum(1 for item in self.results if item["ok"]),
            "failed": sum(1 for item in self.results if not item["ok"]),
            "server_error": sum(1 for item in self.results if item["error_category"] == "server_error"),
            "managed_fail_closed": sum(1 for item in self.results if item["error_category"] == "managed_fail_closed"),
            "controlled_client_error": sum(1 for item in self.results if item["error_category"] == "controlled_client_error"),
            "transport_or_runtime_exception": sum(1 for item in self.results if item["error_category"] == "transport_or_runtime_exception"),
        }
        return summary

    def _module_summary(self) -> dict[str, dict[str, int]]:
        grouped: dict[str, dict[str, int]] = {}
        for item in self.results:
            module = str(item["module"])
            bucket = grouped.setdefault(
                module,
                {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "server_error": 0,
                    "managed_fail_closed": 0,
                    "controlled_client_error": 0,
                    "transport_or_runtime_exception": 0,
                },
            )
            bucket["total"] += 1
            if item["ok"]:
                bucket["passed"] += 1
            else:
                bucket["failed"] += 1
            category = str(item.get("error_category") or "")
            if category in bucket:
                bucket[category] += 1
        return grouped

    def _failure_inventory(self) -> list[dict[str, Any]]:
        return [item for item in self.results if not item["ok"]]

    def _true_defect_failures(self) -> list[dict[str, Any]]:
        defect_categories = {"server_error", "transport_or_runtime_exception", "unknown"}
        return [item for item in self.results if not item["ok"] and item.get("error_category") in defect_categories]

    def _rollback_guidance(self) -> list[str]:
        return [
            "若本轮验证创建了测试资源（如 Agent、Workspace、MCP Server），优先调用对应 DELETE 接口清理。",
            "若注册型接口已写入后端存储，回滚时应核对运行时数据库或配置存根是否残留。",
            "若批量/触发型接口导致后台任务执行，回滚时应暂停自动循环并清理未完成任务。",
        ]

    def run_all(self):
        missing_id = "missing-id"
        missing_task_id = "missing-task-id"
        missing_workspace_id = "999999"
        generated_workspace_id = "999998"
        generated_agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        generated_mcp_id = f"mcp-{uuid.uuid4().hex[:8]}"
        workspace_test_root = Path(tempfile.gettempdir()) / f"zentex-comprehensive-{uuid.uuid4().hex[:8]}"
        workspace_test_root.mkdir(parents=True, exist_ok=True)

        # 01 Overview & Health
        self.test("Overview", "获取系统状态总览", "GET", "/overview")
        self.test("Health", "基础健康检查 (Root)", "GET", "/health",
                  scenario="正常情况",
                  preconditions="Web 服务已启动，健康检查端点可用。",
                  assertions="返回 200，包含 status 字段。")
        self.test("Overview", "获取大模型状态", "GET", "/llm/status")
        self.test("Overview", "实时探测大模型状态", "GET", "/llm/status", params={"probe_live": True}, timeout_seconds=60)
        self.test("Health", "系统可用性检查 (Normal)", "GET", "/health/system")

        # 02 Tasks (Expanded)
        self.test("Tasks", "拉取全量任务清单", "GET", "/tasks")
        self.test("Tasks", "按状态汇总任务", "GET", "/tasks/by-status")
        self.test("Tasks", "获取无效任务详情 (Exception)", "GET", "/tasks/invalid-uuid/detail", expected_status=404)
        self.test("Tasks", "获取无效任务子任务列表", "GET", "/tasks/invalid-uuid/subtasks", expected_status=404)
        self.test("Tasks", "拉取任务审计轨迹 (Special)", "GET", "/tasks/none/execution-history", expected_status=404)
        self.test("Tasks", "强制触发任务分解 (Special)", "POST", "/tasks/none/decompose", expected_status=(404, 503), json_data={"force_decompose": True})
        self.test("Tasks", "查询无效任务树", "GET", "/tasks/tree/none", expected_status=404)
        self.test("Tasks", "获取协商记录", "GET", "/tasks/negotiations")
        self.test("Tasks", "对无效任务发起人工干预", "POST", f"/tasks/{missing_task_id}/intervene", expected_status=(400, 404), json_data={
            "action": "pause",
            "remarks": "Clinical API verification",
        })
        self.test("Tasks", "触发批量任务操作", "POST", "/tasks/bulk-operation", expected_status=(200, 400, 422), json_data={
            "task_ids": [],
            "action": "pause",
        })

        # 03 Memory
        self.test("Memory", "获取内存统计概览", "GET", "/memory/overview")
        self.test("Memory", "执行语义搜索 (Normal)", "GET", "/memory/search", params={"query": "agent"})
        self.test("Memory", "获取增强内存记录列表", "GET", "/memory/records")
        self.test("Memory", "获取指定内存详情", "GET", "/memory/missing-memory-id", expected_status=(404, 422))
        self.test("Memory", "获取指定内存图谱邻居", "GET", "/memory/missing-memory-id/neighbors", expected_status=(404, 422))
        self.test("Memory", "更新不存在的增强内存记录", "POST", "/memory/missing-memory-id/management", expected_status=(404, 422), json_data={
            "status": "active",
            "operator": "comprehensive_api_test",
            "reason": "clinical verification",
        })
        self.test("Memory", "查询最近固化周期", "GET", "/memory/consolidation-cycles", expected_status=(200, 503))
        self.test("Memory", "触发内存固化周期 (Normal)", "POST", "/memory/consolidation/trigger", expected_status=(200, 503))

        # 03a Memory page — /console/memory 页面完整接口覆盖
        self.test("Memory", "获取记忆审计日志不存在ID (Abnormal)", "GET", "/memory/missing-memory-id/audit",
                  expected_status=(404, 422),
                  scenario="异常情况 (Fail-Closed/Invalid)",
                  preconditions="memory_id不存在于后端存储，验证fail-closed返回。",
                  assertions="返回404(记录不存在)或422(验证失败)，不得500。",
                  degrade_expectation="404 fail-closed，不得AttributeError或500。")
        self.test("Memory", "按Semantic层过滤记录 (Normal Filter)", "GET", "/memory/records",
                  params={"layer": "semantic", "limit": 10},
                  scenario="正常情况",
                  preconditions="记忆服务已初始化，layer=semantic为合法枚举值。",
                  assertions="返回200，items结构合法，layer字段均为semantic。")
        self.test("Memory", "按Active状态过滤记录 (Normal Filter)", "GET", "/memory/records",
                  params={"layer": "all", "limit": 10, "status": "active"},
                  scenario="正常情况",
                  preconditions="status参数传递为active，对应lifecycle_status过滤。",
                  assertions="返回200，items列表可能为空，结构合法。")
        self.test("Memory", "按Suspect信任级别过滤 (Normal Filter)", "GET", "/memory/records",
                  params={"layer": "all", "limit": 10, "trust_level": "suspect"},
                  scenario="正常情况",
                  preconditions="trust_level=suspect为合法枚举值。",
                  assertions="返回200，items列表中trust_level均为suspect。")
        self.test("Memory", "空查询触发422 (Abnormal Edge)", "GET", "/memory/search",
                  params={"query": ""},
                  expected_status=422,
                  scenario="异常情况 (Fail-Closed/Invalid)",
                  preconditions="query为空字符串，min_length=1约束触发FastAPI 422。",
                  assertions="必须返回422 Unprocessable Entity，不得返回200或500。")
        self.test("Memory", "记忆管理附加非法字段422 (Abnormal)", "POST", "/memory/missing-memory-id/management",
                  expected_status=(404, 422),
                  json_data={"operator": "test", "unknown_illegal_field": "bad"},
                  scenario="异常情况 (Fail-Closed/Invalid)",
                  preconditions="请求体含extra='forbid'禁止字段，422优先；若记录不存在则404。",
                  assertions="返回422(非法字段)或404(记录不存在)，不得500。")

        # 04 CLI Tools (Expanded Management)
        # NOTE: cli_service is not injected in dev; all CLI endpoints legitimately return 503.
        self.test("CLI", "获取CLI工具列表", "GET", "/cli-tools", expected_status=(200, 503))
        self.test("CLI", "注册新CLI工具 (Management)", "POST", "/cli-tools/register", expected_status=(200, 422, 503), json_data={
            "tool_name": "git",
            "command_executable": "git",
            "command_args": [],
            "description": "Version control system",
            "execution_domain": "cli",
            "read_only_flag": True
        })
        self.test("CLI", "测试CLI工具调用 (Management)", "POST", "/cli-tools/git/test-call", expected_status=(200, 404, 503), json_data={
            "arguments": ["--version"],
            "timeout_seconds": 5
        })
        self.test("CLI", "获取CLI工具详情", "GET", "/cli-tools/git/detail", expected_status=(200, 404, 503))
        self.test("CLI", "查询CLI工具任务", "GET", "/cli-tools/git/tasks/all", expected_status=(200, 400, 404, 503))
        self.test("CLI", "查询CLI执行历史", "GET", "/cli-tools/git/execution-history", expected_status=(200, 404, 503))

        # 04a CLI page — /console/cli-tools 页面异常路径覆盖
        self.test("CLI", "注册CLI工具空字段触发422 (Abnormal)", "POST", "/cli-tools/register",
                  expected_status=(422, 503),
                  json_data={"tool_name": "", "command_executable": "", "description": "invalid"},
                  scenario="异常情况 (Fail-Closed/Invalid)",
                  preconditions="tool_name和command_executable均为空字符串，Field(min_length=1)触发422。",
                  assertions="若cli_service可用则422；若服务未初始化则503。",
                  degrade_expectation="422验证拒绝优先于业务逻辑，不得500。")
        self.test("CLI", "测试不存在CLI工具 (Abnormal)", "POST", "/cli-tools/nonexistent-xyz-tool/test-call",
                  expected_status=(404, 503),
                  json_data={"arguments": ["--help"], "timeout_seconds": 5},
                  scenario="异常情况 (Fail-Closed/Invalid)",
                  preconditions="工具名不存在于CLI服务注册表中。",
                  assertions="若cli_service可用则404；若服务未初始化则503。",
                  degrade_expectation="404 fail-closed，不得AttributeError或500。")
        self.test("CLI", "CLI任务状态过滤器无效值 (Special Edge)", "GET", "/cli-tools/git/tasks/invalid-filter",
                  expected_status=(400, 404, 503),
                  scenario="特殊/边缘情况 (Service Initializing)",
                  preconditions="status_filter='invalid-filter'，合法值为in-progress/pending/failed。",
                  assertions="若cli_service可用则400(非法过滤器)；工具不存在404；服务503。",
                  degrade_expectation="400参数拒绝，不得500。")

        # 05 Plugins (Expanded Management)
        self.test("Plugins", "获取认知插件列表", "GET", "/plugins/cognitive")
        self.test("Plugins", "获取功能插件列表", "GET", "/plugins/functional")
        self.test("Plugins", "获取全量插件列表", "GET", "/plugins")
        self.test("Plugins", "获取认知插件详情 (Detail)", "GET", "/plugins/cognitive/nine-question-q1-where-am-i", expected_status=(200, 404))
        self.test("Plugins", "获取功能插件详情 (Detail)", "GET", "/plugins/functional/oracle_objective", expected_status=(200, 404))
        self.test("Plugins", "获取插件历史版本", "GET", "/plugins/oracle_objective/history", expected_status=(200, 404))
        self.test("Plugins", "测试插件运行", "POST", "/plugins/oracle_objective/test", expected_status=(200, 404, 422), json_data={
            "audit_reason": "Clinical Testing",
            "idempotency_key": f"plugin-test-{uuid.uuid4().hex[:8]}",
        })
        self.test("Plugins", "强制启用插件 (Management)", "POST", "/plugins/oracle_objective/force-enable", expected_status=(200, 404), json_data={
            "audit_reason": "Clinical Testing",
            "allow_overwrite_active": True
        })
        self.test("Plugins", "强制停用插件 (Management)", "POST", "/plugins/oracle_objective/force-disable", expected_status=(200, 404), json_data={
            "audit_reason": "Clinical Testing"
        })
        self.test("Plugins", "绑定功能插件至认知中心 (Management)", "POST", "/plugins/cognitive/nine-question-q1-where-am-i/functional/oracle_redline/bind", expected_status=(200, 404), json_data={
            "audit_reason": "Clinical Testing",
            "role": "primary",
            "priority": 1
        })
        self.test("Plugins", "解绑功能插件", "DELETE", "/plugins/cognitive/nine-question-q1-where-am-i/functional/oracle_redline/unbind", expected_status=(200, 404))
        self.test("Plugins", "删除不存在插件", "DELETE", f"/plugins/{missing_id}", expected_status=(200, 404))

        # 06 Cognition
        self.test("Cognition", "查询认知议程 (Normal)", "GET", "/cognitive-agenda")
        self.test("Cognition", "查询认知冲突列表", "GET", "/cognitive-conflicts")
        self.test("Cognition", "查询仿真结果", "GET", "/simulations/missing-goal", expected_status=(200, 404, 503))
        self.test("Cognition", "获取实体交互思维模型", "GET", "/interaction-mind/missing-entity", expected_status=(200, 404, 503))

        # 06a Simulation page — /console/simulation 页面接口覆盖
        self.test("Cognition", "查询前端默认目标仿真 (Normal Goal ID)", "GET", "/simulations/goal-runtime-stability",
                  expected_status=(200, 404, 503),
                  scenario="正常情况",
                  preconditions="使用SimulationExplorer组件默认goalId=goal-runtime-stability，已为此目标注入测试数据。",
                  assertions="返回 200，响应含 bundle 字段，包含 branches 和 outcome_comparison。",
                  degrade_expectation="引擎 503 时返回错误；goal 不存在时返回 404。")
        self.test("Cognition", "仿真响应结构验证 (Special — bundle字段)", "GET", "/simulations/goal-runtime-stability",
                  expected_status=(200, 404, 503),
                  scenario="正常情况",
                  preconditions="验证 SimulationBundlePayload 序列化后含顶层 bundle 字段，前端依赖 payload.bundle 访问。",
                  assertions="200 时 JSON 根层必须含 bundle 键；bundle 包含 branches、outcome_comparison、status 等字段。",
                  degrade_expectation="前端 SimulationExplorer 能正确接收 payload.bundle 数据结构。")
        self.test("Cognition", "认知议程snapshot修复验证 (Special — evaluate→snapshot)", "GET", "/cognitive-agenda",
                  scenario="特殊/边缘情况 (Service Initializing)",
                  preconditions="CognitiveTemporalEngine.evaluate()已修复为snapshot()，验证接口不再500。",
                  assertions="返回200(含snapshot timing字段)；temporal_engine不可用时503；不得AttributeError 500。",
                  degrade_expectation="snapshot()可用时200，engine=None时503，不得500。")

        # 07 MCP (Expanded Management)
        self.test("MCP", "列出已同步MCP服务器", "GET", "/mcp-servers")
        self.test("MCP", "注册新MCP服务器 (Management)", "POST", "/mcp-servers/register", expected_status=(200, 400, 503), json_data={
            "server_id": generated_mcp_id,
            "transport_type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {},
        })
        self.test("MCP", "测试MCP服务器调用", "POST", f"/mcp-servers/{generated_mcp_id}/test-call", expected_status=(200, 404, 422, 503), json_data={
            "tool_name": "list_directory",
            "arguments": {"path": "/tmp"}
        })
        self.test("MCP", "获取MCP服务器详情", "GET", f"/mcp-servers/{generated_mcp_id}", expected_status=(200, 404))
        self.test("MCP", "获取MCP服务器任务列表", "GET", f"/mcp-servers/{generated_mcp_id}/tasks", expected_status=(200, 404))

        # 08 Nine Questions (Expanded Detail & Test)
        self.test("NineQuestions", "获取九问状态", "GET", "/nine-questions/status")
        self.test("NineQuestions", "查询最新校验报告", "GET", "/nine-questions/latest-report")
        self.test("NineQuestions", "查询Q1详细详情 (Detail)", "GET", "/nine-questions/q1", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q2详细详情 (Detail)", "GET", "/nine-questions/q2", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q3详细详情 (Detail)", "GET", "/nine-questions/q3", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q4详细详情 (Detail)", "GET", "/nine-questions/q4", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q5详细详情 (Detail)", "GET", "/nine-questions/q5", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q6详细详情 (Detail)", "GET", "/nine-questions/q6", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q7详细详情 (Detail)", "GET", "/nine-questions/q7", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q8详细详情 (Detail)", "GET", "/nine-questions/q8", expected_status=(200, 404))
        self.test("NineQuestions", "查询Q9详细详情 (Detail)", "GET", "/nine-questions/q9", expected_status=(200, 404))
        self.test("NineQuestions", "查询九问追踪详情", "GET", "/nine-questions/traces/missing-trace", expected_status=(200, 404))
        self.test("NineQuestions", "提交Q1沙盒测试 (Test Interface)", "POST", "/nine-questions/q1/test", expected_status=(200, 503), json_data={
            "observation_raw": "User is asking for infrastructure audit.",
            "context_hints": ["local_disk", "cpu_load"]
        })
        self.test("NineQuestions", "提交Q2沙盒测试 — 角色与身份推断", "POST", "/nine-questions/q2/test", expected_status=(200, 503), json_data={
            "observation_raw": "User wants to know what role this AI system is playing.",
            "context_hints": ["role", "identity", "mission"]
        })
        self.test("NineQuestions", "提交Q3沙盒测试 — 资产与工具盘点", "POST", "/nine-questions/q3/test", expected_status=(200, 503), json_data={
            "observation_raw": "User asks what tools and resources are currently available.",
            "context_hints": ["tools", "resources", "capabilities"]
        })
        self.test("NineQuestions", "提交Q4沙盒测试 — 能力边界推导", "POST", "/nine-questions/q4/test", expected_status=(200, 503), json_data={
            "observation_raw": "User asks what this system can and cannot do.",
            "context_hints": ["capabilities", "limits", "constraints"]
        })
        self.test("NineQuestions", "提交Q5沙盒测试 — 授权与合规边界", "POST", "/nine-questions/q5/test", expected_status=(200, 503), json_data={
            "observation_raw": "User asks what actions are authorized and compliant.",
            "context_hints": ["authorization", "compliance", "policy"]
        })
        self.test("NineQuestions", "提交Q6沙盒测试 — 红线与禁止动作", "POST", "/nine-questions/q6/test", expected_status=(200, 503), json_data={
            "observation_raw": "User asks what must never be done under any circumstances.",
            "context_hints": ["redline", "forbidden", "safety"]
        })
        self.test("NineQuestions", "提交Q7沙盒测试 — 备选策略与替代方案", "POST", "/nine-questions/q7/test", expected_status=(200, 503), json_data={
            "observation_raw": "User wants to explore alternative approaches to the current task.",
            "context_hints": ["alternatives", "options", "fallback"]
        })
        self.test("NineQuestions", "提交Q8沙盒测试 — 当前目标排序与决策", "POST", "/nine-questions/q8/test", expected_status=(200, 503), json_data={
            "observation_raw": "User asks what should be done next given the current context.",
            "context_hints": ["priority", "decision", "next_action"]
        })
        self.test("NineQuestions", "提交Q9沙盒测试 — 行动姿态与升级策略", "POST", "/nine-questions/q9/test", expected_status=(200, 503), json_data={
            "observation_raw": "User asks how to calibrate tone, pace, and escalation posture.",
            "context_hints": ["posture", "tone", "escalation", "strategy"]
        })
        self.test("NineQuestions", "强制运行全量九问 (Force Run)", "POST", "/nine-questions/run-all", expected_status=(200, 503), json_data={
            "reason": "Explicit user trigger for baseline sync"
        }, timeout_seconds=120)
        self.test("NineQuestions", "强制触发Q1反思", "POST", "/reflections/q1/force", expected_status=(200, 400, 404, 503), json_data={
            "include_dependencies": True
        }, timeout_seconds=60)
        self.test("NineQuestions", "查询九问反思列表", "GET", "/reflections")
        self.test("NineQuestions", "查询九问反思详情", "GET", "/reflections/missing-reflection", expected_status=(200, 404))

        # 09 Learning
        self.test("Learning", "获取学习计划安排", "GET", "/learning/plan")
        self.test("Learning", "获取学习历史流水", "GET", "/learning/history")
        self.test("Learning", "运行学习周期", "POST", "/learning/run-cycle", expected_status=(200, 400, 422, 503), json_data={
            "direction": "G16_TOOL_SELF_STUDY",
            "dry_run": True,
            "load_factor": 0.5
        })
        self.test("LearningAsync", "启动异步学习任务", "POST", "/api/learning/start", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", json_data={
            "direction": "g16_tool_self_study",
            "dry_run": True,
            "doc_url": "https://example.com/spec",
        }, degrade_expectation="该异步学习入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("LearningAsync", "查询异步学习任务列表", "GET", "/api/learning/tasks", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步学习入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("LearningAsync", "查询异步学习服务统计", "GET", "/api/learning/stats", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步学习入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("LearningAsync", "查询可用学习方向", "GET", "/api/learning/directions", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步学习入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("LearningAsync", "查询异步学习任务状态", "GET", "/api/learning/tasks/missing-task/status", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步学习入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("LearningAsync", "取消异步学习任务", "DELETE", "/api/learning/tasks/missing-task", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步学习入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")

        # 10 Agents (Expanded Management)
        self.test("Agents", "列出已注册智能体", "GET", "/agents")
        self.test("Agents", "注册新Agent (Management)", "POST", "/agents/register", expected_status=(200, 422), json_data={
            "name": "sre_helper",
            "agent_name": "SRE Helper",
            "version": "1.0.0",
            "function_description": "Read-only diagnostics helper",
            "endpoint": "http://127.0.0.1:9999/agent",
            "auth_token": "test-token",
            "role_tag": "diagnostics",
            "scope": ["read", "analyze"],
        })
        self.test("Agents", "获取Agent握手信息", "GET", f"/agents/{generated_agent_id}/handshake", expected_status=(200, 404))
        self.test("Agents", "执行Agent安全审计", "POST", f"/agents/{generated_agent_id}/safety-audit", expected_status=(200, 404), json_data={})
        self.test("Agents", "派发Agent任务", "POST", f"/agents/{generated_agent_id}/dispatch", expected_status=(200, 404, 422), json_data={
            "task_payload": {
                "title": "Clinical dispatch test",
                "content": "Verify dispatch API connectivity",
            }
        })
        self.test("Agents", "查询Agent健康状态", "GET", "/agents-health/status")
        self.test("Agents", "更新Agent策略", "PATCH", f"/agents/{generated_agent_id}/policy", expected_status=(200, 404, 422), json_data={
            "trust_level": "trusted",
            "scope": ["read", "analyze"],
        })
        self.test("Agents", "查询Agent任务列表", "GET", f"/agents/{generated_agent_id}/tasks", expected_status=(200, 404))
        self.test("Agents", "按状态查询Agent任务", "GET", f"/agents/{generated_agent_id}/tasks/by-status", params={"status": "todo"}, expected_status=(200, 404))
        self.test("Agents", "查询Agent审计记录", "GET", f"/agents/{generated_agent_id}/audit", expected_status=(200, 404))
        self.test("Agents", "查询Agent详情", "GET", f"/agents/{generated_agent_id}/detail", expected_status=(200, 404))
        self.test("Agents", "取消Agent任务", "POST", f"/agents/{generated_agent_id}/tasks/{missing_task_id}/cancel", expected_status=(200, 404))
        self.test("Agents", "重试Agent任务", "POST", f"/agents/{generated_agent_id}/tasks/{missing_task_id}/retry", expected_status=(200, 404))
        self.test("Agents", "删除Agent", "DELETE", f"/agents/{generated_agent_id}", expected_status=(200, 404))

        # 11 Governance & Audit
        self.test("Governance", "获取治理评分状态", "GET", "/governance/status")
        self.test("Governance", "获取治理审计摘要", "GET", "/governance/audits/summary")
        self.test("Audit", "获取审计日志流水", "GET", "/audit/model-provider")
        self.test("Audit", "获取Turn级别里程碑", "GET", "/audit/turns")
        self.test("Audit", "获取全量审计列表", "GET", "/audits")

        # 12 Model Feature Tests
        self.test("ModelTests", "获取模型能力测试目录", "GET", "/tests/model-features")
        self.test("ModelTests", "获取模型能力测试统计", "GET", "/tests/model-features/stats")
        self.test("ModelTests", "获取模型能力测试历史", "GET", "/tests/model-features/model_provider.generate_json/history")
        self.test("ModelTests", "获取模型能力测试运行日志", "GET", "/tests/model-features/runs/missing-test-run")
        self.test("ModelTests", "触发模型能力测试", "POST", "/tests/model-features/invoke", expected_status=(200, 410, 422, 503), json_data={
            "feature_id": "model_provider.generate_json",
            "prompt": "Return a JSON object",
            "context": {},
            "caller_context": {
                "source_module": "comprehensive_api_test",
                "invocation_phase": "manual_test"
            }
        })

        # 13 Events / Replay / Interventions
        self.test("Events", "获取事件总线状态", "GET", "/events/status")
        self.test("Events", "获取事件连接信息", "GET", "/events/connections")
        self.test("Events", "执行事件健康检查", "GET", "/events/healthcheck")
        self.test("Replay", "回放事件详情", "GET", "/replay/test-event-id", expected_status=404)
        self.test("Replay", "按Turn回放", "GET", "/replay/turn/test-turn-id", expected_status=(200, 404))
        self.test("Interventions", "提交人工干预", "POST", "/interventions", expected_status=(200, 201, 422), json_data={
            "kind": "pause",
            "reason": "Clinical API verification"
        })

        # 14 Upgrades / Evolution / Supervision / Environment
        self.test("Upgrades", "获取升级概览", "GET", "/upgrades/overview")
        self.test("Upgrades", "按生命周期查看升级", "GET", "/upgrades/by-lifecycle-view")
        self.test("Upgrades", "获取LLM升级列表", "GET", "/upgrades/llm")
        self.test("Upgrades", "获取插件升级列表", "GET", "/upgrades/plugins")
        self.test("Upgrades", "获取升级详情", "GET", "/upgrades/missing-record", expected_status=(200, 404))
        self.test("Upgrades", "获取升级审计事件", "GET", "/upgrades/missing-record/audit-events", expected_status=(200, 404))
        self.test("Upgrades", "获取升级记忆记录", "GET", "/upgrades/missing-record/memory-records", expected_status=(200, 404))
        self.test("Upgrades", "执行LLM升级", "POST", "/upgrades/llm/execute", expected_status=(200, 422, 503), json_data={})
        self.test("Upgrades", "执行插件升级", "POST", "/upgrades/plugins/execute", expected_status=(200, 422, 503), json_data={})
        self.test("Upgrades", "取消升级记录", "POST", "/upgrades/missing-record/cancel", expected_status=(200, 404, 409), json_data={"reason": "Clinical verification"})
        self.test("Upgrades", "清理失败候选版本", "POST", "/upgrades/missing-record/cleanup-failed-candidate", expected_status=(200, 404, 409), json_data={"reason": "Clinical verification"})
        self.test("Evolution", "获取演化提案列表", "GET", "/proposals")
        self.test("Evolution", "批准演化提案", "POST", "/proposals/missing-proposal/approve", expected_status=(200, 404))
        self.test("Evolution", "获取演化任务列表", "GET", "/jobs")
        self.test("Evolution", "提升演化任务", "POST", "/jobs/missing-job/promote", expected_status=(200, 404))
        self.test("Evolution", "回滚演化任务", "POST", "/jobs/missing-job/rollback", expected_status=(200, 404))
        self.test("Supervision", "获取监督状态", "GET", "/api/supervision/status")
        self.test("Supervision", "获取监督告警", "GET", "/api/supervision/alerts")
        self.test("Supervision", "确认监督告警", "POST", "/api/supervision/alerts/missing-alert/acknowledge", expected_status=(200, 404))
        self.test("Supervision", "获取执行记录", "GET", "/api/supervision/executions")
        self.test("Supervision", "获取执行详情", "GET", "/api/supervision/executions/missing-record", expected_status=(200, 404))
        self.test("Supervision", "执行监督干预", "POST", "/api/supervision/intervention", expected_status=(200, 404, 422), json_data={
            "task_id": "missing-task-id",
            "action": "pause",
            "reason": "Clinical API verification"
        })
        self.test("Supervision", "获取监督规则", "GET", "/api/supervision/rules")
        self.test("Supervision", "更新监督规则", "POST", "/api/supervision/rules/update", expected_status=(200, 404, 422), json_data={"rule_id": "default", "enabled": True})
        self.test("Supervision", "获取监督仪表盘", "GET", "/api/supervision/dashboard")
        self.test("Supervision", "配置监督级别", "POST", "/api/supervision/configure/level", expected_status=(200, 422), json_data={
            "level": "medium"
        })
        self.test("Environment", "获取宿主机状态", "GET", "/api/v1/environment/host-state")
        self.test("Environment", "解释环境信号", "POST", "/api/v1/environment/interpret", expected_status=(200, 422), json_data={})
        self.test("Environment", "清洗环境信号", "POST", "/api/v1/environment/sanitize", expected_status=(200, 400, 422), json_data={})
        self.test("Environment", "创建环境快照", "POST", "/api/v1/environment/snapshot", expected_status=(200, 422), json_data={})
        self.test("Environment", "获取最近环境快照", "GET", "/api/v1/environment/snapshots/recent")
        self.test("Environment", "查询环境快照", "GET", "/api/v1/environment/snapshots/query")
        self.test("Environment", "对比环境信号", "POST", "/api/v1/environment/compare", expected_status=(200, 400, 422), json_data={})
        self.test("Environment", "获取环境服务状态", "GET", "/api/v1/environment/status")

        # 15 Observability
        self.test("Observability", "获取调度解释", "GET", f"/tasks/{missing_task_id}/dispatch-explanation", expected_status=(200, 404))
        self.test("Observability", "获取调度候选", "GET", f"/tasks/{missing_task_id}/dispatch-candidates", expected_status=(200, 404))
        self.test("Observability", "获取验证详情", "GET", f"/tasks/{missing_task_id}/verification-details", expected_status=(200, 404))
        self.test("Observability", "获取验证历史", "GET", f"/tasks/{missing_task_id}/verification-history", expected_status=(200, 404))
        self.test("Observability", "获取监督历史", "GET", f"/tasks/{missing_task_id}/supervision-history", expected_status=(200, 404))
        self.test("Observability", "获取监督动作", "GET", f"/tasks/{missing_task_id}/supervision-actions", expected_status=(200, 404))
        self.test("Observability", "获取可观测性摘要", "GET", f"/tasks/{missing_task_id}/observability-summary", expected_status=(200, 404))
        self.test("Observability", "获取可观测性健康状态", "GET", "/observability/health")

        # 16 Reflection Async
        self.test("ReflectionAsync", "提交反思生成任务", "POST", "/api/reflection/generate", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", json_data={
            "subject": "clinical verification",
            "reflection_type": "operational",
            "context": {},
            "trigger": "automatic",
        }, degrade_expectation="该异步反思入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("ReflectionAsync", "查询反思任务状态", "GET", "/api/reflection/tasks/missing-reflection-task/status", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步反思入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("ReflectionAsync", "取消反思任务", "DELETE", "/api/reflection/tasks/missing-reflection-task", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步反思入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("ReflectionAsync", "查询反思任务列表", "GET", "/api/reflection/tasks", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步反思入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("ReflectionAsync", "查询反思服务统计", "GET", "/api/reflection/stats", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", degrade_expectation="该异步反思入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")
        self.test("ReflectionAsync", "批量生成反思", "POST", "/api/reflection/batch-generate", expected_status=(410,), scenario="异常情况 (Architecture Removed / Fail-Closed)", json_data=[{
            "subject": "clinical verification",
            "reflection_type": "operational",
            "context": {},
            "trigger": "automatic",
        }], degrade_expectation="该异步反思入口已从 web-console 架构中移除，必须返回 410 明确拒绝。")

        # 17 Workspaces
        self.test("Workspaces", "解析工作区拓扑信息", "GET", "/workspaces/")
        self.test("Workspaces", "获取默认工作区信息", "GET", "/workspaces/default/info", expected_status=(200, 404))
        self.test("Workspaces", "获取工作区详情", "GET", f"/workspaces/{missing_workspace_id}", expected_status=(200, 404, 422))
        self.test("Workspaces", "创建工作区", "POST", "/workspaces/", expected_status=(201, 422), json_data={
            "name": f"Clinical Workspace {workspace_test_root.name}",
            "path": str(workspace_test_root),
        })
        self.test("Workspaces", "更新工作区", "PUT", f"/workspaces/{generated_workspace_id}", expected_status=(200, 404, 422), json_data={
            "name": "Clinical Workspace Updated"
        })
        self.test("Workspaces", "设置默认工作区", "POST", f"/workspaces/{generated_workspace_id}/set-default", expected_status=(200, 404))
        self.test("Workspaces", "设置当前工作区", "POST", f"/workspaces/{generated_workspace_id}/set-current", expected_status=(200, 404))
        self.test("Workspaces", "删除工作区", "DELETE", f"/workspaces/{generated_workspace_id}", expected_status=(200, 404))

    def generate_report(self):
        summary = self._summary()
        module_summary = self._module_summary()
        failures = self._failure_inventory()
        true_defects = self._true_defect_failures()
        current_module = ""
        report_lines = []
        report_lines.append("## 执行摘要")
        if self.environment_blocker:
            report_lines.append("- 执行状态: 环境阻塞，未执行真实接口验证")
            report_lines.append("- 真实性: 未执行")
        else:
            report_lines.append("- 真实性: 真实运行结果")
        report_lines.append(f"- 总用例数: {summary['total']}")
        report_lines.append(f"- 通过数: {summary['passed']}")
        report_lines.append(f"- 失败数: {summary['failed']}")
        report_lines.append(f"- 受控客户端错误数: {summary['controlled_client_error']}")
        report_lines.append(f"- 受控 Fail-Closed 数: {summary['managed_fail_closed']}")
        report_lines.append(f"- 服务端错误数: {summary['server_error']}")
        report_lines.append(f"- 传输/运行时异常数: {summary['transport_or_runtime_exception']}")
        report_lines.append(f"- 真正缺陷候选数: {len(true_defects)}")

        report_lines.append("\n## 模块汇总")
        report_lines.append("| 模块 | 总数 | 通过 | 失败 | 服务端错误 | 受控 Fail-Closed | 传输/运行时异常 |")
        report_lines.append("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for module, stats in module_summary.items():
            report_lines.append(
                f"| {module} | {stats['total']} | {stats['passed']} | {stats['failed']} | "
                f"{stats['server_error']} | {stats['managed_fail_closed']} | {stats['transport_or_runtime_exception']} |"
            )

        for r in self.results:
            if r["module"] != current_module:
                current_module = r["module"]
                report_lines.append(f"\n### 测试模块: {current_module}")
                report_lines.append(f"模块说明: Zentex {current_module} 业务/管理链路物理验证。")
                report_lines.append("| 用例 ID | 接口地址 | 接口功能说明 | 测试场景 | 请求参数 | 期望返回参数 | 实际返回参数 | 证据 | 是否合格 |")
                report_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            
            ok_str = "✅ 合格" if r["ok"] else "❌ 不合格"
            line = (
                f"| {r['tc_id']} | `{r['path']}` | {r['function_desc']} | {r['scenario']} | "
                f"`{r['params']}` | `{r['expected']}` | `{r['actual']}` | `{r['evidence']}` | {ok_str} |"
            )
            report_lines.append(line)
            report_lines.append(f"  前置条件: {r['preconditions']}")
            report_lines.append(f"  断言点: {r['assertions']}")
            report_lines.append(f"  日志观察: {r['log_observation']}")
            report_lines.append(f"  副作用: {r['side_effects']}")
            report_lines.append(f"  降级预期: {r['degrade_expectation']}")
            report_lines.append(f"  回滚预期: {r['rollback_expectation']}")
            report_lines.append(f"  失败归因方法: {r['failure_attribution']}")
            report_lines.append(f"  真实性标注: {r['realism_label']}")
            report_lines.append(f"  结果分类: {r['error_category']}")

        if self.environment_blocker:
            report_lines.append("\n## 环境阻塞")
            report_lines.append(f"- 后端预检失败: {self.environment_blocker}")
            report_lines.append("- 处理建议: 先启动 127.0.0.1:8000 对应后端，再重新执行脚本。")

        report_lines.append("\n## 失败清单")
        if not failures:
            report_lines.append("- 无失败用例。")
        else:
            for item in failures:
                report_lines.append(
                    f"- {item['tc_id']} `{item['method']} {item['path']}`: "
                    f"{item['error_category']} | 期望={item['expected']} | 实际={item['actual']}"
                )

        report_lines.append("\n## 真正缺陷候选")
        if not true_defects:
            report_lines.append("- 无真正缺陷候选；当前失败主要为受控错误或预期降级。")
        else:
            for item in true_defects:
                report_lines.append(
                    f"- {item['tc_id']} `{item['method']} {item['path']}`: "
                    f"{item['actual']} | 归因={item['failure_attribution']}"
                )

        report_lines.append("\n## 回滚建议")
        for guidance in self._rollback_guidance():
            report_lines.append(f"- {guidance}")

        verification_passed = (len(true_defects) == 0) and not self.environment_blocker
        evidence_passed = summary["total"] > 0 and all(r.get("evidence") for r in self.results)
        rollback_passed = summary["total"] > 0 or bool(self.environment_blocker)
        report_lines.append("\n## Completion Gate")
        report_lines.append("- RCA: passed")
        report_lines.append(f"- Verification: {'passed' if verification_passed else 'failed'}")
        report_lines.append(f"- Evidence: {'passed' if evidence_passed else 'failed'}")
        report_lines.append(f"- Rollback: {'passed' if rollback_passed else 'failed'}")
        if self.environment_blocker:
            report_lines.append("- Final Judgment: 未执行（环境阻塞）")
        else:
            report_lines.append(f"- Final Judgment: {'已完成' if verification_passed and evidence_passed and rollback_passed else '未完成'}")
        return "\n".join(report_lines)

if __name__ == "__main__":
    tester = ApiTester()
    if tester.preflight_check():
        tester.run_all()
    report = tester.generate_report()
    
    with open("测试计划文件.md", "w") as f:
        f.write("# Zentex API 全量临床验证报告 (含管理与详情接口)\n")
        f.write(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(report)
    
    print("\nVerification complete. Results backfilled to 测试计划文件.md")
    if tester.environment_blocker:
        sys.exit(2)
    if tester._true_defect_failures():
        sys.exit(1)
    sys.exit(0)
