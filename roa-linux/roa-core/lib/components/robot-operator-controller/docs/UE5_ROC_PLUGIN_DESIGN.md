# UE5 ROC Plugin Design

## Overview

This document defines the UE5 C++ plugin architecture for the Robot Operator Controller (ROC) component. The UE5 side handles direct joint control execution, UI widgets, and input capture.

**Version**: 1.0  
**Date**: 2026-01-13  
**Status**: Design Phase (NOT IMPLEMENTED)

---

## Plugin Structure

```
ROA_PlugIn/Source/ROA/
├── ROC/
│   ├── ROCSubsystem.h              # Main ROC subsystem (GameInstanceSubsystem)
│   ├── ROCSubsystem.cpp
│   ├── RobotController.h           # Per-robot controller class
│   ├── RobotController.cpp
│   ├── JointController.h           # Individual joint controller
│   ├── JointController.cpp
│   ├── ROCTypes.h                  # Shared types and structs
│   │
│   ├── Input/
│   │   ├── ROCInputComponent.h     # Enhanced input handling for RPM
│   │   └── ROCInputComponent.cpp
│   │
│   └── UI/
│       ├── ROCWidgetBase.h         # Base widget class
│       ├── ROCWidgetBase.cpp
│       ├── JointSliderWidget.h     # Reusable joint slider
│       ├── JointSliderWidget.cpp
│       ├── RobotControlPanel.h     # Main control panel
│       └── RobotControlPanel.cpp
│
├── Content/ROC/
│   ├── UI/
│   │   ├── WBP_RobotControlPanel.uasset   # Widget Blueprint
│   │   ├── WBP_JointSlider.uasset         # Joint slider widget
│   │   ├── WBP_ModeSelector.uasset        # RPM/ADM toggle
│   │   └── WBP_RobotSelector.uasset       # Robot dropdown
│   │
│   └── Input/
│       ├── IA_ROC_Movement.uasset         # Input actions
│       ├── IA_ROC_Gripper.uasset
│       └── IMC_ROC.uasset                 # Input mapping context
```

---

## Core Classes

### 1. ROCSubsystem

**Purpose**: Central manager for all robot controllers. Singleton per game instance.

```cpp
// ROCSubsystem.h
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "ROCTypes.h"
#include "ROCSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnRobotRegistered, const FString&, RobotID, bool, Success);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnJointCommandExecuted, const FString&, RobotID, const FROCJointCommand&, Command);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnControlModeChanged, EROCControlMode, NewMode);

UCLASS()
class ROA_API UROCSubsystem : public UGameInstanceSubsystem
{
    GENERATED_BODY()

public:
    // Subsystem lifecycle
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;

    // ==================== Robot Management ====================
    
    /**
     * Register a robot from FTI import data
     * @param RobotSpec JSON string containing robot specification from FTI
     * @return True if registration successful
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robots")
    bool RegisterRobot(const FString& RobotSpecJSON);

    /**
     * Unregister and cleanup a robot
     * @param RobotID Robot identifier to remove
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robots")
    void UnregisterRobot(const FString& RobotID);

    /**
     * Get controller for a specific robot
     * @param RobotID Robot identifier
     * @return Robot controller or nullptr if not found
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robots")
    class URobotController* GetRobotController(const FString& RobotID) const;

    /**
     * Get list of all registered robot IDs
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robots")
    TArray<FString> GetRegisteredRobotIDs() const;

    /**
     * Set the currently selected robot for UI control
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Robots")
    void SetSelectedRobot(const FString& RobotID);

    UFUNCTION(BlueprintCallable, Category = "ROC|Robots")
    FString GetSelectedRobotID() const { return SelectedRobotID; }

    // ==================== Control Mode ====================

    /**
     * Set control mode (RPM = manual, ADM = autonomous)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    void SetControlMode(EROCControlMode NewMode);

    UFUNCTION(BlueprintCallable, Category = "ROC|Mode")
    EROCControlMode GetControlMode() const { return CurrentControlMode; }

    // ==================== Joint Commands ====================

    /**
     * Send joint command to robot (goes through Linux safety validation)
     * @param RobotID Target robot
     * @param Command Joint command to execute
     * @return True if command accepted (pending safety validation)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Control")
    bool SendJointCommand(const FString& RobotID, const FROCJointCommand& Command);

    /**
     * Send batch of joint commands
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Control")
    bool SendJointCommands(const FString& RobotID, const TArray<FROCJointCommand>& Commands);

    /**
     * Emergency stop - immediately halt all robot motion
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    void EmergencyStop(const FString& RobotID);

    /**
     * Emergency stop all robots
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    void EmergencyStopAll();

    // ==================== State Queries ====================

    /**
     * Get current joint states for a robot (from DIMC)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|State")
    TArray<FROCJointState> GetJointStates(const FString& RobotID) const;

    /**
     * Check if commands are being processed (waiting for safety approval)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|State")
    bool HasPendingCommands(const FString& RobotID) const;

    // ==================== Delegates ====================

    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnRobotRegistered OnRobotRegistered;

    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnJointCommandExecuted OnJointCommandExecuted;

    UPROPERTY(BlueprintAssignable, Category = "ROC|Events")
    FOnControlModeChanged OnControlModeChanged;

private:
    // Registered robot controllers
    UPROPERTY()
    TMap<FString, URobotController*> RobotControllers;

    // Currently selected robot for UI
    FString SelectedRobotID;

    // Current control mode
    EROCControlMode CurrentControlMode = EROCControlMode::RPM;

    // IPC Bridge reference (for Linux communication)
    class UROANetworkBridge* NetworkBridge;

    // Process incoming messages from Linux
    void ProcessLinuxMessage(const FString& MessageJSON);

    // Handle safety-approved commands from Linux
    void ExecuteApprovedCommand(const FString& RobotID, const FROCJointCommand& Command);
};
```

