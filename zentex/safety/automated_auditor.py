"""
Automated Security Audit System

Purpose:
    Provides automated security auditing, compliance checking, and anomaly tracing
    for the Zentex system. Generates comprehensive audit reports and maintains
    audit trails for all critical operations.
    
Responsibilities:
    - Automated audit log collection
    - Compliance rule checking
    - Anomaly behavior tracing
    - Audit report generation
    - Audit trail maintenance
    - Security event correlation
    
Not Responsible For:
    - Real-time threat detection (delegated to ML anomaly detector)
    - Access control enforcement (delegated to authorization system)
    - Incident response automation
"""

import logging
import time
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


class AuditSeverity(Enum):
    """Audit event severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplianceStatus(Enum):
    """Compliance check status."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class AuditEvent:
    """Single audit event record."""
    event_id: str
    timestamp: float
    event_type: str
    source_module: str
    actor: str
    action: str
    target: str
    severity: AuditSeverity
    details: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'event_type': self.event_type,
            'source_module': self.source_module,
            'actor': self.actor,
            'action': self.action,
            'target': self.target,
            'severity': self.severity.value,
            'details': self.details,
            'metadata': self.metadata,
        }


@dataclass
class ComplianceCheck:
    """Compliance rule check result."""
    rule_id: str
    rule_name: str
    category: str
    status: ComplianceStatus
    description: str
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    checked_at: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'rule_id': self.rule_id,
            'rule_name': self.rule_name,
            'category': self.category,
            'status': self.status.value,
            'description': self.description,
            'findings': self.findings,
            'recommendations': self.recommendations,
            'checked_at': self.checked_at,
        }


@dataclass
class AnomalyTrace:
    """Anomaly behavior trace."""
    trace_id: str
    anomaly_type: str
    detected_at: float
    source_events: List[str]
    pattern_description: str
    risk_score: float
    related_actors: List[str]
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'trace_id': self.trace_id,
            'anomaly_type': self.anomaly_type,
            'detected_at': self.detected_at,
            'source_events': self.source_events,
            'pattern_description': self.pattern_description,
            'risk_score': round(self.risk_score, 2),
            'related_actors': self.related_actors,
            'timeline': self.timeline,
        }


