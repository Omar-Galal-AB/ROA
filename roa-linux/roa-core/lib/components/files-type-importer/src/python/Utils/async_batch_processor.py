"""
Async Batch Processor for FTI (Fix #10)

Provides asynchronous and concurrent batch processing for multiple file conversions.
Designed for handling large batches of robot files efficiently.

Features:
- Async/await support with asyncio
- Concurrent execution with configurable worker count
- Progress tracking for batch operations
- Result aggregation and error handling
- Cancellation support
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

logger = logging.getLogger(__name__)


class BatchStatus(Enum):
    """Status of a batch operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class BatchItem:
    """Represents a single item in a batch."""

    file_path: str
    robot_name: Optional[str] = None
    import_mode: str = "both"
    output_path: Optional[str] = None

    # Set after processing
    status: BatchStatus = BatchStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0

    @property
    def filename(self) -> str:
        return Path(self.file_path).name


@dataclass
class BatchResult:
    """Result of a batch operation."""

    total_items: int
    successful: int
    failed: int
    cancelled: int
    items: List[BatchItem]
    total_time_ms: float
    average_time_ms: float
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_items == 0:
            return 0.0
        return self.successful / self.total_items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_items": self.total_items,
            "successful": self.successful,
            "failed": self.failed,
            "cancelled": self.cancelled,
            "success_rate": round(self.success_rate * 100, 2),
            "total_time_ms": round(self.total_time_ms, 2),
            "average_time_ms": round(self.average_time_ms, 2),
            "errors": self.errors[:10],  # Limit to first 10 errors
        }


class BatchProgressCallback:
    """Callback interface for batch progress updates."""

    def on_batch_start(self, total_items: int):
        """Called when batch processing starts."""
        pass

    def on_item_start(self, item: BatchItem, index: int, total: int):
        """Called when an item starts processing."""
        pass

    def on_item_complete(self, item: BatchItem, index: int, total: int):
        """Called when an item completes processing."""
        pass

    def on_item_error(self, item: BatchItem, error: str, index: int, total: int):
        """Called when an item fails."""
        pass

    def on_batch_complete(self, result: BatchResult):
        """Called when batch processing completes."""
        pass


class ConsoleBatchProgress(BatchProgressCallback):
    """Simple console-based progress callback."""

    def on_batch_start(self, total_items: int):
        logger.info(f"Starting batch processing of {total_items} items")

    def on_item_start(self, item: BatchItem, index: int, total: int):
        logger.debug(f"Processing [{index + 1}/{total}]: {item.filename}")

    def on_item_complete(self, item: BatchItem, index: int, total: int):
        logger.info(
            f"Completed [{index + 1}/{total}]: {item.filename} ({item.processing_time_ms:.0f}ms)"
        )

    def on_item_error(self, item: BatchItem, error: str, index: int, total: int):
        logger.error(f"Failed [{index + 1}/{total}]: {item.filename} - {error}")

    def on_batch_complete(self, result: BatchResult):
        logger.info(
            f"Batch complete: {result.successful}/{result.total_items} successful "
            f"({result.success_rate * 100:.1f}%) in {result.total_time_ms:.0f}ms"
        )