---

### 2. RobotController

**Purpose**: Manages all joints for a single robot.

```cpp
// RobotController.h
#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "ROCTypes.h"
#include "RobotController.generated.h"

UCLASS(BlueprintType)
class ROA_API URobotController : public UObject
{
    GENERATED_BODY()

public:
    /**
     * Initialize controller from FTI robot specification
     */
    bool Initialize(const FROCRobotSpec& Spec, AActor* RobotActor);

    /**
     * Cleanup and release resources
     */
    void Shutdown();

    // ==================== Properties ====================

    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    FString GetRobotID() const { return RobotSpec.RobotID; }

    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    FString GetRobotName() const { return RobotSpec.RobotName; }

    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    int32 GetJointCount() const { return JointControllers.Num(); }

    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    TArray<FString> GetJointNames() const;

    UFUNCTION(BlueprintCallable, Category = "ROC|Robot")
    bool HasGripper() const { return RobotSpec.Capabilities.bHasGripper; }

    // ==================== Joint Control ====================

    /**
     * Get controller for specific joint
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joints")
    class UJointController* GetJointController(const FString& JointName) const;

    /**
     * Set target position for a joint
     * @param JointName Name of joint
     * @param TargetPosition Target in radians (revolute) or meters (prismatic)
     * @param VelocityLimit Maximum velocity for motion
     * @return True if command accepted
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joints")
    bool SetJointTarget(const FString& JointName, float TargetPosition, float VelocityLimit = 0.0f);

    /**
     * Set target positions for all joints at once
     * @param TargetPositions Map of joint name to target position
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joints")
    bool SetAllJointTargets(const TMap<FString, float>& TargetPositions);

    /**
     * Get current state of a joint
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joints")
    FROCJointState GetJointState(const FString& JointName) const;

    /**
     * Get all joint states
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joints")
    TArray<FROCJointState> GetAllJointStates() const;

    // ==================== Gripper ====================

    UFUNCTION(BlueprintCallable, Category = "ROC|Gripper")
    void OpenGripper(float Speed = 1.0f);

    UFUNCTION(BlueprintCallable, Category = "ROC|Gripper")
    void CloseGripper(float Speed = 1.0f);

    UFUNCTION(BlueprintCallable, Category = "ROC|Gripper")
    void SetGripperPosition(float Position);

    UFUNCTION(BlueprintCallable, Category = "ROC|Gripper")
    float GetGripperPosition() const;

    // ==================== Safety ====================

    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    void EmergencyStop();

    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    void ResetFromEmergencyStop();

    UFUNCTION(BlueprintCallable, Category = "ROC|Safety")
    bool IsInEmergencyStop() const { return bEmergencyStopped; }

    // ==================== Update ====================

    /**
     * Called every tick to update joint states from physics
     */
    void Tick(float DeltaTime);

    /**
     * Update joint states from DIMC data
     */
    void UpdateFromDIMC(const TArray<FROCJointState>& NewStates);

private:
    // Robot specification from FTI
    FROCRobotSpec RobotSpec;

    // Reference to the robot actor in the level
    UPROPERTY()
    AActor* RobotActor;

    // Joint controllers (one per controllable joint)
    UPROPERTY()
    TMap<FString, UJointController*> JointControllers;

    // Gripper joint name (if applicable)
    FString GripperJointName;

    // Emergency stop state
    bool bEmergencyStopped = false;

    // Find physics constraint component by name
    UPhysicsConstraintComponent* FindConstraint(const FString& ConstraintName) const;
};
```

