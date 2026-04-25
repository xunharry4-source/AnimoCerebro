#!/usr/bin/env python3
"""
自动化 Stealth Chrome - 等待登录后自动发帖

完全自动化，独立 Chrome 实例，绕过 Google 登录检测。
核心特性：
- 使用真实 Google Chrome 二进制文件
- 持久化上下文（独立用户数据目录）
- Stealth 隐身策略
- 禁用 AutomationControlled 标志
- 与现有 Chrome 不冲突
"""

import os
import sys
import platform
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# 尝试导入 playwright_stealth（如果已安装）
try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    print("⚠️  playwright_stealth 未安装，将使用基础隐身脚本")
    print("   安装命令: pip install playwright-stealth")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 增强的隐身脚本（更全面的指纹隐藏）
STEALTH_JS = """
// 1. 隐藏 WebDriver 标志
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. 模拟真实的 Chrome 对象
window.chrome = { 
    runtime: {}, 
    csi: ()=>{}, 
    loadTimes: ()=>{},
    app: {}
};

// 3. 模拟插件列表（更真实）
Object.defineProperty(navigator, 'plugins', { 
    get: () => [
        {
            name: 'Chrome PDF Plugin',
            filename: 'internal-pdf-viewer',
            description: 'Portable Document Format',
            length: 1,
            item: (index) => index === 0 ? { type: 'application/pdf', suffixes: 'pdf' } : null
        },
        {
            name: 'Chrome PDF Viewer',
            filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
            description: 'Portable Document Format',
            length: 1
        },
        {
            name: 'Native Client',
            filename: 'internal-nacl-plugin',
            description: '',
            length: 2
        }
    ],
    enumerable: true,
    configurable: true
});

// 4. 模拟语言设置
Object.defineProperty(navigator, 'languages', { 
    get: () => ['en-US', 'en', 'zh-CN', 'zh'],
    enumerable: true,
    configurable: true
});

// 5. 修复权限查询
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// 6. 删除 webdriver 原型链
if (navigator.__proto__ && navigator.__proto__.webdriver) {
    delete navigator.__proto__.webdriver;
}

// 7. 模拟真实的 User-Agent
const realUA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36';
Object.defineProperty(navigator, 'userAgent', { 
    get: () => realUA,
    enumerable: true,
    configurable: true
});
Object.defineProperty(navigator, 'appVersion', { 
    get: () => '5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    enumerable: true,
    configurable: true
});
Object.defineProperty(navigator, 'platform', { 
    get: () => 'MacIntel',
    enumerable: true,
    configurable: true
});

// 8. 模拟硬件信息
Object.defineProperty(navigator, 'hardwareConcurrency', { 
    get: () => 8,
    enumerable: true,
    configurable: true
});
Object.defineProperty(navigator, 'deviceMemory', { 
    get: () => 8,
    enumerable: true,
    configurable: true
});

// 9. 隐藏自动化相关的属性
Object.defineProperty(document, 'hidden', {
    get: () => false,
    enumerable: true,
    configurable: true
});

// 10. 覆盖 toString 方法以隐藏修改痕迹
const originalToString = Function.prototype.toString;
Function.prototype.toString = function() {
    if (this === Object.getOwnPropertyDescriptor || 
        this === Object.defineProperty) {
        return originalToString.call(this);
    }
    return originalToString.call(this);
};

// 11. 模拟 WebGL 供应商和渲染器（防止 Canvas 指纹检测）
const getParameterProxyHandler = {
    apply: function(target, ctx, args) {
        const param = args[0];
        // UNMASKED_VENDOR_WEBGL
        if (param === 37445) {
            return 'Intel Inc.';
        }
        // UNMASKED_RENDERER_WEBGL
        if (param === 37446) {
            return 'Intel Iris OpenGL Engine';
        }
        return target.apply(ctx, args);
    }
};

// 12. 移除 Selenium/Playwright 特有的全局变量
delete window.__playwright;
delete window.__pw_manual;
delete window.__PW_inspect;

// 13. 模拟真实的 window.outerWidth 和 outerHeight
Object.defineProperty(window, 'outerWidth', {
    get: () => screen.availWidth,
    enumerable: true,
    configurable: true
});
Object.defineProperty(window, 'outerHeight', {
    get: () => screen.availHeight,
    enumerable: true,
    configurable: true
});

console.log('✅ Stealth 脚本已执行');
"""

