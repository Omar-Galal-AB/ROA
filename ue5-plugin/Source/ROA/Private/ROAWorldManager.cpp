// Copyright ROA Development Team. All Rights Reserved.

#include "ROAWorldManager.h"
#include "ROARobotActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "Engine/StaticMeshActor.h"
#include "Components/StaticMeshComponent.h"

FROAWorldManager::FROAWorldManager()
{
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Created"));
}

FROAWorldManager::~FROAWorldManager()
{
	CleanupAllRobots();
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Destroyed"));
}

bool FROAWorldManager::SpawnRobot(const FROASpawnRobotRequest& Request, FString& OutErrorMessage)
{
	FScopeLock Lock(&RobotMapMutex);
	
	// Check if robot ID already exists
	if (RobotActors.Contains(Request.RobotId))
	{
		OutErrorMessage = FString::Printf(TEXT("Robot with ID '%s' already exists"), *Request.RobotId);
		return false;
	}

	// Get world
	UWorld* World = GetWorld();
	if (!World)
	{
		OutErrorMessage = TEXT("Failed to get world - no active world found");
		return false;
	}

	// Get robot class
	TSubclassOf<AROARobotActor> RobotClass = GetRobotClass(Request.RobotType);
	if (!RobotClass)
	{
		OutErrorMessage = FString::Printf(TEXT("Unknown robot type: %s"), *Request.RobotType);
		return false;
	}

	// Setup spawn parameters
	FActorSpawnParameters SpawnParams;
	SpawnParams.Name = FName(*Request.RobotId);
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	// Calculate spawn transform
	FVector SpawnLocation = Request.SpawnLocation.ToFVector();
	FRotator SpawnRotation = Request.SpawnRotation.ToFRotator();
	FTransform SpawnTransform(SpawnRotation, SpawnLocation);

	// Spawn the robot actor
	AROARobotActor* RobotActor = World->SpawnActor<AROARobotActor>(
		RobotClass,
		SpawnTransform,
		SpawnParams
	);

	if (!RobotActor)
	{
		OutErrorMessage = FString::Printf(TEXT("Failed to spawn actor for robot '%s'"), *Request.RobotId);
		return false;
	}

	// Initialize robot
	if (!RobotActor->Initialize(Request.RobotId, Request.RobotType, Request.InitialJointStates))
	{
		RobotActor->Destroy();
		OutErrorMessage = FString::Printf(TEXT("Failed to initialize robot '%s'"), *Request.RobotId);
		return false;
	}

	// Add to registry
	RobotActors.Add(Request.RobotId, RobotActor);
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Successfully spawned robot '%s' (Type: %s) at location (%.2f, %.2f, %.2f)"),
		*Request.RobotId, *Request.RobotType, SpawnLocation.X, SpawnLocation.Y, SpawnLocation.Z);
	
	return true;
}

bool FROAWorldManager::DespawnRobot(const FString& RobotId)
{
	FScopeLock Lock(&RobotMapMutex);
	
	AROARobotActor** RobotActorPtr = RobotActors.Find(RobotId);
	if (!RobotActorPtr || !*RobotActorPtr)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA World Manager: Robot '%s' not found"), *RobotId);
		return false;
	}

	// Destroy actor
	(*RobotActorPtr)->Destroy();
	RobotActors.Remove(RobotId);
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Despawned robot '%s'"), *RobotId);
	return true;
}

bool FROAWorldManager::GetRobotState(const FString& RobotId, FROARobotState& OutState)
{
	FScopeLock Lock(&RobotMapMutex);
	
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	OutState = RobotActor->GetRobotState();
	return true;
}

bool FROAWorldManager::MoveRobot(const FString& RobotId, const FROAVector3D& TargetPosition, const FROARotation& TargetRotation)
{
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	// Set actor location and rotation
	FVector NewLocation = TargetPosition.ToFVector();
	FRotator NewRotation = TargetRotation.ToFRotator();
	
	RobotActor->SetActorLocation(NewLocation);
	RobotActor->SetActorRotation(NewRotation);
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Moved robot '%s' to (%.2f, %.2f, %.2f)"),
		*RobotId, NewLocation.X, NewLocation.Y, NewLocation.Z);
	
	return true;
}

bool FROAWorldManager::SetJointPositions(const FROAJointCommand& Command)
{
	AROARobotActor* RobotActor = GetRobotActor(Command.RobotId);
	if (!RobotActor)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA World Manager: Robot '%s' not found for joint command"), *Command.RobotId);
		return false;
	}

	bool bSuccess = RobotActor->SetJointPositions(Command.JointPositions, Command.Duration);
	
	if (bSuccess)
	{
		UE_LOG(LogTemp, Verbose, TEXT("ROA World Manager: Set joint positions for robot '%s'"), *Command.RobotId);
	}
	
	return bSuccess;
}

bool FROAWorldManager::SetJointVelocities(const FString& RobotId, const TArray<float>& Velocities)
{
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	return RobotActor->SetJointVelocities(Velocities);
}

bool FROAWorldManager::EmergencyStop(const FString& RobotId)
{
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	RobotActor->EmergencyStop();
	UE_LOG(LogTemp, Warning, TEXT("ROA World Manager: Emergency stop activated for robot '%s'"), *RobotId);
	return true;
}

TArray<FString> FROAWorldManager::GetAllRobotIds() const
{
	FScopeLock Lock(&RobotMapMutex);
	
	TArray<FString> RobotIds;
	RobotActors.GetKeys(RobotIds);
	return RobotIds;
}