@dataclass
class AuditReport:
    """Comprehensive audit report."""
    report_id: str
    generated_at: float
    period_start: float
    period_end: float
    total_events: int
    severity_summary: Dict[str, int]
    compliance_results: List[ComplianceCheck]
    anomaly_traces: List[AnomalyTrace]
    top_actors: List[Dict[str, Any]]
    recommendations: List[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'report_id': self.report_id,
            'generated_at': self.generated_at,
            'period_start': datetime.fromtimestamp(self.period_start).isoformat(),
            'period_end': datetime.fromtimestamp(self.period_end).isoformat(),
            'total_events': self.total_events,
            'severity_summary': self.severity_summary,
            'compliance_results': [c.to_dict() for c in self.compliance_results],
            'anomaly_traces': [a.to_dict() for a in self.anomaly_traces],
            'top_actors': self.top_actors,
            'recommendations': self.recommendations,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class AutomatedAuditor:
    """
    Automated security audit and compliance checking system.
    
    Features:
        - Comprehensive audit event collection
        - Automated compliance rule checking
        - Anomaly behavior pattern detection
        - Detailed audit report generation
        - Audit trail maintenance and querying
    
    Usage:
        >>> auditor = AutomatedAuditor()
        >>> 
        >>> # Record audit events
        >>> auditor.record_event(
        ...     event_type="plugin_load",
        ...     source_module="runtime",
        ...     actor="system",
        ...     action="load_plugin",
        ...     target="plugin_xyz",
        ...     severity=AuditSeverity.INFO
        ... )
        >>> 
        >>> # Generate audit report
        >>> report = auditor.generate_report(period_hours=24)
        >>> print(report.to_json())
    """
    
    def __init__(
        self,
        max_events: int = 100000,
        enable_auto_compliance: bool = True,
    ):
        self.max_events = max_events
        self.enable_auto_compliance = enable_auto_compliance
        
        # Audit event storage
        self._events: List[AuditEvent] = []
        self._event_index: Dict[str, AuditEvent] = {}
        
        # Compliance rules
        self._compliance_rules: List[Dict[str, Any]] = []
        
        # Anomaly patterns
        self._anomaly_patterns: List[Dict[str, Any]] = []
        
        # Initialize default rules and patterns
        self._initialize_compliance_rules()
        self._initialize_anomaly_patterns()
        
        logger.info(
            f"AutomatedAuditor initialized: "
            f"max_events={max_events}, "
            f"auto_compliance={enable_auto_compliance}"
        )
    
    def record_event(
        self,
        event_type: str,
        source_module: str,
        actor: str,
        action: str,
        target: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """
        Record an audit event.
        
        Args:
            event_type: Type of event (e.g., "plugin_load", "api_call")
            source_module: Source module name
            actor: Who performed the action
            action: What action was performed
            target: Target of the action
            severity: Event severity level
            details: Additional event details
            metadata: Event metadata
        
        Returns:
            Recorded AuditEvent
        """
        # Generate unique event ID
        event_id = self._generate_event_id(
            event_type, source_module, actor, action, target
        )
        
        # Create event
        event = AuditEvent(
            event_id=event_id,
            timestamp=time.time(),
            event_type=event_type,
            source_module=source_module,
            actor=actor,
            action=action,
            target=target,
            severity=severity,
            details=details or {},
            metadata=metadata or {},
        )
        
        # Store event
        self._events.append(event)
        self._event_index[event_id] = event
        
        # Enforce max events limit
        if len(self._events) > self.max_events:
            # Remove oldest events
            removed = self._events[:len(self._events) - self.max_events]
            self._events = self._events[-self.max_events:]
            
            # Remove from index
            for evt in removed:
                self._event_index.pop(evt.event_id, None)
        
        logger.debug(
            f"Audit event recorded: {event_type} by {actor} "
            f"(severity={severity.value})"
        )
        
        return event
    
    def generate_report(
        self,
        period_hours: float = 24,
        include_compliance: bool = True,
        include_anomalies: bool = True,
    ) -> AuditReport:
        """
        Generate comprehensive audit report.
        
        Args:
            period_hours: Report period in hours
            include_compliance: Include compliance check results
            include_anomalies: Include anomaly traces
        
        Returns:
            AuditReport with comprehensive analysis
        """
        now = time.time()
        period_start = now - (period_hours * 3600)
        
        # Filter events for period
        period_events = [
            e for e in self._events
            if e.timestamp >= period_start
        ]
        
        # Calculate severity summary
        severity_summary = self._calculate_severity_summary(period_events)
        
        # Run compliance checks
        compliance_results = []
        if include_compliance and self.enable_auto_compliance:
            compliance_results = self._run_compliance_checks(period_events)
        
        # Detect anomalies
        anomaly_traces = []
        if include_anomalies:
            anomaly_traces = self._detect_anomalies(period_events)
        
        # Get top actors
        top_actors = self._get_top_actors(period_events)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            period_events, compliance_results, anomaly_traces
        )
        
        # Create report
        report = AuditReport(
            report_id=self._generate_report_id(),
            generated_at=now,
            period_start=period_start,
            period_end=now,
            total_events=len(period_events),
            severity_summary=severity_summary,
            compliance_results=compliance_results,
            anomaly_traces=anomaly_traces,
            top_actors=top_actors,
            recommendations=recommendations,
        )
        
        logger.info(
            f"Audit report generated: {report.report_id} "
            f"({len(period_events)} events, {period_hours}h period)"
        )
        
        return report
    
    def query_events(
        self,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        time_range: Optional[Tuple[float, float]] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        Query audit events with filters.
        
        Args:
            event_type: Filter by event type
            actor: Filter by actor
            severity: Filter by severity
            time_range: Filter by time range (start, end)
            limit: Maximum number of events to return
        
        Returns:
            List of matching AuditEvents
        """
        filtered = self._events
        
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        
        if actor:
            filtered = [e for e in filtered if e.actor == actor]
        
        if severity:
            filtered = [e for e in filtered if e.severity == severity]
        
        if time_range:
            start, end = time_range
            filtered = [e for e in filtered if start <= e.timestamp <= end]
        
        # Sort by timestamp descending (most recent first)
        filtered.sort(key=lambda e: e.timestamp, reverse=True)
        
        return filtered[:limit]
    
    def get_compliance_status(self) -> Dict[str, Any]:
        """
        Get overall compliance status.
        
        Returns:
            Dictionary with compliance summary
        """
        if not self._compliance_rules:
            return {'status': 'no_rules_configured', 'rules_count': 0}
        
        # Run all compliance checks on recent events
        recent_events = self._events[-1000:] if self._events else []
        results = self._run_compliance_checks(recent_events)
        
        passed = sum(1 for r in results if r.status == ComplianceStatus.PASS)
        failed = sum(1 for r in results if r.status == ComplianceStatus.FAIL)
        warnings = sum(1 for r in results if r.status == ComplianceStatus.WARNING)
        
        overall_status = 'compliant' if failed == 0 else 'non_compliant'
        
        return {
            'overall_status': overall_status,
            'total_rules': len(results),
            'passed': passed,
            'failed': failed,
            'warnings': warnings,
            'compliance_rate': round((passed / len(results) * 100) if results else 0, 2),
        }
    
    def _initialize_compliance_rules(self):
        """Initialize default compliance rules."""
        self._compliance_rules = [
            {
                'rule_id': 'SEC-001',
                'name': 'Plugin Signature Verification',
                'category': 'security',
                'description': 'All plugins must have valid cryptographic signatures',
                'check_fn': self._check_plugin_signatures,
            },
            {
                'rule_id': 'SEC-002',
                'name': 'API Rate Limiting',
                'category': 'security',
                'description': 'API calls must respect rate limits',
                'check_fn': self._check_api_rate_limits,
            },
            {
                'rule_id': 'SEC-003',
                'name': 'Authentication Events',
                'category': 'access_control',
                'description': 'All authentication events must be logged',
                'check_fn': self._check_auth_logging,
            },
            {
                'rule_id': 'AUD-001',
                'name': 'Audit Trail Completeness',
                'category': 'auditing',
                'description': 'Critical operations must have complete audit trails',
                'check_fn': self._check_audit_completeness,
            },
            {
                'rule_id': 'PRIV-001',
                'name': 'Data Privacy Controls',
                'category': 'privacy',
                'description': 'Sensitive data access must be logged and authorized',
                'check_fn': self._check_data_privacy,
            },
        ]
    
    def _initialize_anomaly_patterns(self):
        """Initialize anomaly detection patterns."""
        self._anomaly_patterns = [
            {
                'pattern_id': 'ANOM-001',
                'name': 'Rapid Failed Attempts',
                'description': 'Multiple failed attempts in short time window',
                'time_window': 300,  # 5 minutes
                'threshold': 10,
                'event_types': ['auth_failure', 'permission_denied'],
            },
            {
                'pattern_id': 'ANOM-002',
                'name': 'Unusual Activity Hours',
                'description': 'Activity during unusual hours',
                'time_window': 3600,  # 1 hour
                'threshold': 50,
                'event_types': ['api_call', 'data_access'],
            },
            {
                'pattern_id': 'ANOM-003',
                'name': 'Privilege Escalation Pattern',
                'description': 'Sequential privilege escalation attempts',
                'time_window': 600,  # 10 minutes
                'threshold': 5,
                'event_types': ['role_change', 'permission_grant'],
            },
        ]
    
    def _generate_event_id(
        self,
        event_type: str,
        source_module: str,
        actor: str,
        action: str,
        target: str,
    ) -> str:
        """Generate unique event ID."""
        data = f"{event_type}:{source_module}:{actor}:{action}:{target}:{time.time()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _generate_report_id(self) -> str:
        """Generate unique report ID."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"AUDIT_{timestamp}"
    
    def _calculate_severity_summary(
        self,
        events: List[AuditEvent],
    ) -> Dict[str, int]:
        """Calculate event count by severity."""
        summary = defaultdict(int)
        for event in events:
            summary[event.severity.value] += 1
        return dict(summary)
    
    def _run_compliance_checks(
        self,
        events: List[AuditEvent],
    ) -> List[ComplianceCheck]:
        """Run all compliance checks."""
        results = []
        
        for rule in self._compliance_rules:
            try:
                check_fn = rule['check_fn']
                status, findings, recommendations = check_fn(events)
                
                result = ComplianceCheck(
                    rule_id=rule['rule_id'],
                    rule_name=rule['name'],
                    category=rule['category'],
                    status=status,
                    description=rule['description'],
                    findings=findings,
                    recommendations=recommendations,
                    checked_at=time.time(),
                )
                
                results.append(result)
            except Exception as e:
                logger.error(f"Compliance check failed: {rule['rule_id']}: {e}")
        
        return results
    
    def _detect_anomalies(
        self,
        events: List[AuditEvent],
    ) -> List[AnomalyTrace]:
        """Detect anomalous behavior patterns."""
        traces = []
        
        for pattern in self._anomaly_patterns:
            try:
                trace = self._check_anomaly_pattern(events, pattern)
                if trace:
                    traces.append(trace)
            except Exception as e:
                logger.error(f"Anomaly detection failed: {pattern['pattern_id']}: {e}")
        
        return traces
    
    def _get_top_actors(
        self,
        events: List[AuditEvent],
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get most active actors."""
        actor_stats = defaultdict(lambda: {
            'event_count': 0,
            'event_types': set(),
            'severity_counts': defaultdict(int),
        })
        
        for event in events:
            stats = actor_stats[event.actor]
            stats['event_count'] += 1
            stats['event_types'].add(event.event_type)
            stats['severity_counts'][event.severity.value] += 1
        
        # Sort by event count
        sorted_actors = sorted(
            actor_stats.items(),
            key=lambda x: x[1]['event_count'],
            reverse=True,
        )
        
        # Convert sets to lists for JSON serialization
        result = []
        for actor, stats in sorted_actors[:top_n]:
            result.append({
                'actor': actor,
                'event_count': stats['event_count'],
                'event_types': list(stats['event_types']),
                'severity_counts': dict(stats['severity_counts']),
            })
        
        return result
    
    def _generate_recommendations(
        self,
        events: List[AuditEvent],
        compliance_results: List[ComplianceCheck],
        anomaly_traces: List[AnomalyTrace],
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Check for compliance failures
        failed_rules = [r for r in compliance_results if r.status == ComplianceStatus.FAIL]
        if failed_rules:
            recommendations.append(
                f"Address {len(failed_rules)} failed compliance rules: "
                + ", ".join(r.rule_name for r in failed_rules[:3])
            )
        
        # Check for anomalies
        if anomaly_traces:
            high_risk = [t for t in anomaly_traces if t.risk_score > 0.7]
            if high_risk:
                recommendations.append(
                    f"Investigate {len(high_risk)} high-risk anomaly patterns"
                )
        
        # Check for high-severity events
        critical_events = [e for e in events if e.severity == AuditSeverity.CRITICAL]
        if critical_events:
            recommendations.append(
                f"Review {len(critical_events)} critical security events"
            )
        
        # General recommendations
        if len(events) > 1000:
            recommendations.append("Consider increasing audit retention period")
        
        recommendations.append("Schedule regular compliance reviews")
        recommendations.append("Update anomaly detection patterns quarterly")
        
        return recommendations
    
    # Compliance check implementations
    
    def _check_plugin_signatures(
        self,
        events: List[AuditEvent],
    ) -> Tuple[ComplianceStatus, List[str], List[str]]:
        """Check plugin signature verification compliance."""
        plugin_events = [e for e in events if e.event_type == 'plugin_load']
        
        if not plugin_events:
            return ComplianceStatus.NOT_APPLICABLE, [], []
        
        unsigned_plugins = [
            e for e in plugin_events
            if not e.details.get('signature_verified', False)
        ]
        
        if unsigned_plugins:
            findings = [f"Found {len(unsigned_plugins)} unsigned plugin loads"]
            recommendations = ["Enforce signature verification for all plugins"]
            return ComplianceStatus.FAIL, findings, recommendations
        
        return ComplianceStatus.PASS, ["All plugins verified"], []
    
    def _check_api_rate_limits(
        self,
        events: List[AuditEvent],
    ) -> Tuple[ComplianceStatus, List[str], List[str]]:
        """Check API rate limiting compliance."""
        api_events = [e for e in events if e.event_type == 'api_call']
        
        if not api_events:
            return ComplianceStatus.NOT_APPLICABLE, [], []
        
        rate_limited = [
            e for e in api_events
            if e.details.get('rate_limited', False)
        ]
        
        if len(rate_limited) > len(api_events) * 0.1:  # More than 10%
            findings = [f"High rate limiting: {len(rate_limited)}/{len(api_events)} calls"]
            recommendations = ["Review API usage patterns and adjust limits"]
            return ComplianceStatus.WARNING, findings, recommendations
        
        return ComplianceStatus.PASS, ["Rate limits within acceptable range"], []
    
    def _check_auth_logging(
        self,
        events: List[AuditEvent],
    ) -> Tuple[ComplianceStatus, List[str], List[str]]:
        """Check authentication event logging."""
        auth_events = [
            e for e in events
            if e.event_type in ['login', 'logout', 'auth_failure']
        ]
        
        if not auth_events:
            return ComplianceStatus.WARNING, ["No authentication events found"], \
                   ["Verify authentication logging is enabled"]
        
        return ComplianceStatus.PASS, [f"Logged {len(auth_events)} auth events"], []
    
    def _check_audit_completeness(
        self,
        events: List[AuditEvent],
    ) -> Tuple[ComplianceStatus, List[str], List[str]]:
        """Check audit trail completeness."""
        critical_actions = ['delete', 'modify_permissions', 'change_config']
        
        incomplete = []
        for event in events:
            if any(action in event.action for action in critical_actions):
                if not event.details.get('audit_complete', True):
                    incomplete.append(event)
        
        if incomplete:
            findings = [f"Found {len(incomplete)} incomplete audit trails"]
            recommendations = ["Ensure all critical operations have complete audit trails"]
            return ComplianceStatus.FAIL, findings, recommendations
        
        return ComplianceStatus.PASS, ["All critical operations fully audited"], []
    
    def _check_data_privacy(
        self,
        events: List[AuditEvent],
    ) -> Tuple[ComplianceStatus, List[str], List[str]]:
        """Check data privacy controls."""
        sensitive_access = [
            e for e in events
            if e.details.get('sensitive_data', False)
        ]
        
        unauthorized = [
            e for e in sensitive_access
            if not e.details.get('authorized', True)
        ]
        
        if unauthorized:
            findings = [f"Found {len(unauthorized)} unauthorized sensitive data accesses"]
            recommendations = ["Review and enforce data access controls"]
            return ComplianceStatus.FAIL, findings, recommendations
        
        return ComplianceStatus.PASS, ["All sensitive data access authorized"], []
    
    def _check_anomaly_pattern(
        self,
        events: List[AuditEvent],
        pattern: Dict[str, Any],
    ) -> Optional[AnomalyTrace]:
        """Check for specific anomaly pattern."""
        # Filter relevant events
        relevant_events = [
            e for e in events
            if e.event_type in pattern['event_types']
        ]
        
        if not relevant_events:
            return None
        
        # Group by time windows
        now = time.time()
        window_start = now - pattern['time_window']
        
        window_events = [
            e for e in relevant_events
            if e.timestamp >= window_start
        ]
        
        if len(window_events) < pattern['threshold']:
            return None
        
        # Pattern detected
        actors = list(set(e.actor for e in window_events))
        
        trace = AnomalyTrace(
            trace_id=f"{pattern['pattern_id']}_{int(now)}",
            anomaly_type=pattern['name'],
            detected_at=now,
            source_events=[e.event_id for e in window_events[:10]],
            pattern_description=pattern['description'],
            risk_score=min(1.0, len(window_events) / (pattern['threshold'] * 2)),
            related_actors=actors,
            timeline=[e.to_dict() for e in window_events[:5]],
        )
        
        logger.warning(
            f"Anomaly detected: {pattern['name']} "
            f"(risk_score={trace.risk_score:.2f})"
        )
        
        return trace
