#!/usr/bin/env python3
"""
FTI Storage Subsystem - Comprehensive File Storage and Logging

This module provides:
1. File storage for inputs/outputs with proper organization
2. Conversion history logging (persistent JSON log)
3. Attempt tracking with timestamps
4. Success/failure statistics
5. Cleanup and retention policies
6. Storage metrics and health monitoring

Architecture:
    .fti_storage/
    ├── inputs/          # Copied input files (hashed subdirs)
    ├── outputs/         # Conversion outputs (by date)
    ├── temp/            # Temporary processing files
    ├── logs/            # Conversion history logs
    │   ├── history.jsonl    # Append-only conversion log
    │   ├── errors.jsonl     # Error-only log
    │   └── stats.json       # Aggregated statistics
    └── cache/           # Deduplication cache
"""

import os
import sys
import json
import shutil
import hashlib
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConversionStatus(Enum):
    """Conversion attempt status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CACHED = "cached"
    CANCELLED = "cancelled"


@dataclass
class ConversionRecord:
    """A single conversion attempt record."""
    record_id: str
    request_id: str
    timestamp: str
    input_path: str
    input_format: str
    output_path: Optional[str]
    output_format: Optional[str]
    status: str
    duration_ms: int = 0
    file_size_bytes: int = 0
    output_size_bytes: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    cached_from: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ConversionRecord':
        return cls(**data)


@dataclass
class StorageStats:
    """Aggregated storage statistics."""
    total_conversions: int = 0
    successful_conversions: int = 0
    failed_conversions: int = 0
    cached_conversions: int = 0
    total_input_bytes: int = 0
    total_output_bytes: int = 0
    total_duration_ms: int = 0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0
    last_conversion: Optional[str] = None
    last_error: Optional[str] = None
    storage_used_bytes: int = 0
    oldest_record: Optional[str] = None
    newest_record: Optional[str] = None
    formats_processed: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StorageStats':
        # Handle missing fields gracefully
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class FTIStorage:
    """
    FTI Storage Subsystem.
    
    Provides comprehensive file storage, logging, and statistics
    for the File-Type Importer conversion pipeline.
    """
    
    # Default paths to try for storage
    DEFAULT_STORAGE_PATHS = [
        Path("/mnt/d/ROA/.fti_storage"),
        Path("/mnt/c/ROA/.fti_storage"),
        Path.home() / ".roa" / "fti_storage",
    ]
    
    # Retention policy defaults
    DEFAULT_RETENTION_DAYS = 30
    DEFAULT_MAX_STORAGE_GB = 10.0
    
    def __init__(self, base_path: Optional[Path] = None, 
                 retention_days: int = DEFAULT_RETENTION_DAYS,
                 max_storage_gb: float = DEFAULT_MAX_STORAGE_GB):
        """
        Initialize FTI Storage.
        
        Args:
            base_path: Override storage base path
            retention_days: Days to keep conversion records
            max_storage_gb: Maximum storage usage in GB
        """
        self.base_path = base_path or self._find_storage_path()
        self.retention_days = retention_days
        self.max_storage_bytes = int(max_storage_gb * 1024 * 1024 * 1024)
        
        # Lock for thread-safe operations
        self._lock = threading.Lock()
        
        # Initialize directories
        self._init_directories()
        
        # Load or initialize stats
        self._stats = self._load_stats()
        
        logger.info(f"FTI Storage initialized at: {self.base_path}")
        logger.info(f"  Retention: {retention_days} days, Max: {max_storage_gb}GB")
    
    def _find_storage_path(self) -> Path:
        """Find or create storage path."""
        for path in self.DEFAULT_STORAGE_PATHS:
            try:
                path.mkdir(parents=True, exist_ok=True)
                # Test write access
                test_file = path / ".write_test"
                test_file.touch()
                test_file.unlink()
                return path
            except Exception as e:
                logger.debug(f"Cannot use {path}: {e}")
        
        # Fallback to temp
        import tempfile
        fallback = Path(tempfile.gettempdir()) / "roa_fti_storage"
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(f"Using fallback storage: {fallback}")
        return fallback
    
    def _init_directories(self):
        """Initialize storage directory structure."""
        subdirs = ['inputs', 'outputs', 'temp', 'logs', 'cache']
        for subdir in subdirs:
            (self.base_path / subdir).mkdir(parents=True, exist_ok=True)
        
        # Initialize log files if they don't exist
        history_file = self.base_path / "logs" / "history.jsonl"
        if not history_file.exists():
            history_file.touch()
        
        errors_file = self.base_path / "logs" / "errors.jsonl"
        if not errors_file.exists():
            errors_file.touch()
    
    # =========================================================================
    # PATHS
    # =========================================================================
    
    @property
    def inputs_dir(self) -> Path:
        return self.base_path / "inputs"
    
    @property
    def outputs_dir(self) -> Path:
        return self.base_path / "outputs"
    
    @property
    def temp_dir(self) -> Path:
        return self.base_path / "temp"
    
    @property
    def logs_dir(self) -> Path:
        return self.base_path / "logs"
    
    @property
    def cache_dir(self) -> Path:
        return self.base_path / "cache"
    
    @property
    def history_file(self) -> Path:
        return self.logs_dir / "history.jsonl"
    
    @property
    def errors_file(self) -> Path:
        return self.logs_dir / "errors.jsonl"
    
    @property
    def stats_file(self) -> Path:
        return self.logs_dir / "stats.json"
    
    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================
    
    def copy_input_file(self, source_path: str, 
                        include_package: bool = True) -> Tuple[str, Optional[str], bool]:
        """
        Copy input file to storage.
        
        Args:
            source_path: Source file path
            include_package: Copy entire ROS package if found
            
        Returns:
            Tuple of (new_path, package_path, was_copied)
        """
        source = Path(source_path)
        
        # Check if already accessible
        if source.exists():
            try:
                with open(source, 'rb') as f:
                    f.read(1)
                logger.debug(f"File already accessible: {source}")
                package_path = self._find_package_root(source)
                return str(source), package_path, False
            except Exception:
                pass
        
        # Create unique subdirectory
        path_hash = hashlib.md5(str(source).encode()).hexdigest()[:12]
        target_dir = self.inputs_dir / path_hash
        
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            
            if include_package:
                package_root = self._find_package_root(source)
                if package_root:
                    package_name = Path(package_root).name
                    target_package = target_dir / package_name
                    
                    if target_package.exists():
                        shutil.rmtree(target_package)
                    
                    shutil.copytree(package_root, target_package)
                    rel_path = source.relative_to(package_root)
                    new_path = target_package / rel_path
                    
                    logger.info(f"Package copied to storage: {target_package}")
                    return str(new_path), str(target_package), True
            
            # Single file copy
            target_file = target_dir / source.name
            shutil.copy2(source, target_file)
            logger.info(f"File copied to storage: {target_file}")
            return str(target_file), None, True
            
        except Exception as e:
            logger.error(f"Failed to copy to storage: {e}")
            return str(source), None, False
    
    def _find_package_root(self, file_path: Path) -> Optional[str]:
        """Find ROS package root containing the file."""
        current = Path(file_path).parent
        
        for _ in range(10):
            if (current / "package.xml").exists():
                return str(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
        
        return None
    
    def create_output_dir(self, name_prefix: str, 
                          request_id: Optional[str] = None) -> Path:
        """
        Create dated output directory.
        
        Args:
            name_prefix: Prefix for the output folder
            request_id: Optional request ID for uniqueness
            
        Returns:
            Path to the created output directory
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H%M%S")
        
        if request_id:
            short_id = request_id[:8]
            dir_name = f"{date_str}_{name_prefix}_{short_id}"
        else:
            dir_name = f"{date_str}_{name_prefix}_{time_str}"
        
        output_dir = self.outputs_dir / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return output_dir
    
    def get_temp_file(self, suffix: str = "") -> Path:
        """Get a temporary file path."""
        import uuid
        temp_name = f"temp_{uuid.uuid4().hex[:12]}{suffix}"
        return self.temp_dir / temp_name
    
    # =========================================================================
    # LOGGING & HISTORY
    # =========================================================================
    
    def log_conversion(self, record: ConversionRecord):
        """
        Log a conversion attempt to persistent storage.
        
        Args:
            record: ConversionRecord to log
        """
        with self._lock:
            try:
                # Append to history
                with open(self.history_file, 'a') as f:
                    f.write(record.to_json() + '\n')
                
                # If error, also append to errors log
                if record.status == ConversionStatus.FAILED.value:
                    with open(self.errors_file, 'a') as f:
                        f.write(record.to_json() + '\n')
                
                # Update stats
                self._update_stats(record)
                
                logger.debug(f"Logged conversion: {record.record_id}")
                
            except Exception as e:
                logger.error(f"Failed to log conversion: {e}")
    
    def log_conversion_start(self, request_id: str, input_path: str,
                             input_format: str) -> str:
        """
        Log the start of a conversion.
        
        Returns:
            record_id for tracking
        """
        import uuid
        record_id = str(uuid.uuid4())
        
        record = ConversionRecord(
            record_id=record_id,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_path=input_path,
            input_format=input_format,
            output_path=None,
            output_format=None,
            status=ConversionStatus.IN_PROGRESS.value,
            file_size_bytes=self._get_file_size(input_path)
        )
        
        self.log_conversion(record)
        return record_id
    
    def log_conversion_complete(self, record_id: str, request_id: str,
                                 input_path: str, input_format: str,
                                 output_path: str, output_format: str,
                                 duration_ms: int, metadata: Dict = None):
        """Log successful conversion completion."""
        record = ConversionRecord(
            record_id=record_id,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_path=input_path,
            input_format=input_format,
            output_path=output_path,
            output_format=output_format,
            status=ConversionStatus.SUCCESS.value,
            duration_ms=duration_ms,
            file_size_bytes=self._get_file_size(input_path),
            output_size_bytes=self._get_file_size(output_path),
            metadata=metadata or {}
        )
        
        self.log_conversion(record)
    
    def log_conversion_failed(self, record_id: str, request_id: str,
                               input_path: str, input_format: str,
                               error_code: str, error_message: str,
                               duration_ms: int = 0):
        """Log failed conversion."""
        record = ConversionRecord(
            record_id=record_id,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_path=input_path,
            input_format=input_format,
            output_path=None,
            output_format=None,
            status=ConversionStatus.FAILED.value,
            duration_ms=duration_ms,
            file_size_bytes=self._get_file_size(input_path),
            error_code=error_code,
            error_message=error_message
        )
        
        self.log_conversion(record)
    
    def log_conversion_cached(self, record_id: str, request_id: str,
                               input_path: str, cached_from: str):
        """Log cached conversion (deduplication hit)."""
        record = ConversionRecord(
            record_id=record_id,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_path=input_path,
            input_format=self._get_format(input_path),
            output_path=None,
            output_format=None,
            status=ConversionStatus.CACHED.value,
            cached_from=cached_from
        )
        
        self.log_conversion(record)
    
    def _get_file_size(self, path: str) -> int:
        """Get file size safely."""
        try:
            return os.path.getsize(path) if path and os.path.exists(path) else 0
        except:
            return 0
    
    def _get_format(self, path: str) -> str:
        """Extract format from path."""
        if not path:
            return "unknown"
        ext = os.path.splitext(path)[1].lower()
        return ext if ext else "unknown"
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def _load_stats(self) -> StorageStats:
        """Load stats from file or create new."""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                return StorageStats.from_dict(data)
            except Exception as e:
                logger.warning(f"Could not load stats: {e}")
        
        return StorageStats()
    
    def _save_stats(self):
        """Save stats to file."""
        try:
            with open(self.stats_file, 'w') as f:
                f.write(self._stats.to_json())
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")
    
    def _update_stats(self, record: ConversionRecord):
        """Update statistics from a conversion record."""
        self._stats.total_conversions += 1
        
        if record.status == ConversionStatus.SUCCESS.value:
            self._stats.successful_conversions += 1
            self._stats.total_duration_ms += record.duration_ms
            self._stats.total_output_bytes += record.output_size_bytes
        elif record.status == ConversionStatus.FAILED.value:
            self._stats.failed_conversions += 1
            self._stats.last_error = record.error_message
        elif record.status == ConversionStatus.CACHED.value:
            self._stats.cached_conversions += 1
        
        self._stats.total_input_bytes += record.file_size_bytes
        self._stats.last_conversion = record.timestamp
        
        # Update format counts
        fmt = record.input_format
        if fmt:
            self._stats.formats_processed[fmt] = \
                self._stats.formats_processed.get(fmt, 0) + 1
        
        # Calculate success rate
        completed = self._stats.successful_conversions + self._stats.failed_conversions
        if completed > 0:
            self._stats.success_rate = self._stats.successful_conversions / completed
        
        # Calculate average duration
        if self._stats.successful_conversions > 0:
            self._stats.avg_duration_ms = \
                self._stats.total_duration_ms / self._stats.successful_conversions
        
        # Update storage usage
        self._stats.storage_used_bytes = self._calculate_storage_usage()
        
        # Track oldest/newest
        if not self._stats.oldest_record:
            self._stats.oldest_record = record.timestamp
        self._stats.newest_record = record.timestamp
        
        self._save_stats()
    
    def get_stats(self) -> StorageStats:
        """Get current statistics."""
        return self._stats
    
    def get_stats_dict(self) -> Dict:
        """Get statistics as dictionary."""
        return self._stats.to_dict()
    
    def _calculate_storage_usage(self) -> int:
        """Calculate total storage usage in bytes."""
        total = 0
        for path in [self.inputs_dir, self.outputs_dir, self.temp_dir, self.cache_dir]:
            for root, dirs, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except:
                        pass
        return total
    
    # =========================================================================
    # HISTORY QUERIES
    # =========================================================================
    
    def get_history(self, limit: int = 100, 
                    status_filter: Optional[str] = None,
                    since: Optional[datetime] = None) -> List[ConversionRecord]:
        """
        Get conversion history.
        
        Args:
            limit: Maximum records to return
            status_filter: Filter by status (success, failed, cached)
            since: Only records after this datetime
            
        Returns:
            List of ConversionRecord objects
        """
        records = []
        
        try:
            with open(self.history_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        record = ConversionRecord.from_dict(data)
                        
                        # Apply filters
                        if status_filter and record.status != status_filter:
                            continue
                        
                        if since:
                            record_time = datetime.fromisoformat(
                                record.timestamp.replace('Z', '+00:00'))
                            if record_time < since:
                                continue
                        
                        records.append(record)
                    except:
                        continue
            
            # Return most recent first
            records.reverse()
            return records[:limit]
            
        except Exception as e:
            logger.error(f"Failed to read history: {e}")
            return []
    
    def get_recent_errors(self, limit: int = 20) -> List[ConversionRecord]:
        """Get recent error records."""
        return self.get_history(limit=limit, status_filter=ConversionStatus.FAILED.value)
    
    def get_conversion_by_request(self, request_id: str) -> Optional[ConversionRecord]:
        """Find conversion by request ID."""
        for record in self.get_history(limit=1000):
            if record.request_id == request_id:
                return record
        return None
    
    # =========================================================================
    # CLEANUP & MAINTENANCE
    # =========================================================================
    
    def cleanup_old_records(self, days: Optional[int] = None) -> int:
        """
        Remove records older than retention period.
        
        Args:
            days: Override retention days
            
        Returns:
            Number of records cleaned up
        """
        retention = days or self.retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        
        cleaned = 0
        
        # Clean history file
        cleaned += self._cleanup_log_file(self.history_file, cutoff)
        cleaned += self._cleanup_log_file(self.errors_file, cutoff)
        
        # Clean old input directories
        cleaned += self._cleanup_old_dirs(self.inputs_dir, cutoff)
        cleaned += self._cleanup_old_dirs(self.outputs_dir, cutoff)
        
        # Clear temp directory
        self._clear_temp()
        
        logger.info(f"Cleanup complete: removed {cleaned} old records/files")
        return cleaned
    
    def _cleanup_log_file(self, log_file: Path, cutoff: datetime) -> int:
        """Clean old entries from a log file."""
        if not log_file.exists():
            return 0
        
        kept = []
        removed = 0
        
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = datetime.fromisoformat(
                            data['timestamp'].replace('Z', '+00:00'))
                        if ts >= cutoff:
                            kept.append(line)
                        else:
                            removed += 1
                    except:
                        kept.append(line)  # Keep unparseable lines
            
            with open(log_file, 'w') as f:
                f.write('\n'.join(kept))
                if kept:
                    f.write('\n')
            
            return removed
            
        except Exception as e:
            logger.error(f"Failed to cleanup {log_file}: {e}")
            return 0
    
    def _cleanup_old_dirs(self, parent_dir: Path, cutoff: datetime) -> int:
        """Clean directories older than cutoff."""
        cleaned = 0
        
        try:
            for item in parent_dir.iterdir():
                if not item.is_dir():
                    continue
                
                # Check modification time
                mtime = datetime.fromtimestamp(
                    item.stat().st_mtime, tz=timezone.utc)
                
                if mtime < cutoff:
                    shutil.rmtree(item)
                    cleaned += 1
                    logger.debug(f"Removed old directory: {item}")
        except Exception as e:
            logger.error(f"Failed to cleanup {parent_dir}: {e}")
        
        return cleaned
    
    def _clear_temp(self):
        """Clear temporary directory."""
        try:
            for item in self.temp_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        except Exception as e:
            logger.warning(f"Could not clear temp: {e}")
    
    def check_storage_limit(self) -> bool:
        """
        Check if storage limit is exceeded.
        
        Returns:
            True if under limit, False if over
        """
        usage = self._calculate_storage_usage()
        if usage > self.max_storage_bytes:
            logger.warning(f"Storage limit exceeded: {usage / 1e9:.2f}GB / "
                          f"{self.max_storage_bytes / 1e9:.2f}GB")
            return False
        return True
    
    def enforce_storage_limit(self):
        """Remove oldest files until under storage limit."""
        while not self.check_storage_limit():
            # Remove oldest input directory
            oldest = None
            oldest_time = None
            
            for item in self.inputs_dir.iterdir():
                if item.is_dir():
                    mtime = item.stat().st_mtime
                    if oldest_time is None or mtime < oldest_time:
                        oldest = item
                        oldest_time = mtime
            
            if oldest:
                shutil.rmtree(oldest)
                logger.info(f"Removed to free space: {oldest}")
            else:
                break  # No more to remove
    
    # =========================================================================
    # REPORTING
    # =========================================================================
    
    def generate_report(self) -> str:
        """Generate a human-readable storage report."""
        stats = self._stats
        
        report = []
        report.append("=" * 60)
        report.append("FTI STORAGE SUBSYSTEM REPORT")
        report.append("=" * 60)
        report.append(f"Storage Path: {self.base_path}")
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        report.append("📊 CONVERSION STATISTICS")
        report.append("-" * 40)
        report.append(f"  Total Conversions: {stats.total_conversions}")
        report.append(f"  Successful: {stats.successful_conversions}")
        report.append(f"  Failed: {stats.failed_conversions}")
        report.append(f"  Cached: {stats.cached_conversions}")
        report.append(f"  Success Rate: {stats.success_rate:.1%}")
        report.append(f"  Avg Duration: {stats.avg_duration_ms:.0f}ms")
        report.append("")
        
        report.append("📁 STORAGE USAGE")
        report.append("-" * 40)
        usage_mb = stats.storage_used_bytes / (1024 * 1024)
        limit_mb = self.max_storage_bytes / (1024 * 1024)
        report.append(f"  Used: {usage_mb:.1f} MB / {limit_mb:.1f} MB")
        report.append(f"  Input Files: {stats.total_input_bytes / 1e6:.1f} MB processed")
        report.append(f"  Output Files: {stats.total_output_bytes / 1e6:.1f} MB generated")
        report.append("")
        
        report.append("📋 FORMAT BREAKDOWN")
        report.append("-" * 40)
        for fmt, count in sorted(stats.formats_processed.items(), 
                                  key=lambda x: -x[1]):
            report.append(f"  {fmt}: {count} files")
        report.append("")
        
        report.append("🕐 TIMELINE")
        report.append("-" * 40)
        report.append(f"  Oldest Record: {stats.oldest_record or 'N/A'}")
        report.append(f"  Newest Record: {stats.newest_record or 'N/A'}")
        report.append(f"  Last Error: {stats.last_error or 'None'}")
        report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)


