// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Misc/FileHelper.h"
#include "XmlParser.h"

/**
 * URDF Link Description
 */
struct FROAURDFLink
{
	FString Name;
	FVector VisualOrigin;
	FRotator VisualRotation;
	FString MeshPath;
	FVector CollisionOrigin;
	FRotator CollisionRotation;
	FString CollisionMeshPath;
	float Mass;
	FVector Inertia;
};

/**
 * URDF Joint Description
 */
struct FROAURDFJoint
{
	FString Name;
	FString Type; // revolute, prismatic, fixed, continuous
	FString ParentLink;
	FString ChildLink;
	FVector Origin;
	FRotator Rotation;
	FVector Axis;
	float LowerLimit;
	float UpperLimit;
	float EffortLimit;
	float VelocityLimit;
};

/**
 * Complete Robot Description from URDF
 */
struct FROARobotDescription
{
	FString RobotName;
	TArray<FROAURDFLink> Links;
	TArray<FROAURDFJoint> Joints;
	FString BaseDirectory; // For resolving relative mesh paths
	
	// Helper methods
	bool IsValid() const { return !RobotName.IsEmpty() && Links.Num() > 0; }
	FROAURDFLink* FindLink(const FString& LinkName);
	FROAURDFJoint* FindJoint(const FString& JointName);
};

/**
 * URDF Parser - Parses Universal Robot Description Format files
 */
class ROA_API FROAURDFParser
{
public:
	/**
	 * Parse URDF file and return robot description
	 * @param URDFFilePath - Full path to .urdf file
	 * @param OutDescription - Parsed robot description
	 * @return true if parsing succeeded
	 */
	static bool ParseURDF(const FString& URDFFilePath, FROARobotDescription& OutDescription);
	
	/**
	 * Parse URDF from XML content string
	 * @param URDFContent - XML content as string
	 * @param BaseDirectory - Base directory for resolving mesh paths
	 * @param OutDescription - Parsed robot description
	 * @return true if parsing succeeded
	 */
	static bool ParseURDFContent(const FString& URDFContent, const FString& BaseDirectory, FROARobotDescription& OutDescription);

private:
	// XML parsing helpers
	static bool ParseRobot(FXmlNode* RobotNode, FROARobotDescription& OutDescription);
	static bool ParseLink(FXmlNode* LinkNode, FROAURDFLink& OutLink);
	static bool ParseJoint(FXmlNode* JointNode, FROAURDFJoint& OutJoint);
	static bool ParseVisual(FXmlNode* VisualNode, FROAURDFLink& OutLink);
	static bool ParseCollision(FXmlNode* CollisionNode, FROAURDFLink& OutLink);
	static bool ParseGeometry(FXmlNode* GeometryNode, FString& OutMeshPath);
	static bool ParseOrigin(FXmlNode* OriginNode, FVector& OutPosition, FRotator& OutRotation);
	static bool ParseAxis(FXmlNode* AxisNode, FVector& OutAxis);
	static bool ParseLimit(FXmlNode* LimitNode, float& OutLower, float& OutUpper, float& OutEffort, float& OutVelocity);
	
	// Utility functions
	static FString ResolvePackagePath(const FString& URIPath, const FString& BaseDirectory);
	static FVector StringToVector(const FString& VectorString);
	static FRotator RPYToRotator(const FString& RPYString);
};
