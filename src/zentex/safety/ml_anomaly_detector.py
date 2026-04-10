"""
ML-Based Anomaly Detection for Safety

Purpose:
    Provides machine learning-based anomaly detection for safety monitoring.
    Detects unusual patterns in system behavior, plugin usage, and cognitive operations.
    
Responsibilities:
    - Monitor system metrics for anomalies
    - Detect behavioral deviations using statistical methods
    - Track plugin usage patterns
    - Identify cognitive operation irregularities
    - Provide risk scoring based on ML models
    
Not Responsible For:
    - Real-time blocking decisions (delegated to SafetyGate)
    - Model training pipeline (separate module)
    - Data collection infrastructure
"""

import logging
import math
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of detected anomalies."""
    BEHAVIORAL_DEVIATION = "behavioral_deviation"
    USAGE_SPIKE = "usage_spike"
    PATTERN_CHANGE = "pattern_change"
    RESOURCE_ANOMALY = "resource_anomaly"
    COGNITIVE_IRREGULARITY = "cognitive_irregularity"


class SeverityLevel(Enum):
    """Anomaly severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AnomalyDetection:
    """Detected anomaly record."""
    anomaly_type: AnomalyType
    severity: SeverityLevel
    description: str
    confidence: float  # 0.0 to 1.0
    timestamp: float
    affected_component: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'anomaly_type': self.anomaly_type.value,
            'severity': self.severity.value,
            'description': self.description,
            'confidence': self.confidence,
            'timestamp': self.timestamp,
            'affected_component': self.affected_component,
            'metrics': self.metrics,
            'recommendation': self.recommendation,
        }