# ============================================================================
# SINGLETON ACCESS
# ============================================================================

_storage_instance: Optional[FTIStorage] = None
_storage_lock = threading.Lock()


def get_storage() -> FTIStorage:
    """Get or create the global FTIStorage instance."""
    global _storage_instance
    
    with _storage_lock:
        if _storage_instance is None:
            _storage_instance = FTIStorage()
        return _storage_instance


def init_storage(base_path: Optional[Path] = None, **kwargs) -> FTIStorage:
    """Initialize storage with custom settings."""
    global _storage_instance
    
    with _storage_lock:
        _storage_instance = FTIStorage(base_path=base_path, **kwargs)
        return _storage_instance


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="FTI Storage Subsystem")
    parser.add_argument("--report", action="store_true", help="Generate storage report")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--history", type=int, default=0, help="Show N recent conversions")
    parser.add_argument("--errors", action="store_true", help="Show recent errors")
    parser.add_argument("--cleanup", action="store_true", help="Run cleanup")
    parser.add_argument("--path", type=str, help="Override storage path")
    
    args = parser.parse_args()
    
    storage = FTIStorage(base_path=Path(args.path) if args.path else None)
    
    if args.report:
        print(storage.generate_report())
    
    elif args.stats:
        stats = storage.get_stats_dict()
        print(json.dumps(stats, indent=2))
    
    elif args.history > 0:
        records = storage.get_history(limit=args.history)
        for r in records:
            print(f"{r.timestamp} | {r.status:10} | {r.input_format:8} | {r.input_path}")
    
    elif args.errors:
        records = storage.get_recent_errors()
        for r in records:
            print(f"{r.timestamp} | {r.error_code} | {r.error_message}")
    
    elif args.cleanup:
        cleaned = storage.cleanup_old_records()
        print(f"Cleaned up {cleaned} old records/files")
    
    else:
        parser.print_help()