class AsyncBatchProcessor:
    """
    Async batch processor for FTI operations.

    Supports both sync and async processing modes with configurable
    concurrency for optimal performance.
    """

    def __init__(
        self,
        max_workers: int = 4,
        progress_callback: Optional[BatchProgressCallback] = None,
    ):
        """
        Initialize batch processor.

        Args:
            max_workers: Maximum concurrent workers
            progress_callback: Optional progress callback
        """
        self.max_workers = max_workers
        self.progress_callback = progress_callback or ConsoleBatchProgress()
        self._cancelled = False
        self._executor: Optional[ThreadPoolExecutor] = None

    def cancel(self):
        """Cancel ongoing batch operation."""
        self._cancelled = True
        logger.info("Batch cancellation requested")

    def reset(self):
        """Reset cancellation state."""
        self._cancelled = False

    def process_batch_sync(
        self,
        items: List[BatchItem],
        process_func: Callable[[BatchItem], Any],
        sequential: bool = False,
    ) -> BatchResult:
        """
        Process a batch of items synchronously.

        Args:
            items: List of BatchItems to process
            process_func: Function to process each item
            sequential: If True, process one at a time

        Returns:
            BatchResult with aggregated results
        """
        self.reset()
        start_time = time.time()
        total = len(items)

        self.progress_callback.on_batch_start(total)

        if sequential:
            results = self._process_sequential(items, process_func)
        else:
            results = self._process_concurrent(items, process_func)

        # Aggregate results
        successful = sum(1 for item in items if item.status == BatchStatus.COMPLETED)
        failed = sum(1 for item in items if item.status == BatchStatus.FAILED)
        cancelled = sum(1 for item in items if item.status == BatchStatus.CANCELLED)

        total_time_ms = (time.time() - start_time) * 1000
        processing_times = [
            item.processing_time_ms for item in items if item.status == BatchStatus.COMPLETED
        ]
        average_time_ms = sum(processing_times) / len(processing_times) if processing_times else 0

        errors = [item.error for item in items if item.error]

        result = BatchResult(
            total_items=total,
            successful=successful,
            failed=failed,
            cancelled=cancelled,
            items=items,
            total_time_ms=total_time_ms,
            average_time_ms=average_time_ms,
            errors=errors,
        )

        self.progress_callback.on_batch_complete(result)
        return result

    def _process_sequential(
        self,
        items: List[BatchItem],
        process_func: Callable[[BatchItem], Any],
    ) -> List[BatchItem]:
        """Process items one at a time."""
        total = len(items)

        for index, item in enumerate(items):
            if self._cancelled:
                item.status = BatchStatus.CANCELLED
                continue

            self.progress_callback.on_item_start(item, index, total)

            try:
                item_start = time.time()
                item.result = process_func(item)
                item.processing_time_ms = (time.time() - item_start) * 1000
                item.status = BatchStatus.COMPLETED
                self.progress_callback.on_item_complete(item, index, total)
            except Exception as e:
                item.error = str(e)
                item.status = BatchStatus.FAILED
                self.progress_callback.on_item_error(item, str(e), index, total)

        return items

    def _process_concurrent(
        self,
        items: List[BatchItem],
        process_func: Callable[[BatchItem], Any],
    ) -> List[BatchItem]:
        """Process items concurrently using thread pool."""
        total = len(items)

        def process_item(index_item: Tuple[int, BatchItem]) -> Tuple[int, BatchItem]:
            index, item = index_item

            if self._cancelled:
                item.status = BatchStatus.CANCELLED
                return index, item

            self.progress_callback.on_item_start(item, index, total)

            try:
                item_start = time.time()
                item.result = process_func(item)
                item.processing_time_ms = (time.time() - item_start) * 1000
                item.status = BatchStatus.COMPLETED
                self.progress_callback.on_item_complete(item, index, total)
            except Exception as e:
                item.error = str(e)
                item.status = BatchStatus.FAILED
                self.progress_callback.on_item_error(item, str(e), index, total)

            return index, item

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            self._executor = executor
            futures = {executor.submit(process_item, (i, item)): i for i, item in enumerate(items)}

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Unexpected error in batch processing: {e}")

            self._executor = None

        return items

    async def process_batch_async(
        self,
        items: List[BatchItem],
        process_func: Callable[[BatchItem], Any],
        semaphore_count: Optional[int] = None,
    ) -> BatchResult:
        """
        Process a batch of items asynchronously.

        Uses asyncio for async operations. If process_func is sync,
        it runs in a thread pool to avoid blocking.

        Args:
            items: List of BatchItems to process
            process_func: Function to process each item (sync or async)
            semaphore_count: Limit concurrent operations (defaults to max_workers)

        Returns:
            BatchResult with aggregated results
        """
        self.reset()
        start_time = time.time()
        total = len(items)

        self.progress_callback.on_batch_start(total)

        semaphore = asyncio.Semaphore(semaphore_count or self.max_workers)

        async def process_with_semaphore(index: int, item: BatchItem):
            async with semaphore:
                if self._cancelled:
                    item.status = BatchStatus.CANCELLED
                    return item

                self.progress_callback.on_item_start(item, index, total)

                try:
                    item_start = time.time()

                    # Check if process_func is async
                    if asyncio.iscoroutinefunction(process_func):
                        item.result = await process_func(item)
                    else:
                        # Run sync function in executor
                        loop = asyncio.get_event_loop()
                        item.result = await loop.run_in_executor(None, process_func, item)

                    item.processing_time_ms = (time.time() - item_start) * 1000
                    item.status = BatchStatus.COMPLETED
                    self.progress_callback.on_item_complete(item, index, total)
                except Exception as e:
                    item.error = str(e)
                    item.status = BatchStatus.FAILED
                    self.progress_callback.on_item_error(item, str(e), index, total)

                return item

        # Process all items concurrently
        tasks = [process_with_semaphore(i, item) for i, item in enumerate(items)]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        successful = sum(1 for item in items if item.status == BatchStatus.COMPLETED)
        failed = sum(1 for item in items if item.status == BatchStatus.FAILED)
        cancelled = sum(1 for item in items if item.status == BatchStatus.CANCELLED)

        total_time_ms = (time.time() - start_time) * 1000
        processing_times = [
            item.processing_time_ms for item in items if item.status == BatchStatus.COMPLETED
        ]
        average_time_ms = sum(processing_times) / len(processing_times) if processing_times else 0

        errors = [item.error for item in items if item.error]

        result = BatchResult(
            total_items=total,
            successful=successful,
            failed=failed,
            cancelled=cancelled,
            items=items,
            total_time_ms=total_time_ms,
            average_time_ms=average_time_ms,
            errors=errors,
        )

        self.progress_callback.on_batch_complete(result)
        return result


