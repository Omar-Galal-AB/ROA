// ROCTypes.h - Shared types for Robot Operator Controller UE5 Plugin
// 
// Contains enums, structs, and delegates used across ROC subsystems.
// Part of the ROA UE5 Plugin.

#pragma once

#include "CoreMinimal.h"
#include "ROCTypes.generated.h"

// Forward declarations
class URobotController;
class UJointController;

// =============================================================================
// Enumerations
// =============================================================================

/**
 * Robot operational status.
 */
UENUM(BlueprintType)
enum class EROCRobotStatus : uint8
{
    Initializing    UMETA(DisplayName = "Initializing"),
    Ready           UMETA(DisplayName = "Ready"),
    Moving          UMETA(DisplayName = "Moving"),
    EmergencyStopped UMETA(DisplayName = "Emergency Stopped"),
    Error           UMETA(DisplayName = "Error"),
    Disconnected    UMETA(DisplayName = "Disconnected")
};

/**
 * Control mode enumeration.
 */
UENUM(BlueprintType)
enum class EROCControlMode : uint8
{
    RPM     UMETA(DisplayName = "Remote Position Mode"),
    ADM     UMETA(DisplayName = "Autonomous Decision Mode")
};

/**
 * Joint type enumeration.
 */
UENUM(BlueprintType)
enum class EROCJointType : uint8
{
    Revolute    UMETA(DisplayName = "Revolute"),
    Prismatic   UMETA(DisplayName = "Prismatic"),
    Continuous  UMETA(DisplayName = "Continuous"),
    Fixed       UMETA(DisplayName = "Fixed")
};

/**
 * Command validation result.
 */
UENUM(BlueprintType)
enum class EROCCommandResult : uint8
{
    Approved        UMETA(DisplayName = "Approved"),
    Modified        UMETA(DisplayName = "Modified"),
    Rejected        UMETA(DisplayName = "Rejected"),
    Pending         UMETA(DisplayName = "Pending Validation")
};

/**
 * Rejection reasons for commands.
 */
UENUM(BlueprintType)
enum class EROCRejectionReason : uint8
{
    None                    UMETA(DisplayName = "None"),
    EmergencyStopActive     UMETA(DisplayName = "Emergency Stop Active"),
    ExceedsPositionLimit    UMETA(DisplayName = "Exceeds Position Limit"),
    ExceedsVelocityLimit    UMETA(DisplayName = "Exceeds Velocity Limit"),
    CollisionRisk           UMETA(DisplayName = "Collision Risk"),
    BoundaryViolation       UMETA(DisplayName = "Boundary Violation"),
    UnknownRobot            UMETA(DisplayName = "Unknown Robot"),
    UnknownJoint            UMETA(DisplayName = "Unknown Joint"),
    InvalidCommand          UMETA(DisplayName = "Invalid Command")
};

/**
 * Alert severity levels.
 */
UENUM(BlueprintType)
enum class EROCAlertSeverity : uint8
{
    Info        UMETA(DisplayName = "Info"),
    Warning     UMETA(DisplayName = "Warning"),
    Critical    UMETA(DisplayName = "Critical")
};

// =============================================================================
// Structs
// =============================================================================

/**
 * Joint limits structure.
 */
USTRUCT(BlueprintType)
struct FROCJointLimits
{
    GENERATED_BODY()
    
    /** Lower position limit (radians for revolute, meters for prismatic) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Limits")
    float Lower = -PI;
    
    /** Upper position limit */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Limits")
    float Upper = PI;
    
    /** Maximum velocity */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Limits")
    float Velocity = 2.0f;
    
    /** Maximum effort/torque */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Limits")
    float Effort = 100.0f;
    
    /** Check if value is within limits */
    bool Contains(float Value, float Margin = 0.0f) const
    {
        return Value >= (Lower + Margin) && Value <= (Upper - Margin);
    }
    
    /** Clamp value to limits */
    float Clamp(float Value, float Margin = 0.0f) const
    {
        return FMath::Clamp(Value, Lower + Margin, Upper - Margin);
    }
};

/**
 * Joint configuration from FTI.
 */
USTRUCT(BlueprintType)
struct FROCJointConfig
{
    GENERATED_BODY()
    
    /** Joint name from URDF */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Joint")
    FString JointName;
    
    /** Joint type */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Joint")
    EROCJointType JointType = EROCJointType::Revolute;
    
    /** Joint limits */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Joint")
    FROCJointLimits Limits;
    
    /** UE5 physics constraint name */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Joint")
    FString UE5ConstraintName;
    
