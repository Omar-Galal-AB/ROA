// RobotController.h - Per-robot controller for ROC
//
// Manages a single robot's joints, state, and control within UE5.
// Created by ROCSubsystem when a robot is registered.

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "ROCTypes.h"
#include "RobotController.generated.h"

// Forward declarations
class UJointController;
class UPhysicsConstraintComponent;
class AActor;

/**
 * Robot Controller - Manages a single robot in the ROC system.
 * 
 * Provides:
 * - Joint controller management
 * - Robot state tracking
 * - Mode-specific behavior
 * - Integration with physics constraints
 */
UCLASS(BlueprintType)
class ROA_API URobotController : public UObject
{
    GENERATED_BODY()
    
public:
    // =========================================================================
    // Initialization
    // =========================================================================
    
    /**
     * Initialize the robot controller.
     * 
     * @param Config Robot configuration from FTI
     * @param InRobotActor The robot actor in the world (optional)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    void Initialize(const FROCRobotConfig& Config, AActor* InRobotActor = nullptr);
    
    /**
     * Shutdown the robot controller.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    void Shutdown();
    
    /**
     * Set the robot actor.
     * 
     * @param InRobotActor The robot actor
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    void SetRobotActor(AActor* InRobotActor);
    
    // =========================================================================
    // State Access
    // =========================================================================
    
    /** Get robot ID */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    FString GetRobotId() const { return RobotId; }
    
    /** Get robot name */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    FString GetRobotName() const { return RobotName; }
    
    /** Get current status */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    EROCRobotStatus GetStatus() const { return Status; }
    
    /** Get current control mode */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    EROCControlMode GetMode() const { return Mode; }
    
    /** Get safety status */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    FROCSafetyStatus GetSafetyStatus() const { return SafetyStatus; }
    
    /** Get number of joints */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    int32 GetJointCount() const { return JointControllers.Num(); }
    
    /** Get all joint names */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    TArray<FString> GetJointNames() const;
    
    /** Get robot actor */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    AActor* GetRobotActor() const { return RobotActor; }
    
    // =========================================================================
    // Joint Access
    // =========================================================================
    
    /**
     * Get joint controller by name.
     * 
     * @param JointName Joint name
     * @return Joint controller or nullptr
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    UJointController* GetJointController(const FString& JointName) const;
    
    /**
     * Get joint state by name.
     * 
     * @param JointName Joint name
     * @return Joint state
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FROCJointState GetJointState(const FString& JointName) const;
    
    /**
     * Get all joint states.
     * 
     * @return Array of joint states
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    TArray<FROCJointState> GetAllJointStates() const;
    
    /**
     * Get currently selected joint name.
     * 
     * @return Selected joint name
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FString GetSelectedJointName() const { return SelectedJointName; }
    
    /**
     * Select a joint.
     * 
     * @param JointName Joint to select
     * @return True if selected
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool SelectJoint(const FString& JointName);
    
    /**
     * Select next joint in order.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SelectNextJoint();
    
    /**
     * Select previous joint in order.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SelectPreviousJoint();
    
    // =========================================================================
    // Mode Control
    // =========================================================================
    
    /**
     * Set control mode.
     * 
     * @param NewMode New control mode
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    void SetMode(EROCControlMode NewMode);
    
    /**
     * Check if in RPM mode.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    bool IsInRPMMode() const { return Mode == EROCControlMode::RPM; }
    
    /**
     * Check if in ADM mode.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    bool IsInADMMode() const { return Mode == EROCControlMode::ADM; }
    
    // =========================================================================
    // Emergency Stop
    // =========================================================================
    
    /**
     * Activate emergency stop.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    void ActivateEmergencyStop();
    
    /**
     * Clear emergency stop.
     * 
     * @return True if cleared (requires RPM mode)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    bool ClearEmergencyStop();
    
    /**
     * Check if emergency stop is active.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    bool IsEmergencyStopActive() const { return SafetyStatus.bEStopActive; }
    
    // =========================================================================
    // Joint Commands
    // =========================================================================
    
    /**
     * Execute approved joint command.
     * Called when Linux approves a command.
     * 
     * @param Command Approved command
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Commands")
    void ExecuteApprovedCommand(const FROCJointCommand& Command);
    
    /**
     * Execute multiple approved commands.
     * 
     * @param Commands Array of approved commands
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Commands")
    void ExecuteApprovedCommands(const TArray<FROCJointCommand>& Commands);
    
    /**
     * Stop all joint movement immediately.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Commands")
    void StopAllJoints();
    
    // =========================================================================
    // State Updates
    // =========================================================================
    
    /**
     * Update safety status from Linux.
     * 
     * @param NewSafetyStatus Updated safety status
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|State")
    void UpdateSafetyStatus(const FROCSafetyStatus& NewSafetyStatus);
    
    /**
     * Update robot status.
     * 
     * @param NewStatus New status
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|State")
    void SetStatus(EROCRobotStatus NewStatus);
    
    // =========================================================================
    // Tick
    // =========================================================================
    
    /**
     * Tick the robot controller.
     * Called each frame to update joint states.
     * 
     * @param DeltaTime Time since last tick
     */
    void Tick(float DeltaTime);
    
protected:
    // =========================================================================
    // Properties
    // =========================================================================
    
    /** Robot identifier */
    UPROPERTY()
    FString RobotId;
    
    /** Robot name */
    UPROPERTY()
    FString RobotName;
    
    /** Robot configuration */
    UPROPERTY()
    FROCRobotConfig Config;
    
    /** Current status */
    UPROPERTY()
    EROCRobotStatus Status = EROCRobotStatus::Initializing;
    
    /** Current control mode */
    UPROPERTY()
    EROCControlMode Mode = EROCControlMode::RPM;
    
    /** Safety status */
    UPROPERTY()
    FROCSafetyStatus SafetyStatus;
    
    /** Robot actor in world */
    UPROPERTY()
    AActor* RobotActor = nullptr;
    
    /** Map of joint name to controller */
    UPROPERTY()
    TMap<FString, UJointController*> JointControllers;
    
    /** Ordered joint names (kinematic chain order) */
    UPROPERTY()
    TArray<FString> JointOrder;
    
    /** Currently selected joint */
    UPROPERTY()
    FString SelectedJointName;
    
    /** Selected joint index */
    UPROPERTY()
    int32 SelectedJointIndex = 0;
    
    // =========================================================================
    // Internal Methods
    // =========================================================================
    
    /** Create joint controllers from config */
    void CreateJointControllers();
    
    /** Find physics constraints on robot actor */
    void BindPhysicsConstraints();
    
    /** Update moving status based on joints */
    void UpdateMovingStatus();
};
