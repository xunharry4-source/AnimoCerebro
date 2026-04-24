#!/usr/bin/env python3
"""
LangGraph + CrewAI 社交媒体发布工作流

整合了：
1. 浏览器自动化（Playwright Stealth Chrome）
2. Reddit 智能发帖（带规则检查和反复纠错）
3. X.com (Twitter) 自动发帖
4. AnimoCerebro 宣传助手
5. 每周发帖计划

架构：
节点 A: 主题分析和计划生成
节点 B: CrewAI 内容创作团队
节点 C: 浏览器自动化执行（Reddit/X）
节点 D: 监控和错误恢复
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, TypedDict, Annotated
from enum import Enum

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# LangGraph imports
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# CrewAI imports
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI

# 导入现有的社交媒体模块
from Agent.social_promotion.reddit_smart_poster import RedditSmartPoster
from Agent.social_promotion.animocerebro_promoter import AnimoCerebroPromoter
from Agent.social_promotion.community_rules_manager import CommunityRulesManager
from Agent.social_promotion.weekly_posting_planner import WeeklyPostingPlanner


class PublishStatus(Enum):
    """发布状态"""
    PENDING = "pending"
    PLANNING = "planning"
    CREATING = "creating"
    PUBLISHING = "publishing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"


class SocialMediaState(TypedDict):
    """社交媒体发布状态"""
    # 输入
    raw_material: str  # 原始素材
    target_platforms: List[str]  # 目标平台 ["reddit", "x", "both"]
    target_subreddits: List[str]  # 目标 Reddit 社区
    use_weekly_plan: bool  # 是否使用每周计划
    
    # 节点 A: 计划生成
    weekly_plan: Dict  # 每周计划
    today_theme: str  # 今天的主题
    content_strategy: str  # 内容策略
    priority: int  # 优先级
    
    # 节点 B: CrewAI 创作
    draft_content: Dict[str, str]  # 草稿内容 {platform: content}
    review_feedback: str  # 校对反馈
    iteration_count: int  # 迭代次数
    max_iterations: int  # 最大迭代次数
    is_approved: bool  # 是否通过审核
    
    # 节点 C: 浏览器自动化发布
    browser_session: Dict  # 浏览器会话信息
    reddit_results: List[Dict]  # Reddit 发布结果
    x_results: List[Dict]  # X.com 发布结果
    publish_errors: List[str]  # 发布错误
    
    # 节点 D: 监控
    monitoring_results: Dict  # 监控结果
    success_count: int  # 成功数量
    failed_count: int  # 失败数量
    retry_count: int  # 重试次数
    max_retries: int  # 最大重试次数
    
    # 元数据
    status: str  # 整体状态
    created_at: str  # 创建时间
    updated_at: str  # 更新时间
    error_message: str  # 错误信息


class PlanningNode:
    """节点 A: 计划生成器"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.weekly_planner = WeeklyPostingPlanner()
    
    def generate_plan(self, state: SocialMediaState) -> SocialMediaState:
        """
        生成发布计划
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print("📅 节点 A: 计划生成")
        print("="*80)
        
        if state.get("use_weekly_plan", False):
            # 使用每周计划
            print("📋 使用每周发帖计划...")
            weekly_plan = self.weekly_planner.generate_weekly_plan()
            state["weekly_plan"] = weekly_plan
            
            # 获取今天的计划
            today = datetime.now().strftime("%A")
            if today in weekly_plan["schedule"]:
                today_plan = weekly_plan["schedule"][today]
                state["today_theme"] = today_plan.get("theme", "一般项目更新")
                state["content_strategy"] = today_plan.get("content_focus", "技术分享")
                state["priority"] = 5
            else:
                state["today_theme"] = "项目更新"
                state["content_strategy"] = "技术分享"
                state["priority"] = 3
        else:
            # 使用 LLM 分析素材
            print("🤖 使用 LLM 分析素材...")
            prompt = f"""
            分析以下素材，制定发布计划：
            
            素材：
            {state['raw_material']}
            
            目标平台：{', '.join(state['target_platforms'])}
            
            请返回 JSON 格式：
            {{
                "today_theme": "主题名称",
                "content_strategy": "内容策略",
                "priority": 优先级（1-5）",
                "reasoning": "选择这个策略的原因"
            }}
            """
            
            try:
                response = self.llm.invoke(prompt)
                result = json.loads(response.content)
                
                state["today_theme"] = result.get("today_theme", "项目更新")
                state["content_strategy"] = result.get("content_strategy", "技术分享")
                state["priority"] = result.get("priority", 3)
                
            except Exception as e:
                print(f"⚠️  计划生成失败，使用默认值: {e}")
                state["today_theme"] = "项目更新"
                state["content_strategy"] = "技术分享"
                state["priority"] = 3
        
        print(f"✅ 主题: {state['today_theme']}")
        print(f"✅ 策略: {state['content_strategy']}")
        print(f"✅ 优先级: {state['priority']}/5")
        
        state["status"] = PublishStatus.CREATING.value
        state["updated_at"] = datetime.now().isoformat()
        
        return state


class ContentCreationNode:
    """节点 B: CrewAI 内容创作团队"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.8,
            api_key=os.getenv("OPENAI_API_KEY")
        )
    
    def create_content(self, state: SocialMediaState) -> SocialMediaState:
        """
        使用 CrewAI 为不同平台创作内容
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print(f"✍️  节点 B: CrewAI 内容创作 (迭代 {state['iteration_count'] + 1}/{state['max_iterations']})")
        print("="*80)
        
        theme = state["today_theme"]
        strategy = state["content_strategy"]
        raw_material = state["raw_material"]
        platforms = state["target_platforms"]
        
        # 创建 Agent 1: 社交媒体文案专家
        writer_agent = Agent(
            role="社交媒体文案专家",
            goal=f"为 {', '.join(platforms)} 创作吸引人的内容",
            backstory="""你是一位经验丰富的社交媒体文案专家，擅长为不同平台创作
            定制化的内容。你了解 Reddit 的技术讨论风格和 X.com 的简洁风格，
            能够根据平台特性调整语气和格式。""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
        
        # 创建 Agent 2: 内容校对编辑
        editor_agent = Agent(
            role="内容校对编辑",
            goal="检查和优化多平台内容，确保质量和合规性",
            backstory="""你是一位严格的校对编辑，专注于内容的准确性、可读性和
            平台适配性。你会检查每个平台的内容是否符合其社区规则和文化。""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
        
        # 任务 1: 为各平台创作文案
        writing_task = Task(
            description=f"""
            根据以下信息为不同平台创作文案：
            
            主题: {theme}
            策略: {strategy}
            目标平台: {', '.join(platforms)}
            原始素材: {raw_material}
            
            要求：
            
            1. **Reddit 内容** (如果 target_platforms 包含 'reddit'):
               - 标题要有吸引力但不过度营销
               - 正文提供详细的技术细节或见解
               - 包含代码示例（如果是技术内容）
               - 长度: 300-800 字
               - 语气: 专业但友好
               - 避免明显的自我推广
            
            2. **X.com 内容** (如果 target_platforms 包含 'x'):
               - 简洁有力，前 100 字抓住注意力
               - 使用适当的 hashtag (#AnimoCerebro #AI 等)
               - 可以分多条推文（thread）
               - 长度: 每条 280 字符以内
               - 包含行动号召
            
            请为每个平台输出独立的内容。
            """,
            expected_output="JSON 格式的多平台内容: {'reddit': {...}, 'x': {...}}",
            agent=writer_agent
        )
        
        # 任务 2: 校对和优化
        editing_task = Task(
            description=f"""
            校对以下多平台内容：
            
            内容：
            {json.dumps(state.get('draft_content', {}), indent=2, ensure_ascii=False)}
            
            检查要点：
            1. 每个平台的内容是否符合该平台的风格
            2. Reddit 内容是否避免了过度自我推广
            3. X.com 内容是否简洁有力
            4. 语法和拼写是否正确
            5. 是否有明确的行动号召
            6. 内容是否有价值
            
            如果发现问题，提供具体的修改建议。
            如果内容已经很好，回复 "APPROVED"。
            """,
            expected_output="校对反馈或 APPROVED",
            agent=editor_agent
        )
        
        # 创建 Crew
        crew = Crew(
            agents=[writer_agent, editor_agent],
            tasks=[writing_task, editing_task],
            process=Process.sequential,
            verbose=True
        )
        
        try:
            # 执行 Crew
            result = crew.kickoff()
            feedback = str(result.raw).strip()
            
            if "APPROVED" in feedback.upper():
                state["is_approved"] = True
                state["review_feedback"] = "内容已通过审核"
                print("✅ 内容审核通过！")
            else:
                state["is_approved"] = False
                state["review_feedback"] = feedback
                # 尝试从反馈中提取改进后的内容
                state["draft_content"] = self._extract_content_from_feedback(feedback, platforms)
                print(f"⚠️  需要修改: {feedback[:200]}...")
            
            state["iteration_count"] += 1
            
        except Exception as e:
            print(f"❌ CrewAI 执行失败: {e}")
            state["is_approved"] = False
            state["review_feedback"] = f"执行错误: {str(e)}"
            state["iteration_count"] += 1
        
        state["updated_at"] = datetime.now().isoformat()
        
        return state
    
    def _extract_content_from_feedback(self, feedback: str, platforms: List[str]) -> Dict[str, str]:
        """从反馈中提取内容"""
        # 简化实现：尝试解析 JSON
        try:
            # 查找 JSON 部分
            import re
            json_match = re.search(r'\{.*\}', feedback, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        # 如果解析失败，返回空字典
        return {platform: "" for platform in platforms}


class BrowserAutomationNode:
    """节点 C: 浏览器自动化执行"""
    
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self.rules_manager = CommunityRulesManager()
    
    def initialize_browser(self):
        """
        初始化浏览器（使用 Stealth Chrome 配置）
        
        完全复用 test_auto_stealth_wait.py 的配置，确保登录状态保持
        """
        if not self.page:
            print("\n🌐 初始化浏览器 (Stealth Chrome 模式)...")
            
            from playwright.sync_api import sync_playwright
            from Agent.browser_automation.test_auto_stealth_wait import STEALTH_JS, get_chrome_path
            from pathlib import Path
            
            # 1. 指定独立用户数据目录（与 test_auto_stealth_wait.py 相同）
            user_data_dir = Path("./chrome_custom_profile").resolve()
            user_data_dir.mkdir(exist_ok=True)
            
            print(f"   📂 用户数据目录: {user_data_dir}")
            
            # 2. 获取 Chrome 路径
            try:
                executable_path = get_chrome_path()
                print(f"   🔍 Chrome 路径: {executable_path}")
            except FileNotFoundError as e:
                print(f"   ❌ {e}")
                raise
            
            # 3. 启动 Playwright
            self.playwright = sync_playwright().start()
            
            # 4. 启动持久化上下文（关键！）
            print("   🚀 正在启动 Chrome...")
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                executable_path=executable_path,
                headless=False,
                slow_mo=500,
                viewport={"width": 1920, "height": 1080},
                no_viewport=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            )
            
            # 5. 注入隐身脚本
            self.context.add_init_script(STEALTH_JS)
            print("   ✓ 已注入 Stealth 脚本")
            
            self.page = self.context.new_page()
            print("   ✅ 浏览器初始化完成")
    
    def execute_publishing(self, state: SocialMediaState) -> SocialMediaState:
        """
        执行发布操作
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print("🚀 节点 C: 浏览器自动化发布")
        print("="*80)
        
        # 初始化浏览器
        self.initialize_browser()
        
        state["status"] = PublishStatus.PUBLISHING.value
        state["reddit_results"] = []
        state["x_results"] = []
        state["publish_errors"] = []
        
        platforms = state["target_platforms"]
        
        # 发布到 Reddit
        if "reddit" in platforms:
            print("\n📤 发布到 Reddit...")
            reddit_result = self._publish_to_reddit(state)
            state["reddit_results"] = reddit_result
        
        # 发布到 X.com
        if "x" in platforms:
            print("\n📤 发布到 X.com...")
            x_result = self._publish_to_x(state)
            state["x_results"] = x_result
        
        # 关闭浏览器
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        
        self.page = None
        self.context = None
        self.playwright = None
        
        # 统计结果
        total_success = len([r for r in state["reddit_results"] if r.get("success")])
        total_success += len([r for r in state["x_results"] if r.get("success")])
        
        total_failed = len([r for r in state["reddit_results"] if not r.get("success")])
        total_failed += len([r for r in state["x_results"] if not r.get("success")])
        
        state["success_count"] = total_success
        state["failed_count"] = total_failed
        
        if total_failed > 0:
            state["status"] = PublishStatus.FAILED.value
        else:
            state["status"] = PublishStatus.SUCCESS.value
        
        state["updated_at"] = datetime.now().isoformat()
        
        return state
    
    def _publish_to_reddit(self, state: SocialMediaState) -> List[Dict]:
        """发布到 Reddit"""
        results = []
        subreddits = state.get("target_subreddits", ["AnimoCerebro"])
        
        reddit_poster = RedditSmartPoster(self.page, self.rules_manager)
        
        for subreddit in subreddits:
            print(f"\n  📝 发布到 r/{subreddit}...")
            
            try:
                # 获取针对该平台的内容
                content = state["draft_content"].get("reddit", {})
                title = content.get("title", state["today_theme"])
                text = content.get("content", state["raw_material"])
                
                # 使用自定义内容发布
                success = reddit_poster.post_custom_content(
                    subreddit=subreddit,
                    title=title,
                    content=text,
                    flair="Discussion",
                    max_retries=2
                )
                
                results.append({
                    "subreddit": subreddit,
                    "success": success,
                    "title": title[:50],
                    "timestamp": datetime.now().isoformat()
                })
                
                if success:
                    print(f"  ✅ r/{subreddit} 发布成功")
                else:
                    print(f"  ❌ r/{subreddit} 发布失败")
                    state["publish_errors"].append(f"Reddit r/{subreddit} 发布失败")
                
                # 避免频繁发帖
                time.sleep(5)
                
            except Exception as e:
                print(f"  ❌ r/{subreddit} 发布出错: {e}")
                results.append({
                    "subreddit": subreddit,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                state["publish_errors"].append(f"Reddit r/{subreddit}: {str(e)}")
        
        return results
    
    def _publish_to_x(self, state: SocialMediaState) -> List[Dict]:
        """发布到 X.com"""
        results = []
        
        try:
            # 获取 X.com 内容
            content = state["draft_content"].get("x", "")
            
            if not content:
                # 如果没有专门的内容，使用通用内容
                content = f"{state['today_theme']}\n\n{state['raw_material'][:200]}"
            
            # 访问 X.com
            print("  🌐 访问 X.com...")
            self.page.goto("https://twitter.com/compose/tweet", 
                          wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            
            # 填写推文
            print("  ✍️  填写推文...")
            tweet_box = self.page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]').first
            
            if tweet_box.count() > 0:
                tweet_box.fill(content)
                time.sleep(2)
                
                # 截图
                screenshot_path = Path("screenshots/x_tweet_compose.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                self.page.screenshot(path=str(screenshot_path))
                
                # 点击发布按钮
                print("  🚀 发布推文...")
                post_button = self.page.locator('button[data-testid="tweetButton"]').first
                
                if post_button.count() > 0 and post_button.is_enabled():
                    post_button.click()
                    time.sleep(5)
                    
                    # 检查是否成功
                    current_url = self.page.url
                    if "status" in current_url or "home" in current_url:
                        print("  ✅ X.com 发布成功")
                        results.append({
                            "platform": "x",
                            "success": True,
                            "content_preview": content[:100],
                            "timestamp": datetime.now().isoformat()
                        })
                    else:
                        print("  ⚠️  X.com 发布状态未知")
                        results.append({
                            "platform": "x",
                            "success": False,
                            "error": "发布状态未知",
                            "timestamp": datetime.now().isoformat()
                        })
                        state["publish_errors"].append("X.com 发布状态未知")
                else:
                    print("  ❌ 未找到发布按钮")
                    results.append({
                        "platform": "x",
                        "success": False,
                        "error": "未找到发布按钮",
                        "timestamp": datetime.now().isoformat()
                    })
                    state["publish_errors"].append("X.com: 未找到发布按钮")
            else:
                print("  ❌ 未找到推文输入框")
                results.append({
                    "platform": "x",
                    "success": False,
                    "error": "未找到推文输入框",
                    "timestamp": datetime.now().isoformat()
                })
                state["publish_errors"].append("X.com: 未找到推文输入框")
            
        except Exception as e:
            print(f"  ❌ X.com 发布出错: {e}")
            results.append({
                "platform": "x",
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            state["publish_errors"].append(f"X.com: {str(e)}")
        
        return results


class MonitoringNode:
    """节点 D: 监控和错误恢复"""
    
    def __init__(self):
        pass
    
    def monitor_and_recover(self, state: SocialMediaState) -> SocialMediaState:
        """
        监控发布结果，决定是否需要重试
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print("👁️  节点 D: 监控和错误恢复")
        print("="*80)
        
        state["retry_count"] = state.get("retry_count", 0)
        
        success_count = state["success_count"]
        failed_count = state["failed_count"]
        
        print(f"\n📊 发布结果统计:")
        print(f"   ✅ 成功: {success_count}")
        print(f"   ❌ 失败: {failed_count}")
        
        if failed_count > 0:
            print(f"\n⚠️  发现 {failed_count} 个失败的发布")
            
            # 显示错误
            for error in state["publish_errors"]:
                print(f"   - {error}")
            
            state["retry_count"] += 1
            
            if state["retry_count"] <= state["max_retries"]:
                print(f"\n🔄 准备重试 ({state['retry_count']}/{state['max_retries']})")
                print(f"   将退回节点 B 重新创作内容")
                
                state["status"] = PublishStatus.RETRY.value
                state["is_approved"] = False  # 需要重新创作
                
                # 清空之前失败的记录
                state["reddit_results"] = [r for r in state["reddit_results"] if r.get("success")]
                state["x_results"] = [r for r in state["x_results"] if r.get("success")]
                state["publish_errors"] = []
            else:
                print(f"\n❌ 已达到最大重试次数 ({state['max_retries']})")
                state["status"] = PublishStatus.FAILED.value
                state["error_message"] = f"重试 {state['max_retries']} 次后仍有 {failed_count} 个失败"
        else:
            print("\n✅ 所有发布成功！")
            state["status"] = PublishStatus.SUCCESS.value
        
        state["updated_at"] = datetime.now().isoformat()
        
        return state


class SocialMediaPublishingWorkflow:
    """
    LangGraph + CrewAI 社交媒体发布工作流
    
    整合了：
    - 浏览器自动化（Playwright）
    - Reddit 智能发帖
    - X.com 自动发帖
    - 每周发帖计划
    - CrewAI 内容创作
    """
    
    def __init__(self, max_iterations: int = 3, max_retries: int = 2):
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        
        # 初始化各个节点
        self.planning_node = PlanningNode()
        self.creation_node = ContentCreationNode()
        self.automation_node = BrowserAutomationNode()
        self.monitoring_node = MonitoringNode()
        
        # 构建 LangGraph
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """构建 LangGraph 工作流"""
        
        workflow = StateGraph(SocialMediaState)
        
        # 添加节点
        workflow.add_node("planning", self.planning_node.generate_plan)
        workflow.add_node("creation", self.creation_node.create_content)
        workflow.add_node("publishing", self.automation_node.execute_publishing)
        workflow.add_node("monitoring", self.monitoring_node.monitor_and_recover)
        
        # 设置入口点
        workflow.set_entry_point("planning")
        
        # 添加边
        workflow.add_edge("planning", "creation")
        
        # 条件边：内容创作是否通过审核
        workflow.add_conditional_edges(
            "creation",
            self._should_continue_creating,
            {
                "continue": "creation",
                "publish": "publishing"
            }
        )
        
        # 发布后进入监控
        workflow.add_edge("publishing", "monitoring")
        
        # 条件边：监控结果决定是否重试
        workflow.add_conditional_edges(
            "monitoring",
            self._should_retry,
            {
                "retry": "creation",
                "end": END
            }
        )
        
        # 编译工作流
        checkpointer = MemorySaver()
        compiled_workflow = workflow.compile(checkpointer=checkpointer)
        
        return compiled_workflow
    
    def _should_continue_creating(self, state: SocialMediaState) -> str:
        """判断是否继续创作迭代"""
        if state["is_approved"]:
            return "publish"
        
        if state["iteration_count"] >= state["max_iterations"]:
            print(f"\n⚠️  达到最大迭代次数 ({state['max_iterations']})，强制发布")
            return "publish"
        
        return "continue"
    
    def _should_retry(self, state: SocialMediaState) -> str:
        """判断是否重试"""
        if state["status"] == PublishStatus.RETRY.value:
            return "retry"
        return "end"
    
    def run(self, 
            raw_material: str,
            target_platforms: List[str] = None,
            target_subreddits: List[str] = None,
            use_weekly_plan: bool = False) -> Dict:
        """
        运行完整的工作流
        
        Args:
            raw_material: 原始素材
            target_platforms: 目标平台 ["reddit", "x", "both"]
            target_subreddits: 目标 Reddit 社区列表
            use_weekly_plan: 是否使用每周计划
            
        Returns:
            最终状态
        """
        print("\n" + "🎯"*40)
        print("LangGraph + CrewAI 社交媒体发布工作流")
        print("整合: 浏览器自动化 + Reddit + X.com")
        print("🎯"*40)
        
        if target_platforms is None:
            target_platforms = ["reddit", "x"]
        
        if target_subreddits is None:
            target_subreddits = ["AnimoCerebro"]
        
        # 规范化平台名称
        normalized_platforms = []
        for platform in target_platforms:
            if platform.lower() in ["reddit", "x", "twitter"]:
                normalized_platforms.append(platform.lower())
            elif platform.lower() == "both":
                normalized_platforms.extend(["reddit", "x"])
        
        # 初始化状态
        initial_state: SocialMediaState = {
            "raw_material": raw_material,
            "target_platforms": normalized_platforms,
            "target_subreddits": target_subreddits,
            "use_weekly_plan": use_weekly_plan,
            "weekly_plan": {},
            "today_theme": "",
            "content_strategy": "",
            "priority": 0,
            "draft_content": {},
            "review_feedback": "",
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "is_approved": False,
            "browser_session": {},
            "reddit_results": [],
            "x_results": [],
            "publish_errors": [],
            "monitoring_results": {},
            "success_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "max_retries": self.max_retries,
            "status": PublishStatus.PENDING.value,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error_message": ""
        }
        
        # 配置
        config = {
            "configurable": {
                "thread_id": f"social_media_{int(time.time())}"
            }
        }
        
        # 运行工作流
        try:
            final_state = self.workflow.invoke(initial_state, config)
            
            print("\n" + "="*80)
            print("📊 工作流执行完成")
            print("="*80)
            print(f"状态: {final_state['status']}")
            print(f"主题: {final_state['today_theme']}")
            print(f"创作迭代: {final_state['iteration_count']}")
            print(f"发布重试: {final_state['retry_count']}")
            print(f"成功: {final_state['success_count']}")
            print(f"失败: {final_state['failed_count']}")
            
            if final_state["error_message"]:
                print(f"错误: {final_state['error_message']}")
            
            # 保存结果
            result_file = Path("Agent/social_media_result.json")
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(final_state, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n✅ 结果已保存到: {result_file}")
            
            return final_state
            
        except Exception as e:
            print(f"\n❌ 工作流执行失败: {e}")
            import traceback
            traceback.print_exc()
            raise


# 使用示例
if __name__ == "__main__":
    # 设置 API Key
    os.environ["OPENAI_API_KEY"] = "your-openai-api-key-here"
    
    # 创建工作流
    workflow = SocialMediaPublishingWorkflow(
        max_iterations=3,
        max_retries=2
    )
    
    # 准备素材
    raw_material = """
    AnimoCerebro 项目重大更新：
    
    1. 完成了 LangGraph + CrewAI 集成
    2. 实现了智能内容创作工作流
    3. 整合了浏览器自动化（Reddit + X.com）
    4. 添加了每周发帖计划系统
    5. 实现了自动监控和错误恢复
    
    技术栈: FastAPI, React, Playwright, LangGraph, CrewAI
    GitHub: https://github.com/AnimoCerebro
    """
    
    # 运行工作流
    result = workflow.run(
        raw_material=raw_material,
        target_platforms=["reddit", "x"],
        target_subreddits=["AnimoCerebro", "Python"],
        use_weekly_plan=False
    )
    
    print("\n🎉 发布完成！")
