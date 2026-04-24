#!/usr/bin/env python3
"""
LangGraph + CrewAI 智能内容发布系统

架构：
节点 A (LangGraph): 接收原始素材，判断今天发什么主题
节点 B (CrewAI 团队): 
  - Agent 1 (文案): 根据素材写草稿
  - Agent 2 (校对): 检查错误
  - 两者反复迭代，直到生成完美文案
节点 C (LangGraph): 拿到 B 的结果，调用 API 发送到 Twitter/小红书
节点 D (LangGraph): 监控回执，如果失败，退回节点 B 重新修改
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, TypedDict, Annotated
from enum import Enum

# LangGraph imports
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# CrewAI imports
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI


class ContentStatus(Enum):
    """内容状态"""
    PENDING = "pending"
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    RETRY = "retry"


class ContentState(TypedDict):
    """内容发布状态"""
    # 输入
    raw_material: str  # 原始素材
    target_platforms: List[str]  # 目标平台
    
    # 节点 A: 主题判断
    today_theme: str  # 今天的主题
    content_type: str  # 内容类型
    priority: int  # 优先级
    
    # 节点 B: CrewAI 创作
    draft_content: str  # 草稿内容
    review_feedback: str  # 校对反馈
    iteration_count: int  # 迭代次数
    max_iterations: int  # 最大迭代次数
    is_approved: bool  # 是否通过审核
    
    # 节点 C: 发布
    published_posts: Dict[str, Dict]  # 已发布的帖子 {platform: result}
    publish_status: Dict[str, str]  # 发布状态
    
    # 节点 D: 监控
    monitoring_results: Dict[str, Dict]  # 监控结果
    failed_platforms: List[str]  # 失败的平台
    retry_count: int  # 重试次数
    max_retries: int  # 最大重试次数
    
    # 元数据
    status: str  # 整体状态
    created_at: str  # 创建时间
    updated_at: str  # 更新时间
    error_message: str  # 错误信息


class ThemeAnalyzer:
    """节点 A: 主题分析器"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY")
        )
    
    def analyze_theme(self, state: ContentState) -> ContentState:
        """
        分析原始素材，确定今天的主题
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print("📊 节点 A: 主题分析")
        print("="*80)
        
        raw_material = state["raw_material"]
        
        # 使用 LLM 分析主题
        prompt = f"""
        分析以下素材，确定今天最适合发布的内容主题：
        
        素材：
        {raw_material}
        
        请返回 JSON 格式：
        {{
            "today_theme": "主题名称",
            "content_type": "内容类型（技术分享/项目进度/学习经验/行业洞察）",
            "priority": 优先级（1-5，5最高）",
            "reasoning": "选择这个主题的原因"
        }}
        """
        
        try:
            response = self.llm.invoke(prompt)
            result = json.loads(response.content)
            
            state["today_theme"] = result.get("today_theme", "一般项目更新")
            state["content_type"] = result.get("content_type", "技术分享")
            state["priority"] = result.get("priority", 3)
            
            print(f"✅ 主题: {state['today_theme']}")
            print(f"✅ 类型: {state['content_type']}")
            print(f"✅ 优先级: {state['priority']}/5")
            print(f"📝 原因: {result.get('reasoning', 'N/A')}")
            
        except Exception as e:
            print(f"⚠️  主题分析失败，使用默认值: {e}")
            state["today_theme"] = "项目更新"
            state["content_type"] = "技术分享"
            state["priority"] = 3
        
        state["status"] = ContentStatus.DRAFTING.value
        state["updated_at"] = datetime.now().isoformat()
        
        return state


class ContentCreationCrew:
    """节点 B: CrewAI 内容创作团队"""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.8,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        # 创建 Agent 1: 文案撰写者
        self.writer_agent = Agent(
            role="社交媒体文案专家",
            goal="根据素材创作吸引人的社交媒体文案",
            backstory="""你是一位经验丰富的社交媒体文案专家，擅长将技术内容转化为
            引人入胜的帖子。你了解不同平台的风格差异，能够写出既专业又有亲和力的内容。""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
        
        # 创建 Agent 2: 校对编辑
        self.editor_agent = Agent(
            role="内容校对编辑",
            goal="检查和优化文案，确保质量完美",
            backstory="""你是一位严格的校对编辑，专注于内容的准确性、可读性和吸引力。
            你会检查语法错误、逻辑清晰度、语气一致性，并提供具体的改进建议。""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
    
    def create_content(self, state: ContentState) -> ContentState:
        """
        使用 CrewAI 团队创作文案
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print(f"✍️  节点 B: CrewAI 内容创作 (迭代 {state['iteration_count'] + 1}/{state['max_iterations']})")
        print("="*80)
        
        theme = state["today_theme"]
        content_type = state["content_type"]
        raw_material = state["raw_material"]
        platforms = ", ".join(state["target_platforms"])
        
        # 任务 1: 文案撰写
        writing_task = Task(
            description=f"""
            根据以下信息创作社交媒体文案：
            
            主题: {theme}
            类型: {content_type}
            目标平台: {platforms}
            原始素材: {raw_material}
            
            要求：
            1. 开头要吸引人（使用前 2 行抓住注意力）
            2. 内容要有价值（提供实用信息或见解）
            3. 结尾要有行动号召（CTA）
            4. 适当使用 emoji 增强可读性
            5. 长度控制在 200-500 字
            6. 为不同平台调整风格
            
            请输出完整的文案内容。
            """,
            expected_output="完整的社交媒体文案",
            agent=self.writer_agent
        )
        
        # 任务 2: 校对编辑
        editing_task = Task(
            description=f"""
            校对和优化以下文案：
            
            文案：
            {state.get('draft_content', '待创作')}
            
            检查要点：
            1. 语法和拼写错误
            2. 逻辑清晰度和连贯性
            3. 语气是否一致且适合目标平台
            4. 是否有足够的吸引力和价值
            5. CTA 是否明确
            6. 长度是否合适
            
            如果发现问题，提供具体的修改建议。
            如果文案已经很好，回复 "APPROVED"。
            """,
            expected_output="校对反馈或 APPROVED",
            agent=self.editor_agent
        )
        
        # 创建 Crew
        crew = Crew(
            agents=[self.writer_agent, self.editor_agent],
            tasks=[writing_task, editing_task],
            process=Process.sequential,
            verbose=True
        )
        
        try:
            # 执行 Crew
            result = crew.kickoff()
            
            # 解析结果
            feedback = str(result.raw).strip()
            
            if "APPROVED" in feedback.upper():
                state["is_approved"] = True
                state["review_feedback"] = "文案已通过审核"
                print("✅ 文案审核通过！")
            else:
                state["is_approved"] = False
                state["review_feedback"] = feedback
                state["draft_content"] = feedback  # 使用反馈作为新的草稿
                print(f"⚠️  需要修改: {feedback[:200]}...")
            
            state["iteration_count"] += 1
            
        except Exception as e:
            print(f"❌ CrewAI 执行失败: {e}")
            state["is_approved"] = False
            state["review_feedback"] = f"执行错误: {str(e)}"
            state["iteration_count"] += 1
        
        state["updated_at"] = datetime.now().isoformat()
        
        return state


class ContentPublisher:
    """节点 C: 内容发布器"""
    
    def __init__(self):
        # 这里可以集成真实的 API
        # Twitter API, 小红书 API 等
        pass
    
    def publish(self, state: ContentState) -> ContentState:
        """
        发布内容到各个平台
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print("🚀 节点 C: 内容发布")
        print("="*80)
        
        content = state["draft_content"]
        platforms = state["target_platforms"]
        
        state["status"] = ContentStatus.PUBLISHING.value
        state["published_posts"] = {}
        state["publish_status"] = {}
        state["failed_platforms"] = []
        
        for platform in platforms:
            print(f"\n📤 发布到 {platform}...")
            
            try:
                # 模拟发布（实际使用时替换为真实 API）
                result = self._publish_to_platform(platform, content)
                
                state["published_posts"][platform] = result
                state["publish_status"][platform] = "success"
                
                print(f"✅ {platform} 发布成功")
                print(f"   Post ID: {result.get('post_id', 'N/A')}")
                print(f"   URL: {result.get('url', 'N/A')}")
                
            except Exception as e:
                print(f"❌ {platform} 发布失败: {e}")
                state["publish_status"][platform] = "failed"
                state["failed_platforms"].append(platform)
                state["error_message"] = str(e)
        
        # 检查是否全部成功
        if not state["failed_platforms"]:
            state["status"] = ContentStatus.PUBLISHED.value
            print("\n✅ 所有平台发布成功！")
        else:
            state["status"] = ContentStatus.FAILED.value
            print(f"\n⚠️  {len(state['failed_platforms'])} 个平台发布失败")
        
        state["updated_at"] = datetime.now().isoformat()
        
        return state
    
    def _publish_to_platform(self, platform: str, content: str) -> Dict:
        """
        发布到指定平台（模拟）
        
        实际使用时，这里应该调用真实的 API：
        - Twitter: tweepy 或 twitter-api-v2
        - 小红书: 小红书开放平台 API
        - 其他平台...
        """
        # 模拟发布延迟
        time.sleep(1)
        
        # 模拟返回结果
        return {
            "platform": platform,
            "post_id": f"{platform}_{int(time.time())}",
            "url": f"https://{platform.lower()}.com/post/{int(time.time())}",
            "published_at": datetime.now().isoformat(),
            "content_preview": content[:100] + "..."
        }


class MonitoringSystem:
    """节点 D: 监控系统"""
    
    def __init__(self):
        pass
    
    def monitor(self, state: ContentState) -> ContentState:
        """
        监控发布结果，决定是否需要重试
        
        Args:
            state: 当前状态
            
        Returns:
            更新后的状态
        """
        print("\n" + "="*80)
        print("👁️  节点 D: 发布监控")
        print("="*80)
        
        state["monitoring_results"] = {}
        state["retry_count"] = state.get("retry_count", 0)
        
        # 检查每个平台的发布状态
        for platform, status in state["publish_status"].items():
            print(f"\n🔍 检查 {platform}...")
            
            if status == "success":
                # 模拟监控（检查点赞、评论等）
                monitoring_result = self._check_post_performance(platform, state["published_posts"][platform])
                state["monitoring_results"][platform] = monitoring_result
                
                print(f"✅ {platform} 正常运行")
                print(f"   点赞: {monitoring_result.get('likes', 0)}")
                print(f"   评论: {monitoring_result.get('comments', 0)}")
                
            elif status == "failed":
                print(f"❌ {platform} 发布失败")
                state["failed_platforms"].append(platform)
        
        # 决定下一步
        if state["failed_platforms"]:
            state["retry_count"] += 1
            
            if state["retry_count"] <= state["max_retries"]:
                print(f"\n🔄 发现 {len(state['failed_platforms'])} 个失败平台")
                print(f"   重试次数: {state['retry_count']}/{state['max_retries']}")
                print(f"   失败平台: {', '.join(state['failed_platforms'])}")
                
                state["status"] = ContentStatus.RETRY.value
                state["is_approved"] = False  # 需要重新创作
                
                # 清空失败的发布记录
                for platform in state["failed_platforms"]:
                    if platform in state["published_posts"]:
                        del state["published_posts"][platform]
                    if platform in state["publish_status"]:
                        del state["publish_status"][platform]
                
                print(f"\n⚠️  将退回节点 B 重新修改并发布")
            else:
                print(f"\n❌ 已达到最大重试次数 ({state['max_retries']})")
                state["status"] = ContentStatus.FAILED.value
                state["error_message"] = f"重试 {state['max_retries']} 次后仍然失败"
        else:
            print("\n✅ 所有平台监控正常")
            state["status"] = ContentStatus.PUBLISHED.value
        
        state["updated_at"] = datetime.now().isoformat()
        
        return state
    
    def _check_post_performance(self, platform: str, post_info: Dict) -> Dict:
        """
        检查帖子表现（模拟）
        
        实际使用时，这里应该调用平台 API 获取真实数据
        """
        # 模拟数据
        return {
            "platform": platform,
            "post_id": post_info.get("post_id"),
            "likes": 0,  # 实际从 API 获取
            "comments": 0,
            "shares": 0,
            "impressions": 0,
            "checked_at": datetime.now().isoformat()
        }


class ContentPublishingWorkflow:
    """
    LangGraph + CrewAI 智能内容发布工作流
    
    架构：
    A (主题分析) → B (CrewAI 创作) → C (发布) → D (监控)
                                    ↑              |
                                    └──────────────┘ (失败时重试)
    """
    
    def __init__(self, max_iterations: int = 3, max_retries: int = 2):
        self.max_iterations = max_iterations
        self.max_retries = max_retries
        
        # 初始化各个节点
        self.theme_analyzer = ThemeAnalyzer()
        self.content_crew = ContentCreationCrew()
        self.publisher = ContentPublisher()
        self.monitor = MonitoringSystem()
        
        # 构建 LangGraph
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """构建 LangGraph 工作流"""
        
        # 创建状态图
        workflow = StateGraph(ContentState)
        
        # 添加节点
        workflow.add_node("theme_analysis", self.theme_analyzer.analyze_theme)
        workflow.add_node("content_creation", self.content_crew.create_content)
        workflow.add_node("publish", self.publisher.publish)
        workflow.add_node("monitor", self.monitor.monitor)
        
        # 设置入口点
        workflow.set_entry_point("theme_analysis")
        
        # 添加边
        workflow.add_edge("theme_analysis", "content_creation")
        
        # 条件边：内容创作是否通过审核
        workflow.add_conditional_edges(
            "content_creation",
            self._should_continue_creating,
            {
                "continue": "content_creation",  # 继续迭代
                "publish": "publish"  # 通过审核，进入发布
            }
        )
        
        # 发布后进入监控
        workflow.add_edge("publish", "monitor")
        
        # 条件边：监控结果决定是否重试
        workflow.add_conditional_edges(
            "monitor",
            self._should_retry,
            {
                "retry": "content_creation",  # 重试，回到创作
                "end": END  # 完成
            }
        )
        
        # 编译工作流
        checkpointer = MemorySaver()
        compiled_workflow = workflow.compile(checkpointer=checkpointer)
        
        return compiled_workflow
    
    def _should_continue_creating(self, state: ContentState) -> str:
        """判断是否继续创作迭代"""
        if state["is_approved"]:
            return "publish"
        
        if state["iteration_count"] >= state["max_iterations"]:
            print(f"\n⚠️  达到最大迭代次数 ({state['max_iterations']})，强制发布")
            return "publish"
        
        return "continue"
    
    def _should_retry(self, state: ContentState) -> str:
        """判断是否重试"""
        if state["status"] == ContentStatus.RETRY.value:
            return "retry"
        return "end"
    
    def run(self, raw_material: str, target_platforms: List[str] = None) -> Dict:
        """
        运行完整的工作流
        
        Args:
            raw_material: 原始素材
            target_platforms: 目标平台列表
            
        Returns:
            最终状态
        """
        print("\n" + "🎯"*40)
        print("LangGraph + CrewAI 智能内容发布系统")
        print("🎯"*40)
        
        if target_platforms is None:
            target_platforms = ["Twitter", "小红书"]
        
        # 初始化状态
        initial_state: ContentState = {
            "raw_material": raw_material,
            "target_platforms": target_platforms,
            "today_theme": "",
            "content_type": "",
            "priority": 0,
            "draft_content": "",
            "review_feedback": "",
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "is_approved": False,
            "published_posts": {},
            "publish_status": {},
            "monitoring_results": {},
            "failed_platforms": [],
            "retry_count": 0,
            "max_retries": self.max_retries,
            "status": ContentStatus.PENDING.value,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error_message": ""
        }
        
        # 配置
        config = {
            "configurable": {
                "thread_id": f"content_{int(time.time())}"
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
            print(f"迭代次数: {final_state['iteration_count']}")
            print(f"重试次数: {final_state['retry_count']}")
            print(f"发布平台: {len(final_state['published_posts'])} 个")
            
            if final_state["error_message"]:
                print(f"错误: {final_state['error_message']}")
            
            return final_state
            
        except Exception as e:
            print(f"\n❌ 工作流执行失败: {e}")
            import traceback
            traceback.print_exc()
            raise


# 使用示例
if __name__ == "__main__":
    # 设置 API Key（实际使用时从环境变量读取）
    os.environ["OPENAI_API_KEY"] = "your-openai-api-key-here"
    
    # 创建发布工作流
    workflow = ContentPublishingWorkflow(
        max_iterations=3,  # 最多迭代 3 次
        max_retries=2      # 最多重试 2 次
    )
    
    # 准备素材
    raw_material = """
    AnimoCerebro 项目最新进展：
    
    1. 完成了浏览器自动化模块，支持 Stealth Chrome
    2. 实现了 Reddit 智能发帖系统，带反复纠错机制
    3. 创建了社区规则管理器，自动缓存和验证规则
    4. 开发了每周发帖计划生成器，防止重复内容
    5. 重构了 Agent 模块，采用模块化目录结构
    
    技术栈：FastAPI, React, Playwright, LangGraph, CrewAI
    GitHub: https://github.com/AnimoCerebro
    """
    
    # 运行工作流
    result = workflow.run(
        raw_material=raw_material,
        target_platforms=["Twitter", "小红书"]
    )
    
    # 保存结果
    with open("Agent/publishing_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    
    print("\n✅ 结果已保存到 Agent/publishing_result.json")
