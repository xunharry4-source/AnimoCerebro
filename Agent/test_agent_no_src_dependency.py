#!/usr/bin/env python3
"""
Agent no-src dependency guard tests.

文件用途:
    防止社交发布核心 Agent 链路重新依赖 `src/` 或 `zentex.*` 内部代码。

主要职责:
    - 检查 Agent 本地 LLM client 和真实 runner 不导入 `zentex.*`。
    - 检查核心发布链路不把 `src/` 注入 `sys.path`。
    - 将“Agent 使用自己代码”的架构约束变成可回归测试。

不负责:
    - 不扫描历史遗留诊断脚本。
    - 不证明真实平台发帖成功。
    - 不验证外部 provider 的网络可用性。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUARDED_PATHS = [
    PROJECT_ROOT / "Agent" / "local_llm_client.py",
    PROJECT_ROOT / "Agent" / "posting_workflows" / "llm_client.py",
    PROJECT_ROOT / "Agent" / "reddit_popup_llm_interpreter.py",
    PROJECT_ROOT / "Agent" / "run_x_real.py",
    PROJECT_ROOT / "Agent" / "run_reddit_smart_poster_real.py",
    PROJECT_ROOT / "Agent" / "browser_automation" / "test_auto_stealth_wait.py",
]


def test_core_agent_posting_code_does_not_import_src_or_zentex():
    forbidden_fragments = (
        "from zentex",
        "import zentex",
        'sys.path.insert(0, str(project_root / "src"))',
        "sys.path.insert(0, str(project_root / 'src'))",
        "sys.path.insert(0, str(repo_src))",
    )
    violations = []
    for path in GUARDED_PATHS:
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {fragment}")

    assert violations == []