---

### 3. JointController

**Purpose**: Controls a single joint via UE5 Physics Constraint.

```cpp
// JointController.h
#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "ROCTypes.h"
#include "JointController.generated.h"

UCLASS(BlueprintType)
class ROA_API UJointController : public UObject
{
    GENERATED_BODY()

public:
    /**
     * Initialize with joint specification and physics constraint
     */
    bool Initialize(const FROCJointSpec& Spec, UPhysicsConstraintComponent* Constraint);

    /**
     * Release resources
     */
    void Shutdown();

    // ==================== Properties ====================

    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FString GetJointName() const { return JointSpec.JointName; }

    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    EROCJointType GetJointType() const { return JointSpec.JointType; }

    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FROCJointLimits GetLimits() const { return JointSpec.Limits; }

    // ==================== Control ====================

    /**
     * Set target position (radians for revolute, meters for prismatic)
     * @param TargetPosition Target position within limits
     * @param VelocityLimit Max velocity (0 = use default)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SetTargetPosition(float TargetPosition, float VelocityLimit = 0.0f);

    /**
     * Set target velocity (for continuous joints or velocity mode)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SetTargetVelocity(float TargetVelocity);

    /**
     * Get current target
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float GetTargetPosition() const { return CurrentTarget; }

    // ==================== State ====================

    /**
     * Get current joint state
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FROCJointState GetState() const;

    /**
     * Get current position
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float GetCurrentPosition() const { return CurrentState.Position; }

    /**
     * Get current velocity
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float GetCurrentVelocity() const { return CurrentState.Velocity; }

    /**
     * Check if joint is at target (within tolerance)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool IsAtTarget(float Tolerance = 0.01f) const;

    // ==================== Safety ====================

    /**
     * Emergency stop - set velocity to zero, hold position
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void EmergencyStop();

    /**
     * Resume from emergency stop
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void Resume();

    /**
     * Check if within limits
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool IsWithinLimits() const;

    // ==================== Update ====================

    /**
     * Update joint - read physics state, apply motor targets
     */
    void Tick(float DeltaTime);

    /**
     * Update from external state (DIMC)
     */
    void UpdateState(const FROCJointState& NewState);

private:
    // Joint specification from FTI
    FROCJointSpec JointSpec;

    // Physics constraint reference
    UPROPERTY()
    UPhysicsConstraintComponent* PhysicsConstraint;

    // Current state
    FROCJointState CurrentState;

    // Current target
    float CurrentTarget = 0.0f;

    // Control parameters
    float DriveStiffness = 10000.0f;
    float DriveDamping = 1000.0f;
    float MaxMotorForce = 100000.0f;

    // Emergency stop state
    bool bEmergencyStopped = false;

    // Apply target to physics constraint
    void ApplyMotorTarget(float Target, float VelocityLimit);

    // Read current state from physics constraint
    void ReadPhysicsState();

    // Clamp value to limits
    float ClampToLimits(float Value) const;
};
```

---

### 4. ROCTypes

**Purpose**: Shared types, structs, and enums.

