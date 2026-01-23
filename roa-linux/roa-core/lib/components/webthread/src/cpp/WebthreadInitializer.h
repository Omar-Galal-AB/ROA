// WebthreadInitializer.h
// ROA - Robot Operations & Automation
// One-time startup orchestrator for the Webthread component
// 
// This module runs once at system startup to configure the entire ROA environment
// and coordinate component initialization. After completion, it exits and hands
// control to the runtime Webthread.

#pragma once

#include <string>
#include <vector>
#include <memory>
#include <functional>

namespace ROA {
namespace Webthread {

/**
 * @brief Initialization phase status
 */
enum class InitPhase {
    NOT_STARTED,
    PRE_CHECKS,
    ENVIRONMENT_SETUP,
    COMPONENT_INITIALIZATION,
    VALIDATION,
    COMPLETE,
    FAILED
};

/**
 * @brief Component startup status
 */
enum class ComponentStatus {
    NOT_STARTED,
    STARTING,
    READY,
    FAILED
};

/**
 * @brief Error severity levels
 */
enum class ErrorSeverity {
    CRITICAL,   // Abort startup
    WARNING,    // Continue with degraded mode
    INFO        // Informational only
};

/**
 * @brief Initialization result structure
 */
struct InitializationResult {
    bool success;
    InitPhase phase;
    std::string message;
    float totalTime;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;
};

/**
 * @brief Component information structure
 */
struct ComponentInfo {
    std::string name;
    ComponentStatus status;
    float startupTime;
    std::string version;
};

/**
 * @brief WebthreadInitializer - One-time startup orchestrator
 * 
 * Responsibilities:
 * - UE5 environment configuration (physics, input, UI)
 * - Component startup coordination (FTI, DIMC, ROC, COMC)
 * - Configuration loading and validation
 * - Error handling and recovery
 * - System validation and handoff to runtime
 * 
 * Lifecycle: Runs once at startup, then exits
 */
class WebthreadInitializer {
public:
    /**
     * @brief Constructor
     */
    WebthreadInitializer();
    
    /**
     * @brief Destructor
     */
    ~WebthreadInitializer();

    /**
     * @brief Initialize the entire ROA system
     * @return InitializationResult with status and details
     */
    InitializationResult Initialize();

    /**
     * @brief Get current initialization phase
     * @return Current InitPhase
     */
    InitPhase GetCurrentPhase() const;

    /**
     * @brief Get initialization progress (0.0 to 1.0)
     * @return Progress percentage
     */
    float GetProgress() const;

    /**
     * @brief Register progress callback
     * @param callback Function to call on progress updates
     */
    void RegisterProgressCallback(std::function<void(InitPhase, float, const std::string&)> callback);

    /**
     * @brief Get component status
     * @param componentName Name of component
     * @return ComponentInfo structure
     */
    ComponentInfo GetComponentStatus(const std::string& componentName) const;

    /**
     * @brief Abort initialization
     * Called on critical errors or user request
     */
    void Abort();

private:
    // Initialization phases
    bool RunPreChecks();
    bool RunEnvironmentSetup();
    bool RunComponentInitialization();
    bool RunValidation();

    // Pre-check methods
    bool CheckUE5Version();
    bool CheckROS2Installation();
    bool CheckPlatformCompatibility();
    bool CheckHardwareRequirements();
    bool CheckNetworkConnectivity();
    bool CheckDatabaseAccess();

    // Environment setup methods
    bool SetupPhysics();
    bool SetupInputSystem();
    bool SetupUISystem();
    bool CreateWorkspaceDirectories();
    bool LoadConfigurations();

    // Component initialization methods
    bool InitializeComponent(const std::string& componentName);
    bool StartFTI();  // Files Type Importer
    bool StartDIMC(); // Dimensions Collector
    bool StartROC();  // Robot Operator Controller
    bool StartCOMC(); // Communication Center
    bool StartRuntimeWebthread();

    // Validation methods
    bool ValidateInterComponentCommunication();
    bool ValidateLatency();
    bool ValidateSafetySystem();
    bool ValidateUIResponsiveness();

    // Error handling
    void HandleError(ErrorSeverity severity, const std::string& message);
    bool RetryOperation(std::function<bool()> operation, int maxAttempts = 3);
    void ApplyFallbackConfiguration();
    void NotifyUser(const std::string& message, ErrorSeverity severity);

    // Logging
    void LogProgress(const std::string& message);
    void LogWarning(const std::string& message);
    void LogError(const std::string& message);
    void WriteInitLog();

    // Utility methods
    void UpdateProgress(InitPhase phase, float progress, const std::string& message);
    float GetPhaseWeight(InitPhase phase) const;

private:
    // State
    InitPhase currentPhase_;
    float overallProgress_;
    bool abortRequested_;
    
    // Timing
    float startTime_;
    float phaseStartTime_;
    
    // Components
    std::vector<ComponentInfo> components_;
    
    // Logging
    std::vector<std::string> initLog_;
    std::vector<std::string> warnings_;
    std::vector<std::string> errors_;
    
    // Callbacks
    std::function<void(InitPhase, float, const std::string&)> progressCallback_;
    
    // Configuration paths
    std::string configPath_;
    std::string workspacePath_;
    std::string logPath_;
    
    // Disable copy and assignment
    WebthreadInitializer(const WebthreadInitializer&) = delete;
    WebthreadInitializer& operator=(const WebthreadInitializer&) = delete;
};

} // namespace Webthread
} // namespace ROA
