#!/usr/bin/env python3
"""
Self-Promotion Agent 完整流程测试脚本

用途:
    演示从生成周计划到实际在 X 和 Reddit 发帖的完整流程
    
流程:
    1. 初始化 Agent
    2. 生成周度推广计划
    3. 获取并缓存社区规则
    4. 验证帖子内容
    5. 登录到社交平台
    6. 发布帖子
    7. 查看审计日志

注意:
    - 需要配置 LLM API 密钥
    - 需要安装 Playwright 和浏览器
    - 需要提供真实的社交账号 credentials
    - 遇到 CAPTCHA 时需要人工协助
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 添加项目根目录和 src 目录到 Python 路径
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

from Agent.self_promotion_agent import self_promotion_agent


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def step1_check_dependencies():
    """步骤 1: 检查依赖"""
    print_section("步骤 1: 检查依赖")
    
    info = self_promotion_agent.get_info()
    
    print(f"\nAgent ID: {info['agent_id']}")
    print(f"Status: {info['status']}")
    print(f"LLM Available: {'✅' if info['llm_available'] else '❌'}")
    print(f"Browser Available: {'✅' if info['browser_available'] else '❌'}")
    
    if not info['llm_available']:
        print("\n⚠️  警告: LLM 服务不可用")
        print("   请配置 .env 文件中的 API 密钥")
        response = input("\n是否继续？(y/n): ").strip().lower()
        if response != 'y':
            return False
    
    if not info['browser_available']:
        print("\n⚠️  警告: 浏览器自动化不可用")
        print("   请安装 Playwright: pip install playwright && playwright install chromium")
        response = input("\n是否继续？(y/n): ").strip().lower()
        if response != 'y':
            return False
    
    print("\n✅ 依赖检查通过")
    return True


def step2_generate_weekly_plan():
    """步骤 2: 生成周度推广计划"""
    print_section("步骤 2: 生成周度推广计划")
    
    project_info = {
        "name": "AnimoCerebro",
        "description": "AI brain for autonomous agents with nine-question cognitive cycle",
        "tech_stack": ["Python", "FastAPI", "React", "TypeScript", "SQLite"],
        "features": [
            "Nine-question cognitive cycle (Q1-Q9)",
            "Autonomous decision making and reflection",
            "Plugin system with hot reload",
            "Web console with real-time monitoring",
            "Long-term memory and experience exchange",
            "Zentex protocol for agent coordination"
        ]
    }
    
    print("\n📋 项目信息:")
    print(f"   名称: {project_info['name']}")
    print(f"   描述: {project_info['description'][:60]}...")
    print(f"   技术栈: {', '.join(project_info['tech_stack'])}")
    
    print("\n🎯 推广目标:")
    goals = [
        "Increase GitHub stars and visibility",
        "Attract AI/ML developers as contributors",
        "Build community awareness in AI agent space"
    ]
    for i, goal in enumerate(goals, 1):
        print(f"   {i}. {goal}")
    
    print("\n🌐 目标社区:")
    communities = ["r/MachineLearning", "r/artificial", "r/Python"]
    for comm in communities:
        print(f"   - {comm}")
    
    response = input("\n是否生成周计划？(y/n): ").strip().lower()
    if response != 'y':
        return None
    
    try:
        result = self_promotion_agent.generate_weekly_plan(
            project_info=project_info,
            target_audience="AI/ML researchers and developers interested in autonomous agents",
            goals=goals,
            target_communities=communities,
            week_start=datetime.now(timezone.utc)
        )
        
        if result["success"]:
            print(f"\n✅ 周计划生成成功!")
            print(f"   Plan ID: {result['plan_id']}")
            print(f"   Title: {result['plan']['title']}")
            print(f"   Days: {len(result['plan']['daily_schedules'])}")
            
            # 显示第一天的计划
            if result['plan']['daily_schedules']:
                day1 = result['plan']['daily_schedules'][0]
                print(f"\n📅 第一天计划:")
                print(f"   Platform: {day1['platform']}")
                print(f"   Date: {day1['date']}")
                if day1.get('subreddit'):
                    print(f"   Subreddit: {day1['subreddit']}")
                if day1.get('title'):
                    print(f"   Title: {day1['title'][:60]}...")
                print(f"   Content Preview: {day1['content'][:100]}...")
            
            return result['plan_id']
        else:
            print(f"\n❌ 计划生成失败: {result.get('error')}")
            return None
            
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        return None


def step3_get_community_rules(subreddit: str):
    """步骤 3: 获取社区规则"""
    print_section(f"步骤 3: 获取 r/{subreddit} 社区规则")
    
    response = input(f"\n是否获取 r/{subreddit} 的规则？(y/n): ").strip().lower()
    if response != 'y':
        return False
    
    try:
        result = self_promotion_agent.get_community_rules(subreddit, auto_download=True)
        
        if result["success"]:
            rules = result["rules"]
            print(f"\n✅ 规则获取成功!")
            print(f"   Subreddit: r/{rules['subreddit']}")
            print(f"   Rule Count: {rules['rule_count']}")
            print(f"   Last Updated: {rules['last_updated']}")
            print(f"   Source: {rules['source']}")
            
            # 显示前几条规则
            if rules['rules']:
                print(f"\n📜 社区规则 (前 {min(3, len(rules['rules']))} 条):")
                for i, rule in enumerate(rules['rules'][:3], 1):
                    print(f"   {i}. {rule.get('title', 'N/A')}")
                    desc = rule.get('description', '')
                    if desc:
                        print(f"      {desc[:80]}...")
            
            return True
        else:
            print(f"\n❌ 规则获取失败: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        return False


def step4_validate_post(subreddit: str, title: str, content: str):
    """步骤 4: 验证帖子是否符合规则"""
    print_section("步骤 4: 验证帖子内容")
    
    print(f"\n📝 帖子内容:")
    print(f"   标题: {title[:60]}...")
    print(f"   内容: {content[:100]}...")
    
    response = input("\n是否验证帖子是否符合社区规则？(y/n): ").strip().lower()
    if response != 'y':
        return True  # 跳过验证
    
    try:
        result = self_promotion_agent.validate_post_against_rules(
            subreddit=subreddit,
            title=title,
            content=content
        )
        
        if result["success"]:
            validation = result["validation"]
            
            if validation["valid"]:
                print("\n✅ 帖子符合社区规则!")
                print(f"   检查的规则数: {validation['rules_checked']}")
                return True
            else:
                print("\n⚠️  帖子可能违反社区规则:")
                
                if validation["violations"]:
                    print(f"\n   违规行为 ({len(validation['violations'])} 条):")
                    for v in validation["violations"]:
                        severity_icon = "❌" if v["severity"] == "error" else "⚠️"
                        print(f"   {severity_icon} {v['rule']}")
                        print(f"      原因: {v['reason']}")
                
                if validation["suggestions"]:
                    print(f"\n   修改建议:")
                    for s in validation["suggestions"]:
                        print(f"   • {s}")
                
                response = input("\n是否仍然发布？(y/n): ").strip().lower()
                return response == 'y'
        else:
            print(f"\n❌ 验证失败: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        return False


def step5_login_to_platform(platform: str):
    """步骤 5: 登录到社交平台"""
    print_section(f"步骤 5: 登录到 {platform.upper()}")
    
    if not self_promotion_agent.browser_manager:
        print("\n❌ 浏览器自动化不可用")
        print("   请确保已安装 Playwright 和 Chromium 浏览器")
        return False
    
    username = input(f"\n请输入 {platform} 用户名: ").strip()
    if not username:
        print("取消登录")
        return False
    
    # 使用 getpass 隐藏密码输入
    import getpass
    password = getpass.getpass(f"请输入 {platform} 密码: ")
    
    try:
        print(f"\n🔐 正在登录到 {platform}...")
        
        if platform.lower() == "x":
            result = self_promotion_agent.browser_manager.login_to_x(username, password)
        elif platform.lower() == "reddit":
            result = self_promotion_agent.browser_manager.login_to_reddit(username, password)
        else:
            print(f"❌ 不支持的平台: {platform}")
            return False
        
        if result["success"]:
            print(f"\n✅ 登录成功!")
            print(f"   消息: {result.get('message', 'N/A')}")
            return True
        else:
            print(f"\n❌ 登录失败: {result.get('error')}")
            print("\n💡 提示: 如果遇到 CAPTCHA，请在打开的浏览器窗口中完成验证")
            return False
            
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        return False


def step6_publish_post(platform: str, subreddit: str, title: str, content: str):
    """步骤 6: 发布帖子"""
    print_section(f"步骤 6: 发布到 {platform.upper()}")
    
    print(f"\n📤 准备发布:")
    print(f"   平台: {platform}")
    if subreddit:
        print(f"   Subreddit: r/{subreddit}")
    if title:
        print(f"   标题: {title[:60]}...")
    print(f"   内容: {content[:100]}...")
    
    response = input("\n确认发布？(y/n): ").strip().lower()
    if response != 'y':
        print("取消发布")
        return False
    
    try:
        if platform.lower() == "x":
            print("\n🚀 正在发布到 X...")
            result = self_promotion_agent.browser_manager.post_to_x(
                content=content
            )
        elif platform.lower() == "reddit":
            print(f"\n🚀 正在发布到 r/{subreddit}...")
            result = self_promotion_agent.browser_manager.post_to_reddit(
                subreddit=subreddit.replace("r/", ""),
                title=title,
                content=content,
                post_type="text"
            )
        else:
            print(f"❌ 不支持的平台: {platform}")
            return False
        
        if result["success"]:
            print(f"\n✅ 发布成功!")
            print(f"   消息: {result.get('message', 'N/A')}")
            if result.get("url"):
                print(f"   链接: {result['url']}")
            return True
        else:
            print(f"\n❌ 发布失败: {result.get('error')}")
            
            # 如果是 Reddit 且失败，尝试自动修复
            if platform.lower() == "reddit":
                print("\n💡 尝试自动修复内容...")
                response = input("是否让 AI 分析错误并提供修正方案？(y/n): ").strip().lower()
                if response == 'y':
                    # 这里可以调用内容策略引擎
                    print("自动修复功能待实现")
            
            return False
            
    except Exception as e:
        print(f"\n❌ 异常: {str(e)}")
        return False


def step7_view_audit_log():
    """步骤 7: 查看审计日志"""
    print_section("步骤 7: 查看审计日志")
    
    try:
        result = self_promotion_agent.get_audit_log(limit=10)
        
        if result["success"]:
            print(f"\n📊 审计日志 (最近 {len(result['audit_log'])} 条):")
            
            if result["audit_log"]:
                for i, log in enumerate(result["audit_log"], 1):
                    print(f"\n   {i}. [{log['timestamp']}]")
                    print(f"      Action: {log['action']}")
                    print(f"      Trace ID: {log['trace_id'][:20]}...")
                    if log.get('details'):
                        details = log['details']
                        if 'subreddit' in details:
                            print(f"      Subreddit: r/{details['subreddit']}")
                        if 'valid' in details:
                            status = "✅ Valid" if details['valid'] else "❌ Invalid"
                            print(f"      Validation: {status}")
            else:
                print("   暂无审计日志")
        else:
            print(f"❌ 获取日志失败: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ 异常: {str(e)}")


def main():
    """主函数 - 执行完整流程"""
    print("\n" + "🚀" * 35)
    print("  Self-Promotion Agent 完整流程测试")
    print("🚀" * 35)
    
    # 步骤 1: 检查依赖
    if not step1_check_dependencies():
        print("\n❌ 依赖检查失败，退出")
        return
    
    # 步骤 2: 生成周计划
    plan_id = step2_generate_weekly_plan()
    
    # 步骤 3-6: 选择平台进行测试
    print("\n" + "=" * 70)
    print("  选择要测试的平台")
    print("=" * 70)
    print("  1. X (Twitter)")
    print("  2. Reddit")
    print("  3. 两者都测试")
    print("  4. 跳过发帖")
    
    choice = input("\n请选择 (1-4): ").strip()
    
    if choice in ['1', '3']:
        # 测试 X
        print_section("测试 X (Twitter) 发帖")
        
        # 获取或创建帖子内容
        x_content = input("\n请输入 X 帖子内容 (280字符以内): ").strip()
        if not x_content:
            x_content = "Excited to share AnimoCerebro - an AI brain for autonomous agents! 🧠 #AI #MachineLearning"
        
        if len(x_content) > 280:
            x_content = x_content[:277] + "..."
        
        # 登录
        if step5_login_to_platform("x"):
            # 发布
            step6_publish_post("x", "", "", x_content)
    
    if choice in ['2', '3']:
        # 测试 Reddit
        print_section("测试 Reddit 发帖")
        
        subreddit = input("\n请输入 Subreddit (如 MachineLearning): ").strip()
        if not subreddit:
            subreddit = "MachineLearning"
        
        # 获取社区规则
        step3_get_community_rules(subreddit)
        
        # 输入帖子内容
        reddit_title = input("\n请输入帖子标题: ").strip()
        if not reddit_title:
            reddit_title = "AnimoCerebro: AI Brain for Autonomous Agents with Nine-Question Cognitive Cycle"
        
        reddit_content = input("\n请输入帖子内容: ").strip()
        if not reddit_content:
            reddit_content = """## Introduction