```cpp
// ROCTypes.h
#pragma once

#include "CoreMinimal.h"
#include "ROCTypes.generated.h"

// ==================== Enums ====================

UENUM(BlueprintType)
enum class EROCControlMode : uint8
{
    RPM     UMETA(DisplayName = "Role Playing Mode (Manual)"),
    ADM     UMETA(DisplayName = "Auto Driven Mode (Autonomous)")
};

UENUM(BlueprintType)
enum class EROCJointType : uint8
{
    Revolute    UMETA(DisplayName = "Revolute (Rotational)"),
    Prismatic   UMETA(DisplayName = "Prismatic (Linear)"),
    Continuous  UMETA(DisplayName = "Continuous (Unlimited Rotation)"),
    Fixed       UMETA(DisplayName = "Fixed (No Motion)")
};

UENUM(BlueprintType)
enum class EROCCommandStatus : uint8
{
    Pending     UMETA(DisplayName = "Pending Safety Validation"),
    Approved    UMETA(DisplayName = "Approved by Safety"),
    Rejected    UMETA(DisplayName = "Rejected by Safety"),
    Executing   UMETA(DisplayName = "Currently Executing"),
    Completed   UMETA(DisplayName = "Completed"),
    Failed      UMETA(DisplayName = "Failed")
};

// ==================== Structs ====================

USTRUCT(BlueprintType)
struct FROCJointLimits
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Limits")
    float Lower = -3.14159f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Limits")
    float Upper = 3.14159f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Limits")
    float MaxVelocity = 2.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Limits")
    float MaxEffort = 100.0f;
};

USTRUCT(BlueprintType)
struct FROCJointSpec
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Joint")
    FString JointName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Joint")
    EROCJointType JointType = EROCJointType::Revolute;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Joint")
    FString ParentLink;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Joint")
    FString ChildLink;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Joint")
    FVector Axis = FVector(0, 0, 1);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Joint")
    FROCJointLimits Limits;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE5")
    FString UE5ConstraintName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE5")
    FString UE5ConstraintPath;
};

USTRUCT(BlueprintType)
struct FROCJointState
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "State")
    FString JointName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "State")
    float Position = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "State")
    float Velocity = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "State")
    float Effort = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "State")
    float Timestamp = 0.0f;
};

USTRUCT(BlueprintType)
struct FROCJointCommand
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Command")
    FString JointName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Command")
    float TargetPosition = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Command")
    float VelocityLimit = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Command")
    EROCCommandStatus Status = EROCCommandStatus::Pending;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Command")
    FString CommandID;
};

USTRUCT(BlueprintType)
struct FROCRobotCapabilities
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Capabilities")
    bool bHasGripper = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Capabilities")
    FString GripperJointName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Capabilities")
    bool bHasMobileBase = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Capabilities")
    float MaxPayloadKg = 5.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Capabilities")
    float MaxReachM = 1.0f;
};

USTRUCT(BlueprintType)
struct FROCRobotSpec
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Robot")
    FString RobotID;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Robot")
    FString RobotName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Robot")
    TArray<FROCJointSpec> Joints;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Robot")
    FROCRobotCapabilities Capabilities;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE5")
    FString BlueprintPath;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "UE5")
    FString RootActorName;
};

// ==================== IPC Message Types ====================

USTRUCT(BlueprintType)
struct FROCIPCMessage
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "IPC")
    FString MessageType;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "IPC")
    FString RobotID;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "IPC")
    FString Payload;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "IPC")
    float Timestamp = 0.0f;
};
```

---

## Widget Design

### Robot Control Panel (Main Widget)

```
┌─────────────────────────────────────────────────────────────┐
│  ROA Robot Controller                            [X] Close  │
├─────────────────────────────────────────────────────────────┤
│  Robot: [ConstructionArm ▼]     Mode: [● RPM] [○ ADM]       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  shoulder_joint  ────────────●────────────  1.57 rad       │
│                  -3.14                      3.14            │
│                                                             │
│  elbow_joint     ──────●──────────────────  -0.79 rad      │
│                  -2.35                      2.35            │
│                                                             │
│  wrist_joint     ────────────●────────────  0.00 rad       │
│                  -1.57                      1.57            │
│                                                             │
│  gripper         ────────────●────────────  0.04 m         │
│                  0.00                       0.08            │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Gripper: [Open] [Close]    Speed: ────●────  1.0x         │
│                                                             │
│  [🔴 E-STOP]                     Status: Ready              │
└─────────────────────────────────────────────────────────────┘
```

