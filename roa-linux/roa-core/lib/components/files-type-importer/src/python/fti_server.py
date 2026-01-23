#!/usr/bin/env python3
"""
FTI Server - Standalone HTTP/WebSocket server for File Type Importer

Provides a standalone server that can convert 3D robot models without requiring
UE5 or the full ROA system. Can be accessed by:
- WT GUI (Webthread GUI) for user-initiated conversions
- CLI tools
- Any HTTP client

Endpoints:
    POST /convert        - Convert a file
    GET  /formats        - List supported formats
    POST /validate       - Validate a file
    GET  /cache/stats    - Get cache statistics
    GET  /cache/list     - List cached conversions
    DELETE /cache/clear  - Clear cache
    GET  /health         - Health check
    WS   /ws             - WebSocket for progress updates

Port: 9877 (default, configurable)
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - FTI Server - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FTIRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for FTI Server."""

    # Class-level reference to FTI instance
    fti_instance = None
    cache_instance = None

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.info("%s - %s" % (self.address_string(), format % args))

    def _send_json_response(self, data: Dict, status: int = 200):
        """Send a JSON response."""
        response = json.dumps(data, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response.encode())

    def _send_error_response(self, message: str, status: int = 400):
        """Send an error response."""
        self._send_json_response(
            {
                "success": False,
                "error": message,
                "timestamp": datetime.now().isoformat(),
            },
            status,
        )

    def _get_fti(self):
        """Get or create FTI instance."""
        if FTIRequestHandler.fti_instance is None:
            from file_type_importer import FileTypeImporter

            FTIRequestHandler.fti_instance = FileTypeImporter(enable_hb=False, enable_obs=False)
        return FTIRequestHandler.fti_instance

    def _get_cache(self):
        """Get or create cache instance."""
        if FTIRequestHandler.cache_instance is None:
            from fti_cache import get_cache

            FTIRequestHandler.cache_instance = get_cache()
        return FTIRequestHandler.cache_instance

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._handle_health()
        elif path == "/formats":
            self._handle_formats()
        elif path == "/cache/stats":
            self._handle_cache_stats()
        elif path == "/cache/list":
            self._handle_cache_list()
        elif path == "/":
            self._handle_index()
        else:
            self._send_error_response(f"Unknown endpoint: {path}", 404)

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error_response("Invalid JSON in request body")
            return

        if path == "/convert":
            self._handle_convert(data)
        elif path == "/validate":
            self._handle_validate(data)
        else:
            self._send_error_response(f"Unknown endpoint: {path}", 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/cache/clear":
            self._handle_cache_clear()
        else:
            self._send_error_response(f"Unknown endpoint: {path}", 404)

    def _handle_index(self):
        """Handle root endpoint - show API info."""
        self._send_json_response(
            {
                "service": "FTI Server",
                "version": "1.0.0",
                "description": "File Type Importer - 3D Robot Model Conversion Service",
                "endpoints": {
                    "GET /": "This API information",
                    "GET /health": "Health check",
                    "GET /formats": "List supported formats",
                    "POST /convert": "Convert a 3D model file",
                    "POST /validate": "Validate a file without converting",
                    "GET /cache/stats": "Get cache statistics",
                    "GET /cache/list": "List cached conversions",
                    "DELETE /cache/clear": "Clear the cache",
                },
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _handle_health(self):
        """Health check endpoint."""
        fti = self._get_fti()
        cache = self._get_cache()

        self._send_json_response(
            {
                "status": "healthy",
                "service": "fti-server",
                "uptime_seconds": time.time() - getattr(self.server, "start_time", time.time()),
                "cache_enabled": cache.enabled if cache else False,
                "cache_entries": len(cache.index) if cache else 0,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _handle_formats(self):
        """List supported formats."""
        fti = self._get_fti()
        formats = fti.get_supported_formats()

        from Converters import CONVERTER_REGISTRY

        self._send_json_response(
            {
                "formats": [
                    {"name": fmt, "has_converter": fmt in CONVERTER_REGISTRY} for fmt in formats
                ],
                "total": len(formats),
                "converters_available": list(CONVERTER_REGISTRY.keys()),
            }
        )

    def _handle_convert(self, data: Dict):
        """
        Handle conversion request.

        Expected data:
        {
            "source_path": "/path/to/file.urdf",
            "output_path": "/path/to/output.usd",  # optional
            "robot_name": "MyRobot",  # optional
            "import_mode": "both",  # optional: parts, assembly, both
            "use_cache": true,  # optional
            "settings": {}  # optional: scale_factor, etc.
        }
        """
        # Validate required fields
        if "source_path" not in data:
            self._send_error_response("Missing required field: source_path")
            return

        source_path = data["source_path"]

        # Check if source file exists
        if not os.path.exists(source_path):
            # Try with /mnt/c/ prefix for Windows paths
            if source_path.startswith("C:") or source_path.startswith("c:"):
                wsl_path = "/mnt/c/" + source_path[3:].replace("\\", "/")
                if os.path.exists(wsl_path):
                    source_path = wsl_path
                else:
                    self._send_error_response(
                        f'File not found: {data["source_path"]} (also tried {wsl_path})'
                    )
                    return
            else:
                self._send_error_response(f"File not found: {source_path}")
                return

        # Check cache first
        cache = self._get_cache()
        use_cache = data.get("use_cache", True)
        settings = data.get("settings", {})

        if use_cache and cache:
            cached = cache.lookup(source_path, settings)
            if cached:
                cached_path, entry = cached

                # If output path specified, copy from cache
                output_path = data.get("output_path")
                if output_path:
                    cache.copy_to_destination(entry.cache_key, output_path)

                self._send_json_response(
                    {
                        "success": True,
                        "from_cache": True,
                        "robot_name": entry.robot_name,
                        "parts_count": entry.parts_count,
                        "output_path": output_path or cached_path,
                        "cached_path": cached_path,
                        "cache_key": entry.cache_key,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                return

        # Perform conversion
        fti = self._get_fti()
        start_time = time.time()

        result = fti.import_robot(
            file_path=source_path,
            robot_name=data.get("robot_name"),
            import_mode=data.get("import_mode", "both"),
            output_path=data.get("output_path"),
        )

        conversion_time_ms = (time.time() - start_time) * 1000

        if result.success:
            # Store in cache
            if use_cache and cache and result.assembly_path:
                cache.store(
                    source_path=source_path,
                    converted_path=result.assembly_path,
                    settings=settings,
                    robot_name=result.robot_name,
                    parts_count=result.parts_count,
                    conversion_time_ms=conversion_time_ms,
                )

            self._send_json_response(
                {
                    "success": True,
                    "from_cache": False,
                    "robot_name": result.robot_name,
                    "parts_count": result.parts_count,
                    "content_path": result.content_path,
                    "assembly_path": result.assembly_path,
                    "parts_paths": result.parts_paths,
                    "warnings": result.warnings,
                    "conversion_time_ms": conversion_time_ms,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        else:
            self._send_error_response(result.error_message)

    def _handle_validate(self, data: Dict):
        """Handle validation request."""
        if "source_path" not in data:
            self._send_error_response("Missing required field: source_path")
            return

        source_path = data["source_path"]

        # Handle Windows paths
        if source_path.startswith("C:") or source_path.startswith("c:"):
            wsl_path = "/mnt/c/" + source_path[3:].replace("\\", "/")
            if os.path.exists(wsl_path):
                source_path = wsl_path

        fti = self._get_fti()
        result = fti.validate_file(source_path)

        self._send_json_response(
            {
                "valid": result["valid"],
                "format": result.get("format"),
                "file_size": result.get("file_size"),
                "file_name": result.get("file_name"),
                "error": result.get("error"),
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _handle_cache_stats(self):
        """Handle cache statistics request."""
        cache = self._get_cache()

        if cache:
            stats = cache.get_stats()
            self._send_json_response(stats)
        else:
            self._send_json_response({"enabled": False})

    def _handle_cache_list(self):
        """Handle cache list request."""
        cache = self._get_cache()

        if cache:
            entries = cache.list_entries()
            self._send_json_response({"entries": entries, "total": len(entries)})
        else:
            self._send_json_response({"entries": [], "total": 0})

    def _handle_cache_clear(self):
        """Handle cache clear request."""
        cache = self._get_cache()

        if cache:
            cache.clear()
            self._send_json_response({"success": True, "message": "Cache cleared"})
        else:
            self._send_json_response({"success": False, "message": "Cache not available"})


class FTIServer:
    """
    FTI Standalone Server.

    Provides HTTP API for 3D model conversion without requiring UE5.
    """

    DEFAULT_PORT = 9877

    def __init__(self, port: int = None, host: str = "0.0.0.0"):
        """
        Initialize FTI Server.

        Args:
            port: Port to listen on (default: 9877)
            host: Host to bind to (default: 0.0.0.0)
        """
        self.port = port or self.DEFAULT_PORT
        self.host = host
        self.server = None
        self._running = False

    def serve(self):
        """Start the server and block."""
        self.server = HTTPServer((self.host, self.port), FTIRequestHandler)
        self.server.start_time = time.time()
        self._running = True

        logger.info("=" * 50)
        logger.info("FTI Server Started")
        logger.info(f"Listening on http://{self.host}:{self.port}")
        logger.info("=" * 50)
        logger.info("")
        logger.info("Endpoints:")
        logger.info(f"  GET  http://localhost:{self.port}/")
        logger.info(f"  GET  http://localhost:{self.port}/health")
        logger.info(f"  GET  http://localhost:{self.port}/formats")
        logger.info(f"  POST http://localhost:{self.port}/convert")
        logger.info(f"  POST http://localhost:{self.port}/validate")
        logger.info(f"  GET  http://localhost:{self.port}/cache/stats")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        logger.info("")

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.stop()

    def serve_in_thread(self) -> threading.Thread:
        """Start the server in a background thread."""
        thread = threading.Thread(target=self.serve, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """Stop the server."""
        if self.server:
            self.server.shutdown()
            self._running = False
            logger.info("Server stopped")


def create_minimal_server(port: int = 9877):
    """Create and run a minimal FTI server."""
    server = FTIServer(port=port)
    server.serve()


def main():
    """Main entry point for FTI Server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FTI Server - Standalone 3D Model Conversion Service"
    )
    parser.add_argument(
        "--port", "-p", type=int, default=9877, help="Port to listen on (default: 9877)"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")

    args = parser.parse_args()

    server = FTIServer(port=args.port, host=args.host)
    server.serve()


if __name__ == "__main__":
    main()
