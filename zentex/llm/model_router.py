"""
Intelligent Model Router

Purpose:
    Routes LLM requests to the most appropriate model based on task complexity,
    cost constraints, and performance requirements. Optimizes cost-performance tradeoff.
    
Responsibilities:
    - Analyze task complexity
    - Select optimal model for each request
    - Balance cost vs performance
    - Track routing decisions and outcomes
    - Provide routing recommendations
    
Not Responsible For:
    - Actual model invocation (delegated to LLM gateway)
    - Cost tracking (delegated to cost monitor)
    - Model training or fine-tuning
"""

import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels."""
    SIMPLE = "simple"           # Basic Q&A, formatting
    MODERATE = "moderate"       # Analysis, summarization
    COMPLEX = "complex"         # Reasoning, planning
    CRITICAL = "critical"       # High-stakes decisions


class ModelTier(Enum):
    """Model performance tiers."""
    BUDGET = "budget"           # Cheapest, fastest
    STANDARD = "standard"       # Balanced cost/performance
    PREMIUM = "premium"         # High quality, higher cost
    ULTRA = "ultra"             # Best quality, highest cost


@dataclass
class ModelCapability:
    """Model capability profile."""
    model_name: str
    provider: str
    tier: ModelTier
    max_context_tokens: int
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    avg_latency_ms: float = 0.0
    
    def get_cost_estimate(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for given token counts."""
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output
        return input_cost + output_cost


@dataclass
class RoutingDecision:
    """Model routing decision record."""
    task_complexity: TaskComplexity
    selected_model: str
    selected_provider: str
    alternative_models: List[str]
    reasoning: str
    estimated_cost: float
    timestamp: float
    actual_cost: float = 0.0
    actual_latency_ms: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'task_complexity': self.task_complexity.value,
            'selected_model': self.selected_model,
            'selected_provider': self.selected_provider,
            'alternative_models': self.alternative_models,
            'reasoning': self.reasoning,
            'estimated_cost': round(self.estimated_cost, 4),
            'actual_cost': round(self.actual_cost, 4),
            'actual_latency_ms': round(self.actual_latency_ms, 2),
            'timestamp': self.timestamp,
        }


