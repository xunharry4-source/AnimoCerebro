"""
LLM Token Cost Monitor

Purpose:
    Tracks and monitors LLM token usage and costs across all model providers.
    Provides real-time cost tracking, budget alerts, and usage analytics.
    
Responsibilities:
    - Track token consumption per provider/model
    - Calculate costs based on pricing tiers
    - Enforce budget limits with automatic throttling
    - Generate usage reports and analytics
    - Provide cost optimization recommendations
    
Not Responsible For:
    - Actual billing/invoicing (delegated to finance system)
    - Model selection logic (delegated to model router)
    - Payment processing
"""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class CostAlertLevel(Enum):
    """Cost alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class TokenUsage:
    """Token usage record for a single request."""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: float
    source_module: str = ""
    decision_id: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'provider': self.provider,
            'model': self.model,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'cost_usd': round(self.cost_usd, 6),
            'timestamp': self.timestamp,
            'source_module': self.source_module,
            'decision_id': self.decision_id,
        }


@dataclass
class CostAlert:
    """Cost alert notification."""
    level: CostAlertLevel
    message: str
    current_cost: float
    budget_limit: float
    percentage_used: float
    timestamp: float
    recommendation: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'level': self.level.value,
            'message': self.message,
            'current_cost': round(self.current_cost, 2),
            'budget_limit': round(self.budget_limit, 2),
            'percentage_used': round(self.percentage_used, 2),
            'timestamp': self.timestamp,
            'recommendation': self.recommendation,
        }


class TokenCostMonitor:
    """
    Real-time LLM token cost monitoring and budget management.
    
    Features:
        - Per-provider/model cost tracking
        - Configurable pricing tiers
        - Budget enforcement with alerts
        - Usage analytics and reporting
        - Cost optimization recommendations
    
    Usage:
        >>> monitor = TokenCostMonitor(monthly_budget=100.0)
        >>> 
        >>> # Record usage
        >>> monitor.record_usage(
        ...     provider="openai",
        ...     model="gpt-4",
        ...     input_tokens=1000,
        ...     output_tokens=500,
        ...     source_module="think_loop"
        ... )
        >>> 
        >>> # Check budget status
        >>> status = monitor.get_budget_status()
        >>> if status['alert']:
        ...     handle_alert(status['alert'])
    """
    
    def __init__(
        self,
        monthly_budget: float = 100.0,
        alert_thresholds: Optional[List[float]] = None,
        enable_auto_throttle: bool = True,
    ):
        self.monthly_budget = monthly_budget
        self.alert_thresholds = alert_thresholds or [0.5, 0.75, 0.9, 1.0]
        self.enable_auto_throttle = enable_auto_throttle
        
        # Pricing configuration (USD per 1K tokens)
        self._pricing: Dict[str, Dict[str, float]] = {
            'openai': {
                'gpt-4': {'input': 0.03, 'output': 0.06},
                'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
                'gpt-3.5-turbo': {'input': 0.0005, 'output': 0.0015},
            },
            'anthropic': {
                'claude-3-opus': {'input': 0.015, 'output': 0.075},
                'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
                'claude-3-haiku': {'input': 0.00025, 'output': 0.00125},
            },
            'default': {'input': 0.001, 'output': 0.002},
        }
        
        # Usage tracking
        self._usage_history: List[TokenUsage] = []
        self._daily_usage: Dict[str, float] = defaultdict(float)
        self._monthly_usage: Dict[str, float] = defaultdict(float)
        
        # Alerts
        self._alerts: List[CostAlert] = []
        self._throttled = False
        
        # Current period
        self._period_start = self._get_current_period_start()
        
        logger.info(
            f"TokenCostMonitor initialized: "
            f"budget=${monthly_budget:.2f}/month, "
            f"auto_throttle={enable_auto_throttle}"
        )
    
    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        source_module: str = "",
        decision_id: str = "",
    ) -> TokenUsage:
        """
        Record token usage and calculate cost.
        
        Args:
            provider: Model provider name
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            source_module: Calling module name
            decision_id: Decision trace ID
        
        Returns:
            TokenUsage record with calculated cost
        """
        total_tokens = input_tokens + output_tokens
        
        # Calculate cost
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
        
        # Create usage record
        usage = TokenUsage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            timestamp=time.time(),
            source_module=source_module,
            decision_id=decision_id,
        )
        
        # Store usage
        self._usage_history.append(usage)
        
        # Update aggregates
        today = datetime.now().strftime('%Y-%m-%d')
        month = datetime.now().strftime('%Y-%m')
        
        self._daily_usage[today] += cost
        self._monthly_usage[month] += cost
        
        # Check budget and generate alerts
        self._check_budget_and_alert()
        
        logger.debug(
            f"Recorded usage: {provider}/{model} "
            f"({total_tokens} tokens, ${cost:.4f})"
        )
        
        return usage
    
    def get_budget_status(self) -> dict:
        """
        Get current budget status.
        
        Returns:
            Dictionary with budget status information
        """
        month = datetime.now().strftime('%Y-%m')
        current_cost = self._monthly_usage.get(month, 0.0)
        
        percentage_used = (current_cost / self.monthly_budget * 100) if self.monthly_budget > 0 else 0
        
        remaining_budget = max(0, self.monthly_budget - current_cost)
        
        # Get latest alert if any
        latest_alert = self._alerts[-1] if self._alerts else None
        
        return {
            'monthly_budget': self.monthly_budget,
            'current_cost': round(current_cost, 2),
            'remaining_budget': round(remaining_budget, 2),
            'percentage_used': round(percentage_used, 2),
            'is_throttled': self._throttled,
            'latest_alert': latest_alert.to_dict() if latest_alert else None,
            'period_start': self._period_start.isoformat(),
        }
    
    def get_usage_summary(
        self,
        period: str = "daily",  # daily, weekly, monthly
    ) -> dict:
        """
        Get usage summary for specified period.
        
        Args:
            period: Time period for summary
        
        Returns:
            Dictionary with usage statistics
        """
        now = datetime.now()
        
        if period == "daily":
            start_date = now.strftime('%Y-%m-%d')
            usage_data = {start_date: self._daily_usage.get(start_date, 0.0)}
        elif period == "monthly":
            month = now.strftime('%Y-%m')
            usage_data = {month: self._monthly_usage.get(month, 0.0)}
        else:
            # Weekly - aggregate last 7 days
            usage_data = {}
            for i in range(7):
                date = (now - timedelta(days=i)).strftime('%Y-%m-%d')
                usage_data[date] = self._daily_usage.get(date, 0.0)
        
        total_cost = sum(usage_data.values())
        
        # Count requests
        cutoff_time = time.time() - (
            86400 if period == "daily" else
            604800 if period == "weekly" else
            2592000
        )
        
        recent_usage = [u for u in self._usage_history if u.timestamp >= cutoff_time]
        
        return {
            'period': period,
            'total_cost': round(total_cost, 2),
            'request_count': len(recent_usage),
            'total_tokens': sum(u.total_tokens for u in recent_usage),
            'by_provider': self._aggregate_by_provider(recent_usage),
            'by_model': self._aggregate_by_model(recent_usage),
            'daily_breakdown': usage_data,
        }
    
    def get_cost_optimization_tips(self) -> List[str]:
        """
        Get cost optimization recommendations.
        
        Returns:
            List of optimization suggestions
        """
        tips = []
        
        # Analyze usage patterns
        if not self._usage_history:
            return ["No usage data available for analysis"]
        
        # Check for expensive models
        expensive_models = self._find_expensive_model_usage()
        if expensive_models:
            tips.append(
                f"Consider using cheaper alternatives for: {', '.join(expensive_models)}. "
                f"Could save up to 50% on costs."
            )
        
        # Check for high-volume modules
        high_volume_modules = self._find_high_volume_modules()
        if high_volume_modules:
            tips.append(
                f"Modules with high usage: {', '.join(high_volume_modules)}. "
                f"Review if caching can be implemented."
            )
        
        # Check budget utilization
        status = self.get_budget_status()
        if status['percentage_used'] > 80:
            tips.append(
                "Budget utilization is high (>80%). Consider upgrading budget "
                "or implementing stricter rate limiting."
            )
        
        # General tips
        tips.append("Enable response caching to reduce redundant API calls")
        tips.append("Use smaller models for simple tasks")
        tips.append("Implement request batching where possible")
        
        return tips
    
    def reset_monthly_usage(self):
        """Reset monthly usage tracking (called at month start)."""
        month = datetime.now().strftime('%Y-%m')
        self._monthly_usage[month] = 0.0
        self._throttled = False
        self._alerts.clear()
        self._period_start = self._get_current_period_start()
        
        logger.info("Monthly usage reset")
    
    def clear_alerts(self):
        """Clear all alerts."""
        self._alerts.clear()
    
    def _calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate cost based on pricing tiers."""
        # Get pricing for provider/model
        provider_pricing = self._pricing.get(provider, {})
        model_pricing = provider_pricing.get(model, self._pricing['default'])
        
        # Calculate cost (per 1K tokens)
        input_cost = (input_tokens / 1000) * model_pricing['input']
        output_cost = (output_tokens / 1000) * model_pricing['output']
        
        return input_cost + output_cost
    
    def _check_budget_and_alert(self):
        """Check budget and generate alerts if needed."""
        status = self.get_budget_status()
        percentage = status['percentage_used'] / 100
        
        # Check each threshold
        for threshold in self.alert_thresholds:
            if percentage >= threshold:
                # Determine alert level
                if percentage >= 1.0:
                    level = CostAlertLevel.BUDGET_EXCEEDED
                elif percentage >= 0.9:
                    level = CostAlertLevel.CRITICAL
                elif percentage >= 0.75:
                    level = CostAlertLevel.WARNING
                else:
                    level = CostAlertLevel.INFO
                
                # Check if we already sent this alert
                if not self._has_alert_for_threshold(threshold):
                    alert = CostAlert(
                        level=level,
                        message=f"Budget usage at {percentage*100:.1f}%",
                        current_cost=status['current_cost'],
                        budget_limit=self.monthly_budget,
                        percentage_used=percentage * 100,
                        timestamp=time.time(),
                        recommendation=self._get_alert_recommendation(level),
                    )
                    
                    self._alerts.append(alert)
                    
                    logger.warning(
                        f"Cost alert ({level.value}): {alert.message} "
                        f"(${status['current_cost']:.2f}/${self.monthly_budget:.2f})"
                    )
                    
                    # Auto-throttle if enabled and budget exceeded
                    if self.enable_auto_throttle and percentage >= 1.0:
                        self._throttled = True
                        logger.error("Auto-throttle activated - budget exceeded")
    
    def _has_alert_for_threshold(self, threshold: float) -> bool:
        """Check if alert already sent for this threshold."""
        for alert in self._alerts:
            alert_threshold = alert.percentage_used / 100
            if abs(alert_threshold - threshold) < 0.05:  # 5% tolerance
                return True
        return False
    
    def _get_alert_recommendation(self, level: CostAlertLevel) -> str:
        """Get recommendation based on alert level."""
        recommendations = {
            CostAlertLevel.INFO: "Monitor usage trends",
            CostAlertLevel.WARNING: "Review high-cost operations",
            CostAlertLevel.CRITICAL: "Consider reducing usage or increasing budget",
            CostAlertLevel.BUDGET_EXCEEDED: "Throttling activated - contact admin",
        }
        return recommendations.get(level, "")
    
    def _aggregate_by_provider(self, usage_list: List[TokenUsage]) -> dict:
        """Aggregate usage by provider."""
        by_provider = defaultdict(lambda: {'cost': 0.0, 'tokens': 0, 'requests': 0})
        
        for usage in usage_list:
            by_provider[usage.provider]['cost'] += usage.cost_usd
            by_provider[usage.provider]['tokens'] += usage.total_tokens
            by_provider[usage.provider]['requests'] += 1
        
        return {k: {'cost': round(v['cost'], 2), 'tokens': v['tokens'], 'requests': v['requests']} 
                for k, v in by_provider.items()}
    
    def _aggregate_by_model(self, usage_list: List[TokenUsage]) -> dict:
        """Aggregate usage by model."""
        by_model = defaultdict(lambda: {'cost': 0.0, 'tokens': 0, 'requests': 0})
        
        for usage in usage_list:
            model_key = f"{usage.provider}/{usage.model}"
            by_model[model_key]['cost'] += usage.cost_usd
            by_model[model_key]['tokens'] += usage.total_tokens
            by_model[model_key]['requests'] += 1
        
        return {k: {'cost': round(v['cost'], 2), 'tokens': v['tokens'], 'requests': v['requests']} 
                for k, v in by_model.items()}
    
    def _find_expensive_model_usage(self) -> List[str]:
        """Find models with high cost per request."""
        if not self._usage_history:
            return []
        
        # Group by model
        model_costs = defaultdict(list)
        for usage in self._usage_history:
            model_key = f"{usage.provider}/{usage.model}"
            cost_per_request = usage.cost_usd if usage.total_tokens > 0 else 0
            model_costs[model_key].append(cost_per_request)
        
        # Find expensive models (avg cost > $0.01 per request)
        expensive = []
        for model, costs in model_costs.items():
            avg_cost = sum(costs) / len(costs)
            if avg_cost > 0.01:
                expensive.append(model)
        
        return expensive[:5]  # Top 5
    
    def _find_high_volume_modules(self) -> List[str]:
        """Find modules with high token volume."""
        if not self._usage_history:
            return []
        
        module_tokens = defaultdict(int)
        for usage in self._usage_history:
            if usage.source_module:
                module_tokens[usage.source_module] += usage.total_tokens
        
        # Sort by volume
        sorted_modules = sorted(module_tokens.items(), key=lambda x: x[1], reverse=True)
        
        return [m[0] for m in sorted_modules[:3]]  # Top 3
    
    def _get_current_period_start(self) -> datetime:
        """Get start of current billing period (first day of month)."""
        now = datetime.now()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
