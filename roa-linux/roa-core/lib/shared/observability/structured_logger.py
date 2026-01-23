"""
ROA Structured Logger
=====================
JSON-formatted logging for Fluent Bit/Loki integration

Features:
- Structured JSON output
- Trace context injection (W3C Trace Context)
- Component-specific fields
- Log level filtering
- File rotation
- Optional Fluent Bit forward
"""

import logging
import json
import sys
import os
import socket
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, asdict

from .config import ObservabilityConfig, LoggingConfig, LogLevel


@dataclass
class LogContext:
    """Additional context for log entries"""
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        return {k: v for k, v in asdict(self).items() if v is not None}


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging
    
    Output format compatible with Fluent Bit JSON parser
    """
    
    def __init__(
        self,
        component_name: str,
        service_version: str,
        instance_id: Optional[str] = None,
        include_trace_context: bool = True,
    ):
        super().__init__()
        self.component_name = component_name
        self.service_version = service_version
        self.instance_id = instance_id or socket.gethostname()
        self.include_trace_context = include_trace_context
        self._hostname = socket.gethostname()
        self._pid = os.getpid()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        
        # Base log structure
        log_entry = {
            # Timestamp in ISO 8601 format with timezone
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            
            # Log level
            "level": record.levelname,
            "level_num": record.levelno,
            
            # Message
            "message": record.getMessage(),
            
            # Source information
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "file": record.filename,
            "path": record.pathname,
            
            # Component identification (for Loki labels)
            "component": self.component_name,
            "service": f"roa-{self.component_name}",
            "version": self.service_version,
            "instance": self.instance_id,
            
            # Host information
            "host": self._hostname,
            "pid": self._pid,
            "thread": record.thread,
            "thread_name": record.threadName,
        }
        
        # Add trace context if available
        if self.include_trace_context:
            trace_id = getattr(record, 'trace_id', None)
            span_id = getattr(record, 'span_id', None)
            
            if trace_id:
                log_entry["trace_id"] = trace_id
            if span_id:
                log_entry["span_id"] = span_id
            
            # Try to get from OpenTelemetry context
            try:
                from opentelemetry import trace
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    ctx = current_span.get_span_context()
                    log_entry["trace_id"] = format(ctx.trace_id, '032x')
                    log_entry["span_id"] = format(ctx.span_id, '016x')
                    log_entry["trace_flags"] = ctx.trace_flags
            except ImportError:
                pass
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": self.formatException(record.exc_info),
            }
        
        # Add extra fields from record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'created', 'filename', 'funcName',
                'levelname', 'levelno', 'lineno', 'module', 'msecs',
                'pathname', 'process', 'processName', 'relativeCreated',
                'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                'trace_id', 'span_id', 'message'
            }:
                try:
                    json.dumps(value)  # Check if serializable
                    extra_fields[key] = value
                except (TypeError, ValueError):
                    extra_fields[key] = str(value)
        
        if extra_fields:
            log_entry["extra"] = extra_fields
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """
    Colored console formatter for human-readable output
    """
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    def __init__(self, component_name: str, use_colors: bool = True):
        super().__init__()
        self.component_name = component_name
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname
        
        if self.use_colors:
            color = self.COLORS.get(level, '')
            formatted = (
                f"{self.BOLD}[{timestamp}]{self.RESET} "
                f"{color}{level:8}{self.RESET} "
                f"[{self.component_name}] "
                f"{record.getMessage()}"
            )
        else:
            formatted = (
                f"[{timestamp}] {level:8} [{self.component_name}] {record.getMessage()}"
            )
        
        # Add trace context if available
        trace_id = getattr(record, 'trace_id', None)
        if trace_id and self.use_colors:
            formatted += f" {self.COLORS['DEBUG']}[trace:{trace_id[:8]}]{self.RESET}"
        
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


class FluentBitHandler(logging.Handler):
    """
    Send logs to Fluent Bit via TCP forward
    """
    
    def __init__(self, host: str, port: int, tag: str = "roa"):
        super().__init__()
        self.host = host
        self.port = port
        self.tag = tag
        self._socket = None
        self._lock = threading.Lock()
    
    def _connect(self):
        """Establish connection to Fluent Bit"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
        except Exception:
            self._socket = None
    
    def emit(self, record: logging.LogRecord):
        """Send log record to Fluent Bit"""
        try:
            with self._lock:
                if self._socket is None:
                    self._connect()
                
                if self._socket:
                    msg = self.format(record)
                    # Forward protocol: [tag, timestamp, record]
                    data = json.dumps([
                        self.tag,
                        int(record.created),
                        json.loads(msg)
                    ]) + "\n"
                    self._socket.sendall(data.encode('utf-8'))
        except Exception:
            self._socket = None
    
    def close(self):
        """Close connection"""
        with self._lock:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
        super().close()


