"""
logger.py
ROA - Robot Operations & Automation
Main logging system
"""

import logging
import os
from datetime import datetime


def setup_roa_logger(name: str = "ROA", log_dir: str = "./Logs", level=logging.INFO):
    """
    Setup ROA logging system

    Args:
        name: Logger name
        log_dir: Directory for log files
        level: Logging level

    Returns:
        Logger instance
    """
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Create formatters
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_formatter = logging.Formatter("%(levelname)s - %(message)s")

    # File handler
    log_file = os.path.join(log_dir, f"roa_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
