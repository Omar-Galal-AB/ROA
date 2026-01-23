#!/usr/bin/env python3
"""
Test script for FTI Storage Subsystem.

Verifies:
1. Storage initialization
2. Conversion logging (success, failure, cached)
3. History retrieval
4. Statistics aggregation
5. Cleanup functionality
6. Report generation
"""

import os
import sys
import tempfile
import time
from pathlib import Path

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fti_storage import (
    ConversionRecord,
    ConversionStatus,
    FTIStorage,
    StorageStats,
    get_storage,
    init_storage,
)


def test_storage_subsystem():
    """Run comprehensive storage subsystem tests."""
    print("=" * 60)
    print("FTI STORAGE SUBSYSTEM TEST")
    print("=" * 60)

    # Use temp directory for testing
    test_dir = Path(tempfile.mkdtemp(prefix="fti_storage_test_"))
    print(f"\n📁 Test storage directory: {test_dir}")

    # Initialize storage
    print("\n🔧 TEST 1: Storage Initialization")
    try:
        storage = FTIStorage(base_path=test_dir)

        # Verify directories exist
        assert storage.inputs_dir.exists(), "inputs dir missing"
        assert storage.outputs_dir.exists(), "outputs dir missing"
        assert storage.temp_dir.exists(), "temp dir missing"
        assert storage.logs_dir.exists(), "logs dir missing"
        assert storage.cache_dir.exists(), "cache dir missing"

        print("   ✅ Storage directories created")
        print(f"   📂 inputs: {storage.inputs_dir}")
        print(f"   📂 outputs: {storage.outputs_dir}")
        print(f"   📂 logs: {storage.logs_dir}")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

    # Test logging conversions
    print("\n📝 TEST 2: Logging Conversions")
    try:
        import uuid

        # Log a successful conversion
        record_id_1 = str(uuid.uuid4())
        storage.log_conversion_complete(
            record_id=record_id_1,
            request_id="req-001",
            input_path="/path/to/robot.urdf",
            input_format=".urdf",
            output_path="/output/robot.usd",
            output_format=".usd",
            duration_ms=1500,
            metadata={"robot_name": "TestRobot", "parts_count": 5},
        )
        print("   ✅ Logged successful conversion")

        # Log a failed conversion
        record_id_2 = str(uuid.uuid4())
        storage.log_conversion_failed(
            record_id=record_id_2,
            request_id="req-002",
            input_path="/path/to/broken.xacro",
            input_format=".xacro",
            error_code="1003",
            error_message="Failed to parse XACRO file",
            duration_ms=250,
        )
        print("   ✅ Logged failed conversion")

        # Log a cached conversion
        record_id_3 = str(uuid.uuid4())
        storage.log_conversion_cached(
            record_id=record_id_3,
            request_id="req-003",
            input_path="/path/to/robot.urdf",
            cached_from="req-001",
        )
        print("   ✅ Logged cached conversion")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test history retrieval
    print("\n📋 TEST 3: History Retrieval")
    try:
        history = storage.get_history(limit=10)
        assert len(history) >= 3, f"Expected 3+ records, got {len(history)}"

        print(f"   ✅ Retrieved {len(history)} history records")
        for r in history:
            status_icon = {"success": "✅", "failed": "❌", "cached": "♻️"}.get(r.status, "❓")
            print(f"      {status_icon} {r.request_id}: {r.status} ({r.input_format})")

        # Test error filtering
        errors = storage.get_recent_errors(limit=10)
        assert len(errors) >= 1, "Expected at least 1 error record"
        print(f"   ✅ Retrieved {len(errors)} error records")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test statistics
    print("\n📊 TEST 4: Statistics Aggregation")
    try:
        stats = storage.get_stats()

        assert stats.total_conversions >= 3, f"Expected 3+ total, got {stats.total_conversions}"
        assert stats.successful_conversions >= 1, "Expected at least 1 success"
        assert stats.failed_conversions >= 1, "Expected at least 1 failure"

        print(f"   ✅ Total conversions: {stats.total_conversions}")
        print(f"   ✅ Successful: {stats.successful_conversions}")
        print(f"   ✅ Failed: {stats.failed_conversions}")
        print(f"   ✅ Cached: {stats.cached_conversions}")
        print(f"   ✅ Success rate: {stats.success_rate:.1%}")
        print(f"   ✅ Formats processed: {stats.formats_processed}")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test report generation
    print("\n📄 TEST 5: Report Generation")
    try:
        report = storage.generate_report()
        assert "FTI STORAGE SUBSYSTEM REPORT" in report, "Report header missing"
        assert "CONVERSION STATISTICS" in report, "Stats section missing"
        assert "STORAGE USAGE" in report, "Usage section missing"

        print("   ✅ Report generated successfully")
        print("\n" + "-" * 50)
        print(report)
        print("-" * 50)

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test file operations
    print("\n📁 TEST 6: Output Directory Creation")
    try:
        out_dir = storage.create_output_dir("robot", request_id="test-req-123")
        assert out_dir.exists(), "Output directory not created"
        print(f"   ✅ Created output directory: {out_dir}")

        temp_file = storage.get_temp_file(".urdf")
        print(f"   ✅ Temp file path: {temp_file}")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

    # Test storage limit check
    print("\n💾 TEST 7: Storage Limit Check")
    try:
        under_limit = storage.check_storage_limit()
        print(f"   ✅ Storage under limit: {under_limit}")

        usage = storage._calculate_storage_usage()
        print(f"   ✅ Current usage: {usage / 1024:.1f} KB")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

    # Test cleanup (with short retention for testing)
    print("\n🧹 TEST 8: Cleanup Functionality")
    try:
        # This shouldn't remove anything since we just added records
        cleaned = storage.cleanup_old_records(days=0)  # 0 days = immediate
        print(f"   ✅ Cleanup completed: {cleaned} items removed")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False

    # Cleanup test directory
    print("\n🗑️ Cleaning up test directory...")
    import shutil

    try:
        shutil.rmtree(test_dir)
        print(f"   ✅ Removed: {test_dir}")
    except Exception as e:
        print(f"   ⚠️ Could not remove test dir: {e}")

    print("\n" + "=" * 60)
    print("✅ ALL STORAGE SUBSYSTEM TESTS PASSED!")
    print("=" * 60)

    return True


