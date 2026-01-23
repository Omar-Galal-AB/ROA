"""
FTI Cache - Conversion caching system for File Type Importer

Caches converted files using content-based hashing to avoid redundant conversions.
When the same source file is converted again with the same settings, the cached
result is returned instantly.

Features:
- Content-based hashing (SHA256) for cache keys
- Settings-aware caching (different settings = different cache entry)
- Cache index with metadata (source, settings, timestamp)
- Automatic cache expiry (configurable)
- Cache statistics and cleanup utilities

Storage Location: roa_linux/data/fti_cache/
"""

import hashlib
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class CacheEntry:
    """Metadata for a cached conversion."""

    cache_key: str
    source_path: str
    source_hash: str
    output_format: str
    settings_hash: str
    cached_path: str
    created_at: str
    accessed_at: str
    access_count: int
    file_size_bytes: int
    conversion_time_ms: float
    robot_name: str
    parts_count: int


class FTICache:
    """
    File Type Importer Cache Manager.

    Provides caching for converted 3D models to avoid redundant conversions.
    Uses content-based hashing to ensure cache validity.
    """

    DEFAULT_CACHE_DIR = "data/fti_cache"
    INDEX_FILE = "cache_index.json"
    MAX_CACHE_SIZE_MB = 1000  # 1GB default
    DEFAULT_EXPIRY_DAYS = 30

    def __init__(self, cache_dir: Optional[str] = None, config: Optional[Dict] = None):
        """
        Initialize the FTI Cache.

        Args:
            cache_dir: Path to cache directory (default: roa_linux/data/fti_cache)
            config: Cache configuration options
        """
        self.logger = logging.getLogger(__name__)
        self.config = config or {}

        # Determine cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Default to roa_linux/data/fti_cache
            fti_dir = Path(__file__).parent
            roa_core = (
                fti_dir.parent.parent.parent.parent
            )  # files-type-importer -> components -> lib -> roa-core
            self.cache_dir = roa_core.parent / "data" / "fti_cache"

        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache configuration
        self.max_size_mb = self.config.get("max_size_mb", self.MAX_CACHE_SIZE_MB)
        self.expiry_days = self.config.get("expiry_days", self.DEFAULT_EXPIRY_DAYS)
        self.enabled = self.config.get("enabled", True)

        # Load index
        self.index: Dict[str, CacheEntry] = {}
        self._load_index()

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "stores": 0,
        }

    @property
    def index_path(self) -> Path:
        """Get path to cache index file."""
        return self.cache_dir / self.INDEX_FILE

    def _load_index(self):
        """Load cache index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r") as f:
                    data = json.load(f)

                self.index = {}
                for key, entry_data in data.get("entries", {}).items():
                    self.index[key] = CacheEntry(**entry_data)

                self.stats = data.get("stats", self.stats)
                self.logger.debug(f"Loaded cache index: {len(self.index)} entries")
            except Exception as e:
                self.logger.warning(f"Failed to load cache index: {e}")
                self.index = {}
        else:
            self.logger.debug("No cache index found, starting fresh")

    def _save_index(self):
        """Save cache index to disk."""
        try:
            data = {
                "version": "1.0",
                "updated": datetime.now().isoformat(),
                "entries": {key: asdict(entry) for key, entry in self.index.items()},
                "stats": self.stats,
            }

            with open(self.index_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save cache index: {e}")

    def _compute_file_hash(self, file_path: str) -> str:
        """
        Compute SHA256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            Hex string of file hash
        """
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        return sha256.hexdigest()

    def _compute_settings_hash(self, settings: Dict) -> str:
        """
        Compute hash of conversion settings.

        Args:
            settings: Conversion settings dictionary

        Returns:
            Hex string of settings hash
        """
        # Sort keys for consistent ordering
        settings_str = json.dumps(settings, sort_keys=True)
        return hashlib.sha256(settings_str.encode()).hexdigest()[:16]

    def _generate_cache_key(self, source_path: str, settings: Optional[Dict] = None) -> str:
        """
        Generate a unique cache key for a conversion.

        Args:
            source_path: Path to source file
            settings: Conversion settings

        Returns:
            Cache key string
        """
        file_hash = self._compute_file_hash(source_path)
        settings_hash = self._compute_settings_hash(settings or {})

        # Format: filehash_settingshash
        return f"{file_hash[:16]}_{settings_hash}"

    def lookup(
        self, source_path: str, settings: Optional[Dict] = None
    ) -> Optional[Tuple[str, CacheEntry]]:
        """
        Look up a cached conversion.

        Args:
            source_path: Path to source file
            settings: Conversion settings

        Returns:
            Tuple of (cached_file_path, cache_entry) or None if not cached
        """
        if not self.enabled:
            return None

        cache_key = self._generate_cache_key(source_path, settings)

        if cache_key in self.index:
            entry = self.index[cache_key]

            # Verify cached file still exists
            if Path(entry.cached_path).exists():
                # Update access time and count
                entry.accessed_at = datetime.now().isoformat()
                entry.access_count += 1
                self._save_index()

                self.stats["hits"] += 1
                self.logger.info(f"Cache HIT: {Path(source_path).name}")
                return entry.cached_path, entry
            else:
                # Cached file missing, remove entry
                del self.index[cache_key]
                self._save_index()

        self.stats["misses"] += 1
        self.logger.debug(f"Cache MISS: {Path(source_path).name}")
        return None

    def store(
        self,
        source_path: str,
        converted_path: str,
        settings: Optional[Dict] = None,
        robot_name: str = "",
        parts_count: int = 0,
        conversion_time_ms: float = 0.0,
    ) -> CacheEntry:
        """
        Store a conversion result in the cache.

        Args:
            source_path: Path to source file
            converted_path: Path to converted file
            settings: Conversion settings used
            robot_name: Name of the robot
            parts_count: Number of parts in the model
            conversion_time_ms: Time taken for conversion

        Returns:
            CacheEntry for the stored conversion
        """
        if not self.enabled:
            return None

        cache_key = self._generate_cache_key(source_path, settings)

        # Determine cached file path
        ext = Path(converted_path).suffix
        cached_filename = f"{cache_key}{ext}"
        cached_path = self.cache_dir / cached_filename

        # Copy converted file to cache
        shutil.copy2(converted_path, cached_path)

        # Create cache entry
        now = datetime.now().isoformat()
        entry = CacheEntry(
            cache_key=cache_key,
            source_path=str(source_path),
            source_hash=self._compute_file_hash(source_path),
            output_format=ext.lstrip("."),
            settings_hash=self._compute_settings_hash(settings or {}),
            cached_path=str(cached_path),
            created_at=now,
            accessed_at=now,
            access_count=0,
            file_size_bytes=cached_path.stat().st_size,
            conversion_time_ms=conversion_time_ms,
            robot_name=robot_name,
            parts_count=parts_count,
        )

        self.index[cache_key] = entry
        self.stats["stores"] += 1
        self._save_index()

        self.logger.info(f"Cached: {Path(source_path).name} -> {cached_filename}")

        # Check cache size and cleanup if needed
        self._check_cache_size()

        return entry

    def copy_to_destination(self, cache_key: str, destination_path: str) -> bool:
        """
        Copy a cached file to a destination.

        Args:
            cache_key: Cache key of the entry
            destination_path: Destination path (can be Windows path via /mnt/c/)

        Returns:
            True if successful
        """
        if cache_key not in self.index:
            return False

        entry = self.index[cache_key]
        cached_path = Path(entry.cached_path)

        if not cached_path.exists():
            return False

        # Ensure destination directory exists
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(cached_path, dest)

        self.logger.info(f"Copied from cache: {dest}")
        return True

    def _check_cache_size(self):
        """Check cache size and cleanup if over limit."""
        total_size = sum(
            Path(e.cached_path).stat().st_size
            for e in self.index.values()
            if Path(e.cached_path).exists()
        )

        max_bytes = self.max_size_mb * 1024 * 1024

        if total_size > max_bytes:
            self.logger.info(
                f"Cache size {total_size / 1024 / 1024:.1f}MB > limit {self.max_size_mb}MB, cleaning up..."
            )
            self._cleanup_oldest()

    def _cleanup_oldest(self, target_reduction_mb: int = 100):
        """Remove oldest cache entries to free space."""
        # Sort entries by access time (oldest first)
        sorted_entries = sorted(self.index.items(), key=lambda x: x[1].accessed_at)

        bytes_freed = 0
        target_bytes = target_reduction_mb * 1024 * 1024

        for cache_key, entry in sorted_entries:
            if bytes_freed >= target_bytes:
                break

            cached_path = Path(entry.cached_path)
            if cached_path.exists():
                bytes_freed += cached_path.stat().st_size
                cached_path.unlink()

            del self.index[cache_key]

        self._save_index()
        self.logger.info(f"Cleanup freed {bytes_freed / 1024 / 1024:.1f}MB")

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        cutoff = datetime.now() - timedelta(days=self.expiry_days)
        cutoff_str = cutoff.isoformat()

        expired_keys = [key for key, entry in self.index.items() if entry.accessed_at < cutoff_str]

        for key in expired_keys:
            entry = self.index[key]
            cached_path = Path(entry.cached_path)
            if cached_path.exists():
                cached_path.unlink()
            del self.index[key]

        if expired_keys:
            self._save_index()
            self.logger.info(f"Expired {len(expired_keys)} cache entries")

        return len(expired_keys)

    def clear(self):
        """Clear entire cache."""
        for entry in self.index.values():
            cached_path = Path(entry.cached_path)
            if cached_path.exists():
                cached_path.unlink()

        self.index = {}
        self.stats = {"hits": 0, "misses": 0, "stores": 0}
        self._save_index()
        self.logger.info("Cache cleared")

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        total_size = sum(
            Path(e.cached_path).stat().st_size
            for e in self.index.values()
            if Path(e.cached_path).exists()
        )

        hit_rate = (
            self.stats["hits"] / (self.stats["hits"] + self.stats["misses"])
            if (self.stats["hits"] + self.stats["misses"]) > 0
            else 0
        )

        return {
            "entries": len(self.index),
            "total_size_mb": total_size / 1024 / 1024,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "stores": self.stats["stores"],
            "hit_rate": hit_rate,
            "cache_dir": str(self.cache_dir),
        }

    def list_entries(self) -> List[Dict]:
        """List all cache entries."""
        return [
            {
                "cache_key": entry.cache_key,
                "source": Path(entry.source_path).name,
                "robot_name": entry.robot_name,
                "size_kb": entry.file_size_bytes / 1024,
                "access_count": entry.access_count,
                "created": entry.created_at[:10],
            }
            for entry in self.index.values()
        ]


# Singleton instance
_cache_instance: Optional[FTICache] = None


def get_cache(cache_dir: Optional[str] = None, config: Optional[Dict] = None) -> FTICache:
    """
    Get the global FTI cache instance.

    Args:
        cache_dir: Optional cache directory
        config: Optional configuration

    Returns:
        FTICache instance
    """
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = FTICache(cache_dir=cache_dir, config=config)

    return _cache_instance
