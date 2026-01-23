"""
conftest.py - pytest configuration for HB Subsystem tests
ROA - Robot Operations & Automation
"""

import sys
import os
import pytest

# Add parent directories to path so we can import hb_subsystem
_current_dir = os.path.dirname(os.path.abspath(__file__))
_hb_subsystem_dir = os.path.dirname(_current_dir)  # hb_subsystem/
_python_dir = os.path.dirname(_hb_subsystem_dir)  # python/

# Add to path
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)
if _hb_subsystem_dir not in sys.path:
    sys.path.insert(0, _hb_subsystem_dir)


@pytest.fixture
def temp_storage_dir(tmp_path):
    """Create temporary storage directories for tests"""
    fast_dir = tmp_path / "fast"
    persistent_dir = tmp_path / "persistent"
    fast_dir.mkdir()
    persistent_dir.mkdir()
    
    return {
        'fast': str(fast_dir),
        'persistent': str(persistent_dir)
    }


@pytest.fixture
def mock_component_state():
    """Mock component state for testing"""
    return {
        'FTI': {'health': 'HEALTHY', 'state': 'ACTIVE'},
        'ROC': {'health': 'HEALTHY', 'state': 'ACTIVE'},
        'DIMC': {'health': 'DEGRADED', 'state': 'ACTIVE'},
    }
