"""
Sensory Data Cleaner / 感官数据清洗器

Implements injection filtering and signal sanitization for external sensory inputs.
Protects the cognitive system from prompt injection and malicious signals.

实现外部感官输入的注入过滤和信号清洗。
保护认知系统免受提示注入和恶意信号的影响。
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zentex.environment.models import SanitizedSignal


# Common prompt injection patterns to detect
INJECTION_PATTERNS = [
    "ignore all previous instructions",
    "ignore previous instructions",
    "execute this command",
    "system prompt",
    "developer message",
    "override security",
    "bypass restrictions",
    "disable safety",
    "you are now",
    "pretend to be",
    "act as if",
]


class SensoryDataCleaner:
    """
    Cleans and sanitizes sensory data from external sources.
    
    感官数据清洗器，清洗和消毒来自外部源的感官数据。
    
    Applies multiple layers of filtering to detect and neutralize potential
    prompt injection attacks, malicious content, and other security threats
    in sensory signals before they enter the cognitive processing pipeline.
    
    应用多层过滤来检测和中和感官信号中的潜在提示注入攻击、
    恶意内容和其他安全威胁，然后才进入认知处理管道。
    """
    
    def __init__(
        self,
        *,
        max_signal_length: int = 10000,
        enable_injection_detection: bool = True,
        redaction_marker: str = "[REDACTED]",
    ) -> None:
        """
        Initialize the SensoryDataCleaner.
        
        Args:
            max_signal_length: Maximum allowed signal length (truncated if exceeded)
            enable_injection_detection: Whether to enable prompt injection detection
            redaction_marker: Marker string used to replace redacted content
        """
        self.max_signal_length = max_signal_length
        self.enable_injection_detection = enable_injection_detection
        self.redaction_marker = redaction_marker
    
    def sanitize_signal(
        self,
        raw_signal: str,
        source_plugin_id: str | None = None,
        source_kind: str | None = None,
    ) -> SanitizedSignal:
        """
        Sanitize a raw sensory signal.
        
        清洗原始感官信号。
        
        Args:
            raw_signal: The raw signal content to sanitize
            source_plugin_id: ID of the plugin that provided this signal
            source_kind: Type of source (webhook, file, api, etc.)
            
        Returns:
            SanitizedSignal: Cleaned signal with security assessment
            
        Processing Steps:
            1. Generate fingerprint of original signal for audit trail
            2. Detect and redact prompt injection attempts
            3. Truncate excessively long signals
            4. Remove potentially dangerous content patterns
            5. Calculate confidence score for sanitization quality
        """
        # Generate fingerprint of original signal
        original_fingerprint = hashlib.sha256(raw_signal.encode("utf-8")).hexdigest()
        
        # Start with normalized signal
        sanitized_text = raw_signal.strip()
        
        # Detect and handle injection risks
        injection_risk = False
        redaction_evidence = []
        
        if self.enable_injection_detection:
            sanitized_text, injection_risk, redaction_evidence = self._detect_and_redact_injections(
                sanitized_text
            )
        
        # Truncate if too long
        if len(sanitized_text) > self.max_signal_length:
            sanitized_text = sanitized_text[: self.max_signal_length]
            redaction_evidence.append(f"Truncated from {len(raw_signal)} to {self.max_signal_length} chars")
        
        # Ensure non-empty result
        if not sanitized_text:
            sanitized_text = "[EMPTY_AFTER_SANITIZATION]"
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(
            injection_risk, len(redaction_evidence), len(raw_signal)
        )
        
        return SanitizedSignal(
            signal_id=str(uuid4()),
            original_fingerprint=original_fingerprint,
            sanitized_content=sanitized_text,
            injection_risk=injection_risk,
            redaction_evidence=redaction_evidence,
            confidence_score=confidence_score,
            source_plugin_id=source_plugin_id,
            source_kind=source_kind,
        )
    
    def _detect_and_redact_injections(
        self, text: str
    ) -> tuple[str, bool, list[str]]:
        """
        Detect and redact prompt injection attempts.
        
        检测并编辑提示注入尝试。
        
        Args:
            text: Text to analyze for injection patterns
            
        Returns:
            Tuple of (sanitized_text, injection_detected, evidence_list)
        """
        lowered = text.lower()
        detected_patterns = []
        
        # Check for known injection patterns
        for pattern in INJECTION_PATTERNS:
            if pattern in lowered:
                detected_patterns.append(pattern)
        
        injection_detected = len(detected_patterns) > 0
        
        # Redact detected patterns
        sanitized = text
        for pattern in detected_patterns:
            # Case-insensitive replacement
            sanitized = re.sub(
                re.escape(pattern),
                self.redaction_marker,
                sanitized,
                flags=re.IGNORECASE,
            )
        
        # Additional heuristic: check for suspicious command-like structures
        if self._contains_suspicious_commands(text):
            if not injection_detected:
                injection_detected = True
            sanitized = self._redact_suspicious_commands(sanitized)
            detected_patterns.append("suspicious_command_structure")
        
        return sanitized, injection_detected, detected_patterns
    
    def _contains_suspicious_commands(self, text: str) -> bool:
        """
        Check if text contains suspicious command-like structures.
        
        检查文本是否包含可疑的命令式结构。
        
        This is a heuristic check for patterns that might indicate
        attempt to execute commands or override behavior.
        """
        suspicious_patterns = [
            r"!?\s*(rm|delete|drop|truncate)\s+",
            r"!?\s*(exec|execute|run)\s+.*\.(sh|bash|py|js)",
            r"__import__\s*\(",
            r"eval\s*\(",
            r"exec\s*\(",
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _redact_suspicious_commands(self, text: str) -> str:
        """
        Redact suspicious command patterns from text.
        
        从文本中编辑可疑命令模式。
        """
        # Replace dangerous function calls
        text = re.sub(r"(__import__|eval|exec)\s*\(", f"{self.redaction_marker}(", text)
        
        # Replace shell command attempts
        text = re.sub(r"(!?\s*(rm|delete|drop|truncate)\s+\S+)", self.redaction_marker, text)
        
        return text
    
    def _calculate_confidence_score(
        self,
        injection_detected: bool,
        redaction_count: int,
        original_length: int,
    ) -> float:
        """
        Calculate confidence score for sanitization quality.
        
        计算清洗质量的置信度分数。
        
        Higher score means higher confidence that sanitization was effective.
        Score decreases with more redactions and injections detected.
        """
        base_score = 1.0
        
        # Penalize for injection detection
        if injection_detected:
            base_score -= 0.3
        
        # Penalize for each redaction
        base_score -= min(0.4, redaction_count * 0.1)
        
        # Slight penalty for very long signals (harder to fully sanitize)
        if original_length > 5000:
            base_score -= 0.1
        
        return max(0.0, min(1.0, base_score))
    
    def batch_sanitize(
        self,
        signals: list[str],
        source_plugin_id: str | None = None,
        source_kind: str | None = None,
    ) -> list[SanitizedSignal]:
        """
        Sanitize multiple signals in batch.
        
        批量清洗多个信号。
        
        Args:
            signals: List of raw signal strings
            source_plugin_id: ID of the plugin that provided these signals
            source_kind: Type of source
            
        Returns:
            List of sanitized signals
        """
        return [
            self.sanitize_signal(signal, source_plugin_id, source_kind)
            for signal in signals
        ]
