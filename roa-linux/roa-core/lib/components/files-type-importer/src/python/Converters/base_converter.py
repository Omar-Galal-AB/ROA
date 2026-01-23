"""
Base Converter - Abstract base class for all format converters

Provides:
- Proper logging integration
- Progress reporting support
- Configuration management
- Error handling patterns
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
import time

# Try to import progress reporter
try:
    from Utils.progress_reporter import ProgressReporter, ProgressStage, ProgressInfo
    PROGRESS_AVAILABLE = True
except ImportError:
    try:
        from ..Utils.progress_reporter import ProgressReporter, ProgressStage, ProgressInfo
        PROGRESS_AVAILABLE = True
    except ImportError:
        PROGRESS_AVAILABLE = False
        ProgressReporter = None
        ProgressStage = None


@dataclass
class ConversionResult:
    """Result of a format conversion operation."""
    success: bool
    output_path: Optional[str] = None
    format: Optional[str] = None
    parts: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    conversion_time_ms: float = 0.0
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize mutable default values for backwards compatibility."""
        if self.parts is None:
            self.parts = []
        if self.materials is None:
            self.materials = []
        if self.warnings is None:
            self.warnings = []
        if self.stats is None:
            self.stats = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'success': self.success,
            'output_path': self.output_path,
            'format': self.format,
            'parts_count': len(self.parts),
            'materials_count': len(self.materials),
            'error_message': self.error_message,
            'warnings': self.warnings,
            'conversion_time_ms': round(self.conversion_time_ms, 2),
            'stats': self.stats
        }


class BaseConverter(ABC):
    """
    Abstract base class for all format converters.
    
    All format-specific converters should inherit from this class
    and implement the convert() method.
    
    Features:
    - Proper Python logging (not print statements)
    - Progress reporting integration
    - Typed configuration
    - Conversion timing
    - Error categorization
    """
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        progress_callback: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the converter.
        
        Args:
            config: Optional configuration dictionary
            progress_callback: Optional callback for progress updates
            logger: Optional logger instance (creates one if not provided)
        """
        self.config = config or {}
        self.supported_extensions: List[str] = []
        
        # Set up proper logging
        self._logger = logger or logging.getLogger(f"fti.{self.__class__.__name__}")
        
        # Progress reporting
        self._progress_callback = progress_callback
        self._progress_reporter: Optional['ProgressReporter'] = None
        
        if PROGRESS_AVAILABLE and progress_callback:
            self._progress_reporter = ProgressReporter(callback=progress_callback)
        
        # Conversion timing
        self._start_time: Optional[float] = None
    
    @property
    def logger(self) -> logging.Logger:
        """Get the logger instance."""
        return self._logger
    
    @abstractmethod
    def convert(
        self,
        input_path: str,
        output_path: str,
        robot_name: str
    ) -> ConversionResult:
        """
        Convert a 3D model file to USD format.
        
        Args:
            input_path: Path to the input file
            output_path: Path for the output USD file
            robot_name: Name of the robot
            
        Returns:
            ConversionResult with operation details
        """
        pass
    
    def validate_input(self, input_path: str) -> bool:
        """
        Validate that the input file exists and is readable.
        
        Args:
            input_path: Path to the input file
            
        Returns:
            True if valid, False otherwise
        """
        path = Path(input_path)
        if not path.exists():
            self._log_error(f"Input file does not exist: {input_path}")
            return False
        if not path.is_file():
            self._log_error(f"Input path is not a file: {input_path}")
            return False
        return True
    
    def validate_output(self, output_path: str) -> bool:
        """
        Validate the output file after conversion.
        
        Args:
            output_path: Path to the output file
            
        Returns:
            True if valid, False otherwise
        """
        if not output_path:
            self._log_error("Output path is empty")
            return False
        
        path = Path(output_path)
        if not path.exists():
            self._log_error(f"Output file not created: {output_path}")
            return False
        
        # Check if file is not empty
        if path.stat().st_size == 0:
            self._log_error(f"Output file is empty: {output_path}")
            return False
        
        return True
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of file extensions supported by this converter.
        
        Returns:
            List of file extensions (e.g., ['.urdf', '.xacro'])
        """
        return self.supported_extensions
    
    # ==================== Logging Methods ====================
    
    def _log_debug(self, message: str, **extra):
        """Log a debug message."""
        self._logger.debug(message, extra=extra)
    
    def _log_info(self, message: str, **extra):
        """Log an informational message."""
        self._logger.info(message, extra=extra)
    
    def _log_warning(self, message: str, **extra):
        """Log a warning message."""
        self._logger.warning(message, extra=extra)
    
    def _log_error(self, message: str, **extra):
        """Log an error message."""
        self._logger.error(message, extra=extra)
    
    # ==================== Progress Reporting ====================
    
    def _start_progress(self, message: str = "Starting conversion"):
        """Start progress tracking."""
        self._start_time = time.time()
        
        if self._progress_reporter:
            self._progress_reporter.start(message)
        else:
            self._log_info(message)
    
    def _update_progress(
        self,
        stage: Optional['ProgressStage'] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None
    ):
        """Update conversion progress."""
        if self._progress_reporter:
            if stage:
                self._progress_reporter.set_stage(stage, message)
            else:
                self._progress_reporter.update(progress, message)
        elif message:
            self._log_debug(message)
    
    def _set_progress_stage(self, stage: 'ProgressStage', message: Optional[str] = None):
        """Set the current progress stage."""
        if self._progress_reporter and PROGRESS_AVAILABLE:
            self._progress_reporter.set_stage(stage, message)
        elif message:
            self._log_info(message)
    
    def _complete_progress(self, message: str = "Conversion completed"):
        """Mark progress as complete."""
        if self._progress_reporter:
            self._progress_reporter.complete(message)
        else:
            self._log_info(message)
    
    def _fail_progress(self, error_message: str):
        """Mark progress as failed."""
        if self._progress_reporter:
            self._progress_reporter.fail(error_message)
        else:
            self._log_error(error_message)
    
    def _get_elapsed_time_ms(self) -> float:
        """Get elapsed time since start in milliseconds."""
        if self._start_time is None:
            return 0.0
        return (time.time() - self._start_time) * 1000
    
    # ==================== Utility Context Managers ====================
    
    @contextmanager
    def conversion_context(self, input_path: str, output_path: str):
        """
        Context manager for conversion operations.
        
        Handles timing, logging, and progress updates.
        
        Usage:
            with self.conversion_context(input_path, output_path):
                # do conversion work
        """
        self._start_time = time.time()
        self._log_info(f"Starting conversion: {input_path} -> {output_path}")
        
        try:
            yield
        except Exception as e:
            self._log_error(f"Conversion failed: {e}")
            raise
        finally:
            elapsed = self._get_elapsed_time_ms()
            self._log_debug(f"Conversion took {elapsed:.2f}ms")
    
    # ==================== Configuration Helpers ====================
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value with a default.
        
        Args:
            key: Configuration key
            default: Default value if not set
            
        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
    
    def get_scale_factor(self) -> float:
        """Get the scale factor from config."""
        return self.get_config_value('scale_factor', 1.0)
