"""
Unit tests for FormatDetector
"""

import pytest
import tempfile
import os
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from format_detector import FormatDetector


class TestFormatDetector:
    """Test suite for FormatDetector class."""
    
    @pytest.fixture
    def detector(self):
        """Create a FormatDetector instance for testing."""
        return FormatDetector()
    
    def test_initialization(self, detector):
        """Test FormatDetector initializes correctly."""
        assert detector is not None
        assert len(detector.FORMAT_EXTENSIONS) > 0
    
    def test_get_supported_formats(self, detector):
        """Test getting list of supported formats."""
        formats = detector.get_supported_formats()
        assert 'urdf' in formats
        assert 'stl' in formats
        assert 'obj' in formats
        assert len(formats) >= 3
    
    def test_get_extensions_for_format(self, detector):
        """Test getting extensions for a specific format."""
        urdf_exts = detector.get_extensions_for_format('urdf')
        assert '.urdf' in urdf_exts
        
        stl_exts = detector.get_extensions_for_format('stl')
        assert '.stl' in stl_exts
    
    def test_is_supported_format(self, detector):
        """Test checking if format is supported."""
        assert detector.is_supported_format('urdf') is True
        assert detector.is_supported_format('stl') is True
        assert detector.is_supported_format('unknown_format') is False
    
    def test_detect_by_extension_urdf(self, detector):
        """Test detection by file extension for URDF."""
        with tempfile.NamedTemporaryFile(suffix='.urdf', delete=False) as f:
            temp_path = f.name
            f.write(b'<robot name="test"></robot>')
        
        try:
            # Note: detect_format will validate content, so we need valid URDF
            result = detector._detect_by_extension(temp_path)
            assert result == 'urdf'
        finally:
            os.unlink(temp_path)
    
    def test_detect_by_extension_stl(self, detector):
        """Test detection by file extension for STL."""
        with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as f:
            temp_path = f.name
        
        try:
            result = detector._detect_by_extension(temp_path)
            assert result == 'stl'
        finally:
            os.unlink(temp_path)
    
    def test_detect_by_extension_obj(self, detector):
        """Test detection by file extension for OBJ."""
        with tempfile.NamedTemporaryFile(suffix='.obj', delete=False) as f:
            temp_path = f.name
        
        try:
            result = detector._detect_by_extension(temp_path)
            assert result == 'obj'
        finally:
            os.unlink(temp_path)
    
    def test_detect_urdf_content(self, detector):
        """Test URDF detection by content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            temp_path = f.name
            f.write('<?xml version="1.0"?>\n<robot name="test_robot"></robot>')
        
        try:
            result = detector._detect_by_content(temp_path)
            assert result == 'urdf'
        finally:
            os.unlink(temp_path)
    
    def test_detect_obj_content(self, detector):
        """Test OBJ detection by content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_path = f.name
            f.write('# OBJ file\nv 0.0 0.0 0.0\nv 1.0 0.0 0.0\nf 1 2 3\n')
        
        try:
            result = detector._detect_by_content(temp_path)
            assert result == 'obj'
        finally:
            os.unlink(temp_path)
    
    def test_detect_format_urdf(self, detector):
        """Test full format detection for URDF file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.urdf', delete=False) as f:
            temp_path = f.name
            f.write('<?xml version="1.0"?>\n<robot name="test_robot">\n</robot>')
        
        try:
            result = detector.detect_format(temp_path)
            assert result == 'urdf'
        finally:
            os.unlink(temp_path)
    
    def test_detect_format_nonexistent_file(self, detector):
        """Test detection with nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            detector.detect_format('/nonexistent/path/file.urdf')
    
    def test_detect_format_unknown(self, detector):
        """Test detection with unknown format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.unknown', delete=False) as f:
            temp_path = f.name
            f.write('some random content')
        
        try:
            result = detector.detect_format(temp_path)
            # Should return None for unknown format
            assert result is None
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
