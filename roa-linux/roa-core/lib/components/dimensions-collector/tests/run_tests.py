#!/usr/bin/env python3
"""
DIMC Test Runner

Runs all DIMC tests with comprehensive output.

Usage:
    ./run_tests.py              # Run all tests
    ./run_tests.py monitoring   # Run monitoring tests only
    ./run_tests.py bridge       # Run bridge tests only
    ./run_tests.py heartbeat    # Run heartbeat tests only
"""

import argparse
import os
import sys
import time
import unittest
from pathlib import Path

# Add source path
src_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(src_path))


def run_all_tests():
    """Run all DIMC tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Discover all tests in tests directory
    tests_dir = Path(__file__).parent
    discovered_suite = loader.discover(str(tests_dir), pattern="test_*.py")
    suite.addTests(discovered_suite)

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_monitoring_tests():
    """Run monitoring subsystem tests."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent), pattern="test_dimc_monitoring.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_bridge_tests():
    """Run bridge subsystem tests."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent), pattern="test_dimc_bridge.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_heartbeat_tests():
    """Run heartbeat subsystem tests."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent), pattern="test_dimc_heartbeat.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_core_tests():
    """Run core functionality tests."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent), pattern="test_dimc_core.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_api_tests():
    """Run API layer tests."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(Path(__file__).parent), pattern="test_dimc_api.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description="DIMC Test Runner")
    parser.add_argument(
        "test_suite",
        nargs="?",
        choices=["all", "monitoring", "bridge", "heartbeat", "core", "api"],
        default="all",
        help="Test suite to run (default: all)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("DIMC Test Runner")
    print("=" * 70)
    print(f"Python: {sys.version}")
    print(f"Source: {src_path}")
    print(f"Test Suite: {args.test_suite}")
    print("=" * 70)
    print()

    start_time = time.time()

    if args.test_suite == "all":
        success = run_all_tests()
    elif args.test_suite == "monitoring":
        success = run_monitoring_tests()
    elif args.test_suite == "bridge":
        success = run_bridge_tests()
    elif args.test_suite == "heartbeat":
        success = run_heartbeat_tests()
    elif args.test_suite == "core":
        success = run_core_tests()
    elif args.test_suite == "api":
        success = run_api_tests()
    else:
        print(f"Unknown test suite: {args.test_suite}")
        return 1

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    print(f"Tests completed in {elapsed:.2f} seconds")
    print(f"Result: {'PASSED' if success else 'FAILED'}")
    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
