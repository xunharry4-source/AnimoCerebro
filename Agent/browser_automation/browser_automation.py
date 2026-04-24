"""
Browser Automation Module - 基于Playwright的浏览器自动化

文件用途:
    提供基于Playwright的浏览器自动化能力，用于在X和Reddit平台自动发帖。
    支持机器人检测、人工协助等待、会话管理等功能。

主要职责:
    - 启动和管理浏览器实例
    - 自动登录X和Reddit账号
    - 自动发布内容到X和Reddit
    - 检测机器人验证(CAPTCHA)并等待人工处理
    - 管理浏览器会话和cookies
    - 提供截图和调试功能

不负责:
    - 不绕过或破解CAPTCHA验证
    - 不存储用户密码（使用环境变量或配置文件）
    - 不违反平台服务条款
    - 不处理付费广告功能
"""

import logging
import os
import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("⚠️ Playwright not installed. Install with: pip install playwright")


class BotDetectionHandler:
    """机器人检测处理器"""

    def __init__(self, page: Page):
        self.page = page
        self.detected = False
        self.detection_time = None

    def check_for_captcha(self) -> bool:
        """检查是否存在CAPTCHA或机器人验证"""
        captcha_indicators = [
            # reCAPTCHA
            "recaptcha",
            "g-recaptcha",
            "#recaptcha",
            # hCaptcha
            "hcaptcha",
            "h-captcha",
            # Cloudflare Turnstile
            "turnstile",
            "cf-turnstile",
            # General CAPTCHA
            "captcha",
            "verify you are human",
            "prove you're not a robot",
            # Checkbox
            "I'm not a robot",
            "我不是机器人"
        ]

        page_content = self.page.content().lower()

        for indicator in captcha_indicators:
            if indicator.lower() in page_content:
                self.detected = True
                self.detection_time = datetime.now(timezone.utc)
                logger.warning(f"⚠️ CAPTCHA detected: {indicator}")
                return True

        # 检查是否有验证iframe
        frames = self.page.frames
        for frame in frames:
            frame_url = frame.url.lower()
            if any(x in frame_url for x in ["recaptcha", "hcaptcha", "turnstile"]):
                self.detected = True
                self.detection_time = datetime.now(timezone.utc)
                logger.warning(f"⚠️ CAPTCHA iframe detected: {frame_url}")
                return True

        return False

    def wait_for_human_assistance(self, timeout_minutes: int = 10) -> bool:
        """
        等待人工协助处理机器人验证

        Args:
            timeout_minutes: 超时时间（分钟）

        Returns:
            是否成功通过验证
        """
        if not self.detected:
            return True

        print("\n" + "=" * 70)
        print("🤖 BOT DETECTION - HUMAN ASSISTANCE REQUIRED")
        print("=" * 70)
        print(f"⚠️ 检测到机器人验证（CAPTCHA）")
        print(f"📍 当前页面: {self.page.url}")
        print(f"⏰ 检测时间: {self.detection_time}")
        print(f"\n请在 {timeout_minutes} 分钟内完成以下操作:")
        print("  1. 在打开的浏览器窗口中完成CAPTCHA验证")
        print("  2. 确保成功通过验证")
        print("  3. 完成后，程序将继续自动执行")
        print("=" * 70)

        # 保存截图
        screenshot_path = f"captcha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        try:
            self.page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n📸 截图已保存: {screenshot_path}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")

        # 等待人工处理
        max_wait = timeout_minutes * 60
        check_interval = 5  # 每5秒检查一次
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(check_interval)
            elapsed += check_interval

            # 检查CAPTCHA是否消失
            if not self.check_for_captcha():
                print("\n✅ CAPTCHA cleared! Continuing...")
                logger.info("CAPTCHA cleared by human assistance")
                return True

            # 显示剩余时间
            remaining = max_wait - elapsed
            if remaining % 60 == 0:
                print(f"⏳ Waiting... {remaining // 60} minutes remaining")

        print(f"\n❌ Timeout after {timeout_minutes} minutes")
        logger.error(f"CAPTCHA timeout after {timeout_minutes} minutes")
        return False


