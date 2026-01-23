// PhysicsConfigurator.h
// ROA - Robot Operations & Automation
// Physics configuration module for UE5 Chaos Physics engine

#pragma once

#include <string>
#include <map>

namespace ROA {
namespace Webthread {

/**
 * @brief Physics material properties
 */
struct PhysicsMaterial {
    float friction_static;
    float friction_dynamic;
    float restitution;
    float density;  // kg/m³
};

/**
 * @brief PhysicsConfigurator
 * 
 * Configures UE5's Chaos Physics engine to Gazebo-equivalent parameters
 * for accurate robotics simulation.
 */
class PhysicsConfigurator {
public:
    PhysicsConfigurator();
    ~PhysicsConfigurator();

    /**
     * @brief Configure all physics settings
     * @return true if successful
     */
    bool ConfigureAll();

    /**
     * @brief Configure physics solver settings
     * @return true if successful
     */
    bool ConfigureSolver();

    /**
     * @brief Configure world physics settings
     * @return true if successful
     */
    bool ConfigureWorld();

    /**
     * @brief Configure physics material presets
     * @return true if successful
     */
    bool ConfigureMaterials();

    /**
     * @brief Configure joint defaults
     * @return true if successful
     */
    bool ConfigureJoints();

    /**
     * @brief Run physics validation tests
     * @return true if all tests pass
     */
    bool RunValidationTests();

    /**
     * @brief Load configuration from file
     * @param configPath Path to configuration file
     * @return true if loaded successfully
     */
    bool LoadConfig(const std::string& configPath);

private:
    // Solver settings
    int positionIterations_;
    int velocityIterations_;
    int substeps_;
    bool enableCCD_;

    // World settings
    float gravity_;
    float unitScale_;

    // Material presets
    std::map<std::string, PhysicsMaterial> materials_;

    // Joint settings
    float jointDamping_;
    float jointStiffness_;
    float angularLimitMin_;
    float angularLimitMax_;

    // Helper methods
    void SetDefaultValues();
    bool ApplySolverSettings();
    bool ApplyWorldSettings();
    bool CreateMaterialPreset(const std::string& name, const PhysicsMaterial& material);
    bool ApplyJointSettings();

    // Validation tests
    bool RunDropTest();
    bool RunFrictionTest();
    bool RunJointTest();
};

} // namespace Webthread
} // namespace ROA
