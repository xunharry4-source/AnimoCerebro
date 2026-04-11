"""
G19 - 用户偏好辨析与意图对齐 - 攻击样本标记器

负责标记恶意信号、存储攻击样本、检测同类攻击。
"""

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .preference_models import AttackMatch, AttackSample, ExtremeSignalRecord
from .preference_storage import PreferenceStore


class AttackSampleMarker:
    """攻击样本标记器"""

    def __init__(self, store: Optional[PreferenceStore] = None):
        """
        初始化攻击样本标记器
        
        Args:
            store: 偏好存储实例
        """
        self.store = store or PreferenceStore()

    async def mark_malicious_signal(
        self,
        signal_record: ExtremeSignalRecord,
        attack_type: str,
        confidence: float,
        analyst_id: Optional[str] = None
    ) -> AttackSample:
        """
        标记恶意信号
        
        Args:
            signal_record: 极端信号记录
            attack_type: 攻击类型 (injection / spoofing / manipulation / other)
            confidence: 置信度
            analyst_id: 分析师 ID（如果是人工标记）
            
        Returns:
            AttackSample: 攻击样本对象
        """
        # 计算信号内容哈希（保护隐私）
        signal_hash = hashlib.sha256(signal_record.signal_content.encode()).hexdigest()
        
        # 生成模式签名（简化实现：使用哈希作为签名）
        pattern_signature = signal_hash
        
        # 创建攻击样本
        sample = AttackSample(
            sample_id=f"atk_{uuid.uuid4().hex[:8]}",
            signal_content_hash=signal_hash,
            attack_type=attack_type,
            risk_indicators=signal_record.risk_indicators,
            confidence=confidence,
            marked_at=datetime.utcnow(),
            marked_by=analyst_id or "auto",
            pattern_signature=pattern_signature,
            metadata={
                "original_signal_record_id": signal_record.record_id,
                "signal_source": signal_record.signal_source,
                "risk_score": signal_record.risk_score
            }
        )
        
        # 保存到数据库
        await self.store.save_attack_sample(sample)
        
        # 更新原始信号记录的恶意标记
        signal_record.is_malicious = True
        
        return sample

    async def store_attack_sample(self, sample: AttackSample) -> str:
        """
        存储攻击样本到数据库
        
        Args:
            sample: 攻击样本
            
        Returns:
            sample_id: 样本 ID
        """
        return await self.store.save_attack_sample(sample)

    async def detect_similar_attack(
        self,
        new_signal: str,
        similarity_threshold: float = 0.85
    ) -> Optional[AttackMatch]:
        """
        检测同类攻击模式
        
        Args:
            new_signal: 新信号内容
            similarity_threshold: 相似度阈值
            
        Returns:
            AttackMatch: 如果匹配到已知攻击，返回匹配结果；否则返回 None
        """
        # 查找相似的已知攻击
        matched_sample = await self.store.find_similar_attack(
            signal_content=new_signal,
            similarity_threshold=similarity_threshold
        )
        
        if matched_sample:
            return AttackMatch(
                matched_sample_id=matched_sample.sample_id,
                similarity_score=1.0,  # 简化实现：完全匹配时相似度为 1.0
                attack_type=matched_sample.attack_type,
                confidence=matched_sample.confidence
            )
        
        return None

    async def query_attack_history(
        self,
        attack_type_filter: Optional[str] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: int = 50
    ) -> List[AttackSample]:
        """
        查询攻击历史
        
        Args:
            attack_type_filter: 攻击类型过滤
            time_range: 时间范围
            limit: 返回数量限制
            
        Returns:
            攻击样本列表
        """
        # 简化实现：返回空列表
        # 实际应从数据库查询，这里需要扩展 PreferenceStore 添加查询方法
        return []

    async def get_attack_statistics(self) -> Dict[str, Any]:
        """
        获取攻击统计信息
        
        Returns:
            统计信息字典
        """
        # 简化实现：返回模拟统计数据
        return {
            "total_samples": 0,
            "by_type": {},
            "recent_attacks_24h": 0,
            "high_confidence_samples": 0
        }