I've been working on AnimoCerebro, an open-source project that provides an "AI brain" for autonomous agents. It implements a nine-question cognitive cycle (Q1-Q9) that enables agents to think, reflect, learn, and make autonomous decisions.

## Key Features

- **Nine-Question Cognitive Cycle**: A structured approach to agent reasoning
- **Autonomous Decision Making**: Agents can drive tasks based on cognitive analysis
- **Plugin System**: Hot-reloadable plugins for extensibility
- **Web Console**: Real-time monitoring and control
- **Long-term Memory**: Experience exchange across tasks and time

## Technical Stack

- Backend: Python, FastAPI
- Frontend: React, TypeScript
- Database: SQLite
- LLM Integration: Gemini, OpenAI, Claude support

## Why I Built This

Existing agent frameworks lack true autonomy. They're either too rigid (rule-based) or too unpredictable (pure LLM). AnimoCerebro bridges this gap with a structured cognitive architecture.

## Links

- GitHub: https://github.com/xunharry4-source/AnimoCerebro-external
- Documentation: See docs/ directory

I'd love to hear your thoughts and feedback! What features would you like to see in an autonomous agent framework?"""
        
        # 验证帖子
        if step4_validate_post(subreddit, reddit_title, reddit_content):
            # 登录
            if step5_login_to_platform("reddit"):
                # 发布
                step6_publish_post("reddit", subreddit, reddit_title, reddit_content)
    
    if choice != '4':
        # 步骤 7: 查看审计日志
        step7_view_audit_log()
    
    # 总结
    print_section("测试完成")
    print("\n✅ 完整流程测试结束!")
    print("\n📝 总结:")
    print("  • 依赖检查: ✅")
    if plan_id:
        print(f"  • 周计划生成: ✅ (Plan ID: {plan_id})")
    else:
        print("  • 周计划生成: ⚠️  跳过")
    print("  • 社区规则: ✅ (如果选择了 Reddit)")
    print("  • 帖子验证: ✅ (如果选择了 Reddit)")
    print("  • 平台登录: ✅ (如果提供了凭证)")
    print("  • 帖子发布: ✅ (如果确认发布)")
    print("  • 审计日志: ✅")
    
    print("\n💡 下一步:")
    print("  • 查看完整文档: cat Agent/SELF_PROMOTION_AGENT_README.md")
    print("  • 查看社区规则指南: cat Agent/COMMUNITY_RULES_GUIDE.md")
    print("  • 运行单元测试: pytest Agent/test_self_promotion_agent.py -v")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
