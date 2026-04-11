"""
Multi-Source Comparator / 多源比较器

Detects and scores conflicts between multiple information sources.
Implements cross-source validation and conflict resolution logic.

检测并评分多个信息源之间的冲突。
实现跨源验证和冲突解决逻辑。
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.environment.models import SourceConflictScore


class MultiSourceComparator:
    """
    Compares data from multiple sources to detect conflicts and inconsistencies.
    
    多源比较器，比较来自多个源的数据以检测冲突和不一致。
    
    Analyzes values from different sources for the same metrics or fields,
    calculates conflict severity, and provides resolution recommendations.
    Useful for validating environmental readings and detecting sensor failures.
    
    分析不同来源的相同指标或字段的值，计算冲突严重程度，
    并提供解决建议。用于验证环境读数和检测传感器故障。
    """
    
    def __init__(
        self,
        *,
        conflict_threshold: float = 0.3,
        high_confidence_threshold: float = 0.7,
    ) -> None:
        """
        Initialize the MultiSourceComparator.
        
        Args:
            conflict_threshold: Minimum difference to consider as conflict (0-1)
            high_confidence_threshold: Threshold for high confidence in conflict detection
        """
        self.conflict_threshold = conflict_threshold
        self.high_confidence_threshold = high_confidence_threshold
    
    def compare_sources(
        self,
        source_a_id: str,
        source_b_id: str,
        field_name: str,
        value_a: Any,
        value_b: Any,
        conflict_type: str = "value_mismatch",
    ) -> SourceConflictScore | None:
        """
        Compare values from two sources for the same field.
        
        比较两个来源的同一字段的值。
        
        Args:
            source_a_id: Identifier for source A
            source_b_id: Identifier for source B
            field_name: Name of the field being compared
            value_a: Value from source A
            value_b: Value from source B
            conflict_type: Type of conflict being detected
            
        Returns:
            SourceConflictScore if conflict detected, None otherwise
        """
        # Calculate conflict severity
        severity = self._calculate_severity(value_a, value_b)
        
        # Only return conflict if severity exceeds threshold
        if severity < self.conflict_threshold:
            return None
        
        # Calculate confidence in the conflict detection
        confidence = self._calculate_confidence(value_a, value_b, severity)
        
        # Determine if human review is needed
        requires_review = (
            severity > 0.7
            or confidence < 0.5
            or self._is_critical_field(field_name)
        )
        
        # Generate resolution suggestion
        resolution = self._suggest_resolution(
            field_name, value_a, value_b, severity, confidence
        )
        
        return SourceConflictScore(
            conflict_id=str(uuid4()),
            source_a=source_a_id,
            source_b=source_b_id,
            conflict_type=conflict_type,
            conflict_field=field_name,
            value_a=value_a,
            value_b=value_b,
            conflict_severity=severity,
            confidence_in_conflict=confidence,
            suggested_resolution=resolution,
            requires_human_review=requires_review,
        )
    
    def compare_multiple_sources(
        self,
        field_name: str,
        sources: dict[str, Any],
    ) -> list[SourceConflictScore]:
        """
        Compare values from multiple sources pairwise.
        
        成对比较多个来源的值。
        
        Args:
            field_name: Name of the field being compared
            sources: Dictionary mapping source IDs to their values
            
        Returns:
            List of detected conflicts
        """
        conflicts = []
        source_ids = list(sources.keys())
        
        # Compare all pairs
        for i in range(len(source_ids)):
            for j in range(i + 1, len(source_ids)):
                source_a = source_ids[i]
                source_b = source_ids[j]
                
                conflict = self.compare_sources(
                    source_a_id=source_a,
                    source_b_id=source_b,
                    field_name=field_name,
                    value_a=sources[source_a],
                    value_b=sources[source_b],
                )
                
                if conflict is not None:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _calculate_severity(self, value_a: Any, value_b: Any) -> float:
        """
        Calculate conflict severity between two values.
        
        计算两个值之间的冲突严重程度。
        
        Returns:
            Severity score from 0.0 (no conflict) to 1.0 (maximum conflict)
        """
        # Handle None values
        if value_a is None and value_b is None:
            return 0.0
        if value_a is None or value_b is None:
            return 1.0
        
        # Handle numeric values
        if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
            if value_a == 0 and value_b == 0:
                return 0.0
            
            # Calculate relative difference
            max_val = max(abs(value_a), abs(value_b))
            if max_val == 0:
                return 0.0
            
            relative_diff = abs(value_a - value_b) / max_val
            return min(1.0, relative_diff)
        
        # Handle string values
        if isinstance(value_a, str) and isinstance(value_b, str):
            if value_a == value_b:
                return 0.0
            
            # Simple string difference (could be enhanced with Levenshtein distance)
            return 1.0
        
        # Handle boolean values
        if isinstance(value_a, bool) and isinstance(value_b, bool):
            return 0.0 if value_a == value_b else 1.0
        
        # For other types, check equality
        return 0.0 if value_a == value_b else 1.0
    
    def _calculate_confidence(
        self,
        value_a: Any,
        value_b: Any,
        severity: float,
    ) -> float:
        """
        Calculate confidence in the conflict detection.
        
        计算冲突检测的置信度。
        
        Higher confidence means we're more certain this is a real conflict.
        """
        base_confidence = 0.8
        
        # Reduce confidence for edge cases
        if value_a is None or value_b is None:
            base_confidence -= 0.2
        
        # Higher severity typically means higher confidence
        if severity > 0.8:
            base_confidence += 0.1
        elif severity < 0.4:
            base_confidence -= 0.2
        
        return max(0.0, min(1.0, base_confidence))
    
    def _is_critical_field(self, field_name: str) -> bool:
        """
        Check if a field is critical and requires human review on conflict.
        
        检查字段是否关键，在冲突时需要人工审查。
        """
        critical_fields = {
            "memory_pressure",
            "network_health",
            "overall_health",
            "cpu_load_percent",
            "disk_usage_percent",
            "security_status",
            "identity_kernel",
        }
        
        return field_name.lower() in critical_fields
    
    def _suggest_resolution(
        self,
        field_name: str,
        value_a: Any,
        value_b: Any,
        severity: float,
        confidence: float,
    ) -> str | None:
        """
        Suggest how to resolve the detected conflict.
        
        建议如何解决检测到的冲突。
        """
        if severity > 0.8:
            return (
                f"Critical conflict in '{field_name}': values differ significantly. "
                f"Recommend manual verification. Source A: {value_a}, Source B: {value_b}"
            )
        
        if confidence < 0.5:
            return (
                f"Low confidence conflict in '{field_name}'. "
                f"May be false positive. Consider additional validation."
            )
        
        if self._is_critical_field(field_name):
            return (
                f"Conflict in critical field '{field_name}'. "
                f"Prefer conservative value. Source A: {value_a}, Source B: {value_b}"
            )
        
        return (
            f"Moderate conflict in '{field_name}'. "
            f"Consider averaging or using most recent value."
        )
