// Copyright ROA Development Team. All Rights Reserved.

#include "ROARobotActor.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/BodyInstance.h"
#include "Engine/SkeletalMesh.h"
#include "Components/ROS2/ROS2NodeComponent.h"
#include "Components/ROS2/ROS2PublisherComponent.h"
#include "Components/ROS2/ROS2SubscriberComponent.h"
#include "Components/ROS2/ROS2Messages.h"
#include "Components/ROS2/ROS2Context.h"

// Sets default values
AROARobotActor::AROARobotActor()
{
	PrimaryActorTick.bCanEverTick = true;

	// Create root skeletal mesh component
	RobotMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("RobotMesh"));
	RootComponent = RobotMesh;

	// Enable physics and collision
	RobotMesh->SetSimulatePhysics(false); // Will be enabled per-joint
	RobotMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	RobotMesh->SetCollisionProfileName(TEXT("BlockAll"));

	// Initialize properties
	bIsColliding = false;
	CollisionCount = 0;
	bEmergencyStop = false;
	MotionTimeAccumulator = 0.0f;
	MotionDuration = 1.0f;

	// v0.2: Component mode (enabled by default, works with both Native ROS2 and TCP fallback)
	bUseComponentMode = true;
	ROS2NodeComponent = nullptr;
	JointStatePublisher = nullptr;
	JointCommandSubscriber = nullptr;
}

// Called when the game starts or when spawned
void AROARobotActor::BeginPlay()
{
	Super::BeginPlay();
	
	// Setup collision callbacks
	if (RobotMesh)
	{
		RobotMesh->OnComponentHit.AddDynamic(this, &AROARobotActor::OnCollisionDetected);
		RobotMesh->SetNotifyRigidBodyCollision(true);
	}

	// v0.2: Setup ROS2 components if enabled
	if (bUseComponentMode)
	{
		// Auto-initialize with test joints if no joints exist
		if (Joints.Num() == 0)
		{
			UE_LOG(LogTemp, Warning, TEXT("ROA Robot: Auto-initializing with 6 test joints"));
			Initialize(RobotId.IsEmpty() ? TEXT("robot_0") : RobotId, TEXT("test_robot"), {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f});
		}
		
		SetupROS2Components();
	}
	
	UE_LOG(LogTemp, Log, TEXT("ROA Robot Actor: BeginPlay for '%s' (ComponentMode=%d, Joints=%d)"), 
		*RobotId, bUseComponentMode, Joints.Num());
}

void AROARobotActor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// v0.2: Cleanup components
	if (bUseComponentMode)
	{
		CleanupROS2Components();
	}

	Super::EndPlay(EndPlayReason);
}

// Called every frame
void AROARobotActor::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (!bEmergencyStop && Joints.Num() > 0)
	{
		UpdateJointPhysics(DeltaTime);

		// v0.2: Publish joint states if component mode
		if (bUseComponentMode && JointStatePublisher)
		{
			PublishJointStates();
		}
	}
}

// ============================================================================
// Component System (v0.2)
// ============================================================================

void AROARobotActor::SetComponentMode(bool bEnabled)
{
	if (bUseComponentMode == bEnabled)
	{
		return;
	}

	bUseComponentMode = bEnabled;

	if (bEnabled)
	{
		SetupROS2Components();
	}
	else
	{
		CleanupROS2Components();
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Robot: Component mode %s"), 
		bEnabled ? TEXT("enabled") : TEXT("disabled"));
}