class IntelligentModelRouter:
    """
    Intelligent model selection based on task requirements.
    
    Features:
        - Task complexity analysis
        - Cost-aware model selection
        - Performance optimization
        - Routing history and analytics
        - Custom routing rules
    
    Usage:
        >>> router = IntelligentModelRouter()
        >>> 
        >>> # Route a request
        >>> decision = router.route_request(
        ...     prompt="Summarize this document...",
        ...     context={"document_length": 5000},
        ...     priority="cost"  # or "performance", "balanced"
        ... )
        >>> 
        >>> print(f"Selected: {decision.selected_model}")
        >>> print(f"Estimated cost: ${decision.estimated_cost:.4f}")
    """
    
    def __init__(
        self,
        default_priority: str = "balanced",  # cost, performance, balanced
        enable_learning: bool = True,
    ):
        self.default_priority = default_priority
        self.enable_learning = enable_learning
        
        # Model registry
        self._models: Dict[str, ModelCapability] = {}
        
        # Routing history
        self._routing_history: List[RoutingDecision] = []
        
        # Performance tracking
        self._model_performance: Dict[str, dict] = {}
        
        # Initialize default models
        self._initialize_default_models()
        
        logger.info(
            f"IntelligentModelRouter initialized: "
            f"priority={default_priority}, "
            f"models={len(self._models)}"
        )
    
    def route_request(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        priority: Optional[str] = None,
        budget_limit: Optional[float] = None,
        max_latency_ms: Optional[float] = None,
    ) -> RoutingDecision:
        """
        Route request to optimal model.
        
        Args:
            prompt: User prompt
            context: Additional context for routing
            priority: Routing priority (cost/performance/balanced)
            budget_limit: Maximum acceptable cost
            max_latency_ms: Maximum acceptable latency
        
        Returns:
            RoutingDecision with selected model
        """
        priority = priority or self.default_priority
        context = context or {}
        
        # Step 1: Analyze task complexity
        complexity = self._analyze_task_complexity(prompt, context)
        
        # Step 2: Get candidate models
        candidates = self._get_candidate_models(complexity)
        
        # Step 3: Score and rank models
        scored_models = self._score_models(candidates, complexity, priority)
        
        # Step 4: Apply constraints
        filtered_models = self._apply_constraints(
            scored_models,
            budget_limit,
            max_latency_ms,
        )
        
        if not filtered_models:
            # Fallback to cheapest available
            filtered_models = [(self._get_cheapest_model(), 1.0)]
        
        # Step 5: Select best model
        selected_model, score = filtered_models[0]
        
        # Step 6: Create routing decision
        alternatives = [m[0].model_name for m in filtered_models[1:3]]
        
        estimated_cost = selected_model.get_cost_estimate(
            input_tokens=len(prompt.split()),
            output_tokens=200,  # Estimate
        )
        
        decision = RoutingDecision(
            task_complexity=complexity,
            selected_model=selected_model.model_name,
            selected_provider=selected_model.provider,
            alternative_models=alternatives,
            reasoning=f"Complexity: {complexity.value}, Priority: {priority}, Score: {score:.2f}",
            estimated_cost=estimated_cost,
            timestamp=time.time(),
        )
        
        # Record decision
        self._routing_history.append(decision)
        
        logger.debug(
            f"Routed request: {selected_model.model_name} "
            f"(complexity={complexity.value}, priority={priority})"
        )
        
        return decision
    
    def record_outcome(
        self,
        decision: RoutingDecision,
        actual_cost: float,
        actual_latency_ms: float,
        success: bool = True,
    ):
        """
        Record actual outcome of routing decision.
        
        Args:
            decision: Original routing decision
            actual_cost: Actual cost incurred
            actual_latency_ms: Actual latency
            success: Whether request succeeded
        """
        decision.actual_cost = actual_cost
        decision.actual_latency_ms = actual_latency_ms
        
        # Update performance tracking
        model_key = f"{decision.selected_provider}/{decision.selected_model}"
        
        if model_key not in self._model_performance:
            self._model_performance[model_key] = {
                'total_requests': 0,
                'successful_requests': 0,
                'avg_cost': 0.0,
                'avg_latency': 0.0,
            }
        
        perf = self._model_performance[model_key]
        perf['total_requests'] += 1
        if success:
            perf['successful_requests'] += 1
        
        # Update averages
        n = perf['total_requests']
        perf['avg_cost'] = (perf['avg_cost'] * (n - 1) + actual_cost) / n
        perf['avg_latency'] = (perf['avg_latency'] * (n - 1) + actual_latency_ms) / n
        
        logger.debug(
            f"Recorded outcome: {model_key} "
            f"(cost=${actual_cost:.4f}, latency={actual_latency_ms:.0f}ms)"
        )
    
    def get_routing_analytics(self) -> dict:
        """Get routing analytics and insights."""
        if not self._routing_history:
            return {
                'total_requests': 0,
                'by_complexity': {},
                'by_model': {},
                'avg_cost': 0.0,
                'cost_savings': 0.0,
            }
        
        # Analyze by complexity
        by_complexity = {}
        by_model = {}
        total_cost = 0.0
        
        for decision in self._routing_history:
            complexity = decision.task_complexity.value
            model = decision.selected_model
            
            by_complexity[complexity] = by_complexity.get(complexity, 0) + 1
            by_model[model] = by_model.get(model, 0) + 1
            total_cost += decision.actual_cost or decision.estimated_cost
        
        # Calculate cost savings (vs always using premium)
        premium_cost = self._estimate_premium_only_cost()
        cost_savings = max(0, premium_cost - total_cost)
        
        return {
            'total_requests': len(self._routing_history),
            'by_complexity': by_complexity,
            'by_model': by_model,
            'avg_cost': round(total_cost / len(self._routing_history), 4),
            'cost_savings': round(cost_savings, 2),
            'savings_percentage': round(
                (cost_savings / premium_cost * 100) if premium_cost > 0 else 0, 2
            ),
        }
    
    def add_custom_model(self, capability: ModelCapability):
        """Add custom model to registry."""
        key = f"{capability.provider}/{capability.model_name}"
        self._models[key] = capability
        logger.info(f"Added custom model: {key}")
    
    def get_model_recommendations(self) -> List[str]:
        """Get model usage recommendations."""
        recommendations = []
        
        analytics = self.get_routing_analytics()
        
        if analytics['total_requests'] == 0:
            return ["No routing data available"]
        
        # Check for overuse of expensive models
        expensive_usage = self._find_expensive_model_overuse()
        if expensive_usage:
            recommendations.append(
                f"Consider downgrading: {', '.join(expensive_usage)}. "
                f"Could save ${analytics['cost_savings']:.2f}"
            )
        
        # General recommendations
        recommendations.append("Review routing rules monthly")
        recommendations.append("Monitor model performance metrics")
        recommendations.append("Update model capabilities as new models release")
        
        return recommendations
    
    def _initialize_default_models(self):
        """Initialize default model registry."""
        # OpenAI models
        self._models["openai/gpt-4"] = ModelCapability(
            model_name="gpt-4",
            provider="openai",
            tier=ModelTier.ULTRA,
            max_context_tokens=8192,
            strengths=["reasoning", "complex_analysis", "code"],
            weaknesses=["cost", "latency"],
            cost_per_1k_input=0.03,
            cost_per_1k_output=0.06,
            avg_latency_ms=3000,
        )
        
        self._models["openai/gpt-4-turbo"] = ModelCapability(
            model_name="gpt-4-turbo",
            provider="openai",
            tier=ModelTier.PREMIUM,
            max_context_tokens=128000,
            strengths=["long_context", "up_to_date"],
            weaknesses=["cost"],
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
            avg_latency_ms=2000,
        )
        
        self._models["openai/gpt-3.5-turbo"] = ModelCapability(
            model_name="gpt-3.5-turbo",
            provider="openai",
            tier=ModelTier.BUDGET,
            max_context_tokens=16385,
            strengths=["speed", "cost"],
            weaknesses=["reasoning", "accuracy"],
            cost_per_1k_input=0.0005,
            cost_per_1k_output=0.0015,
            avg_latency_ms=500,
        )
        
        # Anthropic models
        self._models["anthropic/claude-3-opus"] = ModelCapability(
            model_name="claude-3-opus",
            provider="anthropic",
            tier=ModelTier.ULTRA,
            max_context_tokens=200000,
            strengths=["reasoning", "long_context"],
            weaknesses=["cost"],
            cost_per_1k_input=0.015,
            cost_per_1k_output=0.075,
            avg_latency_ms=4000,
        )
        
        self._models["anthropic/claude-3-sonnet"] = ModelCapability(
            model_name="claude-3-sonnet",
            provider="anthropic",
            tier=ModelTier.PREMIUM,
            max_context_tokens=200000,
            strengths=["balanced", "long_context"],
            weaknesses=[],
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            avg_latency_ms=1500,
        )
        
        self._models["anthropic/claude-3-haiku"] = ModelCapability(
            model_name="claude-3-haiku",
            provider="anthropic",
            tier=ModelTier.BUDGET,
            max_context_tokens=200000,
            strengths=["speed", "cost"],
            weaknesses=["complex_reasoning"],
            cost_per_1k_input=0.00025,
            cost_per_1k_output=0.00125,
            avg_latency_ms=300,
        )
    
    def _analyze_task_complexity(
        self,
        prompt: str,
        context: Dict[str, Any],
    ) -> TaskComplexity:
        """Analyze task complexity from prompt and context."""
        # Simple heuristics for complexity analysis
        prompt_length = len(prompt)
        word_count = len(prompt.split())
        
        # Check for complexity indicators
        complex_indicators = [
            "analyze", "reason", "plan", "strategy", "optimize",
            "compare", "evaluate", "synthesize", "design",
        ]
        
        moderate_indicators = [
            "summarize", "explain", "describe", "list",
            "convert", "format", "organize",
        ]
        
        has_complex = any(indicator in prompt.lower() for indicator in complex_indicators)
        has_moderate = any(indicator in prompt.lower() for indicator in moderate_indicators)
        
        # Determine complexity
        if has_complex or word_count > 200 or prompt_length > 1000:
            return TaskComplexity.COMPLEX
        elif has_moderate or word_count > 50:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE
    
    def _get_candidate_models(
        self,
        complexity: TaskComplexity,
    ) -> List[ModelCapability]:
        """Get candidate models for complexity level."""
        tier_mapping = {
            TaskComplexity.SIMPLE: [ModelTier.BUDGET],
            TaskComplexity.MODERATE: [ModelTier.BUDGET, ModelTier.STANDARD],
            TaskComplexity.COMPLEX: [ModelTier.STANDARD, ModelTier.PREMIUM],
            TaskComplexity.CRITICAL: [ModelTier.PREMIUM, ModelTier.ULTRA],
        }
        
        allowed_tiers = tier_mapping.get(complexity, [ModelTier.BUDGET])
        
        candidates = [
            model for model in self._models.values()
            if model.tier in allowed_tiers
        ]
        
        return candidates
    
    def _score_models(
        self,
        candidates: List[ModelCapability],
        complexity: TaskComplexity,
        priority: str,
    ) -> List[Tuple[ModelCapability, float]]:
        """Score and rank candidate models."""
        scored = []
        
        for model in candidates:
            score = 0.0
            
            # Base score by tier match
            tier_scores = {
                ModelTier.BUDGET: 0.3,
                ModelTier.STANDARD: 0.5,
                ModelTier.PREMIUM: 0.7,
                ModelTier.ULTRA: 0.9,
            }
            score += tier_scores.get(model.tier, 0.5)
            
            # Cost factor (lower is better for cost priority)
            avg_cost = (model.cost_per_1k_input + model.cost_per_1k_output) / 2
            if priority == "cost":
                score += (1.0 / (1.0 + avg_cost * 100)) * 0.4
            elif priority == "performance":
                score += 0.2  # Less weight on cost
            else:  # balanced
                score += (1.0 / (1.0 + avg_cost * 100)) * 0.2
            
            # Latency factor
            if priority == "performance":
                score += (1.0 / (1.0 + model.avg_latency_ms / 1000)) * 0.3
            
            scored.append((model, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored
    
    def _apply_constraints(
        self,
        scored_models: List[Tuple[ModelCapability, float]],
        budget_limit: Optional[float],
        max_latency_ms: Optional[float],
    ) -> List[Tuple[ModelCapability, float]]:
        """Filter models based on constraints."""
        filtered = []
        
        for model, score in scored_models:
            # Check budget constraint
            if budget_limit is not None:
                estimated_cost = model.get_cost_estimate(1000, 500)
                if estimated_cost > budget_limit:
                    continue
            
            # Check latency constraint
            if max_latency_ms is not None:
                if model.avg_latency_ms > max_latency_ms:
                    continue
            
            filtered.append((model, score))
        
        return filtered
    
    def _get_cheapest_model(self) -> ModelCapability:
        """Get cheapest available model."""
        if not self._models:
            raise ValueError("No models registered")
        
        cheapest = min(
            self._models.values(),
            key=lambda m: m.cost_per_1k_input + m.cost_per_1k_output,
        )
        
        return cheapest
    
    def _estimate_premium_only_cost(self) -> float:
        """Estimate cost if all requests used premium models."""
        if not self._routing_history:
            return 0.0
        
        premium_model = self._models.get("openai/gpt-4")
        if not premium_model:
            return 0.0
        
        total_cost = 0.0
        for decision in self._routing_history:
            # Estimate with premium model
            cost = premium_model.get_cost_estimate(1000, 500)
            total_cost += cost
        
        return total_cost
    
    def _find_expensive_model_overuse(self) -> List[str]:
        """Find models that are overused relative to task complexity."""
        if not self._routing_history:
            return []
        
        # Simple heuristic: check if simple tasks use expensive models
        expensive_overuse = []
        
        for decision in self._routing_history:
            if decision.task_complexity == TaskComplexity.SIMPLE:
                model = self._models.get(
                    f"{decision.selected_provider}/{decision.selected_model}"
                )
                if model and model.tier in [ModelTier.PREMIUM, ModelTier.ULTRA]:
                    expensive_overuse.append(decision.selected_model)
        
        return list(set(expensive_overuse))[:3]  # Top 3
