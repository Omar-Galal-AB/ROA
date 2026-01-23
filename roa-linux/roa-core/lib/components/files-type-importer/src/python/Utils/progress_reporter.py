"""
Progress Reporting Utilities for FTI

Provides progress tracking, callbacks, and reporting for long-running
conversion operations.
"""

import time
import threading
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum


class ProgressStage(Enum):
    """Stages of the conversion process."""
    INITIALIZING = "initializing"
    LOADING = "loading"
    PARSING = "parsing"
    VALIDATING = "validating"
    CONVERTING = "converting"
    OPTIMIZING = "optimizing"
    GENERATING_MATERIALS = "generating_materials"
    GENERATING_GEOMETRY = "generating_geometry"
    SAVING = "saving"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProgressInfo:
    """Information about current progress."""
    stage: ProgressStage
    stage_progress: float  # 0.0 - 1.0
    overall_progress: float  # 0.0 - 1.0
    message: str
    elapsed_time: float
    estimated_remaining: Optional[float] = None
    current_item: Optional[str] = None
    items_processed: int = 0
    items_total: int = 0
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'stage': self.stage.value,
            'stage_progress': round(self.stage_progress, 3),
            'overall_progress': round(self.overall_progress, 3),
            'message': self.message,
            'elapsed_time': round(self.elapsed_time, 2),
            'estimated_remaining': round(self.estimated_remaining, 2) if self.estimated_remaining else None,
            'current_item': self.current_item,
            'items_processed': self.items_processed,
            'items_total': self.items_total,
            'warnings': self.warnings
        }


