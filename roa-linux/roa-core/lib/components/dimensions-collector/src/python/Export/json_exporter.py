"""
JSON Exporter - Export tracking data to JSON files
"""

from typing import Dict
import json
import logging
from pathlib import Path
from datetime import datetime


class JsonExporter:
    """
    Exports tracking data to JSON format
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize JSON exporter
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger('DIMC.JsonExporter')
        
        self.enabled = self.config.get('enabled', True)
        self.retention_days = self.config.get('retention_days', 30)
        self.include_task_summary = self.config.get('include_task_summary', True)
        
        self.logger.info(f"JsonExporter initialized (retention: {self.retention_days} days)")
    
    def export(self, robot_data: Dict, filename: str) -> bool:
        """
        Export data to JSON file
        
        Args:
            robot_data: Dictionary of robot tracking data
            filename: Output filename
            
        Returns:
            True if export successful
        """
        if not self.enabled:
            self.logger.info("JSON export disabled")
            return False
        
        try:
            self.logger.info(f"Exporting to JSON: {filename}")
            
            # Prepare export data
            export_data = {
                'metadata': {
                    'export_time': datetime.now().isoformat(),
                    'robot_count': len(robot_data),
                    'version': '1.0.0'
                },
                'robots': {}
            }
            
            # Convert robot data to JSON-serializable format
            for robot_id, data in robot_data.items():
                robot_summary = {
                    'robot_id': robot_id,
                    'registered_at': data.get('registered_at'),
                    'last_update': data.get('last_update'),
                    'dimensions': data.get('dimensions', {})
                }
                
                # Add current state if available
                if 'current_state' in data:
                    state = data['current_state']
                    robot_summary['last_position'] = {
                        'x': state['position'][0],
                        'y': state['position'][1],
                        'z': state['position'][2]
                    }
                    robot_summary['last_orientation'] = {
                        'x': state['orientation'][0],
                        'y': state['orientation'][1],
                        'z': state['orientation'][2],
                        'w': state['orientation'][3]
                    }
                    robot_summary['last_velocity'] = {
                        'vx': state['velocity'][0],
                        'vy': state['velocity'][1],
                        'vz': state['velocity'][2]
                    }
                
                export_data['robots'][robot_id] = robot_summary
            
            # Write to file
            output_path = Path(filename)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            self.logger.info(f"Successfully exported to {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"JSON export failed: {e}")
            return False
