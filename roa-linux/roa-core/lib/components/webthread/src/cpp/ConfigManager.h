// ConfigManager.h
// ROA - Robot Operations & Automation
// Configuration loading and validation

#pragma once

#include <string>
#include <map>

namespace ROA {
namespace Webthread {

/**
 * @brief ConfigManager
 * 
 * Manages loading, validation, and access to configuration files
 */
class ConfigManager {
public:
    ConfigManager();
    ~ConfigManager();

    /**
     * @brief Load all configuration files
     * @return true if successful
     */
    bool LoadAllConfigs();

    /**
     * @brief Load physics configuration
     * @param filePath Path to physics config file
     * @return true if successful
     */
    bool LoadPhysicsConfig(const std::string& filePath);

    /**
     * @brief Load keybindings configuration
     * @param filePath Path to keybindings config file
     * @return true if successful
     */
    bool LoadKeybindingsConfig(const std::string& filePath);

    /**
     * @brief Load UI settings configuration
     * @param filePath Path to UI config file
     * @return true if successful
     */
    bool LoadUIConfig(const std::string& filePath);

    /**
     * @brief Load component configuration
     * @param filePath Path to component config file
     * @return true if successful
     */
    bool LoadComponentConfig(const std::string& filePath);

    /**
     * @brief Load safety rules configuration
     * @param filePath Path to safety config file
     * @return true if successful
     */
    bool LoadSafetyConfig(const std::string& filePath);

    /**
     * @brief Validate all loaded configurations
     * @return true if all valid
     */
    bool ValidateAll();

    /**
     * @brief Get configuration value
     * @param section Configuration section
     * @param key Configuration key
     * @return Configuration value (empty string if not found)
     */
    std::string GetValue(const std::string& section, const std::string& key) const;

    /**
     * @brief Apply fallback configuration
     * Used when config files are missing or corrupted
     */
    void ApplyFallbackConfig();

private:
    std::string configPath_;
    std::map<std::string, std::map<std::string, std::string>> configs_;
    
    bool ValidatePhysicsConfig();
    bool ValidateKeybindingsConfig();
    bool ValidateUIConfig();
    bool ValidateComponentConfig();
    bool ValidateSafetyConfig();
};

} // namespace Webthread
} // namespace ROA
