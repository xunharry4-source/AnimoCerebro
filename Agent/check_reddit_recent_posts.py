#!/usr/bin/env python3
"""
Reddit 只读最新帖子验证脚本。

文件用途:
    在真实浏览器中打开目标 subreddit 最新帖子页，检查指定标题是否可见，
    并在可见时提取 permalink 后主动打开验证。

主要职责:
    - 打开目标 subreddit 的 newest-post 页面
    - 收集可见文本、permalink、截图和主动验证结果
    - 将检查结果写入 Agent/data/reddit_recent_check_last_result.json

不负责:
    - 不发布、编辑或删除 Reddit 帖子
    - 不把仅列表可见当作最终成功证据
    - 不绕过 Reddit API、登录、CAPTCHA 或网络限制
"""

from __future__ import annotations

import sys
import time
import os
import json
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path
from Agent.posting_workflows.verification_gate import is_platform_post_url


DEFAULT_SUBREDDIT = "AnimoCerebro"
DEFAULT_TITLE = "Tesseract OCR 视觉识别测试"
RESULT_PATH = Path("Agent/data/reddit_recent_check_last_result.json")


def check_recent_posts(subreddit: str = DEFAULT_SUBREDDIT, expected_title: str = DEFAULT_TITLE) -> bool:
    print("\n" + "=" * 80)
    print("🔎 Reddit 只读真实帖子检查")
    print("=" * 80)
    executable_path = get_chrome_path()
    user_data_dir = Path("./chrome_custom_profile").resolve()
    screenshot_dir = Path("screenshots")
    screenshot_dir.mkdir(exist_ok=True)

    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        executable_path=executable_path,
        headless=False,
        slow_mo=300,
        viewport={"width": 1920, "height": 1080},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    context.add_init_script(STEALTH_JS)
    page = context.pages[0] if context.pages else context.new_page()

    try:
        url = f"https://www.reddit.com/r/{subreddit}/new/"
        print(f"🌐 打开: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        current_url = page.url
        body_text = page.locator("body").inner_text(timeout=10000)
        found = expected_title in body_text
        post_url = _extract_post_url(page, expected_title)
        screenshot_path = screenshot_dir / f"reddit_recent_check_{int(time.time())}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        active_verification = None
        if found and post_url and is_platform_post_url("reddit", post_url, subreddit=subreddit):
            active_verification = _active_verify_permalink(page, post_url, subreddit, expected_title)

        result = {
            "platform": "reddit",
            "subreddit": subreddit,
            "expected_title": expected_title,
            "found_in_recent_list": found,
            "post_url": post_url,
            "recent_page_url": current_url,
            "recent_screenshot_path": str(screenshot_path),
            "active_verification": active_verification,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"当前 URL: {current_url}")
        print(f"检查标题: {expected_title}")
        print(f"是否可见: {found}")
        print(f"帖子 URL: {post_url}")
        print(f"主动验证: {bool(active_verification and active_verification.get('content_match'))}")
        print(f"截图证据: {screenshot_path}")
        print(f"结果文件: {RESULT_PATH}")
        return bool(active_verification and active_verification.get("content_match"))
    finally:
        context.close()
        playwright.stop()


def _extract_post_url(page, expected_title: str) -> str:
    """从最新帖子页提取包含指定标题的 Reddit permalink。"""
    try:
        return str(page.evaluate(
            """
            (expectedTitle) => {
                const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                const expected = normalize(expectedTitle);
                const absolutize = (href) => {
                    if (!href) return null;
                    try { return new URL(href, location.href).href; } catch { return null; }
                };

                const posts = Array.from(document.querySelectorAll('shreddit-post, article, [data-testid="post-container"]'));
                for (const post of posts) {
                    const text = normalize(post.innerText || post.textContent || '');
                    if (!text.includes(expected)) continue;
                    const attrHref = post.getAttribute('permalink') || post.getAttribute('content-href');
                    const attrUrl = absolutize(attrHref);
                    if (attrUrl) return attrUrl;
                    const link = Array.from(post.querySelectorAll('a[href]'))
                        .find((anchor) => /\\/comments\\//.test(anchor.getAttribute('href') || ''));
                    const linkUrl = absolutize(link?.getAttribute('href'));
                    if (linkUrl) return linkUrl;
                }

                const directLink = Array.from(document.querySelectorAll('a[href]'))
                    .find((anchor) => {
                        const text = normalize(anchor.innerText || anchor.textContent || anchor.getAttribute('aria-label') || '');
                        return text.includes(expected) && /\\/comments\\//.test(anchor.getAttribute('href') || '');
                    });
                return absolutize(directLink?.getAttribute('href')) || '';
            }
            """,
            expected_title,
        ) or "")
    except Exception as exc:
        print(f"提取帖子 URL 失败: {exc}")
        return ""


def _active_verify_permalink(page, post_url: str, subreddit: str, expected_title: str) -> dict:
    """主动打开 permalink 并验证标题可见。"""
    screenshot_dir = Path("screenshots")
    screenshot_dir.mkdir(exist_ok=True)
    response = page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    observed_url = page.url
    body_text = page.locator("body").inner_text(timeout=10000)
    screenshot_path = screenshot_dir / f"reddit_permalink_verify_{int(time.time())}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    status = getattr(response, "status", None)
    return {
        "verification_source": "active_browser_permalink_open",
        "post_url": post_url,
        "observed_url": observed_url,
        "response_status": int(status) if isinstance(status, int) else None,
        "url_shape_valid": is_platform_post_url("reddit", observed_url, subreddit=subreddit),
        "content_match": expected_title in body_text,
        "body_snippet": body_text[:500],
        "screenshot_path": str(screenshot_path),
    }


if __name__ == "__main__":
    subreddit_arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("REDDIT_CHECK_SUBREDDIT", DEFAULT_SUBREDDIT)
    title_arg = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("REDDIT_CHECK_TITLE", DEFAULT_TITLE)
    ok = check_recent_posts(subreddit_arg, title_arg)
    sys.exit(0 if ok else 1)