bool FROAWorldManager::RobotExists(const FString& RobotId) const
{
	FScopeLock Lock(&RobotMapMutex);
	return RobotActors.Contains(RobotId);
}

AROARobotActor* FROAWorldManager::GetRobotActor(const FString& RobotId) const
{
	FScopeLock Lock(&RobotMapMutex);
	
	AROARobotActor* const* RobotActorPtr = RobotActors.Find(RobotId);
	return RobotActorPtr ? *RobotActorPtr : nullptr;
}

void FROAWorldManager::CleanupAllRobots()
{
	FScopeLock Lock(&RobotMapMutex);
	
	for (auto& Pair : RobotActors)
	{
		if (Pair.Value && Pair.Value->IsValidLowLevel())
		{
			Pair.Value->Destroy();
		}
	}
	
	RobotActors.Empty();
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Cleaned up all robots"));
}

bool FROAWorldManager::AddObstacle(const FString& ObstacleId, const FString& Shape, 
	const FROAVector3D& Dimensions, const FROAVector3D& Position, const FROARotation& Rotation)
{
	FScopeLock Lock(&ObstacleMapMutex);
	
	// Check if obstacle already exists
	if (ObstacleActors.Contains(ObstacleId))
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA World Manager: Obstacle '%s' already exists"), *ObstacleId);
		return false;
	}

	UWorld* World = GetWorld();
	if (!World)
	{
		return false;
	}

	// Create static mesh actor for obstacle
	FActorSpawnParameters SpawnParams;
	SpawnParams.Name = FName(*ObstacleId);
	
	FVector SpawnLocation = Position.ToFVector();
	FRotator SpawnRotation = Rotation.ToFRotator();
	
	AStaticMeshActor* ObstacleActor = World->SpawnActor<AStaticMeshActor>(
		AStaticMeshActor::StaticClass(),
		SpawnLocation,
		SpawnRotation,
		SpawnParams
	);

	if (ObstacleActor)
	{
		// TODO: Set appropriate mesh based on Shape and Dimensions
		ObstacleActors.Add(ObstacleId, ObstacleActor);
		UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Added obstacle '%s' (Shape: %s)"), *ObstacleId, *Shape);
		return true;
	}

	return false;
}

bool FROAWorldManager::RemoveObstacle(const FString& ObstacleId)
{
	FScopeLock Lock(&ObstacleMapMutex);
	
	AActor** ObstacleActorPtr = ObstacleActors.Find(ObstacleId);
	if (!ObstacleActorPtr || !*ObstacleActorPtr)
	{
		return false;
	}

	(*ObstacleActorPtr)->Destroy();
	ObstacleActors.Remove(ObstacleId);
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Removed obstacle '%s'"), *ObstacleId);
	return true;
}

void FROAWorldManager::ClearScene()
{
	CleanupAllRobots();
	
	FScopeLock Lock(&ObstacleMapMutex);
	for (auto& Pair : ObstacleActors)
	{
		if (Pair.Value && Pair.Value->IsValidLowLevel())
		{
			Pair.Value->Destroy();
		}
	}
	ObstacleActors.Empty();
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Scene cleared"));
}

UWorld* FROAWorldManager::GetWorld() const
{
	if (!GEngine)
	{
		return nullptr;
	}

	// Get the first valid world (editor or game)
	for (const FWorldContext& Context : GEngine->GetWorldContexts())
	{
		if (Context.WorldType == EWorldType::Game || 
			Context.WorldType == EWorldType::PIE || 
			Context.WorldType == EWorldType::Editor)
		{
			UWorld* World = Context.World();
			if (World && World->IsValidLowLevel())
			{
				return World;
			}
		}
	}
	
	return nullptr;
}

bool FROAWorldManager::SetPhysicsParameters(const FString& RobotId, const FROAVector3D& Gravity,
	float MassScale, float Damping, float Friction)
{
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	RobotActor->SetPhysicsParameters(Gravity.ToFVector(), MassScale, Damping, Friction);
	return true;
}

bool FROAWorldManager::EnableCollision(const FString& RobotId, bool bEnabled)
{
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	RobotActor->SetCollisionEnabled(bEnabled);
	return true;
}

bool FROAWorldManager::GetCollisionStatus(const FString& RobotId, bool& OutIsColliding, int32& OutCollisionCount)
{
	AROARobotActor* RobotActor = GetRobotActor(RobotId);
	if (!RobotActor)
	{
		return false;
	}

	OutIsColliding = RobotActor->IsColliding();
	OutCollisionCount = RobotActor->GetCollisionCount();
	return true;
}

TSubclassOf<AROARobotActor> FROAWorldManager::GetRobotClass(const FString& RobotType)
{
	// For now, return base robot actor class
	// TODO: In future, load specific robot blueprints based on type
	// e.g., different classes for ur3, ur5, ur10, etc.
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Getting robot class for type '%s'"), *RobotType);
	
	// Return base class - robot type will be set during initialization
	return AROARobotActor::StaticClass();
}

bool FROAWorldManager::LoadRobotConfiguration(const FString& RobotType, const FString& UrdfPath)
{
	// TODO: Parse URDF file and load robot configuration
	// This will be implemented when integrating with FTI component
	
	UE_LOG(LogTemp, Log, TEXT("ROA World Manager: Loading configuration for robot type '%s' from '%s'"),
		*RobotType, *UrdfPath);
	
	return false;
}
