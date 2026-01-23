// ComponentStarter.h
// ROA - Robot Operations & Automation
// Component startup coordination

#pragma once

#include <string>
#include <vector>
#include <map>

namespace ROA {
namespace Webthread {

/**
 * @brief Component status enumeration
 */
enum class ComponentStatus {
    NOT_STARTED,
    STARTING,
    READY,
    FAILED
};

/**
 * @brief Component information
 */
struct ComponentInfo {
    std::string name;
    ComponentStatus status;
    int priority;
    float startupTime;
    std::string version;
};

/**
 * @brief ComponentStarter
 * 
 * Coordinates startup of ROA components in correct order:
 * FTI → DIMC → ROC → COMC → Runtime Webthread
 */
class ComponentStarter {
public:
    ComponentStarter();
    ~ComponentStarter();

    /**
     * @brief Start all components in priority order
     * @return true if all essential components started
     */
    bool StartAllComponents();

    /**
     * @brief Start a specific component
     * @param componentName Name of component
     * @return true if started successfully
     */
    bool StartComponent(const std::string& componentName);

    /**
     * @brief Get status of a component
     * @param componentName Name of component
     * @return Component status
     */
    ComponentStatus GetComponentStatus(const std::string& componentName) const;

    /**
     * @brief Verify all components are ready
     * @return true if all are ready
     */
    bool VerifyAllReady() const;

    /**
     * @brief Load configuration from file
     * @param configPath Path to component config file
     * @return true if loaded successfully
     */
    bool LoadConfig(const std::string& configPath);

private:
    std::map<std::string, ComponentInfo> components_;
    int failureTolerance_;

    bool StartFTI();
    bool StartDIMC();
    bool StartROC();
    bool StartCOMC();
    bool StartRuntimeWebthread();
};

} // namespace Webthread
} // namespace ROA
