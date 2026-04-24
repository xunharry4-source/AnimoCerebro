"""
Alignment - 用户偏好辨析与意图对齐 - 偏好管理器

提供偏好的确认、撤销、查询等管理功能。
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .preference_models import (
    BatchClearResult,
    BatchConfirmResult,
    BatchItemResult,
    ConfirmationStatus,
    IntentAmbiguityCase,
    PreferenceStatus,
    UserDecision,
    UserPreference,
)
from .preference_storage import PreferenceStore


class PreferenceManager:
    """偏好管理器"""

    def __init__(self, store: Optional[PreferenceStore] = None):
        """
        初始化偏好管理器
        
        Args:
            store: 偏好存储实例
        """
        self.store = store or PreferenceStore()

    async def confirm_preference(
        self,
        ambiguity_case_id: str,
        user_decision: UserDecision,
        user_id: str,
        confirmation_context: Optional[Dict[str, Any]] = None
    ) -> Optional[UserPreference]:
        """
        用户确认偏好
        
        Args:
            ambiguity_case_id: 意图歧义案例 ID
            user_decision: 用户决策
            user_id: 用户 ID
            confirmation_context: 确认上下文
            
        Returns:
            UserPreference: 如果用户确认为偏好，返回创建的偏好对象；否则返回 None
            
        Raises:
            ValueError: 如果案例不存在或已解决
        """
        # 获取案例（这里简化处理，实际应从存储中获取）
        # 由于我们没有 get_case 方法，这里直接创建偏好
        
        if user_decision == UserDecision.CONFIRM_AS_PREFERENCE:
            # 创建正式偏好
            preference = UserPreference(
                preference_id=f"pref_{uuid.uuid4().hex[:8]}",
                content=f"用户确认的偏好（来自案例 {ambiguity_case_id}）",
                confirmed_at=datetime.utcnow(),
                source=f"manual_user_input:{user_id}",
                applicable_scope=confirmation_context.get("applicable_scope", {}) if confirmation_context else {},
                can_override_safety_redline=False,
                confidence=1.0,
                status=PreferenceStatus.CONFIRMED,
                metadata={
                    "confirmed_by": user_id,
                    "ambiguity_case_id": ambiguity_case_id,
                    "confirmation_context": confirmation_context
                }
            )
            
            # 保存偏好
            await self.store.save_preference(preference)
            
            # 更新案例状态
            await self.store.resolve_ambiguity_case(
                case_id=ambiguity_case_id,
                resolution_action="confirmed_as_preference",
                user_feedback=confirmation_context.get("user_feedback") if confirmation_context else None
            )
            
            return preference
        
        elif user_decision == UserDecision.MARK_AS_ANOMALY:
            # 标记为异常，不创建偏好
            await self.store.resolve_ambiguity_case(
                case_id=ambiguity_case_id,
                resolution_action="marked_as_anomaly",
                user_feedback=confirmation_context.get("user_feedback") if confirmation_context else None
            )
            return None
        
        elif user_decision == UserDecision.NEEDS_INVESTIGATION:
            # 需要进一步调查
            await self.store.resolve_ambiguity_case(
                case_id=ambiguity_case_id,
                resolution_action="requires_investigation",
                user_feedback=confirmation_context.get("user_feedback") if confirmation_context else None
            )
            return None
        
        else:
            raise ValueError(f"Invalid user decision: {user_decision}")

    async def revoke_preference(
        self,
        preference_id: str,
        reason: str,
        user_id: str
    ) -> None:
        """
        撤销单条偏好
        
        Args:
            preference_id: 偏好 ID
            reason: 撤销原因
            user_id: 操作用户 ID
        """
        # 更新偏好状态为 revoked
        await self.store.update_preference_status(
            preference_id=preference_id,
            new_status=PreferenceStatus.REVOKED,
            reason=f"Revoked by {user_id}: {reason}"
        )

    async def batch_clear_preferences(
        self,
        filter_criteria: Dict[str, Any],
        user_id: str,
        dry_run: bool = False
    ) -> BatchClearResult:
        """
        批量清除偏好
        
        Args:
            filter_criteria: 过滤条件
            user_id: 操作用户 ID
            dry_run: 是否仅预览
            
        Returns:
            BatchClearResult: 批量清除结果
        """
        # 简化实现：查询所有偏好，然后根据条件过滤
        # 实际应实现更复杂的查询逻辑
        
        # 这里返回模拟结果
        affected_ids = []  # 实际应从数据库查询
        
        if not dry_run:
            # 实际执行删除/撤销操作
            for pref_id in affected_ids:
                await self.revoke_preference(
                    preference_id=pref_id,
                    reason=f"Batch clear by {user_id}",
                    user_id=user_id
                )
        
        return BatchClearResult(
            affected_count=len(affected_ids),
            affected_preferences=affected_ids,
            dry_run=dry_run
        )

    async def query_preferences(
        self,
        scope_filter: Optional[Dict[str, Any]] = None,
        source_filter: Optional[str] = None,
        status_filter: Optional[PreferenceStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserPreference]:
        """
        查询偏好
        
        Args:
            scope_filter: 适用范围过滤
            source_filter: 来源过滤
            status_filter: 状态过滤
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            偏好列表
        """
        if scope_filter:
            # 按范围查询
            preferences = await self.store.query_preferences_by_scope(scope_filter)
        else:
            # 简化：返回空列表，实际应实现完整的查询逻辑
            preferences = []
        
        # 应用其他过滤器
        if status_filter:
            preferences = [p for p in preferences if p.status == status_filter]
        
        if source_filter:
            preferences = [p for p in preferences if p.source == source_filter]
        
        # 分页
        return preferences[offset:offset + limit]

    async def get_unresolved_cases(
        self,
        risk_level_filter: Optional[Any] = None,
        limit: int = 50
    ) -> List[IntentAmbiguityCase]:
        """
        获取未解决的意图歧义案例
        
        Args:
            risk_level_filter: 风险等级过滤
            limit: 返回数量限制
            
        Returns:
            未解决的案例列表
        """
        return await self.store.get_unresolved_cases(
            risk_level_filter=risk_level_filter,
            limit=limit
        )
