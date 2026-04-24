"""
Predictive Analytics System for Resource Forecasting

Purpose:
    Provides time-series based predictive analytics for resource usage,
    system load, and performance trends. Enables proactive resource management
    and capacity planning.
    
Responsibilities:
    - Time-series data collection and storage
    - Trend analysis and pattern detection
    - Resource usage forecasting
    - Anomaly prediction
    - Capacity planning recommendations
    - Alert generation for predicted issues
    
Not Responsible For:
    - Real-time monitoring (delegated to monitoring system)
    - Resource allocation (delegated to resource manager)
    - Actual scaling actions (delegated to orchestrator)
"""

import logging
import time
import math
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class PredictionHorizon(Enum):
    """Prediction time horizon."""
    SHORT_TERM = "short_term"      # 1-6 hours
    MEDIUM_TERM = "medium_term"    # 6-24 hours
    LONG_TERM = "long_term"        # 1-7 days


class ResourceType(Enum):
    """Resource types for prediction."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK_IO = "disk_io"
    NETWORK = "network"
    LLM_TOKENS = "llm_tokens"
    API_CALLS = "api_calls"
    ACTIVE_SESSIONS = "active_sessions"


@dataclass
class TimeSeriesPoint:
    """Single data point in time series."""
    timestamp: float
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'value': self.value,
            'metadata': self.metadata,
        }


@dataclass
class PredictionResult:
    """Prediction result with confidence interval."""
    resource_type: ResourceType
    prediction_horizon: PredictionHorizon
    predicted_value: float
    confidence_lower: float
    confidence_upper: float
    confidence_level: float  # 0.0-1.0
    trend: str  # increasing, decreasing, stable
    generated_at: float
    data_points_used: int
    model_accuracy: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'resource_type': self.resource_type.value,
            'prediction_horizon': self.prediction_horizon.value,
            'predicted_value': round(self.predicted_value, 2),
            'confidence_interval': {
                'lower': round(self.confidence_lower, 2),
                'upper': round(self.confidence_upper, 2),
            },
            'confidence_level': round(self.confidence_level, 2),
            'trend': self.trend,
            'generated_at': self.generated_at,
            'data_points_used': self.data_points_used,
            'model_accuracy': round(self.model_accuracy, 2),
        }


@dataclass
class CapacityAlert:
    """Capacity planning alert."""
    alert_id: str
    resource_type: ResourceType
    alert_type: str  # capacity_warning, capacity_critical, trend_anomaly
    current_usage: float
    predicted_usage: float
    threshold: float
    time_to_threshold: float  # hours until threshold reached
    severity: str  # low, medium, high, critical
    recommendation: str
    created_at: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'alert_id': self.alert_id,
            'resource_type': self.resource_type.value,
            'alert_type': self.alert_type,
            'current_usage': round(self.current_usage, 2),
            'predicted_usage': round(self.predicted_usage, 2),
            'threshold': round(self.threshold, 2),
            'time_to_threshold_hours': round(self.time_to_threshold, 2),
            'severity': self.severity,
            'recommendation': self.recommendation,
            'created_at': self.created_at,
        }


class PredictiveAnalyticsEngine:
    """
    Time-series based predictive analytics for resource forecasting.
    
    Features:
        - Multi-resource time-series tracking
        - Exponential smoothing for trend detection
        - Linear regression for forecasting
        - Confidence interval calculation
        - Capacity planning alerts
        - Anomaly prediction
    
    Usage:
        >>> engine = PredictiveAnalyticsEngine()
        >>> 
        >>> # Record resource usage
        >>> engine.record_metric(
        ...     resource_type=ResourceType.CPU,
        ...     value=75.5,
        ...     timestamp=time.time()
        ... )
        >>> 
        >>> # Get prediction
        >>> prediction = engine.predict(
        ...     resource_type=ResourceType.CPU,
        ...     horizon=PredictionHorizon.SHORT_TERM
        ... )
        >>> 
        >>> print(f"Predicted CPU: {prediction.predicted_value:.1f}%")
    """
    
    def __init__(
        self,
        max_data_points: int = 10000,
        smoothing_factor: float = 0.3,
        min_data_points: int = 10,
    ):
        self.max_data_points = max_data_points
        self.smoothing_factor = smoothing_factor
        self.min_data_points = min_data_points
        
        # Time-series storage
        self._time_series: Dict[ResourceType, List[TimeSeriesPoint]] = defaultdict(list)
        
        # Prediction history
        self._predictions: List[PredictionResult] = []
        
        # Capacity alerts
        self._alerts: List[CapacityAlert] = []
        
        self._thresholds: Dict[ResourceType, float] = {
            ResourceType.CPU: 85.0,
            ResourceType.MEMORY: 90.0,
            ResourceType.DISK_IO: 80.0,
            ResourceType.NETWORK: 75.0,
            ResourceType.LLM_TOKENS: 80.0,
            ResourceType.API_CALLS: 85.0,
            ResourceType.ACTIVE_SESSIONS: 90.0,
        }

        # Phase 1: Persistence Setup
        from pathlib import Path
        import json
        self.storage_path = Path("./data/environment/telemetry")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.telemetry_file = self.storage_path / "telemetry_state.json"
        
        # Mandatory Recovery
        self._load_from_disk()
        
        logger.info(
            f"PredictiveAnalyticsEngine initialized: "
            f"max_points={max_data_points}, "
            f"smoothing={smoothing_factor}"
        )

    def _save_to_disk(self):
        """Atomic write of all telemetry and alerts."""
        try:
            import json
            data = {
                "time_series": {
                    r_type.value: [vars(p) for p in points]
                    for r_type, points in self._time_series.items()
                },
                "alerts": [vars(a) for a in self._alerts],
                "thresholds": {r.value: v for r, v in self._thresholds.items()}
            }
            temp_file = self.telemetry_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.telemetry_file)
        except Exception as e:
            logger.error(f"CRITICAL: Telemetry persistence failure: {e}")
            raise RuntimeError(f"Telemetry storage failure: {e}. System must halt to preserve analytical integrity.")

    def _load_from_disk(self):
        """Load telemetry history from disk."""
        try:
            import json
            if not self.telemetry_file.exists():
                return
            
            with open(self.telemetry_file, "r") as f:
                data = json.load(f)
                
            # Restore Time Series
            for r_val, points_data in data.get("time_series", {}).items():
                r_type = ResourceType(r_val)
                self._time_series[r_type] = [TimeSeriesPoint(**p) for p in points_data]
                
            # Restore Alerts
            self._alerts = [CapacityAlert(**a) for a in data.get("alerts", [])]
            
            # Restore Thresholds
            for r_val, val in data.get("thresholds", {}).items():
                self._thresholds[ResourceType(r_val)] = val
                
        except Exception as e:
            logger.warning(f"Telemetry recovery failed (continuing with fresh state): {e}")
            # Recovery is best-effort for analytics, but logging failure is mandatory
    
    def record_metric(
        self,
        resource_type: ResourceType,
        value: float,
        timestamp: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimeSeriesPoint:
        """
        Record a resource usage metric.
        
        Args:
            resource_type: Type of resource
            value: Metric value
            timestamp: Timestamp (defaults to now)
            metadata: Additional metadata
        
        Returns:
            Recorded TimeSeriesPoint
        """
        if timestamp is None:
            timestamp = time.time()
        
        point = TimeSeriesPoint(
            timestamp=timestamp,
            value=value,
            metadata=metadata or {},
        )
        
        # Store data point
        self._time_series[resource_type].append(point)
        
        # Enforce max data points limit
        if len(self._time_series[resource_type]) > self.max_data_points:
            self._time_series[resource_type] = self._time_series[resource_type][-self.max_data_points:]
        
        logger.debug(
            f"Recorded metric: {resource_type.value} = {value:.2f}"
        )
        
        # Phase 1: Mandatory Persistence
        self._save_to_disk()
        
        return point
    
    def predict(
        self,
        resource_type: ResourceType,
        horizon: PredictionHorizon = PredictionHorizon.SHORT_TERM,
    ) -> Optional[PredictionResult]:
        """
        Generate prediction for resource usage.
        
        Args:
            resource_type: Type of resource to predict
            horizon: Prediction time horizon
        
        Returns:
            PredictionResult or None if insufficient data
        """
        data_points = self._time_series.get(resource_type, [])
        
        if len(data_points) < self.min_data_points:
            logger.warning(
                f"Insufficient data for prediction: "
                f"{resource_type.value} has {len(data_points)} points"
            )
            return None
        
        # Calculate prediction
        predicted_value, confidence_lower, confidence_upper = self._forecast(
            data_points, horizon
        )
        
        # Detect trend
        trend = self._detect_trend(data_points)
        
        # Calculate model accuracy (simple MAPE on recent data)
        model_accuracy = self._calculate_accuracy(data_points)
        
        # Determine confidence level based on data quality
        confidence_level = self._calculate_confidence(data_points, model_accuracy)
        
        # Create prediction result
        result = PredictionResult(
            resource_type=resource_type,
            prediction_horizon=horizon,
            predicted_value=predicted_value,
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            confidence_level=confidence_level,
            trend=trend,
            generated_at=time.time(),
            data_points_used=len(data_points),
            model_accuracy=model_accuracy,
        )
        
        # Store prediction
        self._predictions.append(result)
        
        # Check for capacity alerts
        self._check_capacity_alerts(resource_type, result)
        
        logger.info(
            f"Prediction generated: {resource_type.value} -> "
            f"{predicted_value:.2f} ({trend})"
        )
        
        # Phase 1: Mandatory Persistence (Store prediction metadata if needed, but alerts are already stored)
        self._save_to_disk()
        
        return result
    
    def get_capacity_alerts(
        self,
        resource_type: Optional[ResourceType] = None,
        severity: Optional[str] = None,
    ) -> List[CapacityAlert]:
        """
        Get capacity planning alerts.
        
        Args:
            resource_type: Filter by resource type
            severity: Filter by severity level
        
        Returns:
            List of matching alerts
        """
        alerts = self._alerts
        
        if resource_type:
            alerts = [a for a in alerts if a.resource_type == resource_type]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        # Sort by severity (critical first)
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        alerts.sort(key=lambda a: severity_order.get(a.severity, 4))
        
        return alerts
    
    def get_resource_summary(
        self,
        resource_type: ResourceType,
    ) -> Dict[str, Any]:
        """
        Get summary statistics for a resource.
        
        Args:
            resource_type: Type of resource
        
        Returns:
            Dictionary with summary statistics
        """
        data_points = self._time_series.get(resource_type, [])
        
        if not data_points:
            return {
                'resource_type': resource_type.value,
                'data_points': 0,
                'current_value': 0.0,
                'avg_value': 0.0,
                'min_value': 0.0,
                'max_value': 0.0,
                'trend': 'unknown',
            }
        
        values = [p.value for p in data_points]
        
        return {
            'resource_type': resource_type.value,
            'data_points': len(data_points),
            'current_value': values[-1],
            'avg_value': sum(values) / len(values),
            'min_value': min(values),
            'max_value': max(values),
            'std_dev': self._calculate_std_dev(values),
            'trend': self._detect_trend(data_points),
            'last_updated': data_points[-1].timestamp,
        }
    
    def clear_old_data(self, older_than_hours: float = 168):
        """
        Clear old data points.
        
        Args:
            older_than_hours: Remove data older than this many hours
        """
        cutoff_time = time.time() - (older_than_hours * 3600)
        
        for resource_type in self._time_series:
            self._time_series[resource_type] = [
                p for p in self._time_series[resource_type]
                if p.timestamp >= cutoff_time
            ]
        
        logger.info(f"Cleared data older than {older_than_hours} hours")
        self._save_to_disk()
    
    def _forecast(
        self,
        data_points: List[TimeSeriesPoint],
        horizon: PredictionHorizon,
    ) -> Tuple[float, float, float]:
        """
        Forecast future value using exponential smoothing and linear regression.
        
        Returns:
            Tuple of (predicted_value, confidence_lower, confidence_upper)
        """
        values = [p.value for p in data_points]
        timestamps = [p.timestamp for p in data_points]
        
        # Apply exponential smoothing
        smoothed_values = self._exponential_smoothing(values)
        
        # Linear regression for trend
        slope, intercept = self._linear_regression(timestamps, smoothed_values)
        
        # Calculate prediction horizon in seconds
        horizon_seconds = {
            PredictionHorizon.SHORT_TERM: 3 * 3600,    # 3 hours
            PredictionHorizon.MEDIUM_TERM: 12 * 3600,  # 12 hours
            PredictionHorizon.LONG_TERM: 3 * 24 * 3600,  # 3 days
        }[horizon]
        
        # Predict future value
        future_timestamp = timestamps[-1] + horizon_seconds
        predicted_value = slope * future_timestamp + intercept
        
        # Ensure non-negative for most resources
        if predicted_value < 0:
            predicted_value = 0.0
        
        # Calculate confidence interval
        std_dev = self._calculate_std_dev(values)
        margin_of_error = 1.96 * std_dev / math.sqrt(len(values))
        
        confidence_lower = max(0, predicted_value - margin_of_error * 2)
        confidence_upper = predicted_value + margin_of_error * 2
        
        return predicted_value, confidence_lower, confidence_upper
    
    def _exponential_smoothing(self, values: List[float]) -> List[float]:
        """Apply exponential smoothing to reduce noise."""
        if not values:
            return []
        
        smoothed = [values[0]]
        
        for i in range(1, len(values)):
            smoothed_value = (
                self.smoothing_factor * values[i] +
                (1 - self.smoothing_factor) * smoothed[-1]
            )
            smoothed.append(smoothed_value)
        
        return smoothed
    
    def _linear_regression(
        self,
        x_values: List[float],
        y_values: List[float],
    ) -> Tuple[float, float]:
        """
        Perform simple linear regression.
        
        Returns:
            Tuple of (slope, intercept)
        """
        n = len(x_values)
        if n < 2:
            return 0.0, y_values[0] if y_values else 0.0
        
        # Normalize x values to prevent overflow
        x_min = min(x_values)
        x_normalized = [x - x_min for x in x_values]
        
        sum_x = sum(x_normalized)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_normalized, y_values))
        sum_x2 = sum(x ** 2 for x in x_normalized)
        
        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            return 0.0, sum_y / n
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        # Adjust intercept for normalization
        intercept = intercept - slope * x_min
        
        return slope, intercept
    
    def _detect_trend(self, data_points: List[TimeSeriesPoint]) -> str:
        """Detect trend direction from data points."""
        if len(data_points) < 2:
            return 'stable'
        
        values = [p.value for p in data_points]
        
        # Compare recent average to earlier average
        mid_point = len(values) // 2
        early_avg = sum(values[:mid_point]) / mid_point
        recent_avg = sum(values[mid_point:]) / (len(values) - mid_point)
        
        change_percent = ((recent_avg - early_avg) / early_avg * 100) if early_avg != 0 else 0
        
        if change_percent > 5:
            return 'increasing'
        elif change_percent < -5:
            return 'decreasing'
        else:
            return 'stable'
    
    def _calculate_accuracy(self, data_points: List[TimeSeriesPoint]) -> float:
        """Calculate model accuracy using MAPE (Mean Absolute Percentage Error)."""
        if len(data_points) < 10:
            return 0.0
        
        values = [p.value for p in data_points]
        smoothed = self._exponential_smoothing(values)
        
        # Calculate MAPE on last portion of data
        test_size = min(10, len(values) // 3)
        if test_size == 0:
            return 0.0
        
        errors = []
        for i in range(len(values) - test_size, len(values)):
            if values[i] != 0:
                error = abs(values[i] - smoothed[i]) / abs(values[i])
                errors.append(error)
        
        if not errors:
            return 0.0
        
        mape = sum(errors) / len(errors)
        accuracy = max(0, 1 - mape)  # Convert to accuracy (0-1)
        
        return accuracy
    
    def _calculate_confidence(
        self,
        data_points: List[TimeSeriesPoint],
        model_accuracy: float,
    ) -> float:
        """Calculate confidence level based on data quality."""
        # Base confidence on number of data points
        data_confidence = min(1.0, len(data_points) / 100)
        
        # Combine with model accuracy
        confidence = (data_confidence * 0.4 + model_accuracy * 0.6)
        
        return min(1.0, max(0.0, confidence))
    
    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        
        return math.sqrt(variance)
    
    def _check_capacity_alerts(
        self,
        resource_type: ResourceType,
        prediction: PredictionResult,
    ):
        """Check if prediction triggers capacity alerts."""
        threshold = self._thresholds.get(resource_type, 100.0)
        current_value = prediction.predicted_value
        
        # Check if predicted to exceed threshold
        if prediction.predicted_value > threshold * 0.8:  # 80% of threshold
            # Determine severity
            if prediction.predicted_value > threshold:
                severity = 'critical'
                alert_type = 'capacity_critical'
            elif prediction.predicted_value > threshold * 0.9:
                severity = 'high'
                alert_type = 'capacity_warning'
            else:
                severity = 'medium'
                alert_type = 'capacity_warning'
            
            # Estimate time to threshold
            time_to_threshold = self._estimate_time_to_threshold(
                resource_type, threshold
            )
            
            # Generate recommendation
            recommendation = self._generate_recommendation(
                resource_type, prediction, threshold
            )
            
            # Create alert
            alert = CapacityAlert(
                alert_id=f"ALERT_{resource_type.value}_{int(time.time())}",
                resource_type=resource_type,
                alert_type=alert_type,
                current_usage=current_value,
                predicted_usage=prediction.predicted_value,
                threshold=threshold,
                time_to_threshold=time_to_threshold,
                severity=severity,
                recommendation=recommendation,
                created_at=time.time(),
            )
            
            self._alerts.append(alert)
            
            logger.warning(
                f"Capacity alert: {resource_type.value} predicted to reach "
                f"{prediction.predicted_value:.1f}% (threshold: {threshold}%)"
            )
    
    def _estimate_time_to_threshold(
        self,
        resource_type: ResourceType,
        threshold: float,
    ) -> float:
        """Estimate hours until resource reaches threshold."""
        data_points = self._time_series.get(resource_type, [])
        
        if len(data_points) < 2:
            return 24.0  # Default 24 hours
        
        values = [p.value for p in data_points]
        timestamps = [p.timestamp for p in data_points]
        
        # Calculate rate of change
        if values[-1] >= threshold:
            return 0.0  # Already exceeded
        
        if values[-1] <= 0:
            return 168.0  # Very long time
        
        # Simple linear extrapolation
        rate_per_hour = (values[-1] - values[0]) / ((timestamps[-1] - timestamps[0]) / 3600)
        
        if rate_per_hour <= 0:
            return 168.0  # Not increasing
        
        remaining = threshold - values[-1]
        hours_to_threshold = remaining / rate_per_hour
        
        return max(0.1, hours_to_threshold)
    
    def _generate_recommendation(
        self,
        resource_type: ResourceType,
        prediction: PredictionResult,
        threshold: float,
    ) -> str:
        """Generate actionable recommendation."""
        recommendations = {
            ResourceType.CPU: "Consider scaling compute resources or optimizing CPU-intensive operations",
            ResourceType.MEMORY: "Review memory usage patterns and consider increasing memory allocation",
            ResourceType.DISK_IO: "Optimize I/O operations or upgrade storage infrastructure",
            ResourceType.NETWORK: "Implement request throttling or increase network bandwidth",
            ResourceType.LLM_TOKENS: "Enable token caching or implement usage quotas",
            ResourceType.API_CALLS: "Implement rate limiting or add API gateway caching",
            ResourceType.ACTIVE_SESSIONS: "Review session timeout policies or scale horizontally",
        }
        
        base_recommendation = recommendations.get(
            resource_type,
            "Monitor resource usage and plan for capacity expansion"
        )
        
        if prediction.trend == 'increasing':
            return f"{base_recommendation}. Current trend is increasing."
        else:
            return base_recommendation
