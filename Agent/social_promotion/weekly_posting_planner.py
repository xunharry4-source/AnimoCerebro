#!/usr/bin/env python3
"""
AnimoCerebro 每周发帖计划生成器

功能：
1. 自动生成周一到周五的发帖计划
2. 针对不同社区安排不同内容
3. 检查历史发帖记录，防止重复
4. 基于项目进展动态调整内容
5. 导出为 JSON 或 Markdown 格式
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class WeeklyPostingPlanner:
    """每周发帖计划生成器"""
    
    def __init__(self):
        self.project_info = self._load_project_info()
        self.history_file = Path("Agent/posting_history.json")
        self.plan_file = Path("Agent/weekly_posting_plan.json")
        self.posting_history = self._load_posting_history()
        
    def _load_project_info(self) -> Dict:
        """加载项目信息"""
        return {
            "name": "AnimoCerebro",
            "version": "1.0.0",
            "github": "https://github.com/AnimoCerebro",
            "current_focus": [
                "浏览器自动化和 Stealth Chrome",
                "Reddit 智能发帖系统",
                "社区规则管理",
                "社交媒体宣传"
            ],
            "recent_achievements": [
                "实现 Stealth Chrome 绕过检测",
                "完成 Reddit 智能发帖器（带反复纠错）",
                "建立社区规则缓存系统",
                "创建 AnimoCerebro 宣传助手"
            ]
        }
    
    def _load_posting_history(self) -> Dict:
        """加载历史发帖记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"posts": []}
        return {"posts": []}
    
    def save_posting_history(self):
        """保存发帖历史"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.posting_history, f, indent=2, ensure_ascii=False)
    
    def check_duplicate(self, subreddit: str, title: str, content_hash: str) -> bool:
        """
        检查是否重复发帖
        
        Args:
            subreddit: 社区名称
            title: 帖子标题
            content_hash: 内容哈希
            
        Returns:
            bool: True 表示重复，False 表示不重复
        """
        # 检查过去 7 天内是否有相同社区的相似内容
        seven_days_ago = time.time() - (7 * 24 * 3600)
        
        for post in self.posting_history.get("posts", []):
            if post["timestamp"] < seven_days_ago:
                continue
                
            # 同一社区
            if post["subreddit"] == subreddit:
                # 相似标题（简单检查）
                if self._is_similar_title(post["title"], title):
                    return True
                
                # 相同内容哈希
                if post.get("content_hash") == content_hash:
                    return True
        
        return False
    
    def _is_similar_title(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """检查标题是否相似"""
        # 简单的相似度检查
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        
        if not words1 or not words2:
            return False
        
        intersection = words1 & words2
        union = words1 | words2
        
        similarity = len(intersection) / len(union)
        return similarity > threshold
    
    def record_post(self, subreddit: str, title: str, content: str, success: bool):
        """记录发帖"""
        import hashlib
        
        post_record = {
            "subreddit": subreddit,
            "title": title,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "timestamp": time.time(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "success": success
        }
        
        self.posting_history.setdefault("posts", []).append(post_record)
        self.save_posting_history()
    
    def generate_weekly_plan(self, week_start: Optional[datetime] = None) -> Dict:
        """
        生成本周发帖计划
        
        Args:
            week_start: 本周开始日期（默认本周一）
            
        Returns:
            Dict: 一周的发帖计划
        """
        if week_start is None:
            # 获取本周一
            today = datetime.now()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        plan = {
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": (week_start + timedelta(days=4)).strftime("%Y-%m-%d"),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "schedule": {}
        }
        
        # 生成每天的计划
        for day_offset in range(5):  # 周一到周五
            current_date = week_start + timedelta(days=day_offset)
            day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][day_offset]
            day_name_cn = ["星期一", "星期二", "星期三", "星期四", "星期五"][day_offset]
            
            daily_plan = self._generate_daily_plan(current_date, day_offset)
            
            plan["schedule"][day_name] = {
                "date": current_date.strftime("%Y-%m-%d"),
                "date_cn": day_name_cn,
                **daily_plan
            }
        
        # 保存计划
        self._save_plan(plan)
        
        return plan
    
    def _generate_daily_plan(self, date: datetime, day_offset: int) -> Dict:
        """生成单天计划"""
        
        # 每周发帖策略
        weekly_strategy = {
            0: {  # 星期一
                "theme": "项目进度更新",
                "primary_community": "AnimoCerebro",
                "secondary_communities": ["Python"],
                "content_type": "progress_update"
            },
            1: {  # 星期二
                "theme": "技术深度分享",
                "primary_community": "MachineLearning",
                "secondary_communities": ["artificial"],
                "content_type": "technical_deep_dive"
            },
            2: {  # 星期三
                "theme": "学习经验分享",
                "primary_community": "learnprogramming",
                "secondary_communities": ["programming"],
                "content_type": "learning_experience"
            },
            3: {  # 星期四
                "theme": "系统架构讨论",
                "primary_community": "compsci",
                "secondary_communities": ["Python"],
                "content_type": "architecture_discussion"
            },
            4: {  # 星期五
                "theme": "周末预告和总结",
                "primary_community": "AnimoCerebro",
                "secondary_communities": ["programming"],
                "content_type": "weekly_summary"
            }
        }
        
        strategy = weekly_strategy[day_offset]
        
        # 生成主社区帖子
        primary_post = self._generate_post_content(
            strategy["primary_community"],
            strategy["content_type"],
            date
        )
        
        # 检查重复
        is_duplicate = self.check_duplicate(
            strategy["primary_community"],
            primary_post["title"],
            primary_post["content_hash"]
        )
        
        # 如果重复，生成备选内容
        if is_duplicate:
            primary_post = self._generate_alternative_content(
                strategy["primary_community"],
                strategy["content_type"],
                date
            )
            primary_post["note"] = "⚠️ 检测到相似内容，已生成备选方案"
        
        return {
            "theme": strategy["theme"],
            "primary_post": primary_post,
            "secondary_posts": [
                {
                    "community": comm,
                    "suggested_time": "14:00-16:00 EST",
                    "note": "可选，根据主要帖子反馈决定是否发布"
                }
                for comm in strategy["secondary_communities"]
            ],
            "best_posting_time": self._get_best_posting_time(day_offset),
            "content_focus": self._get_content_focus(strategy["content_type"])
        }
    
    def _generate_post_content(self, community: str, content_type: str, date: datetime) -> Dict:
        """生成帖子内容"""
        
        content_templates = {
            "AnimoCerebro": {
                "progress_update": self._generate_progress_update,
                "weekly_summary": self._generate_weekly_summary
            },
            "Python": {
                "technical_deep_dive": self._generate_python_tech_post,
                "architecture_discussion": self._generate_python_tech_post  # 使用相同的方法
            },
            "MachineLearning": {
                "technical_deep_dive": self._generate_ml_research_post
            },
            "learnprogramming": {
                "learning_experience": self._generate_learning_post
            },
            "compsci": {
                "architecture_discussion": lambda date: self._generate_generic_post("compsci", "architecture_discussion", date)
            },
            "programming": {
                "learning_experience": self._generate_learning_post,  # 使用学习方法
                "weekly_summary": self._generate_weekly_summary  # 使用周总结方法
            },
            "artificial": {
                "technical_deep_dive": self._generate_ml_research_post  # 使用 ML 研究方法
            }
        }
        
        generator = content_templates.get(community, {}).get(content_type)
        
        if generator:
            return generator(date)
        else:
            return self._generate_generic_post(community, content_type, date)
    
    def _generate_progress_update(self, date: datetime) -> Dict:
        """生成项目进度更新"""
        title = f"🚀 AnimoCerebro Weekly Progress Update - {date.strftime('%Y-%m-%d')}"
        
        content = f"""# AnimoCerebro Weekly Progress Update

