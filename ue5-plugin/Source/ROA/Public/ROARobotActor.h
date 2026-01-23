// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ROAMessageTypes.h"
#include "Components/SkeletalMeshComponent.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"
#include "ROARobotActor.generated.h"

/**
 * Joint information for robot
 */
USTRUCT(BlueprintType)
struct FROAJointInfo
{
	GENERATED_BODY()

	UPROPERTY()
	FString JointName;

	UPROPERTY()
	float MinLimit;

	UPROPERTY()
	float MaxLimit;

	UPROPERTY()
	float CurrentPosition;

	UPROPERTY()
	float CurrentVelocity;

	UPROPERTY()
	float TargetPosition;

	UPROPERTY()
	float MaxVelocity;

	UPROPERTY()
	float MaxEffort;

	FROAJointInfo()
		: MinLimit(-3.14159f)
		, MaxLimit(3.14159f)
		, CurrentPosition(0.0f)
		, CurrentVelocity(0.0f)
		, TargetPosition(0.0f)
		, MaxVelocity(3.14159f)
		, MaxEffort(100.0f)
	{}
};

/**
 * Robot actor that represents a physical robot in UE5
 * Supports Universal Robot models (UR3, UR5, UR10, UR15, UR20, UR30, etc.)
 * 
 * v0.2 Changes:
 * - Component-based architecture support
 * - Auto-creates ROS2NodeComponent if native mode available
 * - Maintains v0.1 backward compatibility
 */
UCLASS()
class ROA_API AROARobotActor : public AActor
{
	GENERATED_BODY()
	
public:	
	AROARobotActor();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

public:	
	virtual void Tick(float DeltaTime) override;

	/**
	 * Initialize robot with configuration
	 * @param InRobotId - Unique robot ID
	 * @param InRobotType - Robot type (e.g., "ur5e")
	 * @param InJointStates - Initial joint positions
	 * @return True if successful
	 */
	bool Initialize(const FString& InRobotId, const FString& InRobotType, const TArray<float>& InJointStates);

	// ========================================================================
	// Component System (v0.2)
	// ========================================================================

	/**
	 * Enable/disable component-based mode
	 * When enabled, auto-creates ROS2 components
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Components")
	void SetComponentMode(bool bEnabled);

	/**
	 * Check if component mode is enabled
	 */
	UFUNCTION(BlueprintPure, Category = "ROA|Components")
	bool IsComponentModeEnabled() const { return bUseComponentMode; }

	/**
	 * Get ROS2 Node Component (auto-created if component mode enabled)
	 */
	UFUNCTION(BlueprintPure, Category = "ROA|Components")
	class UROS2NodeComponent* GetROS2NodeComponent() const { return ROS2NodeComponent; }

	/**
	 * Get ROS2 Publisher Component for joint states
	 */
	UFUNCTION(BlueprintPure, Category = "ROA|Components")
	class UROS2PublisherComponent* GetJointStatePublisher() const { return JointStatePublisher; }

	/**
	 * Get ROS2 Subscriber Component for joint commands
	 */
	UFUNCTION(BlueprintPure, Category = "ROA|Components")
	class UROS2SubscriberComponent* GetJointCommandSubscriber() const { return JointCommandSubscriber; }

	// ========================================================================
	// v0.1 API (Backward Compatible)
	// ========================================================================

	/**
	 * Get robot ID
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	FString GetRobotId() const { return RobotId; }

	/**
	 * Get robot type
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	FString GetRobotType() const { return RobotType; }

	/**
	 * Set joint positions
	 * @param JointPositions - Target joint positions (radians)
	 * @param Duration - Time to reach target
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	bool SetJointPositions(const TArray<float>& JointPositions, float Duration = 1.0f);

	/**
	 * Set joint velocities
	 * @param JointVelocities - Target joint velocities (rad/s)
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	bool SetJointVelocities(const TArray<float>& JointVelocities);

	/**
	 * Get current joint positions
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	TArray<float> GetJointPositions() const;

	/**
	 * Get current joint velocities
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	TArray<float> GetJointVelocities() const;

	/**
	 * Get joint count
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	int32 GetJointCount() const { return Joints.Num(); }

	/**
	 * Get end effector position in world space
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	FVector GetEndEffectorPosition() const;

	/**
	 * Get end effector rotation in world space
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	FRotator GetEndEffectorRotation() const;

	/**
	 * Emergency stop - halt all motion
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void EmergencyStop();

	/**
	 * Set physics parameters
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void SetPhysicsParameters(FVector Gravity, float MassScale, float Damping, float Friction);

	/**
	 * Enable/disable collision
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void SetCollisionEnabled(bool bEnabled);

	/**
	 * Get collision status
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	bool IsColliding() const { return bIsColliding; }

	/**
	 * Get collision count
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	int32 GetCollisionCount() const { return CollisionCount; }

	/**
	 * Get robot state for network transmission
	 */
	FROARobotState GetRobotState() const;

	/**
	 * Called when collision occurs
	 */
	UFUNCTION()
	void OnCollisionDetected(UPrimitiveComponent* HitComponent, AActor* OtherActor, 
	     UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);

protected:
	/** Root skeletal mesh component */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA")
	USkeletalMeshComponent* RobotMesh;

	/** Robot unique ID */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	FString RobotId;

	/** Robot type (ur3, ur5, ur10, etc.) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	FString RobotType;

	/** Joint information array */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA")
	TArray<FROAJointInfo> Joints;

	/** Physics constraint components for joints */
	UPROPERTY()
	TArray<UPhysicsConstraintComponent*> JointConstraints;

	/** Is currently colliding */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA")
	bool bIsColliding;

	/** Collision count */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA")
	int32 CollisionCount;

	/** Emergency stop active */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA")
	bool bEmergencyStop;

	// ========================================================================
	// Component References (v0.2)
	// ========================================================================

	/** Use component-based mode (v0.2) vs monolithic mode (v0.1) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA|Components")
	bool bUseComponentMode;

	/** ROS2 Node Component (auto-created if component mode enabled) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA|Components")
	class UROS2NodeComponent* ROS2NodeComponent;

	/** ROS2 Publisher for joint states */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA|Components")
	class UROS2PublisherComponent* JointStatePublisher;

	/** ROS2 Subscriber for joint commands */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "ROA|Components")
	class UROS2SubscriberComponent* JointCommandSubscriber;

private:
	/** Setup ROS2 components (v0.2) */
	void SetupROS2Components();

	/** Cleanup ROS2 components */
	void CleanupROS2Components();

	/** Publish joint states via ROS2 (component mode) */
	void PublishJointStates();

	/** Handle joint command received (component mode callback) */
	UFUNCTION()
	void OnJointCommandReceived(class UROS2MessageBase* Message);

	// ========================================================================
	// v0.1 Private Methods
	// ========================================================================
	/** Update joint physics based on target positions */
	void UpdateJointPhysics(float DeltaTime);

	/** Apply joint positions to skeletal mesh */
	void ApplyJointPositionsToMesh();

	/** Load robot mesh and skeleton */
	bool LoadRobotMesh();

	/** Setup joint constraints */
	bool SetupJointConstraints();

	/** Clamp joint position to limits */
	float ClampJointPosition(int32 JointIndex, float Position) const;

	/** Time accumulator for smooth motion */
	float MotionTimeAccumulator;

	/** Target duration for motion */
	float MotionDuration;
};
