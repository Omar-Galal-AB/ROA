"""
CSV Exporter - Export tracking data to CSV files
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class CsvExporter:
    """
    Exports tracking data to CSV format
    """

    def __init__(self, config: Dict = None):
        """
        Initialize CSV exporter

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger("DIMC.CsvExporter")

        self.enabled = self.config.get("enabled", False)  # Disabled by default
        self.fields = self.config.get(
            "fields", ["timestamp", "robot_id", "x", "y", "z", "vx", "vy", "vz"]
        )

        self.logger.info(f"CsvExporter initialized (enabled: {self.enabled})")

    def export(self, robot_data: Dict, filename: str) -> bool:
        """
        Export data to CSV file

        Args:
            robot_data: Dictionary of robot tracking data
            filename: Output filename

        Returns:
            True if export successful
        """
        if not self.enabled:
            self.logger.info("CSV export disabled")
            return False

        try:
            self.logger.info(f"Exporting to CSV: {filename}")

            # Prepare CSV rows
            rows: List[Dict] = []

            for robot_id, data in robot_data.items():
                if "current_state" not in data:
                    continue

                state = data["current_state"]
                row = {
                    "timestamp": data.get("last_update", 0.0),
                    "robot_id": robot_id,
                    "x": state["position"][0],
                    "y": state["position"][1],
                    "z": state["position"][2],
                    "vx": state["velocity"][0],
                    "vy": state["velocity"][1],
                    "vz": state["velocity"][2],
                }
                rows.append(row)

            # Write to file
            output_path = Path(filename)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fields)
                writer.writeheader()
                writer.writerows(rows)

            self.logger.info(f"Successfully exported {len(rows)} rows to {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"CSV export failed: {e}")
            return False
