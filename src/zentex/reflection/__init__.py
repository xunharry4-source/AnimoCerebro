from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from zentex.reflection.models import ReflectionRecord, ReflectionTemplate, ReflectionInsight, ReflectionPattern
from zentex.reflection.service import ReflectionService
from zentex.reflection.interface import ReflectionInterface
from zentex.reflection.persistence import ReflectionPersistence

logger = logging.getLogger(__name__)

class ReflectionManager:
    """
    反思模块管理器
    
    提供高级反思管理功能，包括反思生成、管理、分析和治理。
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        *,
        enable_persistence: bool = True,
        backup_count: int = 5
    ) -> None:
        """
        初始化反思管理器
        
        Args:
            storage_path: 存储路径
            enable_persistence: 是否启用持久化
            backup_count: 备份数量
        """
        # 设置持久化
        persistence = None
        if enable_persistence:
            if storage_path:
                persistence = ReflectionPersistence(storage_path, backup_count)
            else:
                # 默认存储路径
                default_path = Path("./reflection_data")
                default_path.mkdir(exist_ok=True)
                persistence = ReflectionPersistence(str(default_path), backup_count)
        
        # 创建服务
        self.service = ReflectionService(persistence)
        
        # 创建统一接口
        self.interface = ReflectionInterface(self.service)
        
        logger.info(f"ReflectionManager initialized with persistence={enable_persistence}")
    
    # === 高级反思生成 ===
    
    def generate_decision_reflection(
        self,
        decision_subject: str,
        decision_data: Dict[str, Any],
        outcome_data: Dict[str, Any],
        alternatives: Optional[List[Dict[str, Any]]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成决策反思
        
        Args:
            decision_subject: 决策主题
            decision_data: 决策数据
            outcome_data: 结果数据
            alternatives: 备选方案
            trace_id: 追踪ID
            
        Returns:
            生成结果
        """
        from zentex.reflection.models import ReflectionType
        
        context = {
            "decision": decision_data,
            "outcome": outcome_data,
            "alternatives": alternatives or [],
            "complexity": self._assess_complexity(decision_data, alternatives),
            "impact": self._assess_impact(outcome_data)
        }
        
        return self.interface.generate_reflection({
            "subject": decision_subject,
            "reflection_type": ReflectionType.DECISION_REFLECTION,
            "context": context,
            "trace_id": trace_id
        })
    
    def generate_error_reflection(
        self,
        error_subject: str,
        error_data: Dict[str, Any],
        impact_data: Dict[str, Any],
        prevention_context: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成错误反思
        
        Args:
            error_subject: 错误主题
            error_data: 错误数据
            impact_data: 影响数据
            prevention_context: 预防上下文
            trace_id: 追踪ID
            
        Returns:
            生成结果
        """
        from zentex.reflection.models import ReflectionType
        
        context = {
            "error": error_data,
            "impact": impact_data,
            "prevention": prevention_context or {},
            "complexity": "high",  # 错误反思通常需要深度分析
            "impact": self._assess_error_impact(impact_data)
        }
        
        return self.interface.generate_reflection({
            "subject": error_subject,
            "reflection_type": ReflectionType.ERROR_REFLECTION,
            "context": context,
            "trace_id": trace_id
        })
    
    def generate_success_reflection(
        self,
        success_subject: str,
        success_data: Dict[str, Any],
        success_factors: List[str],
        replication_context: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成成功反思
        
        Args:
            success_subject: 成功主题
            success_data: 成功数据
            success_factors: 成功因素
            replication_context: 复制上下文
            trace_id: 追踪ID
            
        Returns:
            生成结果
        """
        from zentex.reflection.models import ReflectionType
        
        context = {
            "success": success_data,
            "success_factors": success_factors,
            "replication": replication_context or {},
            "complexity": "medium",
            "impact": self._assess_success_impact(success_data)
        }
        
        return self.interface.generate_reflection({
            "subject": success_subject,
            "reflection_type": ReflectionType.SUCCESS_REFLECTION,
            "context": context,
            "trace_id": trace_id
        })
    
    # === 批量操作 ===
    
    def batch_generate_reflections(
        self,
        reflection_requests: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量生成反思
        
        Args:
            reflection_requests: 反思请求列表
            
        Returns:
            批量生成结果
        """
        results = {"success": [], "failed": []}
        
        for i, request in enumerate(reflection_requests):
            try:
                result = self.interface.generate_reflection(request)
                if result["success"]:
                    results["success"].append({
                        "index": i,
                        "reflection_id": result["reflection"]["reflection_id"],
                        "subject": result["reflection"]["subject"]
                    })
                else:
                    results["failed"].append({
                        "index": i,
                        "error": result["error"],
                        "error_code": result["error_code"]
                    })
            except Exception as e:
                results["failed"].append({
                    "index": i,
                    "error": str(e),
                    "error_code": "GENERATION_ERROR"
                })
        
        return {
            "success": True,
            "results": results,
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "message": f"Batch generation completed: {len(results['success'])} success, {len(results['failed'])} failed"
        }
    
    def batch_analyze_reflections(
        self,
        reflection_ids: List[str],
        analysis_type: str = "summary"
    ) -> Dict[str, Any]:
        """
        批量分析反思
        
        Args:
            reflection_ids: 反思ID列表
            analysis_type: 分析类型
            
        Returns:
            分析结果
        """
        try:
            # 获取反思记录
            reflections = []
            for reflection_id in reflection_ids:
                result = self.interface.get_reflection(reflection_id)
                if result["success"]:
                    reflections.append(result["reflection"])
            
            if not reflections:
                return {
                    "success": False,
                    "error": "No valid reflections found",
                    "error_code": "NO_REFLECTIONS"
                }
            
            # 执行分析
            if analysis_type == "summary":
                analysis_result = self._analyze_summary(reflections)
            elif analysis_type == "patterns":
                analysis_result = self._analyze_patterns(reflections)
            elif analysis_type == "insights":
                analysis_result = self._analyze_insights(reflections)
            elif analysis_type == "quality":
                analysis_result = self._analyze_quality(reflections)
            else:
                return {
                    "success": False,
                    "error": f"Unknown analysis type: {analysis_type}",
                    "error_code": "UNKNOWN_ANALYSIS_TYPE"
                }
            
            return {
                "success": True,
                "analysis_type": analysis_type,
                "reflections_analyzed": len(reflections),
                "result": analysis_result
            }
            
        except Exception as e:
            logger.error(f"Failed to batch analyze reflections: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "BATCH_ANALYSIS_ERROR"
            }
    
    # === 智能推荐 ===
    
    def get_contextual_recommendations(
        self,
        context: Dict[str, Any],
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        获取上下文相关推荐
        
        Args:
            context: 上下文信息
            limit: 推荐数量限制
            
        Returns:
            上下文推荐
        """
        try:
            # 基于上下文筛选相关反思
            filters = self._build_context_filters(context)
            
            reflections_result = self.interface.list_reflections(filters)
            if not reflections_result["success"]:
                return reflections_result
            
            reflections = reflections_result["reflections"]
            
            # 计算相关性评分
            scored_reflections = []
            for reflection in reflections:
                relevance_score = self._calculate_relevance(reflection, context)
                scored_reflections.append({
                    "reflection": reflection,
                    "relevance_score": relevance_score
                })
            
            # 按相关性排序
            scored_reflections.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # 生成推荐
            recommendations = []
            for scored_reflection in scored_reflections[:limit]:
                reflection = scored_reflection["reflection"]
                recommendations.append({
                    "reflection_id": reflection["reflection_id"],
                    "subject": reflection["subject"],
                    "summary": reflection["summary"],
                    "relevance_score": scored_reflection["relevance_score"],
                    "key_insights": reflection["insights"][:2],
                    "created_at": reflection["created_at"]
                })
            
            return {
                "success": True,
                "recommendations": recommendations,
                "count": len(recommendations),
                "context": context
            }
            
        except Exception as e:
            logger.error(f"Failed to get contextual recommendations: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_RECOMMENDATIONS_ERROR"
            }
    
    def get_learning_pathway(
        self,
        goal: str,
        current_level: str = "beginner",
        target_level: str = "advanced"
    ) -> Dict[str, Any]:
        """
        获取学习路径推荐
        
        Args:
            goal: 学习目标
            current_level: 当前水平
            target_level: 目标水平
            
        Returns:
            学习路径
        """
        try:
            # 搜索相关反思
            search_result = self.interface.search_reflections(goal)
            if not search_result["success"]:
                return search_result
            
            # 按质量和影响力筛选
            relevant_reflections = []
            for reflection in search_result["reflections"]:
                if (reflection["quality"] in ["excellent", "good"] and
                    reflection["impact_score"] >= 0.6):
                    relevant_reflections.append(reflection)
            
            # 构建学习路径
            pathway = self._build_learning_pathway(
                relevant_reflections, goal, current_level, target_level
            )
            
            return {
                "success": True,
                "goal": goal,
                "current_level": current_level,
                "target_level": target_level,
                "pathway": pathway,
                "total_steps": len(pathway)
            }
            
        except Exception as e:
            logger.error(f"Failed to get learning pathway: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_LEARNING_PATHWAY_ERROR"
            }
    
    # === 导出和报告 ===
    
    def export_reflections(
        self,
        filters: Optional[Dict[str, Any]] = None,
        format: str = "json"
    ) -> Dict[str, Any]:
        """
        导出反思数据
        
        Args:
            filters: 过滤条件
            format: 导出格式
            
        Returns:
            导出结果
        """
        try:
            reflections_result = self.interface.list_reflections(filters)
            if not reflections_result["success"]:
                return reflections_result
            
            reflections = reflections_result["reflections"]
            
            if format == "json":
                export_data = {
                    "export_timestamp": "2024-01-01T00:00:00Z",
                    "total_reflections": len(reflections),
                    "reflections": reflections
                }
            elif format == "csv":
                export_data = self._convert_to_csv(reflections)
            elif format == "summary":
                export_data = self._generate_summary_report(reflections)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported export format: {format}",
                    "error_code": "UNSUPPORTED_FORMAT"
                }
            
            return {
                "success": True,
                "format": format,
                "data": export_data,
                "count": len(reflections)
            }
            
        except Exception as e:
            logger.error(f"Failed to export reflections: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "EXPORT_ERROR"
            }
    
    def generate_reflection_report(
        self,
        period: str = "weekly",
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        生成反思报告
        
        Args:
            period: 报告周期
            filters: 过滤条件
            
        Returns:
            报告数据
        """
        try:
            # 获取统计数据
            metrics_result = self.interface.get_metrics()
            if not metrics_result["success"]:
                return metrics_result
            
            metrics = metrics_result["metrics"]
            
            # 获取反思列表
            reflections_result = self.interface.list_reflections(filters)
            reflections = reflections_result["reflections"] if reflections_result["success"] else []
            
            # 生成报告
            report = {
                "report_period": period,
                "generated_at": "2024-01-01T00:00:00Z",
                "summary": {
                    "total_reflections": metrics["total_reflections"],
                    "average_quality": self._calculate_average_quality(reflections),
                    "high_impact_reflections": len([r for r in reflections if r["impact_score"] >= 0.8]),
                    "verified_reflections": metrics["verified_reflections"]
                },
                "analysis": {
                    "reflection_types": metrics["reflections_by_type"],
                    "quality_distribution": metrics["reflections_by_quality"],
                    "trends": self._analyze_trends(reflections)
                },
                "recommendations": self._generate_period_recommendations(reflections),
                "top_insights": self._extract_top_insights(reflections, 10)
            }
            
            return {
                "success": True,
                "report": report
            }
            
        except Exception as e:
            logger.error(f"Failed to generate reflection report: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GENERATE_REPORT_ERROR"
            }
    
    # === 统一接口访问 ===
    
    def get_interface(self) -> ReflectionInterface:
        """获取统一服务接口"""
        return self.interface
    
    # === 辅助方法 ===
    
    def _assess_complexity(self, decision_data: Dict[str, Any], alternatives: List[Dict[str, Any]]) -> str:
        """评估决策复杂度"""
        factors = len(decision_data.get("factors", []))
        alternatives_count = len(alternatives)
        
        if factors > 5 or alternatives_count > 3:
            return "high"
        elif factors > 2 or alternatives_count > 1:
            return "medium"
        else:
            return "low"
    
    def _assess_impact(self, outcome_data: Dict[str, Any]) -> str:
        """评估影响程度"""
        success = outcome_data.get("success", False)
        impact_score = outcome_data.get("impact_score", 0.5)
        
        if not success or impact_score < 0.3:
            return "low"
        elif impact_score < 0.7:
            return "medium"
        else:
            return "high"
    
    def _assess_error_impact(self, impact_data: Dict[str, Any]) -> str:
        """评估错误影响"""
        severity = impact_data.get("severity", "medium")
        
        if severity in ["critical", "high"]:
            return "high"
        elif severity == "medium":
            return "medium"
        else:
            return "low"
    
    def _assess_success_impact(self, success_data: Dict[str, Any]) -> str:
        """评估成功影响"""
        degree = success_data.get("degree", "partial")
        impact_score = success_data.get("impact_score", 0.5)
        
        if degree == "complete" and impact_score > 0.8:
            return "high"
        elif degree == "partial" or impact_score > 0.5:
            return "medium"
        else:
            return "low"
    
    def _build_context_filters(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """基于上下文构建过滤条件"""
        filters = {}
        
        # 基于上下文类型过滤
        context_type = context.get("type")
        if context_type == "decision":
            filters["reflection_type"] = "decision_reflection"
        elif context_type == "error":
            filters["reflection_type"] = "error_reflection"
        elif context_type == "success":
            filters["reflection_type"] = "success_reflection"
        
        # 基于时间范围过滤
        if "time_range" in context:
            time_range = context["time_range"]
            if time_range == "recent":
                # 最近7天
                from datetime import datetime, timezone, timedelta
                start_time = datetime.now(timezone.utc) - timedelta(days=7)
                filters["start_time"] = start_time
        
        # 基于质量过滤
        if "min_quality" in context:
            quality_mapping = {
                "good": ["good", "excellent"],
                "excellent": ["excellent"]
            }
            min_quality = context["min_quality"]
            if min_quality in quality_mapping:
                filters["quality"] = quality_mapping[min_quality]
        
        return filters
    
    def _calculate_relevance(self, reflection: Dict[str, Any], context: Dict[str, Any]) -> float:
        """计算反思与上下文的相关性"""
        score = 0.0
        
        # 主题匹配
        subject = reflection.get("subject", "").lower()
        context_keywords = context.get("keywords", [])
        
        for keyword in context_keywords:
            if keyword.lower() in subject:
                score += 0.3
        
        # 类型匹配
        context_type = context.get("type")
        reflection_type = reflection.get("reflection_type")
        
        type_mapping = {
            "decision": "decision_reflection",
            "error": "error_reflection",
            "success": "success_reflection"
        }
        
        if context_type in type_mapping and reflection_type == type_mapping[context_type]:
            score += 0.4
        
        # 质量加分
        quality = reflection.get("quality")
        if quality == "excellent":
            score += 0.2
        elif quality == "good":
            score += 0.1
        
        # 影响力加分
        impact_score = reflection.get("impact_score", 0)
        score += impact_score * 0.1
        
        return min(score, 1.0)
    
    def _analyze_summary(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析摘要"""
        total = len(reflections)
        
        # 基础统计
        type_counts = {}
        quality_counts = {}
        avg_confidence = 0
        avg_impact = 0
        
        for reflection in reflections:
            # 类型统计
            reflection_type = reflection.get("reflection_type", "unknown")
            type_counts[reflection_type] = type_counts.get(reflection_type, 0) + 1
            
            # 质量统计
            quality = reflection.get("quality", "unknown")
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
            
            # 指标统计
            avg_confidence += reflection.get("confidence", 0)
            avg_impact += reflection.get("impact_score", 0)
        
        if total > 0:
            avg_confidence /= total
            avg_impact /= total
        
        return {
            "total_reflections": total,
            "type_distribution": type_counts,
            "quality_distribution": quality_counts,
            "average_confidence": avg_confidence,
            "average_impact": avg_impact
        }
    
    def _analyze_patterns(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析模式"""
        # 简单的模式分析
        patterns = {
            "common_themes": {},
            "insight_patterns": {},
            "lesson_patterns": {}
        }
        
        for reflection in reflections:
            # 主题模式
            subject = reflection.get("subject", "")
            words = subject.lower().split()
            for word in words:
                if len(word) > 3:
                    patterns["common_themes"][word] = patterns["common_themes"].get(word, 0) + 1
            
            # 洞察模式
            insights = reflection.get("insights", [])
            for insight in insights:
                insight_words = insight.lower().split()
                for word in insight_words:
                    if len(word) > 3:
                        patterns["insight_patterns"][word] = patterns["insight_patterns"].get(word, 0) + 1
            
            # 教训模式
            lessons = reflection.get("lessons", [])
            for lesson in lessons:
                lesson_words = lesson.lower().split()
                for word in lesson_words:
                    if len(word) > 3:
                        patterns["lesson_patterns"][word] = patterns["lesson_patterns"].get(word, 0) + 1
        
        # 排序并限制数量
        for pattern_type in patterns:
            patterns[pattern_type] = dict(
                sorted(patterns[pattern_type].items(), key=lambda x: x[1], reverse=True)[:10]
            )
        
        return patterns
    
    def _analyze_insights(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析洞察"""
        all_insights = []
        
        for reflection in reflections:
            insights = reflection.get("insights", [])
            for insight in insights:
                all_insights.append({
                    "insight": insight,
                    "reflection_id": reflection.get("reflection_id"),
                    "subject": reflection.get("subject"),
                    "confidence": reflection.get("confidence", 0),
                    "impact_score": reflection.get("impact_score", 0)
                })
        
        # 按影响力排序
        all_insights.sort(key=lambda x: (x["impact_score"] + x["confidence"]) / 2, reverse=True)
        
        return {
            "total_insights": len(all_insights),
            "top_insights": all_insights[:20],
            "insight_categories": self._categorize_insights(all_insights)
        }
    
    def _analyze_quality(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析质量"""
        quality_scores = []
        
        for reflection in reflections:
            quality = reflection.get("quality", "fair")
            
            # 转换为数值评分
            quality_score_map = {
                "poor": 0.25,
                "fair": 0.5,
                "good": 0.75,
                "excellent": 1.0
            }
            
            score = quality_score_map.get(quality, 0.5)
            quality_scores.append(score)
        
        if quality_scores:
            avg_quality = sum(quality_scores) / len(quality_scores)
            high_quality_rate = len([s for s in quality_scores if s >= 0.75]) / len(quality_scores)
        else:
            avg_quality = 0
            high_quality_rate = 0
        
        return {
            "average_quality_score": avg_quality,
            "high_quality_rate": high_quality_rate,
            "quality_distribution": {
                "poor": quality_scores.count(0.25),
                "fair": quality_scores.count(0.5),
                "good": quality_scores.count(0.75),
                "excellent": quality_scores.count(1.0)
            }
        }
    
    def _build_learning_pathway(
        self,
        reflections: List[Dict[str, Any]],
        goal: str,
        current_level: str,
        target_level: str
    ) -> List[Dict[str, Any]]:
        """构建学习路径"""
        # 按复杂度和影响力排序
        sorted_reflections = sorted(
            reflections,
            key=lambda x: (x.get("impact_score", 0) + x.get("confidence", 0)) / 2,
            reverse=True
        )
        
        pathway = []
        level_mapping = {
            "beginner": 0,
            "intermediate": 1,
            "advanced": 2
        }
        
        current_level_num = level_mapping.get(current_level, 0)
        target_level_num = level_mapping.get(target_level, 2)
        
        # 选择适合当前水平的反思
        suitable_reflections = []
        for reflection in sorted_reflections:
            # 简单的复杂度判断
            complexity = self._estimate_reflection_complexity(reflection)
            
            if current_level_num <= 0 and complexity in ["low", "medium"]:
                suitable_reflections.append(reflection)
            elif current_level_num == 1 and complexity in ["medium", "high"]:
                suitable_reflections.append(reflection)
            elif current_level_num >= 2 and complexity == "high":
                suitable_reflections.append(reflection)
        
        # 构建路径步骤
        for i, reflection in enumerate(suitable_reflections[:10]):  # 限制步骤数
            pathway.append({
                "step": i + 1,
                "reflection_id": reflection.get("reflection_id"),
                "title": reflection.get("subject"),
                "description": reflection.get("summary"),
                "key_insights": reflection.get("insights", [])[:3],
                "estimated_time": "30 minutes",
                "difficulty": self._estimate_reflection_complexity(reflection)
            })
        
        return pathway
    
    def _estimate_reflection_complexity(self, reflection: Dict[str, Any]) -> str:
        """估算反思复杂度"""
        depth = reflection.get("depth", "analytical")
        insights_count = len(reflection.get("insights", []))
        lessons_count = len(reflection.get("lessons", []))
        
        if depth == "systemic" or insights_count > 5 or lessons_count > 3:
            return "high"
        elif depth == "strategic" or insights_count > 3 or lessons_count > 2:
            return "medium"
        else:
            return "low"
    
    def _convert_to_csv(self, reflections: List[Dict[str, Any]]) -> str:
        """转换为CSV格式"""
        import csv
        import io
        
        output = io.StringIO()
        
        if reflections:
            # CSV表头
            fieldnames = [
                "reflection_id", "subject", "reflection_type", "depth", "quality",
                "confidence", "impact_score", "created_at", "summary"
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            # 写入数据
            for reflection in reflections:
                row = {field: reflection.get(field, "") for field in fieldnames}
                writer.writerow(row)
        
        return output.getvalue()
    
    def _generate_summary_report(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成摘要报告"""
        return self._analyze_summary(reflections)
    
    def _analyze_trends(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析趋势"""
        # 简单的趋势分析
        time_series = {}
        
        for reflection in reflections:
            date = reflection.get("created_at", "")[:10]  # 取日期部分
            if date not in time_series:
                time_series[date] = 0
            time_series[date] += 1
        
        return {
            "time_series": time_series,
            "trend_direction": "increasing" if len(time_series) > 1 else "stable"
        }
    
    def _generate_period_recommendations(self, reflections: List[Dict[str, Any]]) -> List[str]:
        """生成周期性建议"""
        recommendations = []
        
        if not reflections:
            return recommendations
        
        # 基于质量分析
        quality_counts = {}
        for reflection in reflections:
            quality = reflection.get("quality", "fair")
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
        
        total = len(reflections)
        poor_rate = quality_counts.get("poor", 0) / total
        
        if poor_rate > 0.2:
            recommendations.append("建议提高反思质量，重点关注洞察深度和可操作性")
        
        # 基于类型分析
        type_counts = {}
        for reflection in reflections:
            reflection_type = reflection.get("reflection_type", "unknown")
            type_counts[reflection_type] = type_counts.get(reflection_type, 0) + 1
        
        if "error_reflection" not in type_counts:
            recommendations.append("建议增加错误反思，从失败中学习")
        
        # 基于影响力分析
        high_impact_count = len([r for r in reflections if r.get("impact_score", 0) >= 0.8])
        if high_impact_count < total * 0.3:
            recommendations.append("建议关注高影响力事件的反思")
        
        return recommendations
    
    def _extract_top_insights(self, reflections: List[Dict[str, Any]], limit: int) -> List[str]:
        """提取顶级洞察"""
        all_insights = []
        
        for reflection in reflections:
            insights = reflection.get("insights", [])
            confidence = reflection.get("confidence", 0)
            impact = reflection.get("impact_score", 0)
            
            for insight in insights:
                all_insights.append({
                    "insight": insight,
                    "score": (confidence + impact) / 2
                })
        
        # 按评分排序
        all_insights.sort(key=lambda x: x["score"], reverse=True)
        
        return [insight["insight"] for insight in all_insights[:limit]]
    
    def _calculate_average_quality(self, reflections: List[Dict[str, Any]]) -> float:
        """计算平均质量"""
        if not reflections:
            return 0.0
        
        quality_map = {
            "poor": 1,
            "fair": 2,
            "good": 3,
            "excellent": 4
        }
        
        total_score = 0
        for reflection in reflections:
            quality = reflection.get("quality", "fair")
            total_score += quality_map.get(quality, 2)
        
        return total_score / len(reflections)
    
    def _categorize_insights(self, insights: List[Dict[str, Any]]) -> Dict[str, int]:
        """洞察分类统计"""
        categories = {
            "process": 0,
            "decision": 0,
            "learning": 0,
            "improvement": 0,
            "other": 0
        }
        
        for insight_data in insights:
            insight = insight_data["insight"].lower()
            
            if any(keyword in insight for keyword in ["process", "流程", "步骤"]):
                categories["process"] += 1
            elif any(keyword in insight for keyword in ["decision", "决策", "选择"]):
                categories["decision"] += 1
            elif any(keyword in insight for keyword in ["learn", "学习", "经验"]):
                categories["learning"] += 1
            elif any(keyword in insight for keyword in ["improve", "改进", "优化"]):
                categories["improvement"] += 1
            else:
                categories["other"] += 1
        
        return categories