void AROARobotActor::SetupROS2Components()
{
	UE_LOG(LogTemp, Log, TEXT("ROA Robot: Setting up ROS2 components (Mode: %s)..."),
		FROS2Context::Get().IsNativeModeAvailable() ? TEXT("Native") : TEXT("TCP Fallback"));

	// Create ROS2 Node Component
	ROS2NodeComponent = NewObject<UROS2NodeComponent>(this, TEXT("ROS2NodeComponent"));
	if (ROS2NodeComponent)
	{
		ROS2NodeComponent->RegisterComponent();
		ROS2NodeComponent->OnAttachedToRobot();
		UE_LOG(LogTemp, Log, TEXT("ROA Robot: ROS2NodeComponent created"));
	}

	// Create Joint State Publisher
	JointStatePublisher = NewObject<UROS2PublisherComponent>(this, TEXT("JointStatePublisher"));
	if (JointStatePublisher)
	{
		JointStatePublisher->TopicName = FString::Printf(TEXT("/robot/%s/joint_states"), *RobotId);
		JointStatePublisher->MessageType = TEXT("sensor_msgs/msg/JointState");
		JointStatePublisher->PublishRateLimit = 30.0f; // 30 Hz
		// Pass node component directly (required for rosbridge mode)
		if (ROS2NodeComponent)
		{
			JointStatePublisher->SetNodeComponent(ROS2NodeComponent);
		}
		JointStatePublisher->RegisterComponent();
		JointStatePublisher->OnAttachedToRobot();
		UE_LOG(LogTemp, Log, TEXT("ROA Robot: JointStatePublisher created"));
	}

	// Create Joint Command Subscriber
	JointCommandSubscriber = NewObject<UROS2SubscriberComponent>(this, TEXT("JointCommandSubscriber"));
	if (JointCommandSubscriber)
	{
		JointCommandSubscriber->TopicName = FString::Printf(TEXT("/robot/%s/joint_commands"), *RobotId);
		JointCommandSubscriber->MessageType = TEXT("trajectory_msgs/msg/JointTrajectory");
		JointCommandSubscriber->RegisterComponent();
		JointCommandSubscriber->OnAttachedToRobot();
		
		// Bind callback
		JointCommandSubscriber->OnMessageReceived.AddDynamic(this, &AROARobotActor::OnJointCommandReceived);
		
		UE_LOG(LogTemp, Log, TEXT("ROA Robot: JointCommandSubscriber created"));
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Robot: ROS2 components setup complete"));
}

void AROARobotActor::CleanupROS2Components()
{
	if (JointCommandSubscriber)
	{
		JointCommandSubscriber->OnMessageReceived.RemoveDynamic(this, &AROARobotActor::OnJointCommandReceived);
		JointCommandSubscriber->UnregisterComponent();
		JointCommandSubscriber = nullptr;
	}

	if (JointStatePublisher)
	{
		JointStatePublisher->UnregisterComponent();
		JointStatePublisher = nullptr;
	}

	if (ROS2NodeComponent)
	{
		ROS2NodeComponent->UnregisterComponent();
		ROS2NodeComponent = nullptr;
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Robot: ROS2 components cleaned up"));
}

void AROARobotActor::PublishJointStates()
{
	if (!JointStatePublisher || !JointStatePublisher->IsPublisherReady())
	{
		return;
	}

	// Debug logging
	static int32 PublishCount = 0;
	if (PublishCount++ % 30 == 0)  // Log every 30 calls (1 second at 30 Hz)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Robot: Publishing joint states - %d joints"), Joints.Num());
	}

	// Create joint state message
	UROS2JointStateMessage* Message = NewObject<UROS2JointStateMessage>();
	
	// Fill joint names
	for (const FROAJointInfo& Joint : Joints)
	{
		Message->JointNames.Add(Joint.JointName);
		Message->Positions.Add(Joint.CurrentPosition);
		Message->Velocities.Add(Joint.CurrentVelocity);
		Message->Efforts.Add(0.0f); // TODO: Calculate actual efforts
	}

	// Publish
	JointStatePublisher->Publish(Message);
}

void AROARobotActor::OnJointCommandReceived(UROS2MessageBase* Message)
{
	if (!Message)
	{
		return;
	}

	// TODO: Parse JointTrajectory message and apply to robot
	// For now, just log
	UE_LOG(LogTemp, Log, TEXT("ROA Robot: Received joint command (%s)"), 
		*Message->GetMessageType());
}

// ============================================================================
// v0.1 API (Backward Compatible)
// ============================================================================

bool AROARobotActor::Initialize(const FString& InRobotId, const FString& InRobotType, const TArray<float>& InJointStates)
{
	RobotId = InRobotId;
	RobotType = InRobotType;

	// Determine number of joints based on robot type (all UR robots have 6 joints)
	int32 NumJoints = InJointStates.Num() > 0 ? InJointStates.Num() : 6;
	
	// Initialize joints
	Joints.SetNum(NumJoints);
	for (int32 i = 0; i < NumJoints; ++i)
	{
		FROAJointInfo& Joint = Joints[i];
		Joint.JointName = FString::Printf(TEXT("joint_%d"), i);
		
		// Set initial position
		if (i < InJointStates.Num())
		{
			Joint.CurrentPosition = InJointStates[i];
			Joint.TargetPosition = InJointStates[i];
		}
		else
		{
			Joint.CurrentPosition = 0.0f;
			Joint.TargetPosition = 0.0f;
		}
		
		// Set default limits based on UR robot specifications
		Joint.MinLimit = -2.0f * PI; // -360 degrees
		Joint.MaxLimit = 2.0f * PI;  // +360 degrees
		Joint.MaxVelocity = PI;      // 180 deg/s
		Joint.MaxEffort = 100.0f;    // Default torque limit
		Joint.CurrentVelocity = 0.0f;
	}

	// Load robot mesh and setup
	if (!LoadRobotMesh())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Robot Actor: Could not load mesh for '%s' - using default"), *RobotType);
		// Continue anyway with basic setup
	}

	if (!SetupJointConstraints())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Robot Actor: Could not setup joint constraints for '%s'"), *RobotType);
		// Continue anyway
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Robot Actor: Initialized '%s' (Type: %s) with %d joints"), 
		*RobotId, *RobotType, NumJoints);
	return true;
}