class ProgressReporter:
    """
    Tracks and reports progress for conversion operations.
    
    Features:
    - Stage-based progress tracking
    - Callback notifications
    - ETA estimation
    - Thread-safe updates
    - Multiple output modes (callback, console, silent)
    
    Usage:
        reporter = ProgressReporter(callback=my_callback)
        reporter.start()
        
        reporter.set_stage(ProgressStage.LOADING, "Loading URDF file")
        reporter.update(0.5, "Parsing robot structure")
        
        reporter.set_stage(ProgressStage.CONVERTING, "Converting meshes")
        reporter.set_total_items(10)
        for i in range(10):
            reporter.item_completed(f"mesh_{i}")
        
        reporter.complete()
    """
    
    # Stage weights for overall progress calculation
    STAGE_WEIGHTS = {
        ProgressStage.INITIALIZING: 0.02,
        ProgressStage.LOADING: 0.10,
        ProgressStage.PARSING: 0.08,
        ProgressStage.VALIDATING: 0.05,
        ProgressStage.CONVERTING: 0.35,
        ProgressStage.OPTIMIZING: 0.15,
        ProgressStage.GENERATING_MATERIALS: 0.10,
        ProgressStage.GENERATING_GEOMETRY: 0.10,
        ProgressStage.SAVING: 0.04,
        ProgressStage.FINALIZING: 0.01,
    }
    
    def __init__(
        self,
        callback: Optional[Callable[[ProgressInfo], None]] = None,
        console_output: bool = False,
        update_interval: float = 0.1
    ):
        """
        Initialize the progress reporter.
        
        Args:
            callback: Function to call on progress updates
            console_output: Whether to print progress to console
            update_interval: Minimum seconds between updates
        """
        self._callback = callback
        self._console_output = console_output
        self._update_interval = update_interval
        
        self._start_time: Optional[float] = None
        self._stage: ProgressStage = ProgressStage.INITIALIZING
        self._stage_progress: float = 0.0
        self._message: str = ""
        
        self._items_processed: int = 0
        self._items_total: int = 0
        self._current_item: Optional[str] = None
        
        self._warnings: List[str] = []
        self._last_update_time: float = 0.0
        
        self._lock = threading.Lock()
        self._completed_stages: List[ProgressStage] = []
    
    def start(self, message: str = "Starting conversion"):
        """Start progress tracking."""
        with self._lock:
            self._start_time = time.time()
            self._stage = ProgressStage.INITIALIZING
            self._stage_progress = 0.0
            self._message = message
            self._items_processed = 0
            self._items_total = 0
            self._warnings = []
            self._completed_stages = []
        
        self._notify()
    
    def set_stage(
        self, 
        stage: ProgressStage, 
        message: Optional[str] = None
    ):
        """
        Move to a new stage.
        
        Args:
            stage: The new stage
            message: Optional message to display
        """
        with self._lock:
            # Mark previous stage as completed
            if self._stage != stage and self._stage not in self._completed_stages:
                self._completed_stages.append(self._stage)
            
            self._stage = stage
            self._stage_progress = 0.0
            self._items_processed = 0
            self._items_total = 0
            self._current_item = None
            
            if message:
                self._message = message
            else:
                self._message = f"Stage: {stage.value}"
        
        self._notify()
    
    def update(
        self,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        current_item: Optional[str] = None
    ):
        """
        Update progress within current stage.
        
        Args:
            progress: Stage progress (0.0 - 1.0)
            message: Optional message update
            current_item: Optional current item being processed
        """
        with self._lock:
            if progress is not None:
                self._stage_progress = min(1.0, max(0.0, progress))
            if message is not None:
                self._message = message
            if current_item is not None:
                self._current_item = current_item
        
        self._notify()
    
    def set_total_items(self, total: int):
        """Set the total number of items to process in current stage."""
        with self._lock:
            self._items_total = total
            self._items_processed = 0
    
    def item_completed(self, item_name: Optional[str] = None):
        """Mark an item as completed."""
        with self._lock:
            self._items_processed += 1
            self._current_item = item_name
            
            if self._items_total > 0:
                self._stage_progress = self._items_processed / self._items_total
        
        self._notify()
    
    def add_warning(self, warning: str):
        """Add a warning message."""
        with self._lock:
            self._warnings.append(warning)
    
    def complete(self, message: str = "Conversion completed"):
        """Mark the operation as complete."""
        with self._lock:
            self._completed_stages.append(self._stage)
            self._stage = ProgressStage.COMPLETED
            self._stage_progress = 1.0
            self._message = message
        
        self._notify(force=True)
    
    def fail(self, error_message: str):
        """Mark the operation as failed."""
        with self._lock:
            self._stage = ProgressStage.FAILED
            self._message = error_message
        
        self._notify(force=True)
    
    def get_progress(self) -> ProgressInfo:
        """Get current progress information."""
        with self._lock:
            overall = self._calculate_overall_progress()
            elapsed = time.time() - self._start_time if self._start_time else 0.0
            eta = self._estimate_remaining(overall, elapsed)
            
            return ProgressInfo(
                stage=self._stage,
                stage_progress=self._stage_progress,
                overall_progress=overall,
                message=self._message,
                elapsed_time=elapsed,
                estimated_remaining=eta,
                current_item=self._current_item,
                items_processed=self._items_processed,
                items_total=self._items_total,
                warnings=list(self._warnings)
            )
    
    def _calculate_overall_progress(self) -> float:
        """Calculate overall progress based on completed stages."""
        total = 0.0
        
        # Add completed stage weights
        for stage in self._completed_stages:
            total += self.STAGE_WEIGHTS.get(stage, 0.0)
        
        # Add current stage partial progress
        current_weight = self.STAGE_WEIGHTS.get(self._stage, 0.0)
        total += current_weight * self._stage_progress
        
        return min(1.0, total)
    
    def _estimate_remaining(self, overall: float, elapsed: float) -> Optional[float]:
        """Estimate remaining time based on progress."""
        if overall <= 0.0 or elapsed <= 0.0:
            return None
        
        if overall >= 1.0:
            return 0.0
        
        # Simple linear estimation
        rate = overall / elapsed
        remaining = (1.0 - overall) / rate
        
        return remaining
    
    def _notify(self, force: bool = False):
        """Send progress notification."""
        current_time = time.time()
        
        # Rate limit updates
        if not force and (current_time - self._last_update_time) < self._update_interval:
            return
        
        self._last_update_time = current_time
        progress = self.get_progress()
        
        # Console output
        if self._console_output:
            self._print_progress(progress)
        
        # Callback
        if self._callback:
            try:
                self._callback(progress)
            except Exception as e:
                print(f"Progress callback error: {e}")
    
    def _print_progress(self, progress: ProgressInfo):
        """Print progress to console."""
        bar_length = 30
        filled = int(bar_length * progress.overall_progress)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        percent = progress.overall_progress * 100
        
        eta_str = ""
        if progress.estimated_remaining is not None:
            if progress.estimated_remaining < 60:
                eta_str = f" ETA: {progress.estimated_remaining:.0f}s"
            else:
                eta_str = f" ETA: {progress.estimated_remaining/60:.1f}m"
        
        item_str = ""
        if progress.items_total > 0:
            item_str = f" [{progress.items_processed}/{progress.items_total}]"
        
        print(f"\r[{bar}] {percent:5.1f}%{item_str} {progress.message[:40]:<40}{eta_str}", end='', flush=True)
        
        if progress.stage in (ProgressStage.COMPLETED, ProgressStage.FAILED):
            print()  # New line after completion


