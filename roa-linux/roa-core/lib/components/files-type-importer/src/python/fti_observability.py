"""
FTI (Files Type Importer) Observability Integration
====================================================
Instrumentation for the FTI component

Enhanced with:
- Comprehensive file processing metrics
- URDF/Xacro/SDF parsing with validation tracking
- Mesh and texture loading metrics
- Asset pipeline tracking
- Import/export operation monitoring
- Cache hit/miss tracking
- Memory usage for large file processing

This module provides observability for file type detection,
URDF/Xacro processing, and data export operations.
"""

import time
import functools
from typing import Optional, Dict, Any, Callable, List
from contextlib import contextmanager

import os
import sys
_current_dir = os.path.dirname(os.path.abspath(__file__))
_shared_path = os.path.abspath(os.path.join(_current_dir, '..', '..', '..', '..', 'shared'))
if _shared_path not in sys.path:
    sys.path.insert(0, _shared_path)

try:
    from observability import (
        ROAObservability,
        ROAMetrics,
        trace_method,
    )
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False


class FTIMetrics:
    """FTI-specific metrics with comprehensive file processing instrumentation"""
    
    def __init__(self, base_metrics: 'ROAMetrics'):
        self.base = base_metrics
        
        # ==================== File Processing Metrics ====================
        self.files_processed = base_metrics.register_counter(
            'files_processed_total',
            'Total files processed',
            ['file_type', 'status'],
        )
        
        self.file_processing_duration = base_metrics.register_histogram(
            'file_processing_duration_seconds',
            'File processing duration',
            ['file_type'],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        
        self.file_size_bytes = base_metrics.register_histogram(
            'file_size_bytes',
            'Size of processed files',
            ['file_type'],
            buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600],
        )
        
        self.files_queued = base_metrics.register_gauge(
            'files_queued',
            'Files currently queued for processing',
        )
        
        self.files_processing = base_metrics.register_gauge(
            'files_processing',
            'Files currently being processed',
        )
        
        self.file_errors = base_metrics.register_counter(
            'file_errors_total',
            'File processing errors by type',
            ['file_type', 'error_type'],  # parse_error, io_error, validation_error
        )
        
        # ==================== URDF/Xacro Metrics ====================
        self.urdf_parsed = base_metrics.register_counter(
            'urdf_parsed_total',
            'Total URDF files parsed',
            ['status'],
        )
        
        self.xacro_processed = base_metrics.register_counter(
            'xacro_processed_total',
            'Total Xacro files processed',
            ['status'],
        )
        
        self.urdf_links_count = base_metrics.register_histogram(
            'urdf_links_count',
            'Number of links in URDF',
            buckets=[1, 5, 10, 20, 50, 100, 200],
        )
        
        self.urdf_joints_count = base_metrics.register_histogram(
            'urdf_joints_count',
            'Number of joints in URDF',
            buckets=[1, 5, 10, 20, 50, 100],
        )
        
        self.urdf_validation_errors = base_metrics.register_counter(
            'urdf_validation_errors_total',
            'URDF validation errors',
            ['error_type'],  # missing_mesh, invalid_joint, circular_reference
        )
        
        self.urdf_complexity_score = base_metrics.register_histogram(
            'urdf_complexity_score',
            'URDF model complexity score',
            buckets=[10, 50, 100, 250, 500, 1000],
        )
        
        # ==================== SDF Metrics ====================
        self.sdf_parsed = base_metrics.register_counter(
            'sdf_parsed_total',
            'Total SDF files parsed',
            ['status'],
        )
        
        self.sdf_models_count = base_metrics.register_histogram(
            'sdf_models_count',
            'Number of models in SDF',
            buckets=[1, 5, 10, 20, 50],
        )
        
        # ==================== Mesh Processing Metrics ====================
        self.meshes_loaded = base_metrics.register_counter(
            'meshes_loaded_total',
            'Total meshes loaded',
            ['mesh_format', 'status'],  # STL, DAE, OBJ
        )
        
        self.mesh_vertices_count = base_metrics.register_histogram(
            'mesh_vertices_count',
            'Number of vertices in mesh',
            ['mesh_format'],
            buckets=[100, 1000, 10000, 50000, 100000, 500000, 1000000],
        )
        
        self.mesh_faces_count = base_metrics.register_histogram(
            'mesh_faces_count',
            'Number of faces in mesh',
            ['mesh_format'],
            buckets=[100, 1000, 10000, 50000, 100000, 500000],
        )
        
        self.mesh_processing_time = base_metrics.register_histogram(
            'mesh_processing_time_seconds',
            'Mesh processing time',
            ['mesh_format', 'operation'],  # load, simplify, transform
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
        )
        
        # ==================== Texture Processing Metrics ====================
        self.textures_loaded = base_metrics.register_counter(
            'textures_loaded_total',
            'Total textures loaded',
            ['texture_format', 'status'],
        )
        
        self.texture_size = base_metrics.register_histogram(
            'texture_size_pixels',
            'Texture size (width * height)',
            ['texture_format'],
            buckets=[1024, 65536, 262144, 1048576, 4194304, 16777216],
        )
        
        # ==================== Format Detection Metrics ====================
        self.format_detection_duration = base_metrics.register_histogram(
            'format_detection_duration_seconds',
            'Format detection duration',
        )
        
        self.formats_detected = base_metrics.register_counter(
            'formats_detected_total',
            'Formats detected',
            ['format'],
        )
        
        self.format_detection_confidence = base_metrics.register_histogram(
            'format_detection_confidence',
            'Format detection confidence score',
            ['format'],
            buckets=[0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0],
        )
        
        # ==================== Import/Export Metrics ====================
        self.imports_total = base_metrics.register_counter(
            'imports_total',
            'Total data imports',
            ['source', 'format', 'status'],
        )
        
        self.import_duration = base_metrics.register_histogram(
            'import_duration_seconds',
            'Import duration',
            ['format'],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
        )
        
        self.exports_total = base_metrics.register_counter(
            'exports_total',
            'Total data exports',
            ['destination', 'format', 'status'],
        )
        
        self.export_size_bytes = base_metrics.register_histogram(
            'export_size_bytes',
            'Export data size',
            ['format'],
        )
        
        self.export_duration = base_metrics.register_histogram(
            'export_duration_seconds',
            'Export duration',
            ['format'],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
        )
        
        # ==================== Cache Metrics ====================
        self.cache_hits = base_metrics.register_counter(
            'cache_hits_total',
            'Cache hits',
            ['cache_type'],  # file, mesh, texture, parsed
        )
        
        self.cache_misses = base_metrics.register_counter(
            'cache_misses_total',
            'Cache misses',
            ['cache_type'],
        )
        
        self.cache_size_bytes = base_metrics.register_gauge(
            'cache_size_bytes',
            'Current cache size',
            ['cache_type'],
        )
        
        self.cache_evictions = base_metrics.register_counter(
            'cache_evictions_total',
            'Cache evictions',
            ['cache_type', 'reason'],  # size_limit, ttl, manual
        )
        
        # ==================== Asset Pipeline Metrics ====================
        self.pipeline_stages_duration = base_metrics.register_histogram(
            'pipeline_stage_duration_seconds',
            'Asset pipeline stage duration',
            ['stage'],  # validate, parse, transform, optimize, export
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
        )
        
        self.pipeline_runs = base_metrics.register_counter(
            'pipeline_runs_total',
            'Asset pipeline runs',
            ['status'],
        )
        
        # ==================== Memory Metrics ====================
        self.memory_usage_bytes = base_metrics.register_gauge(
            'fti_memory_usage_bytes',
            'FTI memory usage during file processing',
        )
        
        self.large_file_processing = base_metrics.register_counter(
            'large_file_processing_total',
            'Large file processing events (>10MB)',
            ['file_type'],
        )