bool AROARobotActor::SetJointPositions(const TArray<float>& JointPositions, float Duration)
{
	if (JointPositions.Num() != Joints.Num())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Robot Actor: Joint count mismatch - Expected %d, got %d"), 
			Joints.Num(), JointPositions.Num());
		return false;
	}

	// Set target positions
	for (int32 i = 0; i < Joints.Num(); ++i)
	{
		Joints[i].TargetPosition = ClampJointPosition(i, JointPositions[i]);
	}

	MotionDuration = FMath::Max(Duration, 0.1f); // Minimum 0.1 second
	MotionTimeAccumulator = 0.0f;
	
	UE_LOG(LogTemp, Verbose, TEXT("ROA Robot Actor: Setting joint positions for '%s' over %.2f seconds"), 
		*RobotId, MotionDuration);

	return true;
}

bool AROARobotActor::SetJointVelocities(const TArray<float>& JointVelocities)
{
	if (JointVelocities.Num() != Joints.Num())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Robot Actor: Joint velocity count mismatch"));
		return false;
	}

	for (int32 i = 0; i < Joints.Num(); ++i)
	{
		Joints[i].CurrentVelocity = FMath::Clamp(JointVelocities[i], 
			-Joints[i].MaxVelocity, Joints[i].MaxVelocity);
	}

	return true;
}

TArray<float> AROARobotActor::GetJointPositions() const
{
	TArray<float> Positions;
	Positions.Reserve(Joints.Num());
	
	for (const FROAJointInfo& Joint : Joints)
	{
		Positions.Add(Joint.CurrentPosition);
	}
	
	return Positions;
}

TArray<float> AROARobotActor::GetJointVelocities() const
{
	TArray<float> Velocities;
	Velocities.Reserve(Joints.Num());
	
	for (const FROAJointInfo& Joint : Joints)
	{
		Velocities.Add(Joint.CurrentVelocity);
	}
	
	return Velocities;
}

FVector AROARobotActor::GetEndEffectorPosition() const
{
	// TODO: Implement forward kinematics based on joint positions
	// For now, return a point offset from base
	
	if (RobotMesh)
	{
		// Get socket or bone location if available
		FName EndEffectorSocket = TEXT("end_effector");
		if (RobotMesh->DoesSocketExist(EndEffectorSocket))
		{
			return RobotMesh->GetSocketLocation(EndEffectorSocket);
		}
	}
	
	// Fallback: return position offset from actor location
	FVector BaseLocation = GetActorLocation();
	return BaseLocation + FVector(0, 0, 100); // 100cm up
}