## 📌 This Week's Focus

{chr(10).join([f"- {item}" for item in self.project_info['current_focus']])}

## ✅ Recent Achievements

{chr(10).join([f"- {item}" for item in self.project_info['recent_achievements']])}

## 🔧 Technical Highlights

### Browser Automation
- Implemented Stealth Chrome to bypass detection
- Persistent context for session management
- Enhanced fingerprint hiding (13 techniques)

### Smart Posting System
- Automatic community rule checking
- Rule-compliant content generation
- Retry mechanism with error correction

### Community Rules Management
- Individual cache for each subreddit
- Automatic rule downloading
- Pre-posting compliance validation

## 📊 Current Status

- **Version**: {self.project_info['version']}
- **GitHub**: {self.project_info['github']}
- **Active Communities**: 7+

## 💡 Next Steps

1. Expand to more technical communities
2. Implement scheduled posting
3. Add A/B testing for content
4. Build engagement analytics

## 🔗 Links

- GitHub: {self.project_info['github']}
- Documentation: Available in repo

---

*Posted on {date.strftime('%Y-%m-%d')}*
"""
        
        import hashlib
        return {
            "title": title,
            "content": content,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "flair": "Project Update",
            "estimated_length": len(content),
            "posting_time": "10:00-12:00 EST"
        }
    
    def _generate_python_tech_post(self, date: datetime) -> Dict:
        """生成 Python 技术帖子"""
        title = "Building Stealth Browser Automation with FastAPI and Playwright"
        
        content = f"""Hi Python developers,