class BrowserAutomationManager:
    """
    浏览器自动化管理器

    功能:
    - 管理浏览器实例和上下文
    - 处理登录和会话
    - 执行发帖操作
    - 检测和处理机器人验证
    """

    def __init__(self, headless: bool = False, slow_mo: int = 500):
        """
        初始化浏览器自动化管理器

        Args:
            headless: 是否无头模式（False为显示浏览器窗口）
            slow_mo: 操作延迟毫秒数（模拟人类操作速度）
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is required for browser automation. "
                "Install with: pip install playwright && playwright install"
            )

        self.headless = headless
        self.slow_mo = slow_mo
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.bot_handler: Optional[BotDetectionHandler] = None

        # 会话存储
        self.session_dir = Path("browser_sessions")
        self.session_dir.mkdir(exist_ok=True)

        logger.info(f"✅ BrowserAutomationManager initialized (headless={headless})")

    def start_browser(self, browser_type: str = "chromium") -> None:
        """
        启动浏览器

        Args:
            browser_type: 浏览器类型 ("chromium", "firefox", "webkit")
        """
        self.playwright = sync_playwright().start()

        if browser_type == "chromium":
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo
            )
        elif browser_type == "firefox":
            self.browser = self.playwright.firefox.launch(
                headless=self.headless,
                slow_mo=self.slow_mo
            )
        elif browser_type == "webkit":
            self.browser = self.playwright.webkit.launch(
                headless=self.headless,
                slow_mo=self.slow_mo
            )
        else:
            raise ValueError(f"Unsupported browser type: {browser_type}")

        # 创建上下文（模拟真实浏览器）
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York"
        )

        # 创建新页面
        self.page = self.context.new_page()
        self.bot_handler = BotDetectionHandler(self.page)

        logger.info(f"✅ Browser started: {browser_type}")

    def stop_browser(self) -> None:
        """关闭浏览器"""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

        logger.info("✅ Browser stopped")

    def save_session(self, session_name: str) -> str:
        """
        保存浏览器会话（cookies和storage）

        Args:
            session_name: 会话名称

        Returns:
            会话文件路径
        """
        if not self.context:
            raise RuntimeError("Browser context not initialized")

        session_file = self.session_dir / f"{session_name}.json"

        # 保存cookies
        cookies = self.context.cookies()
        session_data = {
            "cookies": cookies,
            "url": self.page.url if self.page else "",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)

        logger.info(f"✅ Session saved: {session_file}")
        return str(session_file)

    def load_session(self, session_name: str) -> bool:
        """
        加载浏览器会话

        Args:
            session_name: 会话名称

        Returns:
            是否成功加载
        """
        if not self.context:
            raise RuntimeError("Browser context not initialized")

        session_file = self.session_dir / f"{session_name}.json"

        if not session_file.exists():
            logger.warning(f"Session file not found: {session_file}")
            return False

        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)

        # 恢复cookies
        if "cookies" in session_data:
            self.context.add_cookies(session_data["cookies"])
            logger.info(f"✅ Session loaded: {session_name}")
            return True

        return False

    def login_to_x(self, username: str, password: str) -> Dict[str, Any]:
        """
        登录X (Twitter)

        Args:
            username: 用户名/邮箱/手机号
            password: 密码

        Returns:
            登录结果
        """
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        try:
            logger.info("🔐 Logging in to X...")

            # 导航到登录页面
            self.page.goto("https://twitter.com/i/flow/login", wait_until="networkidle")
            time.sleep(2)

            # 检查是否已登录
            if "home" in self.page.url:
                logger.info("✅ Already logged in to X")
                return {"success": True, "message": "Already logged in"}

            # 输入用户名/邮箱
            username_input = self.page.locator('input[autocomplete="username"]')
            if username_input.count() > 0:
                username_input.fill(username)
                time.sleep(1)
                self.page.keyboard.press("Enter")
                time.sleep(2)

            # 输入密码
            password_input = self.page.locator('input[type="password"]')
            if password_input.count() > 0:
                password_input.fill(password)
                time.sleep(1)
                self.page.keyboard.press("Enter")
                time.sleep(3)

            # 检查登录是否成功
            if "home" in self.page.url or "home" in self.page.title().lower():
                logger.info("✅ Successfully logged in to X")

                # 检查是否有机器人验证
                if self.bot_handler.check_for_captcha():
                    success = self.bot_handler.wait_for_human_assistance()
                    if not success:
                        return {
                            "success": False,
                            "error": "CAPTCHA verification failed or timed out"
                        }

                return {"success": True, "message": "Login successful"}
            else:
                logger.error("❌ Login failed")
                return {
                    "success": False,
                    "error": "Login failed. Check credentials."
                }

        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def login_to_reddit(self, username: str, password: str) -> Dict[str, Any]:
        """
        登录Reddit

        Args:
            username: 用户名
            password: 密码

        Returns:
            登录结果
        """
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        try:
            logger.info("🔐 Logging in to Reddit...")

            # 导航到登录页面
            self.page.goto("https://www.reddit.com/login", wait_until="networkidle")
            time.sleep(2)

            # 检查是否已登录
            if self.page.url == "https://www.reddit.com/" or "reddit.com" in self.page.url:
                user_menu = self.page.locator('button[aria-label="User menu"]')
                if user_menu.count() > 0:
                    logger.info("✅ Already logged in to Reddit")
                    return {"success": True, "message": "Already logged in"}

            # 输入用户名
            username_input = self.page.locator('input[name="username"]')
            if username_input.count() > 0:
                username_input.fill(username)
                time.sleep(1)

            # 输入密码
            password_input = self.page.locator('input[name="password"]')
            if password_input.count() > 0:
                password_input.fill(password)
                time.sleep(1)

            # 点击登录按钮
            login_button = self.page.locator('button[type="submit"]')
            if login_button.count() > 0:
                login_button.click()
                time.sleep(3)

            # 检查登录是否成功
            time.sleep(2)
            if "reddit.com" in self.page.url:
                logger.info("✅ Successfully logged in to Reddit")

                # 检查是否有机器人验证
                if self.bot_handler.check_for_captcha():
                    success = self.bot_handler.wait_for_human_assistance()
                    if not success:
                        return {
                            "success": False,
                            "error": "CAPTCHA verification failed or timed out"
                        }

                return {"success": True, "message": "Login successful"}
            else:
                logger.error("❌ Login failed")
                return {
                    "success": False,
                    "error": "Login failed. Check credentials."
                }

        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def post_to_x(self, content: str, media_files: List[str] = None) -> Dict[str, Any]:
        """
        发布帖子到X

        Args:
            content: 帖子内容
            media_files: 媒体文件路径列表（可选）

        Returns:
            发布结果
        """
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        try:
            logger.info(f"📝 Posting to X: {content[:50]}...")

            # 导航到主页
            self.page.goto("https://twitter.com/home", wait_until="networkidle")
            time.sleep(2)

            # 点击推文按钮
            tweet_button = self.page.locator('div[data-testid="SideNav_NewTweet_Button"]')
            if tweet_button.count() == 0:
                # 尝试其他选择器
                tweet_button = self.page.locator('a[href="/compose/post"]')

            if tweet_button.count() > 0:
                tweet_button.click()
                time.sleep(1)
            else:
                # 直接在文本框中输入
                logger.info("Using direct text input method")

            # 输入内容
            textarea = self.page.locator('div[data-testid="tweetTextarea_0"]')
            if textarea.count() > 0:
                textarea.click()
                time.sleep(0.5)
                textarea.fill(content)
                time.sleep(1)

            # 上传媒体文件（如果有）
            if media_files:
                for media_file in media_files:
                    if os.path.exists(media_file):
                        file_input = self.page.locator('input[type="file"]')
                        if file_input.count() > 0:
                            file_input.set_input_files(media_file)
                            time.sleep(2)

            # 点击发布按钮
            post_button = self.page.locator('div[data-testid="tweetButton"]')
            if post_button.count() > 0:
                # 检查按钮是否可点击
                if "disabled" not in post_button.evaluate("el => el.getAttribute('disabled') or ''"):
                    post_button.click()
                    time.sleep(3)

                    # 检查是否有机器人验证
                    if self.bot_handler.check_for_captcha():
                        success = self.bot_handler.wait_for_human_assistance()
                        if not success:
                            return {
                                "success": False,
                                "error": "CAPTCHA verification failed or timed out"
                            }

                    logger.info("✅ Post published to X")
                    return {
                        "success": True,
                        "message": "Post published successfully",
                        "url": self.page.url
                    }
                else:
                    return {
                        "success": False,
                        "error": "Post button is disabled (content may be empty or too long)"
                    }
            else:
                return {
                    "success": False,
                    "error": "Could not find post button"
                }

        except Exception as e:
            logger.error(f"❌ Post error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def post_to_reddit(self, subreddit: str, title: str,
                       content: str, post_type: str = "text") -> Dict[str, Any]:
        """
        发布帖子到Reddit

        Args:
            subreddit: 子版块名称
            title: 帖子标题
            content: 帖子内容
            post_type: 帖子类型 ("text", "link", "image")

        Returns:
            发布结果
        """
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        try:
            logger.info(f"📝 Posting to r/{subreddit}: {title[:50]}...")

            # 导航到提交页面
            submit_url = f"https://www.reddit.com/r/{subreddit}/submit"
            self.page.goto(submit_url, wait_until="networkidle")
            time.sleep(2)

            # 选择帖子类型
            if post_type == "text":
                text_tab = self.page.locator('button:has-text("Text")')
                if text_tab.count() > 0:
                    text_tab.click()
                    time.sleep(1)

            # 输入标题
            title_input = self.page.locator('input[name="title"]')
            if title_input.count() > 0:
                title_input.fill(title)
                time.sleep(1)

            # 输入内容
            if post_type == "text":
                # 切换到markdown编辑器
                markdown_tab = self.page.locator('button:has-text("Markdown")')
                if markdown_tab.count() > 0:
                    markdown_tab.click()
                    time.sleep(0.5)

                content_input = self.page.locator('textarea[name="text"]')
                if content_input.count() > 0:
                    content_input.fill(content)
                    time.sleep(1)

            # 点击发布按钮
            post_button = self.page.locator('button[type="submit"]')
            if post_button.count() > 0:
                # 滚动到按钮并点击
                post_button.scroll_into_view_if_needed()
                time.sleep(0.5)
                post_button.click()
                time.sleep(3)

                # 检查是否有机器人验证
                if self.bot_handler.check_for_captcha():
                    success = self.bot_handler.wait_for_human_assistance()
                    if not success:
                        return {
                            "success": False,
                            "error": "CAPTCHA verification failed or timed out"
                        }

                # 检查是否发布成功
                current_url = self.page.url
                if f"/r/{subreddit}/comments/" in current_url:
                    logger.info(f"✅ Post published to r/{subreddit}")
                    return {
                        "success": True,
                        "message": f"Post published to r/{subreddit}",
                        "url": current_url
                    }
                else:
                    # 可能有错误
                    error_element = self.page.locator('div[class*="error"]')
                    if error_element.count() > 0:
                        error_text = error_element.text_content()
                        return {
                            "success": False,
                            "error": f"Reddit error: {error_text}"
                        }

                    return {
                        "success": True,
                        "message": "Post submitted (verification needed)",
                        "url": current_url
                    }
            else:
                return {
                    "success": False,
                    "error": "Could not find post button"
                }

        except Exception as e:
            logger.error(f"❌ Reddit post error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def take_screenshot(self, filename: str = None) -> str:
        """
        截取屏幕截图

        Args:
            filename: 文件名（可选）

        Returns:
            截图文件路径
        """
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        screenshot_path = self.page.screenshot(path=filename, full_page=True)
        logger.info(f"📸 Screenshot saved: {filename}")
        return filename

    def check_login_status(self, platform: str) -> bool:
        """
        检查登录状态

        Args:
            platform: 平台名称 ("x" 或 "reddit")

        Returns:
            是否已登录
        """
        if not self.page:
            return False

        try:
            if platform.lower() == "x":
                # 检查X的登录状态
                return "home" in self.page.url or self.page.url == "https://twitter.com/home"

            elif platform.lower() == "reddit":
                # 检查Reddit的登录状态
                user_menu = self.page.locator('button[aria-label="User menu"]')
                return user_menu.count() > 0

        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False