FRotator AROARobotActor::GetEndEffectorRotation() const
{
	// TODO: Implement forward kinematics based on joint positions
	// For now, return actor rotation
	
	if (RobotMesh)
	{
		FName EndEffectorSocket = TEXT("end_effector");
		if (RobotMesh->DoesSocketExist(EndEffectorSocket))
		{
			return RobotMesh->GetSocketRotation(EndEffectorSocket);
		}
	}
	
	return GetActorRotation();
}

void AROARobotActor::EmergencyStop()
{
	bEmergencyStop = true;
	
	// Stop all joint motion immediately
	for (FROAJointInfo& Joint : Joints)
	{
		Joint.CurrentVelocity = 0.0f;
		Joint.TargetPosition = Joint.CurrentPosition;
	}

	// Stop physics simulation if enabled
	if (RobotMesh && RobotMesh->IsSimulatingPhysics())
	{
		RobotMesh->SetPhysicsLinearVelocity(FVector::ZeroVector);
		RobotMesh->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
	}

	UE_LOG(LogTemp, Warning, TEXT("ROA Robot Actor: EMERGENCY STOP activated for '%s'"), *RobotId);
}

void AROARobotActor::SetPhysicsParameters(FVector Gravity, float MassScale, float Damping, float Friction)
{
	if (RobotMesh)
	{
		FBodyInstance* BodyInstance = RobotMesh->GetBodyInstance();
		if (BodyInstance)
		{
			// Set mass scale
			BodyInstance->MassScale = MassScale;
			BodyInstance->UpdateMassProperties();
			
			// Set damping
			BodyInstance->LinearDamping = Damping;
			BodyInstance->AngularDamping = Damping;
			
			// TODO: Set friction on all physics materials
			
			UE_LOG(LogTemp, Log, TEXT("ROA Robot Actor: Physics parameters updated for '%s'"), *RobotId);
		}
	}
}

void AROARobotActor::SetCollisionEnabled(bool bEnabled)
{
	if (RobotMesh)
	{
		if (bEnabled)
		{
			RobotMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			RobotMesh->SetNotifyRigidBodyCollision(true);
		}
		else
		{
			RobotMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			RobotMesh->SetNotifyRigidBodyCollision(false);
		}
		
		UE_LOG(LogTemp, Log, TEXT("ROA Robot Actor: Collision %s for '%s'"), 
			bEnabled ? TEXT("enabled") : TEXT("disabled"), *RobotId);
	}
}

FROARobotState AROARobotActor::GetRobotState() const
{
	FROARobotState State;
	State.RobotId = RobotId;
	
	// Position and rotation
	FVector Location = GetActorLocation();
	FRotator Rotation = GetActorRotation();
	
	State.Position = FROAVector3D::FromFVector(Location);
	State.Rotation = FROARotation::FromFRotator(Rotation);
	
	// Joint states
	for (const FROAJointInfo& Joint : Joints)
	{
		State.JointPositions.Add(Joint.CurrentPosition);
		State.JointVelocities.Add(Joint.CurrentVelocity);
		State.JointEfforts.Add(0.0f); // TODO: Calculate actual efforts/torques
	}
	
	// End effector pose
	FVector EEPos = GetEndEffectorPosition();
	FRotator EERot = GetEndEffectorRotation();
	
	State.EndEffectorPosition = FROAVector3D::FromFVector(EEPos);
	State.EndEffectorRotation = FROARotation::FromFRotator(EERot);
	
	return State;
}

void AROARobotActor::OnCollisionDetected(UPrimitiveComponent* HitComponent, AActor* OtherActor, 
	UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	if (!OtherActor || OtherActor == this)
	{
		return;
	}

	bIsColliding = true;
	CollisionCount++;
	
	UE_LOG(LogTemp, Warning, TEXT("ROA Robot Actor: Collision detected for '%s' with '%s' at (%.2f, %.2f, %.2f)"), 
		*RobotId, *OtherActor->GetName(), Hit.ImpactPoint.X, Hit.ImpactPoint.Y, Hit.ImpactPoint.Z);
	
	// TODO: Send collision event to network server
	// For now, just log the collision
	
	// Reset collision flag after a short time
	FTimerHandle TimerHandle;
	GetWorld()->GetTimerManager().SetTimer(TimerHandle, [this]()
	{
		bIsColliding = false;
	}, 0.5f, false);
}