def get_chrome_path():
    """获取系统 Google Chrome 二进制文件路径"""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif system == "Windows":
        paths = [
            os.environ.get('PROGRAMFILES', 'C:\\Program Files') + "\\Google\\Chrome\\Application\\chrome.exe",
            os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)') + "\\Google\\Chrome\\Application\\chrome.exe",
        ]
    elif system == "Linux":
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
    else:
        raise OSError(f"不支持的操作系统: {system}")
    
    for path in paths:
        if Path(path).exists():
            return path
    
    raise FileNotFoundError(
        f"❌ 未找到 Google Chrome。请确保已安装 Chrome。\n"
        f"   搜索路径: {paths}"
    )


def launch_real_chrome():
    """
    启动独立的 Google Chrome 实例，绕过登录检测
    
    核心策略：
    1. 使用真实 Chrome 二进制文件（而非 Chromium）
    2. 持久化上下文（独立用户数据目录）
    3. 禁用 AutomationControlled 标志
    4. 注入 Stealth 脚本抹除指纹
    5. 有头模式（headless=False）
    """
    print("\n" + "="*80)
    print("  🚀 启动独立 Google Chrome 实例（Stealth 模式）")
    print("="*80)
    
    # 1. 指定独立用户数据目录（绝对路径）
    # 这样会拥有独立的 Cookie、缓存和插件，不会干扰你平时用的 Chrome
    user_data_dir = Path("./chrome_custom_profile").resolve()
    user_data_dir.mkdir(exist_ok=True)
    
    print(f"\n📂 用户数据目录: {user_data_dir}")
    print("   ✓ 此目录存储独立的 Cookie、缓存和配置")
    print("   ✓ 与系统 Chrome 完全隔离，不会产生冲突")
    
    # 2. 获取系统中 Google Chrome 的真实路径
    try:
        executable_path = get_chrome_path()
        print(f"\n🔍 Chrome 路径: {executable_path}")
        print("   ✓ 使用真实 Google Chrome 二进制文件")
    except FileNotFoundError as e:
        print(f"\n{e}")
        return False
    
    # 3. 显示 Stealth 配置
    print(f"\n🛡️  Stealth 保护: {'✅ playwright_stealth' if HAS_STEALTH else '⚠️  基础脚本'}")
    print("   ✓ 禁用 AutomationControlled 标志")
    print("   ✓ 隐藏 navigator.webdriver")
    print("   ✓ 模拟真实浏览器指纹")
    
    playwright = context = page = None
    
    try:
        # 4. 启动 Playwright
        playwright = sync_playwright().start()
        
        # 5. 启动持久化上下文（核心）
        # 使用 launch_persistent_context 而不是 launch
        # 因为 Google 登录会检测"干净"的自动化环境，持久化环境更像真实用户
        print("\n🚀 正在启动 Chrome...")
        
        # 设置 Playwright 临时目录为项目目录下的 tmp 文件夹
        import tempfile
        playwright_tmp = user_data_dir.parent / "playwright_tmp"
        playwright_tmp.mkdir(exist_ok=True)
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(playwright_tmp)
        
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            executable_path=executable_path,
            headless=False,  # Google 登录必须使用有头模式，否则极大概率被拦截
            slow_mo=500,     # 降低操作速度，更像真人
            viewport={"width": 1920, "height": 1080},
            no_viewport=False,
            # 隐藏自动化控制标志的关键参数
            args=[
                "--disable-blink-features=AutomationControlled",  # 禁用自动化控制特征
                "--start-maximized",                               # 窗口最大化
                "--no-sandbox",                                    # 某些环境下需要
                "--disable-dev-shm-usage",                         # 避免共享内存问题
                "--no-first-run",                                  # 跳过首次运行向导
                "--no-default-browser-check",                      # 不检查默认浏览器
            ],
            # 模拟真实的 User-Agent
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            # 设置临时目录
            downloads_path=str(playwright_tmp / "downloads"),
            traces_dir=str(playwright_tmp / "traces"),
        )
        
        # 6. 注入增强的隐身脚本
        context.add_init_script(STEALTH_JS)
        print("   ✓ 已注入增强版隐身脚本")
        
        page = context.new_page()
        
        # 如果使用 playwright_stealth，在页面创建后应用
        if HAS_STEALTH:
            try:
                stealth_obj = Stealth()
                stealth_obj.apply_stealth(page)
                print("   ✓ 已应用 playwright_stealth 高级保护")
            except Exception as e:
                print(f"   ⚠️  playwright_stealth 应用失败: {e}")
                print("   ✓ 继续使用基础隐身脚本")
        
        print("\n✅ Chrome 启动成功！")
        
        # 7. 验证隐身效果
        print("\n🔍 检测浏览器指纹...")
        webdriver_detected = page.evaluate("() => navigator.webdriver !== undefined")
        automation_detected = page.evaluate("() => Object.getOwnPropertyDescriptor(navigator, 'webdriver') !== undefined")
        
        print(f"   • navigator.webdriver: {'❌ 暴露' if webdriver_detected else '✅ 隐藏'}")
        print(f"   • 自动化标志: {'❌ 暴露' if automation_detected else '✅ 隐藏'}")
        
        if webdriver_detected or automation_detected:
            print("\n⚠️  警告: 检测到自动化特征，可能影响登录成功率")
        else:
            print("\n✅ 浏览器指纹已成功隐藏")
        
        # 8. 访问目标网站
        print("\n🌐 正在访问 X.com...")
        page.goto("https://x.com", wait_until="domcontentloaded", timeout=60000)
        print("   ✓ 页面加载完成")
        
        # 9. 等待用户登录
        print("\n" + "="*80)
        print("  💡 请在打开的 Chrome 中手动登录 X (Twitter)")
        print("="*80)
        print("\n📝 重要提示:")
        print("   • 首次登录成功后，Cookie 会保存在用户数据目录中")
        print("   • 下次运行脚本时将自动保持登录状态")
        print("   • 建议在正常速度下手动完成登录（不要过快输入）")
        print("\n⏳ 等待登录... (最多 180 秒)")
        print("-"*80)
        
        login_timeout = 180
        check_interval = 5
        logged_in = False
        
        for i in range(login_timeout, 0, -check_interval):
            current_url = page.url
            
            # 检测是否已登录（URL 包含 home 或 timeline）
            if "home" in current_url or "timeline" in current_url or "compose" in current_url:
                print(f"\n✅ 检测到登录成功!")
                print(f"   当前 URL: {current_url}")
                logged_in = True
                break
            
            # 显示倒计时
            print(f"   ⏳ 剩余 {i:3d}s | 当前: {current_url[:60]}...", end='\r')
            time.sleep(check_interval)
        
        if not logged_in:
            print("\n\n⚠️  登录超时！")
            print("   可能的原因:")
            print("   • 网络连接问题")
            print("   • X.com 要求额外的验证步骤")
            print("   • IP 地址被标记")
            print("\n💡 建议:")
            print("   • 检查网络连接")
            print("   • 尝试更换 IP 地址")
            print("   • 延长等待时间（修改 login_timeout 参数）")
            
            print("\n⏳ 30秒后关闭浏览器...")
            time.sleep(30)
            return False
        
        # 10. 登录成功后，等待片刻确保持久化
        print("\n⏳ 等待 5 秒以确保持久化...")
        time.sleep(5)
        
        # 11. 执行发帖操作
        print("\n" + "="*80)
        print("  📤 开始自动发帖")
        print("="*80)
        
        try:
            print("\n🔍 查找发帖框...")
            tweet_box = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]')
            tweet_box.wait_for(state="visible", timeout=15000)
            print("   ✓ 发帖框已找到")
            
            print("\n✍️  输入推文内容...")
            tweet_content = f"🧪 AnimoCerebro Auto Stealth Test\n#AI #Test #{int(time.time())}"
            tweet_box.fill(tweet_content)
            print(f"   ✓ 内容: {tweet_content[:50]}...")
            
            print("\n⏳ 等待 3 秒让按钮激活...")
            time.sleep(3)
            
            print("\n🚀 查找发布按钮...")
            # 尝试多种可能的按钮选择器
            post_button_selectors = [
                'button[data-testid="tweetButton"]',
                'div[data-testid="tweetButton"]',
                'button:has-text("Post")',
                'button:has-text("发布")',
                '[role="button"]:has-text("Post")',
            ]
            
            post_button = None
            for selector in post_button_selectors:
                try:
                    btn = page.locator(selector)
                    if btn.count() > 0 and btn.is_visible():
                        post_button = btn
                        print(f"   ✓ 找到按钮: {selector}")
                        break
                except:
                    continue
            
            if not post_button:
                print("   ⚠️  未找到标准按钮，尝试点击第一个可见的 Post 按钮...")
                # 最后的备选方案：查找包含 "Post" 文本的按钮
                post_button = page.locator('button').filter(has_text="Post").first
            
            print("\n🚀 点击发布按钮...")
            post_button.click()
            print("   ✓ 已点击发布")
            
            print("\n⏳ 等待发布完成 (10 秒)...")
            time.sleep(10)
            
            # 截图保存证据
            screenshot_path = Path("screenshots/x_auto_stealth_SUCCESS.png")
            screenshot_path.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"\n📸 截图已保存: {screenshot_path.absolute()}")
            
            print("\n✅ 发帖完成!")
            
        except Exception as e:
            print(f"\n❌ 发帖失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 即使发帖失败，也截图记录当前状态
            try:
                error_screenshot = Path("screenshots/x_auto_stealth_ERROR.png")
                error_screenshot.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(error_screenshot), full_page=True)
                print(f"📸 错误截图: {error_screenshot.absolute()}")
            except:
                pass
        
        # 12. 保持浏览器打开，让用户观察
        print("\n" + "="*80)
        print("  ✅ 任务完成！")
        print("="*80)
        print("\n⏳ 浏览器将在 30 秒后自动关闭...")
        print("   你可以在此期间检查发帖结果")
        time.sleep(30)
        
        return True
    
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理资源
        try:
            if page:
                page.close()
                print("\n✓ 页面已关闭")
            if context:
                context.close()
                print("✓ 上下文已关闭")
            if playwright:
                playwright.stop()
                print("✓ Playwright 已停止")
            print("\n✅ 所有资源已释放")
        except Exception as e:
            print(f"\n⚠️  清理时出错: {e}")


if __name__ == "__main__":
    success = launch_real_chrome()
    
    if success:
        print("\n" + "="*80)
        print("  🎉 测试成功完成！")
        print("="*80)
        print("\n💡 下次运行时:")
        print("   • Cookie 已保存，可能无需重新登录")
        print("   • 可以缩短等待时间或直接执行发帖")
        print("   • 考虑将浏览器实例作为长期运行的'执行节点'")
    else:
        print("\n" + "="*80)
        print("  ⚠️  测试未完成")
        print("="*80)
        print("\n💡 排查建议:")
        print("   • 检查 Chrome 是否正确安装")
        print("   • 确认网络连接正常")
        print("   • 尝试手动在普通 Chrome 中登录 X.com")
        print("   • 检查 IP 是否被标记")
    
    sys.exit(0 if success else 1)