class ROALogger:
    """
    ROA Logger with structured JSON output
    
    Usage:
        logger = ROALogger("webthread", "1.0.0")
        logger.info("Starting component", extra={"port": 8080})
        
        # With context
        with logger.context(trace_id="abc123"):
            logger.info("Processing request")
    """
    
    _loggers: Dict[str, 'ROALogger'] = {}
    _lock = threading.Lock()
    
    def __init__(
        self,
        component_name: str,
        config: Optional[Union[ObservabilityConfig, LoggingConfig]] = None,
        service_version: str = "1.0.0",
    ):
        self.component_name = component_name
        self.service_version = service_version
        
        # Extract logging config
        if isinstance(config, ObservabilityConfig):
            self.config = config.logging
            self.service_version = config.service_version
        elif isinstance(config, LoggingConfig):
            self.config = config
        else:
            self.config = LoggingConfig()
        
        # Create logger
        self._logger = logging.getLogger(f"roa.{component_name}")
        self._logger.setLevel(getattr(logging, self.config.level.value))
        self._logger.handlers.clear()
        
        # Thread-local context
        self._context = threading.local()
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Configure log handlers"""
        
        # JSON file handler
        if self.config.log_dir:
            os.makedirs(self.config.log_dir, exist_ok=True)
            log_file = os.path.join(
                self.config.log_dir,
                f"roa-{self.component_name}.log"
            )
            
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=self.config.max_file_size_mb * 1024 * 1024,
                backupCount=self.config.backup_count,
            )
            file_handler.setFormatter(JSONFormatter(
                component_name=self.component_name,
                service_version=self.service_version,
                include_trace_context=self.config.include_trace_context,
            ))
            self._logger.addHandler(file_handler)
        
        # Console handler
        if self.config.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(ConsoleFormatter(self.component_name))
            self._logger.addHandler(console_handler)
        
        # Fluent Bit handler
        if self.config.fluent_bit_host:
            fb_handler = FluentBitHandler(
                host=self.config.fluent_bit_host,
                port=self.config.fluent_bit_port,
                tag=f"roa.{self.component_name}",
            )
            fb_handler.setFormatter(JSONFormatter(
                component_name=self.component_name,
                service_version=self.service_version,
                include_trace_context=self.config.include_trace_context,
            ))
            self._logger.addHandler(fb_handler)
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        """Internal log method with context injection"""
        extra = kwargs.pop('extra', {})
        
        # Inject thread-local context
        ctx = getattr(self._context, 'data', {})
        extra.update(ctx)
        
        kwargs['extra'] = extra
        self._logger.log(level, msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message"""
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message"""
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message"""
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message"""
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Log critical message"""
        self._log(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception with traceback"""
        kwargs['exc_info'] = True
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def set_context(self, **kwargs):
        """Set thread-local context"""
        if not hasattr(self._context, 'data'):
            self._context.data = {}
        self._context.data.update(kwargs)
    
    def clear_context(self):
        """Clear thread-local context"""
        self._context.data = {}
    
    class _ContextManager:
        """Context manager for temporary context"""
        def __init__(self, logger: 'ROALogger', **kwargs):
            self.logger = logger
            self.kwargs = kwargs
            self.previous = {}
        
        def __enter__(self):
            if not hasattr(self.logger._context, 'data'):
                self.logger._context.data = {}
            self.previous = dict(self.logger._context.data)
            self.logger._context.data.update(self.kwargs)
            return self.logger
        
        def __exit__(self, *args):
            self.logger._context.data = self.previous
    
    def context(self, **kwargs) -> '_ContextManager':
        """Create a context manager with temporary context"""
        return self._ContextManager(self, **kwargs)
    
    @classmethod
    def get_logger(cls, component_name: str) -> 'ROALogger':
        """Get or create a logger for a component"""
        with cls._lock:
            if component_name not in cls._loggers:
                cls._loggers[component_name] = cls(component_name)
            return cls._loggers[component_name]


# Convenience function
def get_logger(component_name: str) -> ROALogger:
    """Get or create a logger for a component"""
    return ROALogger.get_logger(component_name)


# Standard logging integration
class ROALoggingHandler(logging.Handler):
    """
    Drop-in handler for standard logging to route to ROALogger
    
    Usage:
        import logging
        logging.basicConfig(handlers=[ROALoggingHandler("webthread")])
    """
    
    def __init__(self, component_name: str):
        super().__init__()
        self.roa_logger = get_logger(component_name)
    
    def emit(self, record: logging.LogRecord):
        """Route to ROALogger"""
        level_map = {
            logging.DEBUG: self.roa_logger.debug,
            logging.INFO: self.roa_logger.info,
            logging.WARNING: self.roa_logger.warning,
            logging.ERROR: self.roa_logger.error,
            logging.CRITICAL: self.roa_logger.critical,
        }
        log_func = level_map.get(record.levelno, self.roa_logger.info)
        
        extra = {
            'original_logger': record.name,
            'original_module': record.module,
        }
        
        if record.exc_info:
            log_func(record.getMessage(), exc_info=record.exc_info, extra=extra)
        else:
            log_func(record.getMessage(), extra=extra)
