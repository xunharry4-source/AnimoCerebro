from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentex.reflection.models import (
    ReflectionRecord, ReflectionType, ReflectionDepth, 
    ReflectionQuality, ReflectionTrigger, GovernanceStatus
)
from zentex.reflection.service import ReflectionService
from zentex.reflection.errors import ReflectionError

logger = logging.getLogger(__name__)

class ReflectionInterface:
    """
    反思模块统一对外服务接口
    
    提供标准化的反思管理服务，供其他模块安全接入。
    所有操作都经过验证、审计和错误处理。
    """
    
    def __init__(self, reflection_service: ReflectionService) -> None:
        """
        初始化反思接口
        
        Args:
            reflection_service: 反思服务实例
        """
        self._service = reflection_service
        self._interface_name = "ReflectionInterface"
        logger.info(f"{self._interface_name} initialized")
    
    # === 反思生成 ===
    
    def generate_reflection(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成反思记录
        
        Args:
            request: 反思生成请求
            
        Returns:
            生成结果
        """
        try:
            # 验证必需字段
            required_fields = ["subject", "reflection_type", "context"]
            for field in required_fields:
                if field not in request:
                    return {
                        "success": False,
                        "error": f"Missing required field: {field}",
                        "error_code": "MISSING_FIELD"
                    }
            
            # 验证反思类型
            try:
                reflection_type = ReflectionType(request["reflection_type"])
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid reflection type: {request['reflection_type']}",
                    "error_code": "INVALID_REFLECTION_TYPE"
                }
            
            # 验证触发器
            trigger = request.get("trigger", "automatic")
            try:
                trigger = ReflectionTrigger(trigger)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid trigger: {trigger}",
                    "error_code": "INVALID_TRIGGER"
                }
            
            # 生成反思
            reflection = self._service.generate_reflection(
                subject=request["subject"],
                reflection_type=reflection_type,
                context=request["context"],
                trigger=trigger,
                trace_id=request.get("trace_id"),
                session_id=request.get("session_id"),
                template_id=request.get("template_id")
            )
            
            return {
                "success": True,
                "reflection": reflection.model_dump(),
                "message": f"Reflection generated successfully: {reflection.reflection_id}"
            }
            
        except ReflectionError as e:
            logger.error(f"Reflection generation error: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "REFLECTION_GENERATION_ERROR"
            }
        except Exception as e:
            logger.error(f"Unexpected error in reflection generation: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "UNEXPECTED_ERROR"
            }
    
    # === 反思查询 ===
    
    def get_reflection(self, reflection_id: str) -> Dict[str, Any]:
        """
        获取反思记录
        
        Args:
            reflection_id: 反思ID
            
        Returns:
            反思记录或错误
        """
        try:
            reflection = self._service.get_reflection(reflection_id)
            
            return {
                "success": True,
                "reflection": reflection.model_dump()
            }
            
        except ReflectionError as e:
            logger.error(f"Failed to get reflection {reflection_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "REFLECTION_NOT_FOUND"
            }
        except Exception as e:
            logger.error(f"Unexpected error getting reflection: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "UNEXPECTED_ERROR"
            }
    
    def list_reflections(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        列出反思记录
        
        Args:
            filters: 过滤条件
            
        Returns:
            反思列表
        """
        try:
            reflections = self._service.list_reflections(filters)
            
            return {
                "success": True,
                "reflections": [reflection.model_dump() for reflection in reflections],
                "count": len(reflections)
            }
            
        except Exception as e:
            logger.error(f"Failed to list reflections: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "LIST_REFLECTIONS_ERROR"
            }
    
    def search_reflections(self, query: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        搜索反思记录
        
        Args:
            query: 搜索查询
            filters: 过滤条件
            
        Returns:
            搜索结果
        """
        try:
            reflections = self._service.list_reflections(filters)
            
            # 简单的文本搜索
            query_lower = query.lower()
            matched_reflections = []
            
            for reflection in reflections:
                # 在主题、摘要、洞察中搜索
                searchable_text = (
                    reflection.subject.lower() + " " +
                    reflection.summary.lower() + " " +
                    " ".join(insight.lower() for insight in reflection.insights) + " " +
                    " ".join(lesson.lower() for lesson in reflection.lessons)
                )
                
                if query_lower in searchable_text:
                    matched_reflections.append(reflection)
            
            return {
                "success": True,
                "reflections": [reflection.model_dump() for reflection in matched_reflections],
                "count": len(matched_reflections),
                "query": query
            }
            
        except Exception as e:
            logger.error(f"Failed to search reflections: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "SEARCH_REFLECTIONS_ERROR"
            }
    
    # === 反思更新 ===
    
    def update_reflection(self, reflection_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新反思记录
        
        Args:
            reflection_id: 反思ID
            updates: 更新内容
            
        Returns:
            更新结果
        """
        try:
            reflection = self._service.update_reflection(reflection_id, updates)
            
            return {
                "success": True,
                "reflection": reflection.model_dump(),
                "message": f"Reflection updated successfully: {reflection_id}"
            }
            
        except ReflectionError as e:
            logger.error(f"Failed to update reflection {reflection_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "UPDATE_REFLECTION_ERROR"
            }
        except Exception as e:
            logger.error(f"Unexpected error updating reflection: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "UNEXPECTED_ERROR"
            }
    
    def delete_reflection(self, reflection_id: str) -> Dict[str, Any]:
        """
        删除反思记录
        
        Args:
            reflection_id: 反思ID
            
        Returns:
            删除结果
        """
        try:
            success = self._service.delete_reflection(reflection_id)
            
            if success:
                return {
                    "success": True,
                    "message": f"Reflection deleted successfully: {reflection_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "Reflection not found or deletion failed",
                    "error_code": "DELETE_REFLECTION_ERROR"
                }
                
        except Exception as e:
            logger.error(f"Failed to delete reflection {reflection_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "DELETE_REFLECTION_ERROR"
            }
    
    # === 反思治理 ===
    
    def verify_reflection(self, reflection_id: str, verified_by: str) -> Dict[str, Any]:
        """
        验证反思
        
        Args:
            reflection_id: 反思ID
            verified_by: 验证者
            
        Returns:
            验证结果
        """
        try:
            reflection = self._service.verify_reflection(reflection_id, verified_by)
            
            return {
                "success": True,
                "reflection": reflection.model_dump(),
                "message": f"Reflection verified successfully: {reflection_id}"
            }
            
        except ReflectionError as e:
            logger.error(f"Failed to verify reflection {reflection_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "VERIFY_REFLECTION_ERROR"
            }
    
    def mark_suspect(self, reflection_id: str, reason: str) -> Dict[str, Any]:
        """
        标记反思为可疑
        
        Args:
            reflection_id: 反思ID
            reason: 可疑原因
            
        Returns:
            标记结果
        """
        try:
            reflection = self._service.mark_suspect(reflection_id, reason)
            
            return {
                "success": True,
                "reflection": reflection.model_dump(),
                "message": f"Reflection marked as suspect: {reflection_id}"
            }
            
        except ReflectionError as e:
            logger.error(f"Failed to mark reflection as suspect {reflection_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "MARK_SUSPECT_ERROR"
            }
    
    def archive_reflection(self, reflection_id: str) -> Dict[str, Any]:
        """
        归档反思
        
        Args:
            reflection_id: 反思ID
            
        Returns:
            归档结果
        """
        try:
            reflection = self._service.archive_reflection(reflection_id)
            
            return {
                "success": True,
                "reflection": reflection.model_dump(),
                "message": f"Reflection archived successfully: {reflection_id}"
            }
            
        except ReflectionError as e:
            logger.error(f"Failed to archive reflection {reflection_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "ARCHIVE_REFLECTION_ERROR"
            }
    
    def batch_governance(self, reflection_ids: List[str], action: str, **kwargs) -> Dict[str, Any]:
        """
        批量治理操作
        
        Args:
            reflection_ids: 反思ID列表
            action: 治理动作 (verify/suspect/archive)
            **kwargs: 动作参数
            
        Returns:
            批量操作结果
        """
        try:
            results = {"success": [], "failed": []}
            
            for reflection_id in reflection_ids:
                try:
                    if action == "verify":
                        verified_by = kwargs.get("verified_by", "system")
                        reflection = self._service.verify_reflection(reflection_id, verified_by)
                        results["success"].append({
                            "reflection_id": reflection_id,
                            "action": "verified",
                            "verified_by": verified_by
                        })
                    elif action == "suspect":
                        reason = kwargs.get("reason", "Batch marked as suspect")
                        reflection = self._service.mark_suspect(reflection_id, reason)
                        results["success"].append({
                            "reflection_id": reflection_id,
                            "action": "suspect",
                            "reason": reason
                        })
                    elif action == "archive":
                        reflection = self._service.archive_reflection(reflection_id)
                        results["success"].append({
                            "reflection_id": reflection_id,
                            "action": "archived"
                        })
                    else:
                        results["failed"].append({
                            "reflection_id": reflection_id,
                            "error": f"Unknown action: {action}"
                        })
                        
                except Exception as e:
                    results["failed"].append({
                        "reflection_id": reflection_id,
                        "error": str(e)
                    })
            
            return {
                "success": True,
                "results": results,
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "message": f"Batch {action} completed: {len(results['success'])} success, {len(results['failed'])} failed"
            }
            
        except Exception as e:
            logger.error(f"Failed to perform batch governance: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "BATCH_GOVERNANCE_ERROR"
            }
    
    # === 模板管理 ===
    
    def create_template(self, name: str, description: str, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建反思模板
        
        Args:
            name: 模板名称
            description: 模板描述
            template_data: 模板数据
            
        Returns:
            创建结果
        """
        try:
            template = self._service.create_template(name, description, template_data)
            
            return {
                "success": True,
                "template": template.model_dump(),
                "message": f"Template created successfully: {template.template_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to create template: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "CREATE_TEMPLATE_ERROR"
            }
    
    def get_template(self, template_id: str) -> Dict[str, Any]:
        """
        获取模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板信息
        """
        try:
            template = self._service.get_template(template_id)
            
            if template:
                return {
                    "success": True,
                    "template": template.model_dump()
                }
            else:
                return {
                    "success": False,
                    "error": f"Template not found: {template_id}",
                    "error_code": "TEMPLATE_NOT_FOUND"
                }
                
        except Exception as e:
            logger.error(f"Failed to get template {template_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_TEMPLATE_ERROR"
            }
    
    def list_templates(self) -> Dict[str, Any]:
        """
        列出所有模板
        
        Returns:
            模板列表
        """
        try:
            templates = self._service.list_templates()
            
            return {
                "success": True,
                "templates": [template.model_dump() for template in templates],
                "count": len(templates)
            }
            
        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "LIST_TEMPLATES_ERROR"
            }
    
    # === 统计分析 ===
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        获取反思指标
        
        Returns:
            指标数据
        """
        try:
            metrics = self._service.get_metrics()
            
            return {
                "success": True,
                "metrics": metrics.model_dump()
            }
            
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_METRICS_ERROR"
            }
    
    def get_reflection_statistics(self) -> Dict[str, Any]:
        """
        获取反思统计信息
        
        Returns:
            统计信息
        """
        try:
            metrics = self._service.get_metrics()
            
            # 计算额外统计
            reflections = self._service.list_reflections()
            
            # 按时间分布统计
            time_distribution = {}
            for reflection in reflections:
                date_key = reflection.created_at.strftime("%Y-%m-%d")
                time_distribution[date_key] = time_distribution.get(date_key, 0) + 1
            
            # 按质量分布统计
            quality_stats = {}
            for reflection in reflections:
                quality = reflection.quality.value
                quality_stats[quality] = quality_stats.get(quality, 0) + 1
            
            # 高质量反思（优秀+良好）
            high_quality_count = sum(
                1 for r in reflections 
                if r.quality in [ReflectionQuality.EXCELLENT, ReflectionQuality.GOOD]
            )
            
            # 可操作性高的反思
            high_actionability_count = sum(
                1 for r in reflections 
                if r.actionability >= 0.7
            )
            
            statistics = {
                "basic_metrics": metrics.model_dump(),
                "time_distribution": time_distribution,
                "quality_distribution": quality_stats,
                "high_quality_rate": high_quality_count / len(reflections) if reflections else 0,
                "high_actionability_rate": high_actionability_count / len(reflections) if reflections else 0,
                "average_insights_per_reflection": sum(len(r.insights) for r in reflections) / len(reflections) if reflections else 0,
                "average_lessons_per_reflection": sum(len(r.lessons) for r in reflections) / len(reflections) if reflections else 0
            }
            
            return {
                "success": True,
                "statistics": statistics
            }
            
        except Exception as e:
            logger.error(f"Failed to get reflection statistics: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_STATISTICS_ERROR"
            }
    
    # === 高级分析 ===
    
    def analyze_reflection_patterns(self) -> Dict[str, Any]:
        """
        分析反思模式
        
        Returns:
            模式分析结果
        """
        try:
            reflections = self._service.list_reflections()
            
            # 按类型分析模式
            type_patterns = {}
            for reflection in reflections:
                reflection_type = reflection.reflection_type.value
                
                if reflection_type not in type_patterns:
                    type_patterns[reflection_type] = {
                        "count": 0,
                        "average_confidence": 0,
                        "average_impact": 0,
                        "common_themes": {},
                        "quality_distribution": {}
                    }
                
                pattern = type_patterns[reflection_type]
                pattern["count"] += 1
                pattern["average_confidence"] += reflection.confidence
                pattern["average_impact"] += reflection.impact_score
                
                # 质量分布
                quality = reflection.quality.value
                pattern["quality_distribution"][quality] = pattern["quality_distribution"].get(quality, 0) + 1
                
                # 主题分析（简单关键词提取）
                words = reflection.subject.lower().split()
                for word in words:
                    if len(word) > 3:  # 忽略短词
                        pattern["common_themes"][word] = pattern["common_themes"].get(word, 0) + 1
            
            # 计算平均值
            for pattern in type_patterns.values():
                if pattern["count"] > 0:
                    pattern["average_confidence"] /= pattern["count"]
                    pattern["average_impact"] /= pattern["count"]
                
                # 排序主题
                pattern["common_themes"] = dict(
                    sorted(pattern["common_themes"].items(), key=lambda x: x[1], reverse=True)[:10]
                )
            
            return {
                "success": True,
                "patterns": type_patterns,
                "total_reflections_analyzed": len(reflections)
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze reflection patterns: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "ANALYZE_PATTERNS_ERROR"
            }
    
    def get_reflection_recommendations(self, limit: int = 10) -> Dict[str, Any]:
        """
        获取反思推荐
        
        Args:
            limit: 推荐数量限制
            
        Returns:
            推荐列表
        """
        try:
            reflections = self._service.list_reflections()
            
            # 筛选高质量、高影响力的反思
            high_quality_reflections = [
                r for r in reflections 
                if (r.quality in [ReflectionQuality.EXCELLENT, ReflectionQuality.GOOD] and
                    r.impact_score >= 0.7 and
                    r.actionability >= 0.6 and
                    r.governance_status == GovernanceStatus.VERIFIED)
            ]
            
            # 按影响评分和置信度排序
            sorted_reflections = sorted(
                high_quality_reflections,
                key=lambda r: (r.impact_score + r.confidence) / 2,
                reverse=True
            )
            
            recommendations = []
            for reflection in sorted_reflections[:limit]:
                recommendations.append({
                    "reflection_id": reflection.reflection_id,
                    "subject": reflection.subject,
                    "summary": reflection.summary,
                    "key_insights": reflection.insights[:3],  # 前3个洞察
                    "key_lessons": reflection.lessons[:2],  # 前2个教训
                    "impact_score": reflection.impact_score,
                    "confidence": reflection.confidence,
                    "created_at": reflection.created_at.isoformat()
                })
            
            return {
                "success": True,
                "recommendations": recommendations,
                "count": len(recommendations)
            }
            
        except Exception as e:
            logger.error(f"Failed to get reflection recommendations: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_code": "GET_RECOMMENDATIONS_ERROR"
            }
