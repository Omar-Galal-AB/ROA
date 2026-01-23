// InputInitializer.h
// ROA - Robot Operations & Automation
// Input system initialization for UE5

#pragma once

#include <string>
#include <map>
#include <vector>

namespace ROA {
namespace Webthread {

/**
 * @brief Input binding configuration
 */
struct InputBinding {
    std::string key;
    std::string action;
    std::string context;  // RPM, ADM, or Shared
};

/**
 * @brief InputInitializer
 * 
 * Initializes UE5 input system with keyboard/mouse handlers
 * Configures 120 Hz polling with <10ms keyboard and <15ms mouse latency targets
 */
class InputInitializer {
public:
    InputInitializer();
    ~InputInitializer();

    /**
     * @brief Initialize all input systems
     * @return true if successful
     */
    bool InitializeAll();

    /**
     * @brief Setup keyboard input handlers
     * @return true if successful
     */
    bool SetupKeyboardHandlers();

    /**
     * @brief Setup mouse input handlers
     * @return true if successful
     */
    bool SetupMouseHandlers();

    /**
     * @brief Configure input polling rate
     * @param rateHz Polling rate in Hz (default: 120)
     * @return true if successful
     */
    bool ConfigurePollingRate(int rateHz = 120);

    /**
     * @brief Detect keybinding conflicts
     * @return true if no conflicts found
     */
    bool DetectConflicts();

    /**
     * @brief Validate input latency
     * @return true if meets latency requirements
     */
    bool ValidateLatency();

    /**
     * @brief Load configuration from file
     * @param configPath Path to keybindings config file
     * @return true if loaded successfully
     */
    bool LoadConfig(const std::string& configPath);

private:
    int pollingRateHz_;
    float keyboardLatencyTarget_;  // ms
    float mouseLatencyTarget_;     // ms
    
    std::vector<InputBinding> rpmBindings_;
    std::vector<InputBinding> admBindings_;
    std::vector<InputBinding> sharedBindings_;

    bool RegisterBinding(const InputBinding& binding);
    bool TestKeyboardLatency();
    bool TestMouseLatency();
};

} // namespace Webthread
} // namespace ROA