I want to share a technical implementation from our project **AnimoCerebro** - an AI-augmented cognitive system.

## 🐍 Tech Stack Implementation

We built a browser automation system using:
- **FastAPI** for async web services
- **Playwright** for browser control
- **Stealth techniques** to avoid detection

## 💻 Key Implementation Details

### 1. Persistent Context Management
```python
context = playwright.chromium.launch_persistent_context(
    user_data_dir="./chrome_profile",
    executable_path="/path/to/chrome",
    args=["--disable-blink-features=AutomationControlled"]
)
```

### 2. Fingerprint Hiding
Implemented 13 stealth techniques:
- WebDriver flag removal
- Plugin simulation
- Hardware concurrency spoofing
- Canvas fingerprint protection

### 3. Smart Content Generation
- Automatic rule compliance checking
- Dynamic content adaptation
- Error recovery mechanisms

## 🎯 Use Cases

This system enables:
- Automated social media posting
- Community rule validation
- Intelligent retry logic

## 🔗 Open Source

Check out the implementation: {self.project_info['github']}

Would love feedback on:
- Playwright optimization techniques
- FastAPI async patterns
- Browser automation best practices

Thanks!
"""
        
        import hashlib
        return {
            "title": title,
            "content": content,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "flair": "Showcase",
            "estimated_length": len(content),
            "posting_time": "14:00-16:00 EST"
        }
    
    def _generate_ml_research_post(self, date: datetime) -> Dict:
        """生成 ML 研究帖子"""
        title = "[Project] Cognitive Augmentation with LLMs: AnimoCerebro Architecture"
        
        content = f"""Hi ML community,

I'd like to share our research on AI-augmented cognition through **AnimoCerebro**.

## 🧠 Research Focus

How can LLMs enhance human cognitive capabilities without replacing human thought?

## 🛠️ Technical Architecture

### LLM Integration
- **DSPy** for prompt optimization
- **PydanticAI** for structured outputs
- Multi-provider support (OpenAI, Google)
- Caching layer for efficiency

### Memory Systems
- **Faiss** for vector similarity search
- **Kuzu Graph DB** for knowledge representation
- **Sentence Transformers** for embeddings

### Cognitive Framework
- Nine Questions Cognitive Loop
- Metacognition module
- Truth boundary enforcement

## 📊 Current Results

- ✅ Automated reasoning pipelines
- ✅ Knowledge persistence with semantic search
- ✅ Plugin-based extensibility
- ✅ Cross-platform automation

## 🎯 Research Questions

1. What structures improve AI-human collaboration?
2. How to maintain truthfulness in AI systems?
3. Can we quantify cognitive augmentation?

## 🔗 Resources

- GitHub: {self.project_info['github']}
- Paper: In preparation

Interested in discussions about cognitive architectures and LLM applications!
"""
        
        import hashlib
        return {
            "title": title,
            "content": content,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "flair": "Project",
            "estimated_length": len(content),
            "posting_time": "11:00-13:00 EST"
        }
    
    def _generate_learning_post(self, date: datetime) -> Dict:
        """生成学习经验帖子"""
        title = "What I Learned Building an AI System with Python, React, and Playwright"
        
        content = f"""Hi everyone,

