#!/usr/bin/env python3
"""
RedditSmartPoster real entry runner.

文件用途:
    使用 Agent/social_promotion/reddit_smart_poster.py 作为唯一 Reddit 发帖入口，
    运行真实浏览器发帖尝试并保存结构化结果。

主要职责:
    - 启动真实 Chrome 持久化上下文
    - 调用 RedditSmartPoster.post_custom_content_with_evidence()
    - 将成功或失败证据写入 Agent/data/reddit_smart_poster_last_result.json

不负责:
    - 不创建模拟成功结果
    - 不绕过 Reddit 登录、CAPTCHA、风控或社区规则
    - 不在缺少 permalink 主动验证时写入真实成功证据
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path
from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster


TEST_SUBREDDIT = "AnimoCerebro"
TEST_TITLE = f"RedditSmartPoster 真实验证 {int(time.time())}"
TEST_BODY = "这是 RedditSmartPoster 入口的真实发帖验证。只有拿到 permalink 并主动打开验证后才算成功。"
TARGET_FLAIR = "不适合工作场合"
RESULT_PATH = Path("Agent/data/reddit_smart_poster_last_result.json")


def main() -> bool:
    print("\n" + "=" * 80)
    print("RedditSmartPoster 真实入口测试")
    print("=" * 80)
    print(f"社区: r/{TEST_SUBREDDIT}")
    print(f"标题: {TEST_TITLE}")

    executable_path = get_chrome_path()
    user_data_dir = Path("./chrome_custom_profile").resolve()
    user_data_dir.mkdir(exist_ok=True)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)

    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        executable_path=executable_path,
        headless=False,
        slow_mo=500,
        viewport={"width": 1920, "height": 1080},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    context.add_init_script(STEALTH_JS)
    page = context.pages[0] if context.pages else context.new_page()

    try:
        poster = RedditSmartPoster(page)
        result = poster.post_custom_content_with_evidence(
            subreddit=TEST_SUBREDDIT,
            title=TEST_TITLE,
            content=TEST_BODY,
            flair=TARGET_FLAIR,
            max_retries=1,
        )
        serializable_result = _make_json_safe(result)
        RESULT_PATH.write_text(
            json.dumps(serializable_result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        print("\n结果:")
        print(json.dumps(serializable_result, ensure_ascii=False, indent=2, default=str))
        print(f"\n结果文件: {RESULT_PATH}")
        return bool(result.get("success"))
    finally:
        context.close()
        playwright.stop()


def _make_json_safe(value, seen=None):
    """转换运行结果为 JSON 安全对象，循环引用明确标记而不是写入失败。"""
    seen = seen or set()
    object_id = id(value)
    if isinstance(value, (dict, list, tuple, set)):
        if object_id in seen:
            return "<circular_reference_removed>"
        seen.add(object_id)
        if isinstance(value, dict):
            return {str(key): _make_json_safe(item, seen) for key, item in value.items()}
        return [_make_json_safe(item, seen) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
