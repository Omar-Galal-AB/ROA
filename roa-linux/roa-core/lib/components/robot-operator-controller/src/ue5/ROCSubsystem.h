// ROCSubsystem.h - Game Instance Subsystem for Robot Operator Controller
//
// Central coordinator for ROC functionality in UE5.
// Manages robot controllers, IPC communication, and widget integration.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "ROCTypes.h"
#include "ROCSubsystem.generated.h"

// Forward declarations
class URobotController;
class UROCIPCHandler;

/**
 * ROC Subsystem - Game Instance Subsystem for Robot Operator Controller.
 * 
 * Provides:
 * - Robot registration and management
 * - IPC communication with Linux ROC
 * - Mode management (RPM/ADM)
 * - Widget interface
 * 
 * Access via: GetGameInstance()->GetSubsystem<UROCSubsystem>()
 */
UCLASS()
class ROA_API UROCSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()
    
public:
    // =========================================================================
    // Subsystem Lifecycle
    // =========================================================================
    
    /** Initialize subsystem */
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    
    /** Deinitialize subsystem */
    virtual void Deinitialize() override;
    
    /** Check if subsystem should be created */
    virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
    
    // =========================================================================
    // Robot Management
    // =========================================================================
    
    /**
     * Register a robot with the ROC system.
     * Called when FTI imports a robot or robot spawns in world.
     * 
     * @param Config Robot configuration from FTI
     * @return True if registered successfully
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    bool RegisterRobot(const FROCRobotConfig& Config);
    
    /**
     * Unregister a robot.
     * 
     * @param RobotId Robot identifier
     * @return True if unregistered
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    bool UnregisterRobot(const FString& RobotId);
    
    /**
     * Get robot controller by ID.
     * 
     * @param RobotId Robot identifier
     * @return Robot controller or nullptr
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    URobotController* GetRobotController(const FString& RobotId) const;
    
    /**
     * Get all registered robot IDs.
     * 
     * @return Array of robot IDs
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    TArray<FString> GetRegisteredRobotIds() const;
    
    /**
     * Get currently selected robot ID.
     * 
     * @return Selected robot ID or empty string
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    FString GetSelectedRobotId() const { return SelectedRobotId; }
    
    /**
     * Select a robot as the active robot.
     * 
     * @param RobotId Robot to select
     * @return True if selected
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    bool SelectRobot(const FString& RobotId);
    
    /**
     * Get currently selected robot controller.
     * 
     * @return Selected robot controller or nullptr
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    URobotController* GetSelectedRobotController() const;
    
    // =========================================================================
    // Mode Control
    // =========================================================================
    
    /**
     * Request mode change for a robot.
     * 
     * @param RobotId Robot identifier
     * @param NewMode Target mode
     * @return True if mode change initiated
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    bool RequestModeChange(const FString& RobotId, EROCControlMode NewMode);
    
    /**
     * Get current mode for a robot.
     * 
     * @param RobotId Robot identifier
     * @return Current control mode
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    EROCControlMode GetRobotMode(const FString& RobotId) const;
    
    /**
     * Toggle mode between RPM and ADM.
     * 
     * @param RobotId Robot identifier
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    void ToggleMode(const FString& RobotId);
    
    // =========================================================================
    // Emergency Stop
    // =========================================================================
    
    /**
     * Trigger emergency stop for a robot.
     * 
     * @param RobotId Robot identifier (use "all" for all robots)
     * @param Reason Reason for emergency stop
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    void TriggerEmergencyStop(const FString& RobotId, const FString& Reason);
    
    /**
     * Clear emergency stop for a robot.
     * 
     * @param RobotId Robot identifier
     * @return True if cleared
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    bool ClearEmergencyStop(const FString& RobotId);
    
    /**
     * Check if emergency stop is active for a robot.
     * 
     * @param RobotId Robot identifier
     * @return True if E-Stop is active
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    bool IsEmergencyStopActive(const FString& RobotId) const;
    
    // =========================================================================
    // Joint Commands
    // =========================================================================
    
    /**
     * Send joint command for validation and execution.
     * Command is sent to Linux for validation, then executed if approved.
     * 
     * @param RobotId Robot identifier
     * @param Commands Array of joint commands
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Commands")
    void SendJointCommands(const FString& RobotId, const TArray<FROCJointCommand>& Commands);
    
    /**
     * Send single joint command.
     * 
     * @param RobotId Robot identifier
     * @param JointName Joint name
     * @param TargetPosition Target position
     * @param VelocityLimit Velocity limit (0 = default)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Commands")
    void SendJointCommand(const FString& RobotId, const FString& JointName, 
                         float TargetPosition, float VelocityLimit = 0.0f);
    
    // =========================================================================
    // Connection
    // =========================================================================
    
    /**
     * Check if connected to Linux ROC.
     * 
     * @return True if connected
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Connection")
    bool IsConnectedToLinux() const;
    
    /**
     * Attempt to reconnect to Linux ROC.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Connection")
    void Reconnect();
    
    // =========================================================================
    // Delegates
    // =========================================================================
    
    /** Broadcast when robot status changes */
    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnROCRobotStatusChanged OnRobotStatusChanged;
    
    /** Broadcast when mode changes */
    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnROCModeChanged OnModeChanged;
    
    /** Broadcast when command is validated */
    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnROCCommandValidated OnCommandValidated;
    
    /** Broadcast on safety alert */
    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnROCSafetyAlert OnSafetyAlert;
    
    /** Broadcast on emergency stop */
    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnROCEmergencyStop OnEmergencyStop;
    
    /** Broadcast on connection status change */
    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnROCConnectionChanged OnConnectionChanged;
    
protected:
    // =========================================================================
    // Internal
    // =========================================================================
    
    /** Map of robot ID to controller */
    UPROPERTY()
    TMap<FString, URobotController*> RobotControllers;
    
    /** Currently selected robot ID */
    UPROPERTY()
    FString SelectedRobotId;
    
    /** IPC handler for Linux communication */
    UPROPERTY()
    UROCIPCHandler* IPCHandler;
    
    /** Initialize IPC connection */
    void InitializeIPC();
    
    /** Handle incoming IPC messages */
    void HandleIPCMessage(const FString& MessageType, const TSharedPtr<FJsonObject>& Data);
    
    /** Handle command approved from Linux */
    void HandleCommandApproved(const TSharedPtr<FJsonObject>& Data);
    
    /** Handle command rejected from Linux */
    void HandleCommandRejected(const TSharedPtr<FJsonObject>& Data);
    
    /** Handle safety alert from Linux */
    void HandleSafetyAlert(const TSharedPtr<FJsonObject>& Data);
    
    /** Handle state update from Linux */
    void HandleStateUpdate(const TSharedPtr<FJsonObject>& Data);
    
    /** Generate unique command ID */
    FString GenerateCommandId();
    
    /** Command ID counter */
    int32 CommandIdCounter = 0;
};