def test_actual_storage():
    """Test with actual FTI storage location."""
    print("\n" + "=" * 60)
    print("ACTUAL STORAGE LOCATION TEST")
    print("=" * 60)

    try:
        # Try to init at real location
        storage = get_storage()
        print(f"\n📁 Storage location: {storage.base_path}")

        # Check if we have history
        history = storage.get_history(limit=5)
        print(f"📋 History records: {len(history)}")

        if history:
            print("\nRecent conversions:")
            for r in history:
                status_icon = {
                    "success": "✅",
                    "failed": "❌",
                    "cached": "♻️",
                    "in_progress": "🔄",
                    "pending": "⏳",
                }.get(r.status, "❓")
                print(f"  {status_icon} {r.timestamp[:19]} | {r.request_id[:8]}... | {r.status}")

        # Show stats
        stats = storage.get_stats()
        print(f"\n📊 Statistics:")
        print(f"   Total: {stats.total_conversions}")
        print(f"   Success: {stats.successful_conversions}")
        print(f"   Failed: {stats.failed_conversions}")
        print(f"   Success rate: {stats.success_rate:.1%}")

        print("\n✅ Actual storage check complete")

    except Exception as e:
        print(f"⚠️ Could not access actual storage: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test FTI Storage Subsystem")
    parser.add_argument("--actual", action="store_true", help="Also test actual storage location")
    args = parser.parse_args()

    success = test_storage_subsystem()

    if args.actual:
        test_actual_storage()

    sys.exit(0 if success else 1)
