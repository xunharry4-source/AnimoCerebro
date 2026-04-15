from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from zentex.reflection.models import (
    ReflectionRecord, ReflectionTemplate, ReflectionInsight, 
    ReflectionPattern, ReflectionMetrics, GovernanceStatus
)

logger = logging.getLogger(__name__)

class ReflectionPersistence:
    """
    反思持久化层
    
    负责反思数据的存储、检索、备份和恢复。
    """
    
    def __init__(self, storage_path: str, backup_count: int = 5) -> None:
        """
        初始化持久化层
        
        Args:
            storage_path: 存储路径
            backup_count: 备份数量
        """
        self.storage_path = Path(storage_path)
        self.backup_count = backup_count
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 文件路径
        self.reflections_file = self.storage_path / "reflections.json"
        self.templates_file = self.storage_path / "templates.json"
        self.insights_file = self.storage_path / "insights.json"
        self.patterns_file = self.storage_path / "patterns.json"
        self.metrics_file = self.storage_path / "metrics.json"
        
        logger.info(f"ReflectionPersistence initialized with path: {storage_path}")
    
    def save_reflection(self, reflection: ReflectionRecord) -> bool:
        """保存单个反思记录"""
        try:
            # 加载现有数据
            reflections = self.load_reflections()
            
            # ✅ 关键修复：转换所有对象为字典，不仅仅是新的那个！
            reflections_data = {}
            for reflection_id, ref in reflections.items():
                if isinstance(ref, ReflectionRecord):
                    reflections_data[reflection_id] = ref.model_dump(mode='json')
                else:
                    reflections_data[reflection_id] = ref
            
            # 添加或更新新的反思
            reflections_data[reflection.reflection_id] = reflection.model_dump(mode='json')
            
            # 保存到文件
            return self._save_json(self.reflections_file, reflections_data)
            
        except Exception as e:
            logger.error(f"Failed to save reflection {reflection.reflection_id}: {e}")
            return False
    
    def save_reflections(self, reflections: Dict[str, ReflectionRecord]) -> bool:
        """批量保存反思记录"""
        try:
            # 创建备份
            self._create_backup()
            
            # 转换为字典 - ✅ 使用 mode='json' 确保所有 datetime 被正确序列化
            reflections_data = {
                reflection_id: reflection.model_dump(mode='json')
                for reflection_id, reflection in reflections.items()
            }
            
            return self._save_json(self.reflections_file, reflections_data)
            
        except Exception as e:
            logger.error(f"Failed to save reflections: {e}")
            return False
    
    def load_reflections(self) -> Dict[str, ReflectionRecord]:
        """加载所有反思记录"""
        try:
            data = self._load_json(self.reflections_file, {})
            reflections = {}
            
            # 确保data是字典
            if not isinstance(data, dict):
                logger.warning(f"Invalid data format in reflections file: expected dict, got {type(data)}")
                return reflections
            
            for reflection_id, reflection_data in data.items():
                # 确保reflection_data是字典
                if not isinstance(reflection_data, dict):
                    logger.warning(f"Invalid reflection data format for {reflection_id}: expected dict, got {type(reflection_data)}")
                    continue
                
                # 转换时间字段
                reflection_data = self._convert_datetime_fields(reflection_data)
                
                try:
                    reflections[reflection_id] = ReflectionRecord(**reflection_data)
                except Exception as e:
                    logger.warning(f"Failed to create ReflectionRecord for {reflection_id}: {e}")
                    continue
            
            return reflections
            
        except Exception as e:
            logger.error(f"Failed to load reflections: {e}")
            return {}
    
    def get_reflection(self, reflection_id: str) -> Optional[ReflectionRecord]:
        """获取单个反思记录"""
        reflections = self.load_reflections()
        return reflections.get(reflection_id)
    
    def delete_reflection(self, reflection_id: str) -> bool:
        """删除反思记录"""
        try:
            reflections = self.load_reflections()
            
            if reflection_id not in reflections:
                return False
            
            del reflections[reflection_id]
            return self.save_reflections(reflections)
            
        except Exception as e:
            logger.error(f"Failed to delete reflection {reflection_id}: {e}")
            return False
    
    # 模板相关
    def save_template(self, template: ReflectionTemplate) -> bool:
        """保存反思模板"""
        try:
            templates = self.load_templates()
            
            # ✅ 转换所有对象为字典
            templates_data = {}
            for template_id, tpl in templates.items():
                if isinstance(tpl, ReflectionTemplate):
                    templates_data[template_id] = tpl.model_dump(mode='json')
                else:
                    templates_data[template_id] = tpl
            
            templates_data[template.template_id] = template.model_dump(mode='json')
            return self._save_json(self.templates_file, templates_data)
            
        except Exception as e:
            logger.error(f"Failed to save template {template.template_id}: {e}")
            return False
    
    def load_templates(self) -> Dict[str, ReflectionTemplate]:
        """加载所有模板"""
        try:
            data = self._load_json(self.templates_file, {})
            templates = {}
            
            for template_id, template_data in data.items():
                if isinstance(template_data, dict):
                    template_data = self._convert_datetime_fields(template_data)
                    templates[template_id] = ReflectionTemplate(**template_data)
            
            return templates
            
        except Exception as e:
            logger.error(f"Failed to load templates: {e}")
            return {}
    
    def get_template(self, template_id: str) -> Optional[ReflectionTemplate]:
        """获取单个模板"""
        templates = self.load_templates()
        return templates.get(template_id)
    
    # 洞察相关
    def save_insight(self, insight: ReflectionInsight) -> bool:
        """保存反思洞察"""
        try:
            insights = self.load_insights()
            
            # ✅ 转换所有对象为字典
            insights_data = {}
            for insight_id, ins in insights.items():
                if isinstance(ins, ReflectionInsight):
                    insights_data[insight_id] = ins.model_dump(mode='json')
                else:
                    insights_data[insight_id] = ins
            
            insights_data[insight.insight_id] = insight.model_dump(mode='json')
            return self._save_json(self.insights_file, insights_data)
            
        except Exception as e:
            logger.error(f"Failed to save insight {insight.insight_id}: {e}")
            return False
    
    def load_insights(self) -> Dict[str, ReflectionInsight]:
        """加载所有洞察"""
        try:
            data = self._load_json(self.insights_file, {})
            insights = {}
            
            for insight_id, insight_data in data.items():
                insight_data = self._convert_datetime_fields(insight_data)
                insights[insight_id] = ReflectionInsight(**insight_data)
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to load insights: {e}")
            return {}
    
    # 模式相关
    def save_pattern(self, pattern: ReflectionPattern) -> bool:
        """保存反思模式"""
        try:
            patterns = self.load_patterns()
            
            # ✅ 转换所有对象为字典
            patterns_data = {}
            for pattern_id, pat in patterns.items():
                if isinstance(pat, ReflectionPattern):
                    patterns_data[pattern_id] = pat.model_dump(mode='json')
                else:
                    patterns_data[pattern_id] = pat
            
            patterns_data[pattern.pattern_id] = pattern.model_dump(mode='json')
            return self._save_json(self.patterns_file, patterns_data)
            
        except Exception as e:
            logger.error(f"Failed to save pattern {pattern.pattern_id}: {e}")
            return False
    
    def load_patterns(self) -> Dict[str, ReflectionPattern]:
        """加载所有模式"""
        try:
            data = self._load_json(self.patterns_file, {})
            patterns = {}
            
            for pattern_id, pattern_data in data.items():
                pattern_data = self._convert_datetime_fields(pattern_data)
                patterns[pattern_id] = ReflectionPattern(**pattern_data)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Failed to load patterns: {e}")
            return {}
    
    # 指标相关
    def save_metrics(self, metrics: ReflectionMetrics) -> bool:
        """保存反思指标"""
        try:
            return self._save_json(self.metrics_file, metrics.model_dump(mode='json'))
            
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
            return False
    
    def load_metrics(self) -> Optional[ReflectionMetrics]:
        """加载反思指标"""
        try:
            data = self._load_json(self.metrics_file, {})
            if not data:
                return ReflectionMetrics()
            
            data = self._convert_datetime_fields(data)
            return ReflectionMetrics(**data)
            
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
            return ReflectionMetrics()
    
    # 查询方法
    def query_reflections(self, filters: Dict[str, Any]) -> List[ReflectionRecord]:
        """查询反思记录"""
        reflections = self.load_reflections()
        filtered_reflections = []
        
        for reflection in reflections.values():
            if self._matches_filters(reflection, filters):
                filtered_reflections.append(reflection)
        
        return filtered_reflections
    
    def _matches_filters(self, reflection: ReflectionRecord, filters: Dict[str, Any]) -> bool:
        """检查反思是否匹配过滤条件"""
        # 类型过滤
        if "reflection_type" in filters:
            if reflection.reflection_type != filters["reflection_type"]:
                return False
        
        # 深度过滤
        if "depth" in filters:
            if reflection.depth != filters["depth"]:
                return False
        
        # 质量过滤
        if "quality" in filters:
            if reflection.quality != filters["quality"]:
                return False
        
        # 治理状态过滤
        if "governance_status" in filters:
            if reflection.governance_status != filters["governance_status"]:
                return False
        
        # 时间范围过滤
        if "start_time" in filters:
            if reflection.created_at < filters["start_time"]:
                return False
        
        if "end_time" in filters:
            if reflection.created_at > filters["end_time"]:
                return False
        
        # 标签过滤
        if "tags" in filters:
            required_tags = set(filters["tags"])
            if not required_tags.issubset(set(reflection.tags)):
                return False
        
        # 置信度过滤
        if "min_confidence" in filters:
            if reflection.confidence < filters["min_confidence"]:
                return False
        
        # 影响评分过滤
        if "min_impact_score" in filters:
            if reflection.impact_score < filters["min_impact_score"]:
                return False
        
        return True
    
    # 备份和恢复
    def _create_backup(self) -> None:
        """创建备份"""
        import shutil
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.storage_path / f"backup_{timestamp}"
        backup_dir.mkdir(exist_ok=True)
        
        files_to_backup = [
            self.reflections_file,
            self.templates_file,
            self.insights_file,
            self.patterns_file,
            self.metrics_file
        ]
        
        for file_path in files_to_backup:
            if file_path.exists():
                shutil.copy2(file_path, backup_dir / file_path.name)
        
        # 清理旧备份
        self._cleanup_old_backups()
    
    def _cleanup_old_backups(self) -> None:
        """清理旧备份"""
        import shutil
        
        backup_dirs = sorted(
            [d for d in self.storage_path.iterdir() if d.is_dir() and d.name.startswith('backup_')],
            key=lambda x: x.name,
            reverse=True
        )
        
        for old_backup in backup_dirs[self.backup_count:]:
            shutil.rmtree(old_backup)
    
    def restore_from_backup(self, backup_timestamp: str) -> bool:
        """从备份恢复"""
        import shutil
        
        backup_dir = self.storage_path / f"backup_{backup_timestamp}"
        if not backup_dir.exists():
            logger.error(f"Backup directory not found: {backup_timestamp}")
            return False
        
        try:
            for backup_file in backup_dir.iterdir():
                target_file = self.storage_path / backup_file.name
                shutil.copy2(backup_file, target_file)
            
            logger.info(f"Successfully restored from backup: {backup_timestamp}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")
            return False
    
    # 辅助方法
    def _save_json(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """
        原子方式保存JSON数据 (write-then-move 模式)
        
        优点:
        1. 防止部分写入导致的文件损坏
        2. 原子性操作 - 要么完全成功，要么完全失败
        3. 文件丢失或损坏概率极低
        """
        import os
        import tempfile
        
        try:
            # 1. 写入到临时文件
            temp_fd, temp_path = tempfile.mkstemp(
                suffix='.json',
                prefix=f'.{file_path.name}.',
                dir=file_path.parent,
                text=True
            )
            
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    # ✅ 移除 default=str，因为所有日期已通过 model_dump(mode='json') 转换
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # 2. 原子地移动临时文件到目标位置 (write-then-move)
                # 在 POSIX 系统上，os.replace() 是原子操作
                os.replace(temp_path, str(file_path))
                
                logger.debug(f"Successfully saved JSON to {file_path}")
                return True
                
            except Exception as write_error:
                # 清理临时文件
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                raise write_error
        
        except TypeError as e:
            logger.error(f"JSON serialization error for {file_path}: {e}")
            # 提供调试信息
            logger.debug(f"Data sample: {str(data)[:500]}")
            return False
        except Exception as e:
            logger.error(f"Failed to save JSON to {file_path}: {e}")
            return False
    
    def _load_json(self, file_path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        """
        安全加载JSON数据，并支持从损坏文件恢复
        """
        import shutil
        
        if not file_path.exists():
            return default
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except json.JSONDecodeError as e:
            logger.warning(f"JSON file corrupted at {file_path}: {e}")
            
            # 尝试从备份恢复
            backup_dirs = sorted(
                [d for d in self.storage_path.iterdir() if d.is_dir() and d.name.startswith('backup_')],
                key=lambda x: x.name,
                reverse=True
            )
            
            for backup_dir in backup_dirs:
                backup_file = backup_dir / file_path.name
                if backup_file.exists():
                    try:
                        logger.info(f"Attempting to recover from backup: {backup_file}")
                        with open(backup_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 恢复成功 - 恢复到主文件
                        shutil.copy2(backup_file, file_path)
                        logger.info(f"Successfully recovered {file_path} from backup")
                        return data
                    except Exception as recovery_error:
                        logger.warning(f"Failed to recover from backup {backup_file}: {recovery_error}")
                        continue
            
            # 如果无法从备份恢复，删除损坏的文件并返回默认值
            logger.error(f"Cannot recover from backup, removing corrupted file: {file_path}")
            try:
                file_path.unlink()
            except:
                pass
            
            return default
        
        except Exception as e:
            logger.error(f"Failed to load JSON from {file_path}: {e}")
            return default
    
    def _convert_datetime_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """转换日期时间字段"""
        datetime_fields = [
            'created_at', 'updated_at', 'reflection_timestamp', 'verified_at',
            'expires_at', 'last_updated', 'calculated_at'
        ]
        
        for field in datetime_fields:
            if field in data and data[field]:
                if isinstance(data[field], str):
                    try:
                        data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # 如果解析失败，保持原样
                        pass
        
        return data
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        stats = {
            "storage_path": str(self.storage_path),
            "files_exist": {
                "reflections": self.reflections_file.exists(),
                "templates": self.templates_file.exists(),
                "insights": self.insights_file.exists(),
                "patterns": self.patterns_file.exists(),
                "metrics": self.metrics_file.exists()
            },
            "file_sizes": {},
            "backup_count": len([d for d in self.storage_path.iterdir() 
                                if d.is_dir() and d.name.startswith('backup_')])
        }
        
        # 文件大小
        for file_path in [self.reflections_file, self.templates_file, 
                         self.insights_file, self.patterns_file, self.metrics_file]:
            if file_path.exists():
                stats["file_sizes"][file_path.stem] = file_path.stat().st_size
        
        return stats
