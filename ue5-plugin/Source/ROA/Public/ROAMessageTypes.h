// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "HAL/PlatformTime.h"

/**
 * Message types for ROA communication protocol
 */
enum class EROAMessageType : uint8
{
	REQUEST,
	RESPONSE,
	EVENT,
	ERROR
};

/**
 * Error codes for ROA protocol
 */
enum class EROAErrorCode : uint8
{
	ERR_NONE,
	ERR_CONNECTION_FAILED,
	ERR_ROBOT_NOT_FOUND,
	ERR_INVALID_COMMAND,
	ERR_INVALID_PAYLOAD,
	ERR_SPAWN_FAILED,
	ERR_PHYSICS_ERROR,
	ERR_FILE_NOT_FOUND,
	ERR_WIDGET_ERROR,
	ERR_COLLISION,
	ERR_JOINT_LIMIT,
	ERR_TIMEOUT
};

/**
 * Base structure for ROA messages
 */
struct FROAMessage
{
	FString MessageId;
	double Timestamp;
	EROAMessageType MessageType;
	FString Command;
	TSharedPtr<FJsonObject> Payload;

	FROAMessage()
		: Timestamp(0.0)
		, MessageType(EROAMessageType::REQUEST)
	{
		// Generate unique message ID
		MessageId = FGuid::NewGuid().ToString();
		// Get current timestamp
		Timestamp = FPlatformTime::Seconds();
	}

	/**
	 * Convert message to JSON string
	 */
	FString ToJsonString() const;

	/**
	 * Parse message from JSON string
	 */
	static bool FromJsonString(const FString& JsonString, FROAMessage& OutMessage);
};

/**
 * Vector3D for positions, rotations, etc.
 */
struct FROAVector3D
{
	double X;
	double Y;
	double Z;

	FROAVector3D() : X(0.0), Y(0.0), Z(0.0) {}
	FROAVector3D(double InX, double InY, double InZ) : X(InX), Y(InY), Z(InZ) {}

	// Convert to UE5 vector
	FVector ToFVector() const { return FVector(X, Y, Z); }

	// Convert from UE5 vector
	static FROAVector3D FromFVector(const FVector& Vec)
	{
		return FROAVector3D(Vec.X, Vec.Y, Vec.Z);
	}

	// Serialize to JSON
	TSharedPtr<FJsonObject> ToJson() const;
	
	// Deserialize from JSON
	static FROAVector3D FromJson(const TSharedPtr<FJsonObject>& JsonObj);
};

/**
 * Rotation (Roll, Pitch, Yaw in radians)
 */
struct FROARotation
{
	double Roll;
	double Pitch;
	double Yaw;

	FROARotation() : Roll(0.0), Pitch(0.0), Yaw(0.0) {}
	FROARotation(double InRoll, double InPitch, double InYaw) 
		: Roll(InRoll), Pitch(InPitch), Yaw(InYaw) {}

	// Convert to UE5 rotator
	FRotator ToFRotator() const 
	{ 
		return FRotator(FMath::RadiansToDegrees(Pitch), 
		          FMath::RadiansToDegrees(Yaw), 
		          FMath::RadiansToDegrees(Roll)); 
	}

	// Convert from UE5 rotator
	static FROARotation FromFRotator(const FRotator& Rot)
	{
		return FROARotation(FMath::DegreesToRadians(Rot.Roll),
		            FMath::DegreesToRadians(Rot.Pitch),
		       FMath::DegreesToRadians(Rot.Yaw));
	}

	// Serialize to JSON
	TSharedPtr<FJsonObject> ToJson() const;
	
	// Deserialize from JSON
	static FROARotation FromJson(const TSharedPtr<FJsonObject>& JsonObj);
};

/**
 * Robot spawn request data
 */
struct FROASpawnRobotRequest
{
	FString RobotId;
	FString RobotType;
	FString UrdfPath;
	FROAVector3D SpawnLocation;
	FROARotation SpawnRotation;
	TArray<float> InitialJointStates;

	// Parse from JSON payload
	static bool FromJson(const TSharedPtr<FJsonObject>& JsonObj, FROASpawnRobotRequest& OutRequest);
};

/**
 * Robot state data
 */
struct FROARobotState
{
	FString RobotId;
	FROAVector3D Position;
	FROARotation Rotation;
	TArray<float> JointPositions;
	TArray<float> JointVelocities;
	TArray<float> JointEfforts;
	FROAVector3D EndEffectorPosition;
	FROARotation EndEffectorRotation;

	// Serialize to JSON
	TSharedPtr<FJsonObject> ToJson() const;
};

/**
 * Joint command data
 */
struct FROAJointCommand
{
	FString RobotId;
	TArray<float> JointPositions;
	float Duration;

	// Parse from JSON payload
	static bool FromJson(const TSharedPtr<FJsonObject>& JsonObj, FROAJointCommand& OutCommand);
};

/**
 * Collision event data
 */
struct FROACollisionEvent
{
	FString RobotId;
	FROAVector3D CollisionPoint;
	FROAVector3D CollisionNormal;
	float CollisionForce;
	FString OtherObject;

	// Serialize to JSON
	TSharedPtr<FJsonObject> ToJson() const;
};

/**
 * Utility class for message type conversion
 */
class FROAMessageUtils
{
public:
	static FString MessageTypeToString(EROAMessageType Type);
	static EROAMessageType StringToMessageType(const FString& TypeString);
	
	static FString ErrorCodeToString(EROAErrorCode Code);
	static EROAErrorCode StringToErrorCode(const FString& CodeString);

	/**
	 * Create success response
	 */
	static FROAMessage CreateSuccessResponse(const FString& Command, const TSharedPtr<FJsonObject>& Payload);

	/**
	 * Create error response
	 */
	static FROAMessage CreateErrorResponse(const FString& Command, EROAErrorCode ErrorCode, const FString& ErrorMessage);

	/**
	 * Create event message
	 */
	static FROAMessage CreateEvent(const FString& EventName, const TSharedPtr<FJsonObject>& Payload);
};
