"""
log_viewer.py
ROA - Robot Operations & Automation
Log viewing utilities
"""

import logging
from typing import List, Optional


class LogViewer:
    """Utilities for viewing and analyzing logs"""

    def __init__(self):
        """Initialize Log Viewer"""
        self.logger = logging.getLogger(__name__)

    def view_log(self, log_file: str, num_lines: int = 50) -> List[str]:
        """
        View recent lines from a log file
        
        Args:
            log_file: Path to log file
            num_lines: Number of recent lines to view
            
        Returns:
            List of log lines
        """
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                return lines[-num_lines:]
        except Exception as e:
            self.logger.error(f"Failed to read log file: {e}")
            return []

    def search_log(self, log_file: str, search_term: str) -> List[str]:
        """
        Search for term in log file
        
        Args:
            log_file: Path to log file
            search_term: Term to search for
            
        Returns:
            List of matching lines
        """
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                return [line for line in lines if search_term in line]
        except Exception as e:
            self.logger.error(f"Failed to search log file: {e}")
            return []