def create_batch_items(
    file_paths: List[str],
    import_mode: str = "both",
    output_dir: Optional[str] = None,
) -> List[BatchItem]:
    """
    Create BatchItem list from file paths.

    Convenience function for creating batch items with
    auto-generated robot names.

    Args:
        file_paths: List of file paths to process
        import_mode: Import mode for all items
        output_dir: Optional output directory

    Returns:
        List of BatchItem objects
    """
    items = []

    for path in file_paths:
        # Auto-generate robot name from filename
        robot_name = Path(path).stem.replace("_", "").replace("-", "").title()

        # Determine output path
        if output_dir:
            output_path = os.path.join(output_dir, robot_name)
        else:
            output_path = None

        items.append(
            BatchItem(
                file_path=path,
                robot_name=robot_name,
                import_mode=import_mode,
                output_path=output_path,
            )
        )

    return items


async def batch_import_async(
    fti_instance,
    file_paths: List[str],
    import_mode: str = "both",
    output_dir: Optional[str] = None,
    max_workers: int = 4,
    progress_callback: Optional[BatchProgressCallback] = None,
) -> BatchResult:
    """
    Async batch import convenience function.

    Args:
        fti_instance: FileTypeImporter instance
        file_paths: List of file paths to import
        import_mode: Import mode for all files
        output_dir: Optional output directory
        max_workers: Maximum concurrent workers
        progress_callback: Optional progress callback

    Returns:
        BatchResult with all import results
    """
    items = create_batch_items(file_paths, import_mode, output_dir)
    processor = AsyncBatchProcessor(
        max_workers=max_workers,
        progress_callback=progress_callback,
    )

    def process_item(item: BatchItem):
        return fti_instance.import_robot(
            file_path=item.file_path,
            robot_name=item.robot_name,
            import_mode=item.import_mode,
            output_path=item.output_path,
        )

    return await processor.process_batch_async(items, process_item)


def batch_import_sync(
    fti_instance,
    file_paths: List[str],
    import_mode: str = "both",
    output_dir: Optional[str] = None,
    max_workers: int = 4,
    sequential: bool = False,
    progress_callback: Optional[BatchProgressCallback] = None,
) -> BatchResult:
    """
    Synchronous batch import convenience function.

    Args:
        fti_instance: FileTypeImporter instance
        file_paths: List of file paths to import
        import_mode: Import mode for all files
        output_dir: Optional output directory
        max_workers: Maximum concurrent workers
        sequential: If True, process files one at a time
        progress_callback: Optional progress callback

    Returns:
        BatchResult with all import results
    """
    items = create_batch_items(file_paths, import_mode, output_dir)
    processor = AsyncBatchProcessor(
        max_workers=max_workers,
        progress_callback=progress_callback,
    )

    def process_item(item: BatchItem):
        return fti_instance.import_robot(
            file_path=item.file_path,
            robot_name=item.robot_name,
            import_mode=item.import_mode,
            output_path=item.output_path,
        )

    return processor.process_batch_sync(items, process_item, sequential=sequential)


# Export main classes and functions
__all__ = [
    "BatchStatus",
    "BatchItem",
    "BatchResult",
    "BatchProgressCallback",
    "ConsoleBatchProgress",
    "AsyncBatchProcessor",
    "create_batch_items",
    "batch_import_async",
    "batch_import_sync",
]