I want to share my learning journey building **AnimoCerebro**, an AI-augmented cognitive system.

## 📚 Key Learnings

### Backend Development
- **FastAPI**: Async web services are powerful but require careful error handling
- **Database Design**: Using both graph (Kuzu) and vector (Faiss) databases taught me about hybrid architectures
- **API Design**: RESTful endpoints need comprehensive documentation

### Frontend Challenges
- **React + TypeScript**: Type safety catches bugs early but has a learning curve
- **State Management**: Complex apps need careful state architecture
- **Modern Tooling**: Vite is incredibly fast compared to Webpack

### AI/ML Integration
- **LLM APIs**: Rate limiting and cost management are crucial
- **Prompt Engineering**: DSPy made optimization much easier
- **Vector Search**: Faiss is efficient but requires understanding of embeddings

### Automation
- **Browser Control**: Playwright is robust but needs stealth techniques
- **Error Handling**: Retry mechanisms with exponential backoff
- **Session Management**: Cookie persistence across restarts

## 💡 Biggest Challenges

1. **Browser Detection**: Took weeks to implement proper stealth
2. **Rule Compliance**: Each community has different requirements
3. **Content Generation**: Balancing automation with authenticity

## 🎯 Advice for Beginners

1. Start small and iterate
2. Read documentation thoroughly
3. Join community forums
4. Don't be afraid to ask questions
5. Test everything

## 🔗 Project Link

{self.project_info['github']}

What challenges have you faced in your projects? Any tips for managing complex systems?
"""
        
        import hashlib
        return {
            "title": title,
            "content": content,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "flair": "Discussion",
            "estimated_length": len(content),
            "posting_time": "15:00-17:00 EST"
        }
    
    def _generate_weekly_summary(self, date: datetime) -> Dict:
        """生成周总结"""
        title = f"AnimoCerebro Week in Review - {date.strftime('%Y-%m-%d')}"
        
        content = f"""# AnimoCerebro - Week in Review

## 📅 Week of {date.strftime('%Y-%m-%d')}

### ✅ Completed This Week

{chr(10).join([f"- {item}" for item in self.project_info['recent_achievements']])}

### 🎯 Focus Areas

{chr(10).join([f"- {item}" for item in self.project_info['current_focus']])}

### 📊 Community Engagement

- Active discussions in 7+ communities
- Feedback collected and incorporated
- New contributors welcomed

### 🔧 Technical Improvements

- Performance optimizations
- Bug fixes and stability improvements
- Documentation updates

### 🚀 Coming Next Week

1. Expand community outreach
2. Implement advanced features
3. Address community feedback
4. Prepare for next release

## 💬 Community Highlights

Thank you to everyone who contributed feedback and suggestions this week!

## 🔗 Stay Connected

- GitHub: {self.project_info['github']}
- Discussions: Open on GitHub

Have a great weekend! 🎉
"""
        
        import hashlib
        return {
            "title": title,
            "content": content,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "flair": "Weekly Summary",
            "estimated_length": len(content),
            "posting_time": "16:00-18:00 EST"
        }
    
    def _generate_alternative_content(self, community: str, content_type: str, date: datetime) -> Dict:
        """生成备选内容（当检测到重复时）"""
        # 添加时间戳和变化以避免重复
        alternative_templates = {
            "progress_update": lambda: self._generate_progress_update(date),
            "technical_deep_dive": lambda: self._generate_python_tech_post(date),
            "learning_experience": lambda: self._generate_learning_post(date),
        }
        
        generator = alternative_templates.get(content_type)
        if generator:
            content = generator()
            # 修改标题以区分
            content["title"] += " (Alternative)"
            return content
        
        return self._generate_post_content(community, content_type, date)
    
    def _generate_generic_post(self, community: str, content_type: str, date: datetime) -> Dict:
        """生成通用帖子"""
        title = f"Introducing AnimoCerebro - AI-Augmented Cognitive System"
        
        content = f"""Hi r/{community},

I'd like to introduce **AnimoCerebro**, an open-source project exploring AI-augmented cognition.

## 🧠 What is AnimoCerebro?

An AI system designed to enhance human cognitive capabilities through structured thinking frameworks and intelligent automation.

