// UIInitializer.h
// ROA - Robot Operations & Automation
// UI system initialization for UE5

#pragma once

#include <string>

namespace ROA {
namespace Webthread {

/**
 * @brief UIInitializer
 * 
 * Initializes UE5 UI overlays and configuration
 * Configures 60 Hz refresh rate with performance targets
 */
class UIInitializer {
public:
    UIInitializer();
    ~UIInitializer();

    /**
     * @brief Initialize all UI systems
     * @return true if successful
     */
    bool InitializeAll();

    /**
     * @brief Load UI overlays
     * @return true if successful
     */
    bool LoadOverlays();

    /**
     * @brief Configure display settings
     * @return true if successful
     */
    bool ConfigureDisplay();

    /**
     * @brief Setup shortcuts panel overlay
     * @return true if successful
     */
    bool SetupShortcutsPanel();

    /**
     * @brief Setup mode indicator (RPM/ADM)
     * @return true if successful
     */
    bool SetupModeIndicator();

    /**
     * @brief Setup robot status panel
     * @return true if successful
     */
    bool SetupStatusPanel();

    /**
     * @brief Validate UI performance targets
     * @return true if meets requirements
     */
    bool ValidatePerformance();

    /**
     * @brief Load configuration from file
     * @param configPath Path to UI settings config file
     * @return true if loaded successfully
     */
    bool LoadConfig(const std::string& configPath);

private:
    int refreshRateHz_;
    float toggleResponseTarget_;   // ms
    float menuOpenTarget_;         // ms
    float fadeTransitionTime_;     // ms
    float uiOpacity_;

    bool CreateOverlay(const std::string& name);
    bool TestToggleResponse();
    bool TestMenuOpenTime();
};

} // namespace Webthread
} // namespace ROA
