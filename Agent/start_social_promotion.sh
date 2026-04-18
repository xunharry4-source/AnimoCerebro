#!/bin/bash
# 启动社交媒体宣传 Agent

echo "🚀 Starting Social Media Promotion Agent..."

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed"
    exit 1
fi

# 检查 Playwright 是否安装
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "⚠️  Playwright is not installed. Installing..."
    pip install playwright
    python3 -m playwright install chromium
fi

# 运行 Agent
cd "$(dirname "$0")/.."
python3 -c "
import asyncio
from Agent.social_promotion_agent import social_promotion_agent

async def main():
    print('✅ Social Media Promotion Agent loaded successfully')
    print(f'Agent ID: {social_promotion_agent.agent_id}')
    print(f'Name: {social_promotion_agent.name}')
    print(f'Capabilities: {\", \".join(social_promotion_agent.capabilities)}')
    
    # 初始化浏览器
    print('\\n🌐 Initializing browser...')
    await social_promotion_agent.initialize_browser(headless=False)
    print('✅ Browser initialized')
    
    print('\\n💡 Usage examples:')
    print('1. Create a promotion plan')
    print('2. Login to X and Reddit')
    print('3. Post content to social media')
    print('4. View promotion results')
    
    # 保持浏览器打开以便手动操作
    print('\\n🔍 Browser is open. Press Ctrl+C to exit...')
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print('\\n\\n👋 Closing browser...')
        await social_promotion_agent.close_browser()
        print('✅ Done!')

if __name__ == '__main__':
    asyncio.run(main())
"