class BatchProgressReporter:
    """
    Progress reporter for batch operations (multiple files).
    
    Aggregates progress across multiple conversions and provides
    batch-level progress tracking.
    """
    
    def __init__(
        self,
        callback: Optional[Callable[[Dict], None]] = None,
        console_output: bool = False
    ):
        """Initialize batch progress reporter."""
        self._callback = callback
        self._console_output = console_output
        
        self._total_files: int = 0
        self._completed_files: int = 0
        self._failed_files: int = 0
        self._current_file: Optional[str] = None
        self._current_reporter: Optional[ProgressReporter] = None
        
        self._start_time: Optional[float] = None
        self._lock = threading.Lock()
        self._results: List[Dict] = []
    
    def start_batch(self, total_files: int):
        """Start batch processing."""
        with self._lock:
            self._total_files = total_files
            self._completed_files = 0
            self._failed_files = 0
            self._start_time = time.time()
            self._results = []
        
        if self._console_output:
            print(f"Starting batch conversion of {total_files} file(s)")
    
    def start_file(self, file_path: str) -> ProgressReporter:
        """
        Start processing a file.
        
        Returns:
            ProgressReporter for the individual file
        """
        with self._lock:
            self._current_file = file_path
            self._current_reporter = ProgressReporter(
                callback=self._file_progress_callback,
                console_output=False
            )
        
        if self._console_output:
            print(f"\n[{self._completed_files + 1}/{self._total_files}] {file_path}")
        
        self._current_reporter.start(f"Converting {file_path}")
        return self._current_reporter
    
    def file_completed(self, success: bool, result: Optional[Dict] = None):
        """Mark current file as completed."""
        with self._lock:
            if success:
                self._completed_files += 1
            else:
                self._failed_files += 1
            
            if result:
                result['file'] = self._current_file
                self._results.append(result)
            
            self._current_file = None
            self._current_reporter = None
        
        self._notify()
    
    def complete_batch(self) -> Dict:
        """Complete batch and return summary."""
        elapsed = time.time() - self._start_time if self._start_time else 0.0
        
        summary = {
            'total_files': self._total_files,
            'completed': self._completed_files,
            'failed': self._failed_files,
            'elapsed_time': round(elapsed, 2),
            'results': self._results
        }
        
        if self._console_output:
            print(f"\n\nBatch complete: {self._completed_files}/{self._total_files} succeeded, "
                  f"{self._failed_files} failed, {elapsed:.1f}s elapsed")
        
        if self._callback:
            self._callback({'type': 'batch_complete', 'summary': summary})
        
        return summary
    
    def _file_progress_callback(self, progress: ProgressInfo):
        """Handle progress from individual file."""
        self._notify()
    
    def _notify(self):
        """Send batch progress notification."""
        if not self._callback:
            return
        
        with self._lock:
            overall = (self._completed_files + self._failed_files) / max(1, self._total_files)
            
            file_progress = 0.0
            if self._current_reporter:
                file_progress = self._current_reporter.get_progress().overall_progress
            
            # Weight current file progress
            current_contribution = file_progress / max(1, self._total_files)
            overall = min(1.0, overall + current_contribution)
        
        self._callback({
            'type': 'batch_progress',
            'overall': round(overall, 3),
            'completed': self._completed_files,
            'failed': self._failed_files,
            'total': self._total_files,
            'current_file': self._current_file
        })


# Convenience function for simple progress tracking
def create_progress_reporter(
    callback: Optional[Callable[[ProgressInfo], None]] = None,
    console: bool = False
) -> ProgressReporter:
    """
    Create a progress reporter with common settings.
    
    Args:
        callback: Optional callback for progress updates
        console: Whether to output to console
        
    Returns:
        Configured ProgressReporter
    """
    return ProgressReporter(callback=callback, console_output=console)
