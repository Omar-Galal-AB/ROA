// Copyright ROA Development Team. All Rights Reserved.
// ROABlueprintUtils.h - Blueprint component manipulation utilities
// Exposes C++ functions to Python for setting PhysicsConstraint component names
// v7.18: Added runtime constraint control functions for ROC integration

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Engine/Blueprint.h"
#include "GameFramework/Actor.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"
#include "ROABlueprintUtils.generated.h"

/**
 * ROA Blueprint Utilities
 * 
 * This class provides functions for programmatically modifying Blueprint components
 * in ways that persist after save. Specifically designed to solve the constraint
 * component_name1/2 persistence problem that Python cannot handle.
 * 
 * Usage from Python:
 *   import unreal
 *   unreal.ROABlueprintUtils.set_constraint_component_names(
 *       blueprint, "Constraint_shoulder_pan_joint", "base_link", "shoulder_link"
 *   )
 */
UCLASS()
class ROA_API UROABlueprintUtils : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// =========================================================================
	// CONSTRAINT COMPONENT NAME FUNCTIONS
	// =========================================================================

	/**
	 * Set the component_name1 and component_name2 on a PhysicsConstraintComponent in a Blueprint.
	 * This uses proper Blueprint modification channels to ensure persistence.
	 * 
	 * @param Blueprint The Blueprint asset containing the constraint
	 * @param ConstraintComponentName Name of the constraint component (e.g., "Constraint_shoulder_pan_joint")
	 * @param ComponentName1 Name of the first component to constrain (parent)
	 * @param ComponentName2 Name of the second component to constrain (child)
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint", 
		meta = (DisplayName = "Set Constraint Component Names", Keywords = "ROA Physics Constraint Blueprint"))
	static bool SetConstraintComponentNames(
		UBlueprint* Blueprint,
		const FString& ConstraintComponentName,
		const FName& ComponentName1,
		const FName& ComponentName2);

	/**
	 * Set constraint component names on ALL PhysicsConstraintComponents in a Blueprint
	 * based on a mapping of constraint name -> (parent, child) pairs.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintMapping Map of ConstraintName -> Pair(ComponentName1, ComponentName2)
	 * @return Number of constraints successfully configured
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Set All Constraint Component Names", Keywords = "ROA Physics Constraint Blueprint"))
	static int32 SetAllConstraintComponentNames(
		UBlueprint* Blueprint,
		const TMap<FString, FString>& ParentChildMapping);

	// =========================================================================
	// BLUEPRINT COMPONENT ACCESS FUNCTIONS
	// =========================================================================

	/**
	 * Get all PhysicsConstraintComponents from a Blueprint's SimpleConstructionScript.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @return Array of constraint components (as their ComponentTemplate objects)
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Get Blueprint Constraints", Keywords = "ROA Physics Constraint Blueprint"))
	static TArray<UPhysicsConstraintComponent*> GetBlueprintConstraints(UBlueprint* Blueprint);

	/**
	 * Set the position of a PhysicsConstraintComponent in a Blueprint.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintComponentName Name of the constraint component
	 * @param Position The world position for the constraint
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Set Constraint Position", Keywords = "ROA Physics Constraint Position"))
	static bool SetConstraintPosition(
		UBlueprint* Blueprint,
		const FString& ConstraintComponentName,
		const FVector& Position);

	/**
	 * Set positions for ALL PhysicsConstraintComponents in a Blueprint.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param PositionMapping Map of ConstraintName -> Position (X,Y,Z as "X|Y|Z" string)
	 * @return Number of constraints positioned
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Set All Constraint Positions", Keywords = "ROA Physics Constraint Position"))
	static int32 SetAllConstraintPositions(
		UBlueprint* Blueprint,
		const TMap<FString, FString>& PositionMapping);

	/**
	 * Auto-position constraints based on mesh geometry.
	 * Finds where the child mesh is closest to the parent mesh (attachment point).
	 * Works with USD-baked meshes where geometry contains world positions.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintParentChildMapping Map of ConstraintName -> "ParentMesh|ChildMesh"
	 * @return Number of constraints positioned
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Auto Position Constraints From Mesh", Keywords = "ROA Physics Constraint Position Mesh"))
	static int32 AutoPositionConstraintsFromMesh(
		UBlueprint* Blueprint,
		const TMap<FString, FString>& ConstraintParentChildMapping);

	/**
	 * Find the attachment point between two meshes.
	 * Returns the point on the child mesh closest to the parent mesh.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ParentMeshName Name of the parent mesh component
	 * @param ChildMeshName Name of the child mesh component
	 * @return Attachment point (edge of child mesh closest to parent)
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Get Mesh Attachment Point", Keywords = "ROA Mesh Attachment Joint"))
	static FVector GetMeshAttachmentPoint(UBlueprint* Blueprint, const FString& ParentMeshName, const FString& ChildMeshName);

	/**
	 * Get the bounds/origin of a mesh component in a Blueprint.
	 * For USD-baked meshes, this returns where the mesh geometry actually is.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param MeshComponentName Name of the mesh component
	 * @return Bounds origin (center) of the mesh, or zero vector if not found
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Get Mesh Component Origin", Keywords = "ROA Mesh Bounds Origin"))
	static FVector GetMeshComponentOrigin(UBlueprint* Blueprint, const FString& MeshComponentName);

	/**
	 * Get all component names in a Blueprint (useful for validation).
	 * 
	 * @param Blueprint The Blueprint asset
	 * @return Array of component names
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Get Blueprint Component Names", Keywords = "ROA Blueprint Component"))
	static TArray<FString> GetBlueprintComponentNames(UBlueprint* Blueprint);

	/**
	 * Compile and mark a Blueprint as modified (ensures changes persist).
	 * 
	 * @param Blueprint The Blueprint asset to compile
	 * @return True if compilation successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Compile Blueprint", Keywords = "ROA Blueprint Compile"))
	static bool CompileAndMarkModified(UBlueprint* Blueprint);

	// =========================================================================
	// HELPER FUNCTIONS
	// =========================================================================

	/**
	 * Find a component in a Blueprint's SCS by name.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ComponentName Name to search for
	 * @return The component template, or nullptr if not found
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Find Blueprint Component", Keywords = "ROA Blueprint Component"))
	static UActorComponent* FindBlueprintComponent(UBlueprint* Blueprint, const FString& ComponentName);

	// =========================================================================
	// PHYSICS CONFIGURATION FUNCTIONS (v7.0)
	// =========================================================================

	/**
	 * Configure physics on a PhysicsConstraintComponent for robot joints.
	 * Sets angular motion (locked/limited/free), limits, and drive settings.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintName Name of the constraint component
	 * @param JointType "fixed", "revolute", "continuous", or "prismatic"
	 * @param AxisX Rotation axis X component (0 or 1)
	 * @param AxisY Rotation axis Y component (0 or 1)
	 * @param AxisZ Rotation axis Z component (0 or 1)
	 * @param LimitLower Lower limit in radians (for revolute)
	 * @param LimitUpper Upper limit in radians (for revolute)
	 * @param MaxVelocity Maximum angular velocity in rad/s
	 * @param MaxEffort Maximum torque in N·m
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Configure Constraint Physics", Keywords = "ROA Physics Constraint Joint"))
	static bool ConfigureConstraintPhysics(
		UBlueprint* Blueprint,
		const FString& ConstraintName,
		const FString& JointType,
		float AxisX,
		float AxisY,
		float AxisZ,
		float LimitLower,
		float LimitUpper,
		float MaxVelocity,
		float MaxEffort);

	/**
	 * Configure physics on ALL constraints using joint data.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintConfigMapping Map of ConstraintName -> "JointType|AxisX,AxisY,AxisZ|Lower,Upper|Velocity,Effort"
	 * @return Number of constraints configured
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Configure All Constraint Physics", Keywords = "ROA Physics Constraint Joint"))
	static int32 ConfigureAllConstraintPhysics(
		UBlueprint* Blueprint,
		const TMap<FString, FString>& ConstraintConfigMapping);

	/**
	 * Enable physics simulation on a StaticMeshComponent in a Blueprint.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param MeshName Name of the mesh component
	 * @param bEnablePhysics Whether to enable physics simulation
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Enable Mesh Physics", Keywords = "ROA Physics Mesh Simulate"))
	static bool EnableMeshPhysics(
		UBlueprint* Blueprint,
		const FString& MeshName,
		bool bEnablePhysics);

	/**
	 * Enable physics on ALL mesh components in a Blueprint.
	 * Base components (base_link, base, base_link_inertia) are kept static.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param BaseLinkNames Array of names that should remain static (no physics)
	 * @return Number of meshes configured
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Enable All Mesh Physics", Keywords = "ROA Physics Mesh Simulate"))
	static int32 EnableAllMeshPhysics(
		UBlueprint* Blueprint,
		const TArray<FString>& BaseLinkNames);

	/**
	 * Set the rotation of a constraint based on mesh geometry analysis.
	 * Analyzes where the child mesh extends from the joint position and
	 * orients the constraint's twist axis along the expansion direction.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintName Name of the constraint component
	 * @param ParentMeshName Name of the parent mesh component
	 * @param ChildMeshName Name of the child mesh component
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Set Constraint Rotation From Geometry", Keywords = "ROA Physics Constraint Rotation"))
	static bool SetConstraintRotationFromGeometry(
		UBlueprint* Blueprint,
		const FString& ConstraintName,
		const FString& ParentMeshName,
		const FString& ChildMeshName);

	/**
	 * Auto-orient ALL constraints based on mesh geometry.
	 * Uses the expansion direction (joint -> child center) to determine rotation.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintParentChildMapping Map of ConstraintName -> "ParentMesh|ChildMesh"
	 * @return Number of constraints rotated
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Auto Rotate All Constraints", Keywords = "ROA Physics Constraint Rotation"))
	static int32 AutoRotateAllConstraints(
		UBlueprint* Blueprint,
		const TMap<FString, FString>& ConstraintParentChildMapping);

	// =========================================================================
	// v7.16: CREATE CONSTRAINTS WITH ROTATION (like assemble_robot's spawn approach)
	// =========================================================================

	/**
	 * Create a PhysicsConstraintComponent in a Blueprint with position, rotation, and physics already set.
	 * This mimics how assemble_robot spawns actors with rotation at creation time.
	 * 
	 * Unlike setting rotation after creation (which doesn't persist), this creates the component
	 * with all properties correctly initialized in the SCS node template.
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ConstraintName Name for the new constraint (e.g., "Constraint_shoulder_pan_joint")
	 * @param ParentComponentName Name of the component to attach to (usually root), empty for default
	 * @param Position World position for the constraint
	 * @param Rotation World rotation for the constraint (aligns twist axis with URDF axis)
	 * @param ComponentName1 First component to constrain (parent link)
	 * @param ComponentName2 Second component to constrain (child link)
	 * @param JointType "fixed", "revolute", "continuous", or "prismatic"
	 * @param AxisX URDF axis X component
	 * @param AxisY URDF axis Y component (already converted for UE5 Y-flip)
	 * @param AxisZ URDF axis Z component
	 * @param LimitLower Lower limit in radians
	 * @param LimitUpper Upper limit in radians
	 * @param MaxVelocity Maximum velocity in rad/s
	 * @param MaxEffort Maximum torque in N·m
	 * @return True if constraint was created successfully
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Create Constraint In Blueprint", Keywords = "ROA Physics Constraint Create Rotation"))
	static bool CreateConstraintInBlueprint(
		UBlueprint* Blueprint,
		const FString& ConstraintName,
		const FString& ParentComponentName,
		const FVector& Position,
		const FRotator& Rotation,
		const FString& ComponentName1,
		const FString& ComponentName2,
		const FString& JointType,
		float AxisX,
		float AxisY,
		float AxisZ,
		float LimitLower,
		float LimitUpper,
		float MaxVelocity,
		float MaxEffort);

	/**
	 * Create ALL constraints in a Blueprint from an array of constraint data strings.
	 * Each string contains all info needed to create one constraint.
	 * 
	 * Format: "Name|PosX,PosY,PosZ|RotP,RotY,RotR|Comp1|Comp2|Type|AxisX,AxisY,AxisZ|Lower,Upper|Vel,Effort"
	 * 
	 * @param Blueprint The Blueprint asset
	 * @param ParentComponentName Name of the component to attach all constraints to
	 * @param ConstraintDataArray Array of constraint data strings
	 * @return Number of constraints created
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Blueprint",
		meta = (DisplayName = "Create All Constraints In Blueprint", Keywords = "ROA Physics Constraint Create Batch"))
	static int32 CreateAllConstraintsInBlueprint(
		UBlueprint* Blueprint,
		const FString& ParentComponentName,
		const TArray<FString>& ConstraintDataArray);

	// =========================================================================
	// v7.18: RUNTIME CONSTRAINT CONTROL (for ROC integration)
	// These functions work on SPAWNED ACTORS at runtime, not Blueprints.
	// =========================================================================

	/**
	 * Set the angular orientation target for a constraint (position control).
	 * This drives the joint to the specified angle using the angular drive.
	 * 
	 * @param Actor The spawned actor containing the constraint
	 * @param ConstraintName Name of the PhysicsConstraintComponent
	 * @param TargetAngle Target angle in radians
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Set Constraint Target Angle", Keywords = "ROA Physics Constraint Runtime Joint Angle"))
	static bool SetConstraintTargetAngle(
		AActor* Actor,
		const FString& ConstraintName,
		float TargetAngle);

	/**
	 * Set target angles for ALL constraints on an actor.
	 * Constraints are matched by name in the order of JointNames array.
	 * 
	 * @param Actor The spawned actor
	 * @param JointNames Array of constraint/joint names
	 * @param TargetAngles Array of target angles in radians (same order as JointNames)
	 * @return Number of joints successfully set
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Set All Constraint Target Angles", Keywords = "ROA Physics Constraint Runtime Joint Angles"))
	static int32 SetAllConstraintTargetAngles(
		AActor* Actor,
		const TArray<FString>& JointNames,
		const TArray<float>& TargetAngles);

	/**
	 * Get the current angle of a constraint.
	 * Returns the twist angle for revolute joints.
	 * 
	 * @param Actor The spawned actor containing the constraint
	 * @param ConstraintName Name of the PhysicsConstraintComponent
	 * @param OutAngle Output: current angle in radians
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Get Constraint Current Angle", Keywords = "ROA Physics Constraint Runtime Joint Angle Read"))
	static bool GetConstraintCurrentAngle(
		AActor* Actor,
		const FString& ConstraintName,
		float& OutAngle);

	/**
	 * Get current angles for ALL constraints on an actor.
	 * 
	 * @param Actor The spawned actor
	 * @param JointNames Array of constraint/joint names to query
	 * @return Array of current angles in radians (same order as JointNames)
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Get All Constraint Current Angles", Keywords = "ROA Physics Constraint Runtime Joint Angles Read"))
	static TArray<float> GetAllConstraintCurrentAngles(
		AActor* Actor,
		const TArray<FString>& JointNames);

	/**
	 * Set the angular velocity target for a constraint (velocity control).
	 * 
	 * @param Actor The spawned actor containing the constraint
	 * @param ConstraintName Name of the PhysicsConstraintComponent
	 * @param TargetVelocity Target angular velocity in radians/second
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Set Constraint Target Velocity", Keywords = "ROA Physics Constraint Runtime Joint Velocity"))
	static bool SetConstraintTargetVelocity(
		AActor* Actor,
		const FString& ConstraintName,
		float TargetVelocity);

	/**
	 * Set velocity targets for ALL constraints on an actor.
	 * 
	 * @param Actor The spawned actor
	 * @param JointNames Array of constraint/joint names
	 * @param TargetVelocities Array of target velocities in radians/second
	 * @return Number of joints successfully set
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Set All Constraint Target Velocities", Keywords = "ROA Physics Constraint Runtime Joint Velocities"))
	static int32 SetAllConstraintTargetVelocities(
		AActor* Actor,
		const TArray<FString>& JointNames,
		const TArray<float>& TargetVelocities);

	/**
	 * Get all PhysicsConstraintComponent names on a spawned actor.
	 * Useful for discovering available joints on a robot.
	 * 
	 * @param Actor The spawned actor
	 * @return Array of constraint component names
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Get Actor Constraint Names", Keywords = "ROA Physics Constraint Runtime List"))
	static TArray<FString> GetActorConstraintNames(AActor* Actor);

	/**
	 * Get all PhysicsConstraintComponents on a spawned actor.
	 * Returns the actual component pointers for advanced usage.
	 * 
	 * @param Actor The spawned actor
	 * @return Array of PhysicsConstraintComponent pointers
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Get Actor Constraints", Keywords = "ROA Physics Constraint Runtime List"))
	static TArray<UPhysicsConstraintComponent*> GetActorConstraints(AActor* Actor);

	/**
	 * Emergency stop: set all constraint velocities to zero and targets to current position.
	 * 
	 * @param Actor The spawned actor
	 * @return True if any constraints were stopped
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA|Runtime",
		meta = (DisplayName = "Emergency Stop Actor Joints", Keywords = "ROA Physics Constraint Runtime Stop Emergency"))
	static bool EmergencyStopActorJoints(AActor* Actor);

private:
	/** Internal helper to get SCS nodes */
	static class USCS_Node* FindSCSNode(UBlueprint* Blueprint, const FString& ComponentName);

	/** Internal helper to find constraint component on spawned actor by name */
	static UPhysicsConstraintComponent* FindConstraintOnActor(AActor* Actor, const FString& ConstraintName);
};