class StatisticalAnomalyDetector:
    """
    Statistical anomaly detector using z-score and moving averages.
    
    Features:
        - Z-score based outlier detection
        - Exponential moving average tracking
        - Configurable sensitivity
        - Multi-metric correlation
    
    Usage:
        >>> detector = StatisticalAnomalyDetector(window_size=100)
        >>> detector.add_observation("metric_name", value)
        >>> is_anomaly, score = detector.check_anomaly("metric_name", new_value)
    """
    
    def __init__(
        self,
        window_size: int = 100,
        z_threshold: float = 3.0,
        min_samples: int = 30,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        
        # Store observations per metric
        self._observations: Dict[str, deque] = {}
        
        # Statistics cache
        self._stats_cache: Dict[str, dict] = {}
        
        logger.info(
            f"StatisticalAnomalyDetector initialized: "
            f"window={window_size}, z_threshold={z_threshold}"
        )
    
    def add_observation(self, metric_name: str, value: float):
        """
        Add observation for a metric.
        
        Args:
            metric_name: Name of the metric
            value: Observed value
        """
        if metric_name not in self._observations:
            self._observations[metric_name] = deque(maxlen=self.window_size)
        
        self._observations[metric_name].append(value)
        
        # Invalidate cache
        if metric_name in self._stats_cache:
            del self._stats_cache[metric_name]
    
    def check_anomaly(
        self,
        metric_name: str,
        value: float,
    ) -> Tuple[bool, float]:
        """
        Check if value is anomalous.
        
        Args:
            metric_name: Name of the metric
            value: Value to check
        
        Returns:
            Tuple of (is_anomaly, z_score)
        """
        if metric_name not in self._observations:
            return False, 0.0
        
        observations = list(self._observations[metric_name])
        
        # Need minimum samples
        if len(observations) < self.min_samples:
            return False, 0.0
        
        # Calculate statistics
        mean, std = self._compute_stats(observations)
        
        if std == 0:
            return False, 0.0
        
        # Calculate z-score
        z_score = abs(value - mean) / std
        
        is_anomaly = z_score > self.z_threshold
        
        if is_anomaly:
            logger.warning(
                f"Anomaly detected: {metric_name}={value:.2f}, "
                f"z_score={z_score:.2f} (threshold={self.z_threshold})"
            )
        
        return is_anomaly, z_score
    
    def _compute_stats(self, values: List[float]) -> Tuple[float, float]:
        """Compute mean and standard deviation."""
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        
        mean = sum(values) / n
        
        if n < 2:
            return mean, 0.0
        
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        std = math.sqrt(variance)
        
        return mean, std
    
    def get_metric_stats(self, metric_name: str) -> Optional[dict]:
        """Get cached statistics for a metric."""
        if metric_name in self._stats_cache:
            return self._stats_cache[metric_name]
        
        if metric_name not in self._observations:
            return None
        
        observations = list(self._observations[metric_name])
        
        if not observations:
            return None
        
        mean, std = self._compute_stats(observations)
        
        stats = {
            'mean': mean,
            'std': std,
            'count': len(observations),
            'min': min(observations),
            'max': max(observations),
        }
        
        self._stats_cache[metric_name] = stats
        
        return stats


class MLAnomalyDetector:
    """
    Machine learning-based anomaly detection system.
    
    Features:
        - Multiple detection strategies
        - Configurable sensitivity per component
        - Anomaly history tracking
        - Risk scoring
        - Automated recommendations
    
    Usage:
        >>> detector = MLAnomalyDetector()
        >>> 
        >>> # Monitor plugin usage
        >>> detector.track_plugin_usage("plugin-1", duration_ms=1500)
        >>> 
        >>> # Check for anomalies
        >>> anomalies = detector.detect_anomalies()
        >>> 
        >>> for anomaly in anomalies:
        ...     print(f"{anomaly.severity}: {anomaly.description}")
    """
    
    def __init__(
        self,
        sensitivity: str = "medium",  # low, medium, high
        enable_statistical: bool = True,
        enable_pattern_detection: bool = True,
    ):
        self.sensitivity = sensitivity
        self.enable_statistical = enable_statistical
        self.enable_pattern_detection = enable_pattern_detection
        
        # Statistical detectors per component
        self._stat_detectors: Dict[str, StatisticalAnomalyDetector] = {}
        
        # Anomaly history
        self._anomaly_history: deque = deque(maxlen=1000)
        
        # Component baselines
        self._baselines: Dict[str, dict] = {}
        
        # Configure z-threshold based on sensitivity
        self.z_threshold = {
            'low': 4.0,
            'medium': 3.0,
            'high': 2.0,
        }.get(sensitivity, 3.0)
        
        logger.info(
            f"MLAnomalyDetector initialized: "
            f"sensitivity={sensitivity}, z_threshold={self.z_threshold}"
        )
    
    def track_plugin_usage(
        self,
        plugin_id: str,
        duration_ms: float,
        success: bool = True,
    ):
        """
        Track plugin usage for anomaly detection.
        
        Args:
            plugin_id: Plugin identifier
            duration_ms: Execution duration in milliseconds
            success: Whether execution succeeded
        """
        metric_name = f"plugin.{plugin_id}.duration"
        
        if self.enable_statistical:
            if plugin_id not in self._stat_detectors:
                self._stat_detectors[plugin_id] = StatisticalAnomalyDetector(
                    window_size=100,
                    z_threshold=self.z_threshold,
                )
            
            self._stat_detectors[plugin_id].add_observation(metric_name, duration_ms)
    
    def track_cognitive_operation(
        self,
        operation_type: str,
        duration_ms: float,
        turn_count: int,
    ):
        """
        Track cognitive operation metrics.
        
        Args:
            operation_type: Type of cognitive operation
            duration_ms: Operation duration
            turn_count: Number of turns in operation
        """
        metric_name = f"cognitive.{operation_type}.duration"
        
        if self.enable_statistical:
            detector_key = f"cognitive_{operation_type}"
            if detector_key not in self._stat_detectors:
                self._stat_detectors[detector_key] = StatisticalAnomalyDetector(
                    window_size=50,
                    z_threshold=self.z_threshold,
                )
            
            self._stat_detectors[detector_key].add_observation(metric_name, duration_ms)
    
    def track_resource_usage(
        self,
        resource_type: str,
        usage_percent: float,
    ):
        """
        Track resource usage metrics.
        
        Args:
            resource_type: Type of resource (cpu, memory, disk)
            usage_percent: Usage percentage (0-100)
        """
        metric_name = f"resource.{resource_type}.usage"
        
        if self.enable_statistical:
            detector_key = f"resource_{resource_type}"
            if detector_key not in self._stat_detectors:
                self._stat_detectors[detector_key] = StatisticalAnomalyDetector(
                    window_size=200,
                    z_threshold=self.z_threshold,
                )
            
            self._stat_detectors[detector_key].add_observation(metric_name, usage_percent)
    
    def detect_anomalies(self) -> List[AnomalyDetection]:
        """
        Detect anomalies across all tracked metrics.
        
        Returns:
            List of detected anomalies
        """
        anomalies = []
        
        # Check statistical anomalies
        if self.enable_statistical:
            statistical_anomalies = self._detect_statistical_anomalies()
            anomalies.extend(statistical_anomalies)
        
        # Check pattern anomalies
        if self.enable_pattern_detection:
            pattern_anomalies = self._detect_pattern_anomalies()
            anomalies.extend(pattern_anomalies)
        
        # Record anomalies
        for anomaly in anomalies:
            self._anomaly_history.append(anomaly)
        
        if anomalies:
            logger.info(f"Detected {len(anomalies)} anomalies")
        
        return anomalies
    
    def get_risk_score(self) -> float:
        """
        Calculate overall risk score based on recent anomalies.
        
        Returns:
            Risk score from 0.0 (safe) to 1.0 (critical)
        """
        if not self._anomaly_history:
            return 0.0
        
        # Weight by severity and recency
        now = time.time()
        total_weight = 0.0
        weighted_sum = 0.0
        
        severity_weights = {
            SeverityLevel.LOW: 0.2,
            SeverityLevel.MEDIUM: 0.5,
            SeverityLevel.HIGH: 0.8,
            SeverityLevel.CRITICAL: 1.0,
        }
        
        for anomaly in self._anomaly_history:
            # Exponential decay based on age (half-life: 1 hour)
            age_hours = (now - anomaly.timestamp) / 3600
            recency_weight = math.exp(-age_hours * math.log(2))
            
            severity_weight = severity_weights.get(anomaly.severity, 0.5)
            
            weight = recency_weight * severity_weight * anomaly.confidence
            
            total_weight += weight
            weighted_sum += weight
        
        if total_weight == 0:
            return 0.0
        
        # Normalize to 0-1 range
        risk_score = min(weighted_sum / max(total_weight, 1.0), 1.0)
        
        return risk_score
    
    def get_anomaly_summary(self) -> dict:
        """Get summary of recent anomalies."""
        if not self._anomaly_history:
            return {
                'total_anomalies': 0,
                'by_severity': {},
                'by_type': {},
                'risk_score': 0.0,
            }
        
        # Count by severity
        by_severity = {}
        by_type = {}
        
        for anomaly in self._anomaly_history:
            severity = anomaly.severity.value
            anomaly_type = anomaly.anomaly_type.value
            
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_type[anomaly_type] = by_type.get(anomaly_type, 0) + 1
        
        return {
            'total_anomalies': len(self._anomaly_history),
            'by_severity': by_severity,
            'by_type': by_type,
            'risk_score': self.get_risk_score(),
        }
    
    def clear_history(self):
        """Clear anomaly history."""
        self._anomaly_history.clear()
        logger.info("Anomaly history cleared")
    
    def _detect_statistical_anomalies(self) -> List[AnomalyDetection]:
        """Detect anomalies using statistical methods."""
        anomalies = []
        
        for component, detector in self._stat_detectors.items():
            # Get latest observation for each metric
            for metric_name, observations in detector._observations.items():
                if len(observations) < detector.min_samples:
                    continue
                
                latest_value = observations[-1]
                is_anomaly, z_score = detector.check_anomaly(metric_name, latest_value)
                
                if is_anomaly:
                    # Determine severity based on z-score
                    if z_score > 5.0:
                        severity = SeverityLevel.CRITICAL
                    elif z_score > 4.0:
                        severity = SeverityLevel.HIGH
                    elif z_score > 3.0:
                        severity = SeverityLevel.MEDIUM
                    else:
                        severity = SeverityLevel.LOW
                    
                    confidence = min(z_score / 5.0, 1.0)
                    
                    anomaly = AnomalyDetection(
                        anomaly_type=AnomalyType.BEHAVIORAL_DEVIATION,
                        severity=severity,
                        description=f"Statistical anomaly in {metric_name}: value={latest_value:.2f}, z_score={z_score:.2f}",
                        confidence=confidence,
                        timestamp=time.time(),
                        affected_component=component,
                        metrics={'z_score': z_score, 'value': latest_value},
                        recommendation=f"Investigate {component} for unusual behavior",
                    )
                    
                    anomalies.append(anomaly)
        
        return anomalies
    
    def _detect_pattern_anomalies(self) -> List[AnomalyDetection]:
        """Detect pattern-based anomalies."""
        anomalies = []
        
        # Placeholder for pattern detection logic
        # In production, implement more sophisticated pattern analysis
        
        return anomalies