### Joint Slider Widget (Reusable)

```cpp
// JointSliderWidget.h (conceptual - actual implementation as Widget Blueprint)
UCLASS()
class UJointSliderWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UPROPERTY(meta = (BindWidget))
    UTextBlock* JointNameText;

    UPROPERTY(meta = (BindWidget))
    USlider* PositionSlider;

    UPROPERTY(meta = (BindWidget))
    UTextBlock* CurrentValueText;

    UPROPERTY(meta = (BindWidget))
    UTextBlock* MinValueText;

    UPROPERTY(meta = (BindWidget))
    UTextBlock* MaxValueText;

    // Delegate when slider changes
    DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnJointValueChanged, FString, JointName, float, NewValue);
    
    UPROPERTY(BlueprintAssignable)
    FOnJointValueChanged OnJointValueChanged;

    UFUNCTION(BlueprintCallable)
    void SetJointSpec(const FROCJointSpec& Spec);

    UFUNCTION(BlueprintCallable)
    void UpdateCurrentValue(float Position);
};
```

---

## Input Mapping

### Input Actions (Enhanced Input System)

| Action | Key Bindings | Description |
|--------|--------------|-------------|
| `IA_ROC_MoveForward` | W, Up Arrow | Move selected joint positive |
| `IA_ROC_MoveBackward` | S, Down Arrow | Move selected joint negative |
| `IA_ROC_NextJoint` | E, Tab | Select next joint |
| `IA_ROC_PrevJoint` | Q, Shift+Tab | Select previous joint |
| `IA_ROC_GripperToggle` | G | Toggle gripper open/close |
| `IA_ROC_SpeedModifier` | Shift (hold) | Increase movement speed |
| `IA_ROC_EmergencyStop` | Space, Esc | Emergency stop |
| `IA_ROC_ModeToggle` | M | Toggle RPM/ADM mode |

---

## IPC Protocol (UE5 ↔ Linux)

### UE5 → Linux Messages

**Joint Command Request:**
```json
{
  "type": "joint_command_request",
  "robot_id": "robot_0",
  "commands": [
    {"joint": "shoulder_joint", "target_position": 1.57, "velocity_limit": 1.0}
  ],
  "source": "rpm",
  "timestamp": 1705167200.123
}
```

**Emergency Stop:**
```json
{
  "type": "emergency_stop",
  "robot_id": "robot_0",
  "reason": "user_requested",
  "timestamp": 1705167200.123
}
```

### Linux → UE5 Messages

**Command Approved:**
```json
{
  "type": "command_approved",
  "robot_id": "robot_0",
  "commands": [
    {"joint": "shoulder_joint", "target_position": 1.57, "approved": true}
  ],
  "timestamp": 1705167200.123
}
```

**Command Rejected:**
```json
{
  "type": "command_rejected",
  "robot_id": "robot_0",
  "command_id": "cmd_001",
  "reason": "exceeds_velocity_limit",
  "timestamp": 1705167200.123
}
```

---

## Implementation Notes

### Phase 1: Basic Control (UE5-only)
1. Create widget blueprint with sliders
2. Directly control physics constraints (no Linux validation)
3. Test joint control works

### Phase 2: Safety Integration
1. Route all commands through IPC to Linux
2. Linux validates and returns approved/rejected
3. Only execute approved commands

### Phase 3: Full Integration
1. Receive DIMC data for state feedback
2. Receive FTI data for robot registration
3. Full RPM keyboard control
4. ADM task execution

---

## File Checklist

**C++ Classes to Create:**
- [ ] `ROCSubsystem.h/cpp`
- [ ] `RobotController.h/cpp`
- [ ] `JointController.h/cpp`
- [ ] `ROCTypes.h`
- [ ] `ROCInputComponent.h/cpp`

**Widget Blueprints to Create:**
- [ ] `WBP_RobotControlPanel`
- [ ] `WBP_JointSlider`
- [ ] `WBP_ModeSelector`
- [ ] `WBP_RobotSelector`

**Input Assets to Create:**
- [ ] `IMC_ROC` (Input Mapping Context)
- [ ] `IA_ROC_*` (Input Actions)

---

## Status

**Current Status**: Design Complete, NOT IMPLEMENTED  
**Next Step**: Wait for implementation approval