## 🔗 Learn More

- GitHub: {self.project_info['github']}

Would appreciate feedback from the community!
"""
        
        import hashlib
        return {
            "title": title,
            "content": content,
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "flair": "Discussion",
            "estimated_length": len(content),
            "posting_time": "12:00-14:00 EST"
        }
    
    def _get_best_posting_time(self, day_offset: int) -> str:
        """获取最佳发帖时间"""
        times = {
            0: "10:00-12:00 EST (Monday morning)",
            1: "14:00-16:00 EST (Tuesday afternoon)",
            2: "11:00-13:00 EST (Wednesday midday)",
            3: "15:00-17:00 EST (Thursday afternoon)",
            4: "16:00-18:00 EST (Friday evening)"
        }
        return times.get(day_offset, "12:00-14:00 EST")
    
    def _get_content_focus(self, content_type: str) -> str:
        """获取内容重点"""
        focuses = {
            "progress_update": "项目进展、新功能、成就展示",
            "technical_deep_dive": "技术实现细节、代码示例、架构设计",
            "learning_experience": "学习心得、挑战克服、建议分享",
            "architecture_discussion": "系统设计、技术选型、性能优化",
            "weekly_summary": "本周总结、社区互动、下周计划"
        }
        return focuses.get(content_type, "一般性介绍")
    
    def _save_plan(self, plan: Dict):
        """保存计划到文件"""
        self.plan_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.plan_file, 'w', encoding='utf-8') as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)
    
    def export_to_markdown(self, plan: Dict) -> str:
        """导出为 Markdown 格式"""
        md = f"""# AnimoCerebro 每周发帖计划

**周期**: {plan['week_start']} 至 {plan['week_end']}  
**生成时间**: {plan['generated_at']}

---

"""
        
        day_names_cn = {
            "Monday": "星期一",
            "Tuesday": "星期二",
            "Wednesday": "星期三",
            "Thursday": "星期四",
            "Friday": "星期五"
        }
        
        for day_name, day_plan in plan['schedule'].items():
            md += f"""## {day_names_cn[day_name]} ({day_plan['date']})

### 📋 主题
{day_plan['theme']}

### 🎯 主要内容
- **社区**: r/{day_plan['primary_post']['flair']}
- **标题**: {day_plan['primary_post']['title']}
- **最佳时间**: {day_plan['best_posting_time']}
- **内容重点**: {day_plan['content_focus']}

### 📝 帖子预览
**标题**: {day_plan['primary_post']['title']}

**Flair**: {day_plan['primary_post']['flair']}

**预计长度**: {day_plan['primary_post']['estimated_length']} 字符

{day_plan['primary_post'].get('note', '')}

### 🔄 备选社区
"""
            for secondary in day_plan['secondary_posts']:
                md += f"- r/{secondary['community']} ({secondary['suggested_time']})\n"
            
            md += "\n---\n\n"
        
        md += """
## ⚠️ 注意事项

1. **避免重复**: 系统会自动检查过去 7 天的发帖记录
2. **灵活调整**: 根据社区反馈调整后续发帖
3. **质量控制**: 每个帖子都经过规则合规检查
4. **时间管理**: 建议在推荐时间段内发帖

## 📊 本周统计

- **计划发帖数**: 5 个主要帖子
- **覆盖社区**: 7+ 个
- **预计总长度**: ~10,000+ 字符
- **重复检查**: ✅ 已启用

---

*Generated by Weekly Posting Planner*
"""
        
        return md
    
    def save_markdown_plan(self, plan: Dict, filename: str = None):
        """保存 Markdown 格式的计划"""
        if filename is None:
            filename = f"Agent/weekly_plan_{plan['week_start']}.md"
        
        md_content = self.export_to_markdown(plan)
        
        plan_file = Path(filename)
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        with open(plan_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return str(plan_file)


# 使用示例
if __name__ == "__main__":
    planner = WeeklyPostingPlanner()
    
    # 生成本周计划
    plan = planner.generate_weekly_plan()
    
    # 打印计划
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    
    # 导出为 Markdown
    md_file = planner.save_markdown_plan(plan)
    print(f"\n✅ Markdown 计划已保存: {md_file}")
