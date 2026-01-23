// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "ROAMessageTypes.h"
#include "GameFramework/Actor.h"

// Forward declarations
class AROARobotActor;

/**
 * Manages all robots and actors in the UE5 world for ROA
 * Handles spawning, despawning, and state management
 */
class FROAWorldManager
{
public:
	FROAWorldManager();
	~FROAWorldManager();

	/**
	 * Spawn a robot in the world
	 * @param Request - Spawn request data
	 * @param OutErrorMessage - Error message if spawn fails
	 * @return True if successful
	 */
	bool SpawnRobot(const FROASpawnRobotRequest& Request, FString& OutErrorMessage);

	/**
	 * Despawn a robot from the world
	 * @param RobotId - ID of robot to despawn
	 * @return True if successful
	 */
	bool DespawnRobot(const FString& RobotId);

	/**
	 * Get robot state
	 * @param RobotId - ID of robot
	 * @param OutState - Output state data
	 * @return True if robot found
	 */
	bool GetRobotState(const FString& RobotId, FROARobotState& OutState);

	/**
	 * Move robot to target position/rotation
	 * @param RobotId - ID of robot
	 * @param TargetPosition - Target position
	 * @param TargetRotation - Target rotation
	 * @return True if successful
	 */
	bool MoveRobot(const FString& RobotId, const FROAVector3D& TargetPosition, const FROARotation& TargetRotation);

	/**
	 * Set joint positions
	 * @param Command - Joint command data
	 * @return True if successful
	 */
	bool SetJointPositions(const FROAJointCommand& Command);

	/**
	 * Set joint velocities
	 * @param RobotId - ID of robot
	 * @param Velocities - Joint velocities
	 * @return True if successful
	 */
	bool SetJointVelocities(const FString& RobotId, const TArray<float>& Velocities);

	/**
	 * Emergency stop for robot
	 * @param RobotId - ID of robot
	 * @return True if successful
	 */
	bool EmergencyStop(const FString& RobotId);

	/**
	 * Get list of all active robots
	 * @return Array of robot IDs
	 */
	TArray<FString> GetAllRobotIds() const;

	/**
	 * Check if robot exists
	 * @param RobotId - ID of robot
	 * @return True if robot exists
	 */
	bool RobotExists(const FString& RobotId) const;

	/**
	 * Get robot actor by ID
	 * @param RobotId - ID of robot
	 * @return Robot actor pointer (nullptr if not found)
	 */
	AROARobotActor* GetRobotActor(const FString& RobotId) const;

	/**
	 * Clean up all robots
	 */
	void CleanupAllRobots();

	/**
	 * Add obstacle to scene
	 * @param ObstacleId - Unique obstacle ID
	 * @param Shape - Shape type (box, sphere, cylinder)
	 * @param Dimensions - Dimensions of obstacle
	 * @param Position - Position in world
	 * @param Rotation - Rotation
	 * @return True if successful
	 */
	bool AddObstacle(const FString& ObstacleId, const FString& Shape, 
	 const FROAVector3D& Dimensions, const FROAVector3D& Position, 
	      const FROARotation& Rotation);

	/**
	 * Remove obstacle from scene
	 * @param ObstacleId - ID of obstacle
	 * @return True if successful
	 */
	bool RemoveObstacle(const FString& ObstacleId);

	/**
	 * Clear entire scene (remove all robots and obstacles)
	 */
	void ClearScene();

	/**
	 * Get world pointer (safely)
	 * @return World pointer or nullptr
	 */
	UWorld* GetWorld() const;

	/**
	 * Set physics parameters for robot
	 * @param RobotId - ID of robot
	 * @param Gravity - Gravity vector
	 * @param MassScale - Mass multiplier
	 * @param Damping - Damping factor
	 * @param Friction - Friction coefficient
	 * @return True if successful
	 */
	bool SetPhysicsParameters(const FString& RobotId, const FROAVector3D& Gravity,
	    float MassScale, float Damping, float Friction);

	/**
	 * Enable/disable collision for robot
	 * @param RobotId - ID of robot
	 * @param bEnabled - Enable or disable
	 * @return True if successful
	 */
	bool EnableCollision(const FString& RobotId, bool bEnabled);

	/**
	 * Get collision status for robot
	 * @param RobotId - ID of robot
	 * @param OutIsColliding - Output: is currently colliding
	 * @param OutCollisionCount - Output: number of collisions
	 * @return True if successful
	 */
	bool GetCollisionStatus(const FString& RobotId, bool& OutIsColliding, int32& OutCollisionCount);

private:
	/** Map of robot ID to robot actor */
	TMap<FString, AROARobotActor*> RobotActors;

	/** Map of obstacle ID to obstacle actor */
	TMap<FString, AActor*> ObstacleActors;

	/** Critical section for thread safety */
	mutable FCriticalSection RobotMapMutex;

	/** Critical section for obstacles */
	mutable FCriticalSection ObstacleMapMutex;

	/**
	 * Get robot type class based on robot type string
	 * @param RobotType - Type string (e.g., "ur5e")
	 * @return Robot class or nullptr
	 */
	TSubclassOf<AROARobotActor> GetRobotClass(const FString& RobotType);

	/**
	 * Load robot mesh and configuration
	 * @param RobotType - Type string
	 * @param UrdfPath - Path to URDF file
	 * @return True if successful
	 */
	bool LoadRobotConfiguration(const FString& RobotType, const FString& UrdfPath);
};
