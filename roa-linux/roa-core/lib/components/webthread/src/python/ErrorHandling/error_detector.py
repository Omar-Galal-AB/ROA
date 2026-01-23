"""
error_detector.py
ROA - Robot Operations & Automation
Error detection system
"""

import logging
from typing import Dict, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class ErrorSeverity(Enum):
    """Error severity levels"""
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class DetectedError:
    """Detected error information"""
    timestamp: datetime
    severity: ErrorSeverity
    source: str
    message: str
    details: Dict


class ErrorDetector:
    """Detects and classifies errors"""

    def __init__(self):
        """Initialize Error Detector"""
        self.logger = logging.getLogger(__name__)
        self.detected_errors: List[DetectedError] = []
        self.error_callbacks: List[Callable] = []
        
        self.logger.info("ErrorDetector initialized")

    def detect_error(self, source: str, message: str, 
                    severity: ErrorSeverity = ErrorSeverity.ERROR,
                    details: Optional[Dict] = None) -> DetectedError:
        """
        Detect and record an error
        
        Args:
            source: Error source
            message: Error message
            severity: Error severity
            details: Additional details
            
        Returns:
            DetectedError object
        """
        error = DetectedError(
            timestamp=datetime.now(),
            severity=severity,
            source=source,
            message=message,
            details=details or {}
        )
        
        self.detected_errors.append(error)
        self.logger.log(
            self._severity_to_log_level(severity),
            f"{source}: {message}"
        )
        
        # Notify callbacks
        for callback in self.error_callbacks:
            try:
                callback(error)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")
        
        return error

    def _severity_to_log_level(self, severity: ErrorSeverity) -> int:
        """Convert severity to logging level"""
        mapping = {
            ErrorSeverity.CRITICAL: logging.CRITICAL,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.INFO: logging.INFO,
        }
        return mapping.get(severity, logging.INFO)

    def register_error_callback(self, callback: Callable):
        """Register callback for error notifications"""
        self.error_callbacks.append(callback)

    def get_errors(self, severity: Optional[ErrorSeverity] = None) -> List[DetectedError]:
        """Get detected errors, optionally filtered by severity"""
        if severity is None:
            return self.detected_errors.copy()
        return [e for e in self.detected_errors if e.severity == severity]

    def clear_errors(self):
        """Clear error history"""
        self.detected_errors.clear()
        self.logger.info("Cleared error history")