    /** Parent link name */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Joint")
    FString ParentLink;
    
    /** Child link name */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Joint")
    FString ChildLink;
};

/**
 * Joint state - current position, velocity, effort.
 */
USTRUCT(BlueprintType)
struct FROCJointState
{
    GENERATED_BODY()
    
    /** Joint name */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    FString JointName;
    
    /** Current position (radians or meters) */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    float Position = 0.0f;
    
    /** Current velocity */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    float Velocity = 0.0f;
    
    /** Current effort/torque */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    float Effort = 0.0f;
    
    /** Target position (if set) */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    float TargetPosition = 0.0f;
    
    /** Whether joint is currently moving */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    bool bIsMoving = false;
    
    /** Whether joint is at limit */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    bool bAtLimit = false;
    
    /** Whether joint has an error */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|State")
    bool bHasError = false;
};

/**
 * Joint command - request to move a joint.
 */
USTRUCT(BlueprintType)
struct FROCJointCommand
{
    GENERATED_BODY()
    
    /** Joint name */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Command")
    FString JointName;
    
    /** Target position */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Command")
    float TargetPosition = 0.0f;
    
    /** Velocity limit (0 = use default) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Command")
    float VelocityLimit = 0.0f;
    
    /** Unique command ID for tracking */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Command")
    FString CommandId;
    
    /** Command result (set after validation) */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Command")
    EROCCommandResult Result = EROCCommandResult::Pending;
    
    /** Rejection reason if rejected */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Command")
    EROCRejectionReason RejectionReason = EROCRejectionReason::None;
};

/**
 * Safety status for a robot.
 */
USTRUCT(BlueprintType)
struct FROCSafetyStatus
{
    GENERATED_BODY()
    
    /** All joints within limits */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Safety")
    bool bAllLimitsOK = true;
    
    /** Distance to nearest obstacle (cm) */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Safety")
    float ObstacleDistance = TNumericLimits<float>::Max();
    
    /** Whether robot is within workspace bounds */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Safety")
    bool bWithinBounds = true;
    
    /** Emergency stop active */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Safety")
    bool bEStopActive = false;
};

/**
 * Robot capabilities from FTI.
 */
USTRUCT(BlueprintType)
struct FROCRobotCapabilities
{
    GENERATED_BODY()
    
    /** Whether robot has a gripper */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Capabilities")
    bool bHasGripper = false;
    
    /** Maximum payload in kg */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Capabilities")
    float MaxPayloadKg = 0.0f;
    
    /** Maximum reach in cm */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Capabilities")
    float ReachCm = 0.0f;
    
    /** Degrees of freedom */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Capabilities")
    int32 DOF = 0;
};

/**
 * Robot configuration from FTI.
 */
USTRUCT(BlueprintType)
struct FROCRobotConfig
{
    GENERATED_BODY()
    
    /** Unique robot identifier */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Config")
    FString RobotId;
    
    /** Human-readable robot name */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Config")
    FString RobotName;
    
    /** Joint configurations */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Config")
    TArray<FROCJointConfig> Joints;
    
    /** Robot capabilities */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROC|Config")
    FROCRobotCapabilities Capabilities;
};

/**
 * Safety alert from Linux.
 */
USTRUCT(BlueprintType)
struct FROCSafetyAlert
{
    GENERATED_BODY()
    
    /** Robot this alert applies to */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Alert")
    FString RobotId;
    
    /** Type of alert */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Alert")
    FString AlertType;
    
    /** Severity level */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Alert")
    EROCAlertSeverity Severity = EROCAlertSeverity::Info;
    
    /** Alert message */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Alert")
    FString Message;
    
    /** Timestamp */
    UPROPERTY(BlueprintReadOnly, Category = "ROC|Alert")
    float Timestamp = 0.0f;
};

// =============================================================================
// Delegates
// =============================================================================

/** Delegate for robot status changes */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnROCRobotStatusChanged, 
    const FString&, RobotId, 
    EROCRobotStatus, NewStatus);

/** Delegate for mode changes */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnROCModeChanged,
    const FString&, RobotId,
    EROCControlMode, OldMode,
    EROCControlMode, NewMode);

/** Delegate for command validation result */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnROCCommandValidated,
    const FString&, RobotId,
    const FROCJointCommand&, Command);

/** Delegate for safety alerts */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnROCSafetyAlert,
    const FROCSafetyAlert&, Alert);

/** Delegate for emergency stop */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnROCEmergencyStop,
    const FString&, RobotId,
    const FString&, Reason);

/** Delegate for connection status */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnROCConnectionChanged,
    bool, bConnected);
