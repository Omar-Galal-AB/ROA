"""
Temporary File Manager for FTI

Provides safe temp file handling with automatic cleanup on success/failure.
Implements transaction-like behavior for file operations.
"""

import atexit
import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class TempFileRecord:
    """Record of a temporary file or directory."""

    path: str
    created_at: datetime
    purpose: str
    is_directory: bool = False
    keep_on_success: bool = False


class TempFileManager:
    """
    Manages temporary files with automatic cleanup.

    Features:
    - Transaction-like file operations
    - Automatic cleanup on success/failure
    - Rollback support
    - Cleanup at process exit
    - Configurable temp location

    Usage:
        with TempFileManager() as tmp:
            temp_file = tmp.create_file("output.usd")
            # Do work...
            tmp.commit()  # Success - cleanup temps
        # On exception: automatic rollback and cleanup
    """

    _instances: List["TempFileManager"] = []
    _atexit_registered = False

    def __init__(
        self,
        base_dir: Optional[str] = None,
        prefix: str = "fti_",
        cleanup_on_exit: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize temp file manager.

        Args:
            base_dir: Base directory for temp files (default: system temp)
            prefix: Prefix for temp file/dir names
            cleanup_on_exit: Clean up all temps when process exits
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.prefix = prefix
        self.cleanup_on_exit = cleanup_on_exit

        # Determine base directory
        if base_dir:
            self.base_dir = Path(base_dir)
            self.base_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.base_dir = Path(tempfile.gettempdir()) / "fti_temp"
            self.base_dir.mkdir(parents=True, exist_ok=True)

        # Track temp files
        self._temp_files: List[TempFileRecord] = []
        self._committed = False
        self._rolled_back = False

        # Track instances for global cleanup
        TempFileManager._instances.append(self)

        # Register atexit handler once
        if cleanup_on_exit and not TempFileManager._atexit_registered:
            atexit.register(TempFileManager._cleanup_all_instances)
            TempFileManager._atexit_registered = True

    @classmethod
    def _cleanup_all_instances(cls):
        """Clean up all manager instances at process exit."""
        for instance in cls._instances:
            try:
                instance.cleanup()
            except Exception:
                pass

    def create_file(self, name: str, purpose: str = "temp", keep_on_success: bool = False) -> str:
        """
        Create a temp file path.

        Args:
            name: Filename or suffix
            purpose: Description of file purpose
            keep_on_success: If True, don't delete on commit

        Returns:
            Path to temp file (not yet created)
        """
        if self._committed or self._rolled_back:
            raise RuntimeError("Transaction already completed")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{self.prefix}{timestamp}_{name}"
        filepath = self.base_dir / filename

        self._temp_files.append(
            TempFileRecord(
                path=str(filepath),
                created_at=datetime.now(),
                purpose=purpose,
                is_directory=False,
                keep_on_success=keep_on_success,
            )
        )

        self.logger.debug(f"Temp file created: {filepath} ({purpose})")
        return str(filepath)

    def create_directory(
        self, name: str = "work", purpose: str = "temp", keep_on_success: bool = False
    ) -> str:
        """
        Create a temp directory.

        Args:
            name: Directory name suffix
            purpose: Description of directory purpose
            keep_on_success: If True, don't delete on commit

        Returns:
            Path to temp directory (created)
        """
        if self._committed or self._rolled_back:
            raise RuntimeError("Transaction already completed")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dirname = f"{self.prefix}{timestamp}_{name}"
        dirpath = self.base_dir / dirname
        dirpath.mkdir(parents=True, exist_ok=True)

        self._temp_files.append(
            TempFileRecord(
                path=str(dirpath),
                created_at=datetime.now(),
                purpose=purpose,
                is_directory=True,
                keep_on_success=keep_on_success,
            )
        )

        self.logger.debug(f"Temp directory created: {dirpath} ({purpose})")
        return str(dirpath)

    def copy_to_final(self, temp_path: str, final_path: str, overwrite: bool = True) -> bool:
        """
        Copy temp file to final destination.

        Args:
            temp_path: Path to temp file
            final_path: Final destination path
            overwrite: Overwrite if exists

        Returns:
            True if successful
        """
        src = Path(temp_path)
        dst = Path(final_path)

        if not src.exists():
            self.logger.error(f"Temp file does not exist: {temp_path}")
            return False

        if dst.exists() and not overwrite:
            self.logger.warning(f"Destination exists, not overwriting: {final_path}")
            return False

        # Ensure parent directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

        self.logger.debug(f"Copied: {temp_path} -> {final_path}")
        return True

    def move_to_final(self, temp_path: str, final_path: str, overwrite: bool = True) -> bool:
        """
        Move temp file to final destination.

        Args:
            temp_path: Path to temp file
            final_path: Final destination path
            overwrite: Overwrite if exists

        Returns:
            True if successful
        """
        src = Path(temp_path)
        dst = Path(final_path)

        if not src.exists():
            self.logger.error(f"Temp file does not exist: {temp_path}")
            return False

        if dst.exists():
            if overwrite:
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            else:
                self.logger.warning(f"Destination exists, not overwriting: {final_path}")
                return False

        # Ensure parent directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(src, dst)

        # Remove from tracking since it's moved
        self._temp_files = [t for t in self._temp_files if t.path != str(src)]

        self.logger.debug(f"Moved: {temp_path} -> {final_path}")
        return True

    def commit(self):
        """
        Commit transaction - success path.
        Cleans up temp files not marked keep_on_success.
        """
        if self._committed or self._rolled_back:
            return

        self._committed = True

        # Clean up temps not marked for keeping
        for record in self._temp_files:
            if not record.keep_on_success:
                self._delete_path(record.path, record.is_directory)

        self.logger.debug("Transaction committed")

    def rollback(self):
        """
        Rollback transaction - failure path.
        Cleans up ALL temp files.
        """
        if self._committed or self._rolled_back:
            return

        self._rolled_back = True

        # Clean up ALL temps
        for record in self._temp_files:
            self._delete_path(record.path, record.is_directory)

        self.logger.debug("Transaction rolled back")

    def cleanup(self):
        """Force cleanup all tracked temp files."""
        for record in self._temp_files:
            self._delete_path(record.path, record.is_directory)

        self._temp_files.clear()

    def _delete_path(self, path: str, is_directory: bool):
        """Delete a file or directory."""
        try:
            p = Path(path)
            if p.exists():
                if is_directory:
                    shutil.rmtree(p)
                else:
                    p.unlink()
                self.logger.debug(f"Deleted: {path}")
        except Exception as e:
            self.logger.warning(f"Failed to delete {path}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get stats about temp files."""
        total_size = 0
        for record in self._temp_files:
            p = Path(record.path)
            if p.exists():
                if p.is_dir():
                    total_size += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                else:
                    total_size += p.stat().st_size

        return {
            "count": len(self._temp_files),
            "total_size_mb": total_size / (1024 * 1024),
            "committed": self._committed,
            "rolled_back": self._rolled_back,
            "base_dir": str(self.base_dir),
        }

    def __enter__(self) -> "TempFileManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - auto rollback on exception."""
        if exc_type is not None:
            # Exception occurred, rollback
            self.rollback()
        elif not self._committed:
            # No exception but not committed - treat as success
            self.commit()

        # Remove from instances tracking
        if self in TempFileManager._instances:
            TempFileManager._instances.remove(self)

        return False  # Don't suppress exceptions


@contextmanager
def temp_transaction(base_dir: Optional[str] = None, prefix: str = "fti_"):
    """
    Context manager for temp file transactions.

    Usage:
        with temp_transaction() as tmp:
            temp_file = tmp.create_file("output.usd")
            # Work with temp_file...
            tmp.copy_to_final(temp_file, final_path)
            tmp.commit()

    Args:
        base_dir: Base directory for temps
        prefix: Prefix for temp names

    Yields:
        TempFileManager instance
    """
    manager = TempFileManager(base_dir=base_dir, prefix=prefix)
    try:
        yield manager
    except Exception:
        manager.rollback()
        raise
    else:
        if not manager._committed:
            manager.commit()


def cleanup_old_temp_files(base_dir: Optional[str] = None, max_age_hours: int = 24) -> int:
    """
    Clean up old temp files.

    Args:
        base_dir: Base directory to clean
        max_age_hours: Maximum age in hours

    Returns:
        Number of files/dirs deleted
    """
    logger = logging.getLogger(__name__)

    if base_dir:
        temp_dir = Path(base_dir)
    else:
        temp_dir = Path(tempfile.gettempdir()) / "fti_temp"

    if not temp_dir.exists():
        return 0

    import time

    cutoff_time = time.time() - (max_age_hours * 3600)
    deleted = 0

    for item in temp_dir.iterdir():
        try:
            if item.stat().st_mtime < cutoff_time:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                deleted += 1
                logger.debug(f"Cleaned up old temp: {item}")
        except Exception as e:
            logger.warning(f"Failed to clean {item}: {e}")

    return deleted
