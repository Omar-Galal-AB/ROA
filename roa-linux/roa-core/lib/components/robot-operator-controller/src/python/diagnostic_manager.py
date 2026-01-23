"""
Diagnostic Manager - Self-test and health verification for ROC.

Provides:
- Startup self-test for all subsystems
- Periodic health checks with pass/fail
- Diagnostic API for testing specific subsystems
- Readiness reporting

Based on ROC_CRITICAL_ANALYSIS.md Gap #6.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple


class DiagnosticResult(Enum):
    """Result of a diagnostic test."""
    PASSED = auto()
    WARNING = auto()
    FAILED = auto()
    SKIPPED = auto()
    ERROR = auto()


class DiagnosticCategory(Enum):
    """Categories of diagnostics."""
    CONNECTIVITY = "connectivity"
    SUBSYSTEM = "subsystem"
    SAFETY = "safety"
    PERFORMANCE = "performance"
    INTEGRATION = "integration"


@dataclass
class DiagnosticTest:
    """Definition of a diagnostic test."""
    name: str
    category: DiagnosticCategory
    description: str
    test_func: Callable[[], Tuple[DiagnosticResult, str]]
    critical: bool = False  # If True, failure blocks startup
    timeout_s: float = 5.0


@dataclass
class DiagnosticTestResult:
    """Result of running a diagnostic test."""
    test_name: str
    category: DiagnosticCategory
    result: DiagnosticResult
    message: str
    duration_ms: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "category": self.category.value,
            "result": self.result.name,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp
        }


@dataclass
class DiagnosticManagerConfig:
    """Configuration for DiagnosticManager."""
    # Startup settings
    run_startup_diagnostics: bool = True
    skip_non_critical_on_startup: bool = False
    startup_timeout_s: float = 30.0
    
    # Periodic settings
    enable_periodic_diagnostics: bool = True
    periodic_interval_s: float = 60.0  # 1 minute
    
    # Failure handling
    max_consecutive_failures: int = 3
    alert_on_warning: bool = True


DiagnosticCallback = Callable[[DiagnosticTestResult], None]


class DiagnosticManager:
    """
    Manages self-test and health verification for ROC.
    
    Responsibilities:
    - Run startup diagnostics before system ready
    - Periodic health checks
    - On-demand diagnostic API
    - Report readiness to Webthread
    
    Usage:
        manager = DiagnosticManager()
        
        # Register tests
        manager.register_test(DiagnosticTest(
            name="ipc_connection",
            category=DiagnosticCategory.CONNECTIVITY,
            description="Test UE5 IPC connection",
            test_func=test_ipc,
            critical=True
        ))
        
        # Run startup diagnostics
        ready = await manager.run_startup_diagnostics()
        
        # Run specific test
        result = await manager.run_test("ipc_connection")
    """
    
    def __init__(
        self,
        config: Optional[DiagnosticManagerConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize DiagnosticManager.
        
        Args:
            config: Manager configuration
            logger: Logger instance
        """
        self.config = config or DiagnosticManagerConfig()
        self.logger = logger or logging.getLogger(__name__)
        
        # Registered tests
        self._tests: Dict[str, DiagnosticTest] = {}
        
        # Results history
        self._last_results: Dict[str, DiagnosticTestResult] = {}
        self._result_history: List[DiagnosticTestResult] = []
        self._max_history = 1000
        
        # State
        self._startup_complete = False
        self._startup_passed = False
        self._running = False
        self._periodic_task: Optional[asyncio.Task] = None
        
        # Failure tracking
        self._consecutive_failures: Dict[str, int] = {}
        
        # Callbacks
        self._result_callbacks: List[DiagnosticCallback] = []
        
        # Statistics
        self._stats = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_warned": 0,
            "startup_duration_ms": 0.0
        }
        
        self.logger.info("DiagnosticManager initialized")
    
    # =========================================================================
    # TEST REGISTRATION
    # =========================================================================
    
    def register_test(self, test: DiagnosticTest):
        """
        Register a diagnostic test.
        
        Args:
            test: Diagnostic test definition
        """
        self._tests[test.name] = test
        self.logger.debug(f"Registered diagnostic: {test.name}")
    
    def register_tests(self, tests: List[DiagnosticTest]):
        """
        Register multiple diagnostic tests.
        
        Args:
            tests: List of test definitions
        """
        for test in tests:
            self.register_test(test)
    
    def unregister_test(self, name: str):
        """Unregister a diagnostic test."""
        if name in self._tests:
            del self._tests[name]
    
    # =========================================================================
    # STANDARD TESTS
    # =========================================================================
    
    def register_standard_tests(
        self,
        ipc_handler: Any = None,
        robot_manager: Any = None,
        mode_manager: Any = None,
        limit_checker: Any = None,
        heartbeat_agent: Any = None,
        bridge_health_agent: Any = None
    ):
        """
        Register standard ROC diagnostic tests.
        
        Args:
            ipc_handler: UE5 IPC handler reference
            robot_manager: Robot manager reference
            mode_manager: Mode manager reference
            limit_checker: Limit checker reference
            heartbeat_agent: Heartbeat agent reference
            bridge_health_agent: Bridge health agent reference
        """
        # IPC Connection Test
        if ipc_handler:
            self.register_test(DiagnosticTest(
                name="ipc_connection",
                category=DiagnosticCategory.CONNECTIVITY,
                description="Test UE5 IPC connection status",
                test_func=lambda: self._test_ipc(ipc_handler),
                critical=True
            ))
        
        # Robot Manager Test
        if robot_manager:
            self.register_test(DiagnosticTest(
                name="robot_manager",
                category=DiagnosticCategory.SUBSYSTEM,
                description="Test robot manager initialization",
                test_func=lambda: self._test_robot_manager(robot_manager),
                critical=True
            ))
        
        # Mode Manager Test
        if mode_manager:
            self.register_test(DiagnosticTest(
                name="mode_manager",
                category=DiagnosticCategory.SUBSYSTEM,
                description="Test mode manager state machine",
                test_func=lambda: self._test_mode_manager(mode_manager),
                critical=True
            ))
        
        # Limit Checker Test
        if limit_checker:
            self.register_test(DiagnosticTest(
                name="limit_checker",
                category=DiagnosticCategory.SAFETY,
                description="Test safety limit checker",
                test_func=lambda: self._test_limit_checker(limit_checker),
                critical=True
            ))
        
        # Heartbeat Agent Test
        if heartbeat_agent:
            self.register_test(DiagnosticTest(
                name="heartbeat_agent",
                category=DiagnosticCategory.SUBSYSTEM,
                description="Test heartbeat agent status",
                test_func=lambda: self._test_heartbeat_agent(heartbeat_agent),
                critical=False
            ))
        
        # Bridge Health Test
        if bridge_health_agent:
            self.register_test(DiagnosticTest(
                name="bridge_health",
                category=DiagnosticCategory.CONNECTIVITY,
                description="Test bridge health status",
                test_func=lambda: self._test_bridge_health(bridge_health_agent),
                critical=False
            ))
        
        # Memory Test
        self.register_test(DiagnosticTest(
            name="memory_usage",
            category=DiagnosticCategory.PERFORMANCE,
            description="Check memory usage is within limits",
            test_func=self._test_memory,
            critical=False
        ))
    
    def _test_ipc(self, ipc_handler: Any) -> Tuple[DiagnosticResult, str]:
        """Test IPC connection."""
        try:
            if hasattr(ipc_handler, 'is_connected'):
                if ipc_handler.is_connected:
                    return (DiagnosticResult.PASSED, "IPC connected")
                else:
                    return (DiagnosticResult.FAILED, "IPC not connected")
            return (DiagnosticResult.WARNING, "Cannot determine IPC status")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"IPC test error: {e}")
    
    def _test_robot_manager(self, robot_manager: Any) -> Tuple[DiagnosticResult, str]:
        """Test robot manager."""
        try:
            if hasattr(robot_manager, 'robot_count'):
                count = robot_manager.robot_count
                return (DiagnosticResult.PASSED, f"{count} robots registered")
            return (DiagnosticResult.WARNING, "Cannot determine robot count")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"Robot manager test error: {e}")
    
    def _test_mode_manager(self, mode_manager: Any) -> Tuple[DiagnosticResult, str]:
        """Test mode manager."""
        try:
            if hasattr(mode_manager, 'get_default_mode'):
                mode = mode_manager.get_default_mode()
                return (DiagnosticResult.PASSED, f"Default mode: {mode.value}")
            return (DiagnosticResult.WARNING, "Cannot determine mode status")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"Mode manager test error: {e}")
    
    def _test_limit_checker(self, limit_checker: Any) -> Tuple[DiagnosticResult, str]:
        """Test limit checker."""
        try:
            if hasattr(limit_checker, 'get_statistics'):
                stats = limit_checker.get_statistics()
                return (DiagnosticResult.PASSED, "Limit checker operational")
            return (DiagnosticResult.WARNING, "Cannot verify limit checker")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"Limit checker test error: {e}")
    
    def _test_heartbeat_agent(self, heartbeat_agent: Any) -> Tuple[DiagnosticResult, str]:
        """Test heartbeat agent."""
        try:
            if hasattr(heartbeat_agent, 'get_health_report'):
                report = heartbeat_agent.get_health_report()
                if report.get('healthy', False):
                    return (DiagnosticResult.PASSED, "Heartbeat agent healthy")
                else:
                    return (DiagnosticResult.WARNING, "Heartbeat agent degraded")
            return (DiagnosticResult.WARNING, "Cannot verify heartbeat agent")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"Heartbeat test error: {e}")
    
    def _test_bridge_health(self, bridge_agent: Any) -> Tuple[DiagnosticResult, str]:
        """Test bridge health."""
        try:
            if hasattr(bridge_agent, 'get_health_report'):
                report = bridge_agent.get_health_report()
                status = report.get('status', 'UNKNOWN')
                if status == 'HEALTHY':
                    return (DiagnosticResult.PASSED, "Bridge healthy")
                elif status == 'DEGRADED':
                    return (DiagnosticResult.WARNING, "Bridge degraded")
                else:
                    return (DiagnosticResult.FAILED, f"Bridge status: {status}")
            return (DiagnosticResult.WARNING, "Cannot verify bridge health")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"Bridge test error: {e}")
    
    def _test_memory(self) -> Tuple[DiagnosticResult, str]:
        """Test memory usage."""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            
            if memory_mb < 500:
                return (DiagnosticResult.PASSED, f"Memory: {memory_mb:.1f}MB")
            elif memory_mb < 1000:
                return (DiagnosticResult.WARNING, f"Memory elevated: {memory_mb:.1f}MB")
            else:
                return (DiagnosticResult.FAILED, f"Memory high: {memory_mb:.1f}MB")
        except ImportError:
            return (DiagnosticResult.SKIPPED, "psutil not available")
        except Exception as e:
            return (DiagnosticResult.ERROR, f"Memory test error: {e}")
    
    # =========================================================================
    # TEST EXECUTION
    # =========================================================================
    
    async def run_test(self, name: str) -> Optional[DiagnosticTestResult]:
        """
        Run a specific diagnostic test.
        
        Args:
            name: Test name
            
        Returns:
            Test result or None if test not found
        """
        if name not in self._tests:
            self.logger.warning(f"Unknown diagnostic test: {name}")
            return None
        
        test = self._tests[name]
        return await self._execute_test(test)
    
    async def _execute_test(self, test: DiagnosticTest) -> DiagnosticTestResult:
        """Execute a single diagnostic test."""
        start_time = time.perf_counter()
        
        try:
            # Run with timeout
            result, message = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, test.test_func
                ),
                timeout=test.timeout_s
            )
        except asyncio.TimeoutError:
            result = DiagnosticResult.ERROR
            message = f"Test timed out after {test.timeout_s}s"
        except Exception as e:
            result = DiagnosticResult.ERROR
            message = f"Test exception: {e}"
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        test_result = DiagnosticTestResult(
            test_name=test.name,
            category=test.category,
            result=result,
            message=message,
            duration_ms=duration_ms,
            timestamp=time.time()
        )
        
        # Update tracking
        self._last_results[test.name] = test_result
        self._result_history.append(test_result)
        if len(self._result_history) > self._max_history:
            self._result_history = self._result_history[-self._max_history:]
        
        # Update stats
        self._stats["tests_run"] += 1
        if result == DiagnosticResult.PASSED:
            self._stats["tests_passed"] += 1
            self._consecutive_failures[test.name] = 0
        elif result == DiagnosticResult.FAILED or result == DiagnosticResult.ERROR:
            self._stats["tests_failed"] += 1
            self._consecutive_failures[test.name] = \
                self._consecutive_failures.get(test.name, 0) + 1
        elif result == DiagnosticResult.WARNING:
            self._stats["tests_warned"] += 1
        
        # Log result
        if result == DiagnosticResult.PASSED:
            self.logger.debug(f"Diagnostic {test.name}: PASSED - {message}")
        elif result == DiagnosticResult.WARNING:
            self.logger.warning(f"Diagnostic {test.name}: WARNING - {message}")
        else:
            self.logger.error(f"Diagnostic {test.name}: {result.name} - {message}")
        
        # Notify callbacks
        for callback in self._result_callbacks:
            try:
                callback(test_result)
            except Exception as e:
                self.logger.error(f"Diagnostic callback error: {e}")
        
        return test_result
    
    async def run_all_tests(
        self,
        category: Optional[DiagnosticCategory] = None,
        critical_only: bool = False
    ) -> List[DiagnosticTestResult]:
        """
        Run all registered diagnostic tests.
        
        Args:
            category: Filter by category
            critical_only: Only run critical tests
            
        Returns:
            List of test results
        """
        results = []
        
        for test in self._tests.values():
            # Apply filters
            if category and test.category != category:
                continue
            if critical_only and not test.critical:
                continue
            
            result = await self._execute_test(test)
            results.append(result)
        
        return results
    
    # =========================================================================
    # STARTUP DIAGNOSTICS
    # =========================================================================
    
    async def run_startup_diagnostics(self) -> bool:
        """
        Run startup diagnostics.
        
        Returns:
            True if all critical tests passed
        """
        if not self.config.run_startup_diagnostics:
            self._startup_complete = True
            self._startup_passed = True
            return True
        
        self.logger.info("Running startup diagnostics...")
        start_time = time.perf_counter()
        
        try:
            results = await asyncio.wait_for(
                self.run_all_tests(
                    critical_only=self.config.skip_non_critical_on_startup
                ),
                timeout=self.config.startup_timeout_s
            )
        except asyncio.TimeoutError:
            self.logger.error(
                f"Startup diagnostics timed out after "
                f"{self.config.startup_timeout_s}s"
            )
            self._startup_complete = True
            self._startup_passed = False
            return False
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        self._stats["startup_duration_ms"] = duration_ms
        
        # Check critical tests
        critical_passed = True
        for result in results:
            test = self._tests.get(result.test_name)
            if test and test.critical:
                if result.result in (DiagnosticResult.FAILED, DiagnosticResult.ERROR):
                    critical_passed = False
                    self.logger.error(
                        f"Critical diagnostic failed: {result.test_name}"
                    )
        
        self._startup_complete = True
        self._startup_passed = critical_passed
        
        # Summary
        passed = sum(1 for r in results if r.result == DiagnosticResult.PASSED)
        failed = sum(1 for r in results if r.result in (
            DiagnosticResult.FAILED, DiagnosticResult.ERROR
        ))
        
        self.logger.info(
            f"Startup diagnostics complete: {passed}/{len(results)} passed, "
            f"{failed} failed, {duration_ms:.1f}ms"
        )
        
        return critical_passed
    
    @property
    def is_ready(self) -> bool:
        """Check if startup diagnostics passed."""
        return self._startup_complete and self._startup_passed
    
    # =========================================================================
    # PERIODIC DIAGNOSTICS
    # =========================================================================
    
    async def start_periodic(self):
        """Start periodic diagnostic checks."""
        if not self.config.enable_periodic_diagnostics:
            return
        
        if self._running:
            return
        
        self._running = True
        self._periodic_task = asyncio.create_task(self._periodic_loop())
        self.logger.info("Started periodic diagnostics")
    
    async def stop_periodic(self):
        """Stop periodic diagnostic checks."""
        self._running = False
        
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None
    
    async def _periodic_loop(self):
        """Periodic diagnostic loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.periodic_interval_s)
                await self.run_all_tests()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Periodic diagnostic error: {e}")
    
    # =========================================================================
    # CALLBACKS
    # =========================================================================
    
    def on_result(self, callback: DiagnosticCallback):
        """Register result callback."""
        self._result_callbacks.append(callback)
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_last_results(self) -> Dict[str, DiagnosticTestResult]:
        """Get last result for each test."""
        return self._last_results.copy()
    
    def get_status(self) -> Dict[str, Any]:
        """Get diagnostic manager status."""
        return {
            "registered_tests": len(self._tests),
            "startup_complete": self._startup_complete,
            "startup_passed": self._startup_passed,
            "periodic_running": self._running,
            "last_results": {
                name: result.to_dict()
                for name, result in self._last_results.items()
            },
            "stats": self._stats.copy()
        }
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get health report for Webthread."""
        failed_tests = [
            name for name, result in self._last_results.items()
            if result.result in (DiagnosticResult.FAILED, DiagnosticResult.ERROR)
        ]
        
        warning_tests = [
            name for name, result in self._last_results.items()
            if result.result == DiagnosticResult.WARNING
        ]
        
        return {
            "healthy": len(failed_tests) == 0 and self._startup_passed,
            "ready": self.is_ready,
            "failed_tests": failed_tests,
            "warning_tests": warning_tests,
            "tests_run": self._stats["tests_run"],
            "startup_duration_ms": self._stats["startup_duration_ms"]
        }
    
    def get_readiness_summary(self) -> Dict[str, Any]:
        """Get detailed readiness summary."""
        return {
            "ready": self.is_ready,
            "startup_complete": self._startup_complete,
            "startup_passed": self._startup_passed,
            "critical_tests": {
                name: {
                    "passed": self._last_results.get(name, DiagnosticTestResult(
                        test_name=name,
                        category=test.category,
                        result=DiagnosticResult.SKIPPED,
                        message="Not run",
                        duration_ms=0,
                        timestamp=0
                    )).result == DiagnosticResult.PASSED,
                    "result": self._last_results.get(name).result.name
                    if name in self._last_results else "NOT_RUN"
                }
                for name, test in self._tests.items()
                if test.critical
            }
        }