void AROARobotActor::UpdateJointPhysics(float DeltaTime)
{
	if (MotionDuration <= 0.0f)
	{
		return;
	}

	MotionTimeAccumulator += DeltaTime;
	float Alpha = FMath::Clamp(MotionTimeAccumulator / MotionDuration, 0.0f, 1.0f);
	
	// Smooth interpolation using ease-in-out
	float SmoothAlpha = Alpha * Alpha * (3.0f - 2.0f * Alpha);
	
	bool bAnyJointMoving = false;
	
	for (int32 i = 0; i < Joints.Num(); ++i)
	{
		FROAJointInfo& Joint = Joints[i];
		
		// Calculate difference
		float PositionDiff = Joint.TargetPosition - Joint.CurrentPosition;
		
		if (FMath::Abs(PositionDiff) > 0.001f)
		{
			// Interpolate to target position
			float OldPosition = Joint.CurrentPosition;
			Joint.CurrentPosition = FMath::Lerp(Joint.CurrentPosition, Joint.TargetPosition, SmoothAlpha);
			
			// Calculate velocity
			Joint.CurrentVelocity = (Joint.CurrentPosition - OldPosition) / DeltaTime;
			
			bAnyJointMoving = true;
		}
		else
		{
			// Close enough to target
			Joint.CurrentPosition = Joint.TargetPosition;
			Joint.CurrentVelocity = 0.0f;
		}
	}
	
	// Apply joint positions to skeletal mesh
	ApplyJointPositionsToMesh();
	
	// Reset motion accumulator if motion is complete
	if (!bAnyJointMoving || Alpha >= 1.0f)
	{
		MotionTimeAccumulator = 0.0f;
		MotionDuration = 0.0f;
	}
}

void AROARobotActor::ApplyJointPositionsToMesh()
{
	if (!RobotMesh)
	{
		return;
	}

	// TODO: Apply joint positions to skeletal mesh bones/joints
	// This requires proper skeletal mesh setup with named bones
	// For now, we just store the joint positions
	
	// Example of how to set bone rotation:
	// for (int32 i = 0; i < Joints.Num(); ++i)
	// {
	//     FName BoneName = FName(*Joints[i].JointName);
	//     FRotator BoneRotation(0, FMath::RadiansToDegrees(Joints[i].CurrentPosition), 0);
	//     RobotMesh->SetBoneRotationByName(BoneName, BoneRotation, EBoneSpaces::ComponentSpace);
	// }
}

bool AROARobotActor::LoadRobotMesh()
{
	// TODO: Load appropriate skeletal mesh based on RobotType
	// This will integrate with FTI to load URDF-based meshes
	
	UE_LOG(LogTemp, Log, TEXT("ROA Robot Actor: Loading mesh for robot type '%s'"), *RobotType);
	
	// For now, just log - actual mesh loading will be implemented with FTI integration
	// Example path: /Game/Robots/UR5/SK_UR5.SK_UR5
	
	return true;
}

bool AROARobotActor::SetupJointConstraints()
{
	// TODO: Create physics constraints for each joint
	// This will be implemented when proper skeletal mesh with physics asset is loaded
	
	UE_LOG(LogTemp, Log, TEXT("ROA Robot Actor: Setting up %d joint constraints"), Joints.Num());
	
	// For now, just reserve space for constraints
	JointConstraints.Reserve(Joints.Num());
	
	return true;
}

float AROARobotActor::ClampJointPosition(int32 JointIndex, float Position) const
{
	if (JointIndex >= 0 && JointIndex < Joints.Num())
	{
		return FMath::Clamp(Position, Joints[JointIndex].MinLimit, Joints[JointIndex].MaxLimit);
	}
	return Position;
}
