"""
快速诊断：找出"添加标记"按钮的真实属性
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def get_chrome_path():
    """获取 Chrome 浏览器路径"""
    paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for path in paths:
        if Path(path).exists():
            return path
    raise FileNotFoundError("未找到 Chrome 浏览器")


print("=" * 80)
print("🔍 查找'添加标记'按钮的真实属性")
print("=" * 80)

user_data_dir = Path("./chrome_custom_profile").resolve()
executable_path = get_chrome_path()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
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
    
    page = context.pages[0]
    
    print("\n📋 请在浏览器中:")
    print("   1. 进入 r/AnimoCerebro")
    print("   2. 点击 'Create Post' / '发布帖子'")
    print("   3. 看到发帖编辑器后按回车...")
    input("\n按回车继续...")
    
    # 深度扫描所有包含"标记"的元素
    print("\n🔍 深度扫描所有包含'标记'、'flair'、'Add'的元素...")
    print("-" * 80)
    
    all_matches = page.evaluate("""
        () => {
            const results = [];
            const allElements = document.querySelectorAll('*');
            
            for (const el of allElements) {
                // 检查文本内容
                const text = (el.textContent || '').trim();
                const ariaLabel = el.getAttribute('aria-label') || '';
                const title = el.getAttribute('title') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                
                const combined = `${text} ${ariaLabel} ${title} ${placeholder}`.toLowerCase();
                
                // 搜索关键词
                if (combined.includes('标记') || 
                    combined.includes('flair') ||
                    combined.includes('add flair') ||
                    (combined.includes('add') && combined.length < 50)) {
                    
                    const rect = el.getBoundingClientRect();
                    const isVisible = rect.width > 0 && rect.height > 0;
                    
                    // 获取父元素信息
                    let parentInfo = '';
                    if (el.parentElement) {
                        parentInfo = el.parentElement.tagName;
                        if (el.parentElement.className) {
                            parentInfo += '.' + el.parentElement.className.split(' ').slice(0, 2).join('.');
                        }
                    }
                    
                    results.push({
                        tagName: el.tagName,
                        text: text.substring(0, 80),
                        ariaLabel: ariaLabel.substring(0, 80),
                        title: title.substring(0, 80),
                        className: (el.className || '').substring(0, 100),
                        id: el.id || '',
                        role: el.getAttribute('role'),
                        visible: isVisible,
                        parentElement: parentInfo,
                        selector: el.tagName.toLowerCase() + 
                                 (el.id ? '#' + el.id : '') +
                                 (el.className ? '.' + el.className.split(' ').filter(c => c && !c.startsWith('_')).slice(0, 3).join('.') : ''),
                        depth: (() => {
                            let depth = 0;
                            let node = el;
                            while (node.parentElement) {
                                depth++;
                                node = node.parentElement;
                            }
                            return depth;
                        })()
                    });
                }
            }
            
            return results.sort((a, b) => a.depth - b.depth).slice(0, 15);
        }
    """)
    
    if all_matches:
        print(f"\n✅ 找到 {len(all_matches)} 个相关元素:\n")
        for i, elem in enumerate(all_matches):
            print(f"[{i}] <{elem['tagName']}> {'(可见)' if elem['visible'] else '(隐藏)'}")
            if elem['text']:
                print(f"    文本: \"{elem['text']}\"")
            if elem['ariaLabel']:
                print(f"    aria-label: \"{elem['ariaLabel']}\"")
            if elem['title']:
                print(f"    title: \"{elem['title']}\"")
            print(f"    class: {elem['className'][:80]}")
            if elem['id']:
                print(f"    id: {elem['id']}")
            if elem['role']:
                print(f"    role: {elem['role']}")
            print(f"    父元素: {elem['parentElement']}")
            print(f"    层级深度: {elem['depth']}")
            print(f"    CSS选择器: {elem['selector']}")
            print()
    else:
        print("\n❌ 未找到任何包含'标记'或'flair'的元素")
        print("\n💡 可能原因:")
        print("   1. 页面还未加载完成")
        print("   2. 按钮在 iframe 中")
        print("   3. 按钮文本不是'添加标记'")
        
        # 列出所有可见按钮
        print("\n📋 列出所有可见按钮（前20个）:")
        all_buttons = page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
                return buttons
                    .filter(b => {
                        const rect = b.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    })
                    .slice(0, 20)
                    .map((b, i) => ({
                        index: i,
                        text: b.textContent?.trim().substring(0, 60),
                        ariaLabel: b.getAttribute('aria-label'),
                        className: b.className?.substring(0, 80),
                        tagName: b.tagName
                    }));
            }
        """)
        
        for btn in all_buttons:
            print(f"  [{btn['index']}] <{btn['tagName']}> \"{btn['text']}\" (aria: {btn['ariaLabel']})")
    
    print("\n" + "=" * 80)
    print("请按回车关闭浏览器...")
    input()
    
    context.close()