class FTIObservability:
    """
    FTI Observability wrapper with comprehensive file processing instrumentation
    
    Provides detailed file import/export monitoring with:
    - File processing pipeline tracking
    - URDF/Xacro/SDF parsing metrics
    - Mesh and texture loading metrics
    - Cache hit/miss tracking
    - Import/export operation timing
    
    Usage:
        obs = FTIObservability()
        obs.start()
        
        # Track file processing
        with obs.trace_file_processing('model.urdf', 'urdf') as ctx:
            result = process_file()
            ctx.set_size(len(content))
        
        # Track mesh loading
        with obs.trace_mesh_loading('mesh.stl', 'stl'):
            mesh = load_mesh()
        obs.record_mesh_stats('stl', vertices=50000, faces=25000)
        
        # Cache tracking
        if cached:
            obs.record_cache_hit('parsed')
        else:
            obs.record_cache_miss('parsed')
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self._obs: Optional[ROAObservability] = None
        self._metrics: Optional[FTIMetrics] = None
        
        if OBSERVABILITY_AVAILABLE:
            self._obs = ROAObservability(
                component_name='fti',
                service_version=config.get('version', '1.0.0') if config else '1.0.0',
            )
            self._metrics = FTIMetrics(self._obs.metrics)
    
    def start(self):
        """Start observability"""
        if self._obs:
            self._obs.start()
            self._obs.set_ready()
    
    def stop(self):
        """Stop observability"""
        if self._obs:
            self._obs.stop()
    
    @property
    def logger(self):
        return self._obs.logger if self._obs else None
    
    @property
    def metrics(self) -> Optional[FTIMetrics]:
        return self._metrics
    
    @property
    def tracer(self):
        return self._obs.tracer if self._obs else None
    
    # ==================== File Processing ====================
    
    def track_file_processing(self, filename: str, file_type: str):
        """Context manager to track file processing (legacy)"""
        return _FileProcessingTracker(self, filename, file_type)
    
    @contextmanager
    def trace_file_processing(self, filename: str, file_type: str):
        """
        Context manager to trace file processing with result tracking
        
        Usage:
            with obs.trace_file_processing('model.urdf', 'urdf') as ctx:
                result = process()
                ctx.set_size(file_size)
        """
        start_time = time.perf_counter()
        result = {'size': None, 'success': True}
        
        class FileContext:
            def set_size(self, size: int):
                result['size'] = size
            
            def set_failed(self):
                result['success'] = False
        
        if self._metrics:
            self._metrics.files_processing.inc()
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'file.process.{file_type}',
                    attributes={
                        'file.name': filename,
                        'file.type': file_type,
                        'component': 'fti',
                    }
                ):
                    yield FileContext()
            else:
                yield FileContext()
        except Exception:
            result['success'] = False
            raise
        finally:
            if self._metrics:
                self._metrics.files_processing.dec()
                
                duration = time.perf_counter() - start_time
                self._metrics.files_processed.labels(
                    file_type=file_type,
                    status='success' if result['success'] else 'error',
                ).inc()
                self._metrics.file_processing_duration.labels(
                    file_type=file_type
                ).observe(duration)
                
                if result['size']:
                    self._metrics.file_size_bytes.labels(
                        file_type=file_type
                    ).observe(result['size'])
                    
                    # Track large files
                    if result['size'] > 10 * 1024 * 1024:  # 10MB
                        self._metrics.large_file_processing.labels(
                            file_type=file_type
                        ).inc()
    
    def record_file_error(self, file_type: str, error_type: str):
        """Record file processing error"""
        if self._metrics:
            self._metrics.file_errors.labels(
                file_type=file_type,
                error_type=error_type,
            ).inc()
    
    def set_files_queued(self, count: int):
        """Set number of files queued for processing"""
        if self._metrics:
            self._metrics.files_queued.set(count)
    
    # ==================== URDF/Xacro/SDF ====================
    
    def record_urdf_parsed(
        self, 
        links: int, 
        joints: int, 
        success: bool = True,
        complexity_score: float = None,
    ):
        """Record URDF parsing metrics"""
        if self._metrics:
            self._metrics.urdf_parsed.labels(
                status='success' if success else 'error'
            ).inc()
            self._metrics.urdf_links_count.observe(links)
            self._metrics.urdf_joints_count.observe(joints)
            
            if complexity_score is not None:
                self._metrics.urdf_complexity_score.observe(complexity_score)
    
    def record_urdf_validation_error(self, error_type: str):
        """Record URDF validation error"""
        if self._metrics:
            self._metrics.urdf_validation_errors.labels(error_type=error_type).inc()
    
    def record_xacro_processed(self, success: bool = True):
        """Record Xacro processing"""
        if self._metrics:
            self._metrics.xacro_processed.labels(
                status='success' if success else 'error'
            ).inc()
    
    def record_sdf_parsed(self, models: int, success: bool = True):
        """Record SDF parsing metrics"""
        if self._metrics:
            self._metrics.sdf_parsed.labels(
                status='success' if success else 'error'
            ).inc()
            self._metrics.sdf_models_count.observe(models)
    
    @contextmanager
    def trace_urdf_parsing(self, filename: str):
        """Context manager for tracing URDF parsing"""
        start_time = time.perf_counter()
        result = {'links': 0, 'joints': 0, 'success': True}
        
        class URDFContext:
            def set_stats(self, links: int, joints: int):
                result['links'] = links
                result['joints'] = joints
            
            def set_failed(self):
                result['success'] = False
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    'urdf.parse',
                    attributes={
                        'file.name': filename,
                        'component': 'fti',
                    }
                ):
                    yield URDFContext()
            else:
                yield URDFContext()
        except Exception:
            result['success'] = False
            raise
        finally:
            self.record_urdf_parsed(
                result['links'],
                result['joints'],
                result['success'],
            )
    
    # ==================== Mesh Processing ====================
    
    def record_mesh_loaded(self, mesh_format: str, success: bool = True):
        """Record mesh loading"""
        if self._metrics:
            self._metrics.meshes_loaded.labels(
                mesh_format=mesh_format,
                status='success' if success else 'error',
            ).inc()
    
    def record_mesh_stats(self, mesh_format: str, vertices: int, faces: int):
        """Record mesh statistics"""
        if self._metrics:
            self._metrics.mesh_vertices_count.labels(mesh_format=mesh_format).observe(vertices)
            self._metrics.mesh_faces_count.labels(mesh_format=mesh_format).observe(faces)
    
    def record_mesh_processing_time(self, mesh_format: str, operation: str, duration: float):
        """Record mesh processing time"""
        if self._metrics:
            self._metrics.mesh_processing_time.labels(
                mesh_format=mesh_format,
                operation=operation,
            ).observe(duration)
    
    @contextmanager
    def trace_mesh_loading(self, filename: str, mesh_format: str):
        """Context manager for tracing mesh loading"""
        start_time = time.perf_counter()
        result = {'success': True}
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'mesh.load.{mesh_format}',
                    attributes={
                        'mesh.filename': filename,
                        'mesh.format': mesh_format,
                        'component': 'fti',
                    }
                ):
                    yield
            else:
                yield
        except Exception:
            result['success'] = False
            raise
        finally:
            duration = time.perf_counter() - start_time
            self.record_mesh_loaded(mesh_format, result['success'])
            self.record_mesh_processing_time(mesh_format, 'load', duration)
    
    # ==================== Texture Processing ====================
    
    def record_texture_loaded(
        self, 
        texture_format: str, 
        success: bool = True,
        width: int = None,
        height: int = None,
    ):
        """Record texture loading"""
        if self._metrics:
            self._metrics.textures_loaded.labels(
                texture_format=texture_format,
                status='success' if success else 'error',
            ).inc()
            
            if width and height:
                self._metrics.texture_size.labels(
                    texture_format=texture_format
                ).observe(width * height)
    
    # ==================== Format Detection ====================
    
    def record_format_detected(
        self, 
        format_name: str, 
        duration: float,
        confidence: float = None,
    ):
        """Record format detection"""
        if self._metrics:
            self._metrics.formats_detected.labels(format=format_name).inc()
            self._metrics.format_detection_duration.observe(duration)
            
            if confidence is not None:
                self._metrics.format_detection_confidence.labels(
                    format=format_name
                ).observe(confidence)
    
    # ==================== Import/Export ====================
    
    def record_import(
        self, 
        source: str, 
        format_name: str, 
        success: bool = True,
        duration: float = None,
    ):
        """Record data import"""
        if self._metrics:
            self._metrics.imports_total.labels(
                source=source,
                format=format_name,
                status='success' if success else 'error',
            ).inc()
            
            if duration is not None:
                self._metrics.import_duration.labels(format=format_name).observe(duration)
    
    def record_export(
        self, 
        destination: str, 
        format_name: str, 
        size: int, 
        success: bool = True,
        duration: float = None,
    ):
        """Record data export"""
        if self._metrics:
            self._metrics.exports_total.labels(
                destination=destination,
                format=format_name,
                status='success' if success else 'error',
            ).inc()
            self._metrics.export_size_bytes.labels(format=format_name).observe(size)
            
            if duration is not None:
                self._metrics.export_duration.labels(format=format_name).observe(duration)
    
    @contextmanager
    def trace_import(self, source: str, format_name: str):
        """Context manager for tracing import operations"""
        start_time = time.perf_counter()
        result = {'success': True}
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'import.{format_name}',
                    attributes={
                        'import.source': source,
                        'import.format': format_name,
                        'component': 'fti',
                    }
                ):
                    yield
            else:
                yield
        except Exception:
            result['success'] = False
            raise
        finally:
            duration = time.perf_counter() - start_time
            self.record_import(source, format_name, result['success'], duration)
    
    @contextmanager
    def trace_export(self, destination: str, format_name: str):
        """Context manager for tracing export operations"""
        start_time = time.perf_counter()
        result = {'success': True, 'size': 0}
        
        class ExportContext:
            def set_size(self, size: int):
                result['size'] = size
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'export.{format_name}',
                    attributes={
                        'export.destination': destination,
                        'export.format': format_name,
                        'component': 'fti',
                    }
                ):
                    yield ExportContext()
            else:
                yield ExportContext()
        except Exception:
            result['success'] = False
            raise
        finally:
            duration = time.perf_counter() - start_time
            self.record_export(
                destination, format_name, result['size'],
                result['success'], duration,
            )
    
    # ==================== Cache Metrics ====================
    
    def record_cache_hit(self, cache_type: str):
        """Record cache hit"""
        if self._metrics:
            self._metrics.cache_hits.labels(cache_type=cache_type).inc()
    
    def record_cache_miss(self, cache_type: str):
        """Record cache miss"""
        if self._metrics:
            self._metrics.cache_misses.labels(cache_type=cache_type).inc()
    
    def set_cache_size(self, cache_type: str, size_bytes: int):
        """Set cache size"""
        if self._metrics:
            self._metrics.cache_size_bytes.labels(cache_type=cache_type).set(size_bytes)
    
    def record_cache_eviction(self, cache_type: str, reason: str):
        """Record cache eviction"""
        if self._metrics:
            self._metrics.cache_evictions.labels(
                cache_type=cache_type,
                reason=reason,
            ).inc()
    
    # ==================== Pipeline Metrics ====================
    
    def record_pipeline_stage(self, stage: str, duration: float):
        """Record pipeline stage duration"""
        if self._metrics:
            self._metrics.pipeline_stages_duration.labels(stage=stage).observe(duration)
    
    def record_pipeline_run(self, success: bool = True):
        """Record pipeline run"""
        if self._metrics:
            self._metrics.pipeline_runs.labels(
                status='success' if success else 'error'
            ).inc()
    
    @contextmanager
    def trace_pipeline_stage(self, stage: str):
        """Context manager for tracing pipeline stage"""
        start_time = time.perf_counter()
        
        try:
            if self._obs:
                with self._obs.tracer.start_span(
                    f'pipeline.{stage}',
                    attributes={'pipeline.stage': stage, 'component': 'fti'}
                ):
                    yield
            else:
                yield
        finally:
            duration = time.perf_counter() - start_time
            self.record_pipeline_stage(stage, duration)
    
    # ==================== Memory Metrics ====================
    
    def set_memory_usage(self, usage_bytes: int):
        """Set current memory usage"""
        if self._metrics:
            self._metrics.memory_usage_bytes.set(usage_bytes)


class _FileProcessingTracker:
    """Context manager for tracking file processing"""
    
    def __init__(self, obs: FTIObservability, filename: str, file_type: str):
        self.obs = obs
        self.filename = filename
        self.file_type = file_type
        self.start_time = None
        self.success = True
    
    def __enter__(self):
        self.start_time = time.time()
        if self.obs._obs:
            self.obs._obs.tracer.set_attribute('filename', self.filename)
            self.obs._obs.tracer.set_attribute('file_type', self.file_type)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.success = exc_type is None
        
        if self.obs._metrics:
            self.obs._metrics.files_processed.labels(
                file_type=self.file_type,
                status='success' if self.success else 'error',
            ).inc()
            self.obs._metrics.file_processing_duration.labels(
                file_type=self.file_type,
            ).observe(duration)
        
        if not self.success and self.obs._obs:
            self.obs._obs.record_error(
                'file_processing_error',
                str(exc_val),
                exc_val,
            )
        
        return False


# ─── Decorator for FTI functions ───────────────────────────────

def fti_traced(obs: FTIObservability):
    """Decorator to trace FTI functions"""
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if obs.tracer:
                with obs.tracer.start_span(f'fti.{func.__name__}'):
                    return func(*args, **kwargs)
            return func(*args, **kwargs)
        return wrapper
    return decorator
