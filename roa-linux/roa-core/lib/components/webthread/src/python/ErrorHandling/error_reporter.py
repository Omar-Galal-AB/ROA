"""
error_reporter.py
ROA - Robot Operations & Automation
Error reporting system
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List


class ErrorReporter:
    """Reports errors to various outputs"""

    def __init__(self, report_dir: str = "./Logs/errors"):
        """
        Initialize Error Reporter

        Args:
            report_dir: Directory for error reports
        """
        self.logger = logging.getLogger(__name__)
        self.report_dir = report_dir

        os.makedirs(report_dir, exist_ok=True)
        self.logger.info("ErrorReporter initialized")

    def generate_error_report(self, errors: List, filename: Optional[str] = None) -> str:
        """
        Generate error report

        Args:
            errors: List of errors
            filename: Optional filename

        Returns:
            Path to generated report
        """
        if filename is None:
            filename = f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join(self.report_dir, filename)

        try:
            report_data = {
                "generated_at": datetime.now().isoformat(),
                "error_count": len(errors),
                "errors": [self._error_to_dict(e) for e in errors],
            }

            with open(filepath, "w") as f:
                json.dump(report_data, f, indent=2, default=str)

            self.logger.info(f"Generated error report: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to generate error report: {e}")
            return ""

    def _error_to_dict(self, error) -> Dict:
        """Convert error to dictionary"""
        return {
            "timestamp": (
                error.timestamp.isoformat()
                if hasattr(error.timestamp, "isoformat")
                else str(error.timestamp)
            ),
            "severity": (
                error.severity.value if hasattr(error.severity, "value") else str(error.severity)
            ),
            "source": error.source,
            "message": error.message,
            "details": error.details,
        }

    def report_to_console(self, errors: List):
        """Report errors to console"""
        print(f"\n=== Error Report ({len(errors)} errors) ===")
        for error in errors:
            print(f"[{error.severity.value.upper()}] {error.source}: {error.message}")
        print("=" * 50)

    def report_to_user(self, error):
        """Report error to user (UI notification)"""
        # TODO: Implement UI notification
        self.logger.warning(f"User notification: {error.message}")
