// JointController.h - Per-joint controller for ROC
//
// Controls a single joint via UE5 physics constraint.
// Handles position targeting, velocity limits, and state tracking.

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "ROCTypes.h"
#include "JointController.generated.h"

// Forward declarations
class UPhysicsConstraintComponent;

/**
 * Joint Controller - Manages a single joint in the ROC system.
 * 
 * Provides:
 * - Physics constraint motor control
 * - Position targeting
 * - Velocity limiting
 * - State tracking
 */
UCLASS(BlueprintType)
class ROA_API UJointController : public UObject
{
    GENERATED_BODY()
    
public:
    // =========================================================================
    // Initialization
    // =========================================================================
    
    /**
     * Initialize the joint controller.
     * 
     * @param InConfig Joint configuration from FTI
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void Initialize(const FROCJointConfig& InConfig);
    
    /**
     * Bind to a physics constraint component.
     * 
     * @param Constraint Physics constraint to control
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void BindPhysicsConstraint(UPhysicsConstraintComponent* Constraint);
    
    /**
     * Shutdown the joint controller.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void Shutdown();
    
    // =========================================================================
    // State Access
    // =========================================================================
    
    /** Get joint name */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FString GetJointName() const { return Config.JointName; }
    
    /** Get joint type */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    EROCJointType GetJointType() const { return Config.JointType; }
    
    /** Get joint limits */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FROCJointLimits GetLimits() const { return Config.Limits; }
    
    /** Get UE5 constraint name */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FString GetUE5ConstraintName() const { return Config.UE5ConstraintName; }
    
    /** Get current joint state */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    FROCJointState GetState() const { return State; }
    
    /** Get current position */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float GetPosition() const { return State.Position; }
    
    /** Get current velocity */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float GetVelocity() const { return State.Velocity; }
    
    /** Get target position */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float GetTargetPosition() const { return State.TargetPosition; }
    
    /** Check if joint is moving */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool IsMoving() const { return State.bIsMoving; }
    
    /** Check if joint is at limit */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool IsAtLimit() const { return State.bAtLimit; }
    
    /** Check if physics constraint is bound */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool IsConstraintBound() const { return PhysicsConstraint != nullptr; }
    
    // =========================================================================
    // Movement Control
    // =========================================================================
    
    /**
     * Set target position for the joint.
     * Motor will drive toward this position.
     * 
     * @param Position Target position (radians for revolute, meters for prismatic)
     * @param VelocityLimit Maximum velocity (0 = use default)
     * @return True if target set successfully
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool SetTargetPosition(float Position, float VelocityLimit = 0.0f);
    
    /**
     * Increment target position.
     * 
     * @param Delta Amount to add to current target
     * @param VelocityLimit Maximum velocity
     * @return New target position
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    float IncrementTarget(float Delta, float VelocityLimit = 0.0f);
    
    /**
     * Stop joint movement immediately.
     * Sets target to current position.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void Stop();
    
    /**
     * Move to home position (zero).
     * 
     * @param VelocityLimit Maximum velocity
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void MoveToHome(float VelocityLimit = 0.0f);
    
    // =========================================================================
    // Motor Configuration
    // =========================================================================
    
    /**
     * Enable/disable the joint motor.
     * 
     * @param bEnable Whether to enable the motor
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SetMotorEnabled(bool bEnable);
    
    /**
     * Check if motor is enabled.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    bool IsMotorEnabled() const { return bMotorEnabled; }
    
    /**
     * Set motor strength.
     * 
     * @param Strength Motor strength (0-1)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SetMotorStrength(float Strength);
    
    /**
     * Set default velocity limit.
     * 
     * @param Velocity Default velocity
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|Joint")
    void SetDefaultVelocity(float Velocity);
    
    // =========================================================================
    // Tick
    // =========================================================================
    
    /**
     * Tick the joint controller.
     * Updates state from physics constraint.
     * 
     * @param DeltaTime Time since last tick
     */
    void Tick(float DeltaTime);
    
protected:
    // =========================================================================
    // Properties
    // =========================================================================
    
    /** Joint configuration */
    UPROPERTY()
    FROCJointConfig Config;
    
    /** Current joint state */
    UPROPERTY()
    FROCJointState State;
    
    /** Physics constraint reference */
    UPROPERTY()
    UPhysicsConstraintComponent* PhysicsConstraint = nullptr;
    
    /** Whether motor is enabled */
    UPROPERTY()
    bool bMotorEnabled = true;
    
    /** Motor strength (0-1) */
    UPROPERTY()
    float MotorStrength = 1.0f;
    
    /** Default velocity limit */
    UPROPERTY()
    float DefaultVelocity = 1.0f;
    
    /** Current velocity limit */
    UPROPERTY()
    float CurrentVelocityLimit = 1.0f;
    
    /** Previous position for velocity calculation */
    UPROPERTY()
    float PreviousPosition = 0.0f;
    
    /** Velocity smoothing */
    UPROPERTY()
    float SmoothedVelocity = 0.0f;
    
    /** Moving threshold */
    static constexpr float MovingThreshold = 0.001f;
    
    /** Limit margin */
    static constexpr float LimitMargin = 0.01f;
    
    // =========================================================================
    // Internal Methods
    // =========================================================================
    
    /** Apply target to physics constraint */
    void ApplyTargetToConstraint();
    
    /** Read current position from constraint */
    float ReadPositionFromConstraint() const;
    
    /** Update state flags */
    void UpdateStateFlags();
    
    /** Configure constraint motor settings */
    void ConfigureMotor();
};
