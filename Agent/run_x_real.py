#!/usr/bin/env python3
"""
X real posting runner.

文件用途:
    使用真实 LLM、真实 Google Chrome 持久化会话和 LangGraph X 节点执行真实 X 发帖测试，
    并保存主动 permalink 验证结果。

主要职责:
    - 启动真实 Chrome profile，并复用已有 X 登录态。
    - 调用 XPostingWorkflow 的真实节点链路。
    - 只在拿到 X status URL 且主动打开验证通过后写入 success=true。
    - 将成功或失败结果写入 Agent/data/x_real_post_last_result.json。

不负责:
    - 不生成或保存 X 账号密码。
    - 不绕过 X CAPTCHA、风控或平台限制。
    - 不使用 Mock LLM、fixture 页面或示例 URL 冒充真实成功。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path  # noqa: E402
from Agent.posting_workflows.errors import PostingWorkflowError  # noqa: E402
from Agent.posting_workflows.state import WorkflowContext, XPostingState  # noqa: E402
from Agent.posting_workflows.x.orchestrator import XPostingWorkflow  # noqa: E402


RESULT_PATH = Path("Agent/data/x_real_post_last_result.json")
PROFILE_DIR = Path("./chrome_custom_profile")


def main(*, page: Optional[Any] = None, trace_id: Optional[str] = None) -> bool:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {
        "success": False,
        "platform": "x",
        "target": "https://x.com",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "post_url": None,
        "realism": "真实运行结果",
        "browser_reuse": "injected_service_page" if page is not None else "runner_owned_persistent_context",
    }
    playwright = None
    context = None
    owns_browser = page is None

    try:
        if page is None:
            executable_path = get_chrome_path()
            user_data_dir = PROFILE_DIR.resolve()
            user_data_dir.mkdir(parents=True, exist_ok=True)
            _remove_stale_singleton_links(user_data_dir)
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                executable_path=executable_path,
                headless=False,
                slow_mo=500,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-infobars",
                    "--disable-search-engine-choice-screen",
                    "--disable-sync",
                ],
                bypass_csp=True,
            )
            context.add_init_script(STEALTH_JS)
            page = context.pages[0] if context.pages else context.new_page()
            page.add_init_script(STEALTH_JS)

        workflow_context = WorkflowContext(page=page, trace_id=trace_id) if trace_id else WorkflowContext(page=page)
        state = XPostingWorkflow(context=workflow_context).run(XPostingState())
        result.update(
            {
                "success": state.status == "success",
                "status": state.status,
                "trace_id": workflow_context.trace_id,
                "topic": state.topic,
                "content": state.content,
                "post_url": state.post_url,
                "attempts": state.attempts,
                "error": state.error,
                "evidence": [_evidence_to_dict(item) for item in state.evidence],
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        result["page_evidence"] = _capture_page_evidence(page)
    except PostingWorkflowError as exc:
        result.update(
            {
                "success": False,
                "error": exc.to_dict(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as exc:
        result.update(
            {
                "success": False,
                "error": {
                    "node": "run_x_real",
                    "code": "unexpected_exception",
                    "message": f"{exc.__class__.__name__}: {exc}",
                    "details": {},
                },
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    finally:
        if owns_browser and context is not None:
            context.close()
        if owns_browser and playwright is not None:
            playwright.stop()

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"结果文件: {RESULT_PATH}")
    return bool(result.get("success"))


def _evidence_to_dict(item: Any) -> Dict[str, Any]:
    return {
        "node": getattr(item, "node", None),
        "success": getattr(item, "success", None),
        "message": getattr(item, "message", None),
        "data": getattr(item, "data", {}),
        "timestamp": getattr(item, "timestamp", None),
    }


def _capture_page_evidence(page: Any) -> Dict[str, Any]:
    screenshot_path = Path("Agent/data/x_real_last_page.png")
    evidence: Dict[str, Any] = {
        "url": str(getattr(page, "url", "") or ""),
        "screenshot_path": str(screenshot_path),
    }
    try:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as exc:
        evidence["screenshot_error"] = f"{exc.__class__.__name__}: {exc}"
    try:
        evidence["body_snippet"] = str(page.locator("body").inner_text(timeout=5000) or "")[:2000]
    except Exception as exc:
        evidence["body_error"] = f"{exc.__class__.__name__}: {exc}"
    return evidence


def _remove_stale_singleton_links(user_data_dir: Path) -> None:
    """Remove Chrome singleton links only when their target no longer exists."""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = user_data_dir / name
        if not path.exists() and not path.is_symlink():
            continue
        try:
            target = Path(path.resolve(strict=False)) if path.is_symlink() else path
            if path.is_symlink() and not target.exists():
                path.unlink()
        except OSError:
            # If the profile is genuinely in use, Chrome will fail closed during launch.
            continue


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
