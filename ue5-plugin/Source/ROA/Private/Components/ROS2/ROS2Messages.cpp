// Copyright ROA Development Team. All Rights Reserved.

#include "Components/ROS2/ROS2Messages.h"
#include "Serialization/BufferArchive.h"

// ============================================================================
// UROS2JointStateMessage
// ============================================================================

TArray<uint8> UROS2JointStateMessage::SerializeToBytes() const
{
	TArray<uint8> Data;
	FBufferArchive Archive;

	// TODO: Implement proper ROS2 serialization when rclcpp is integrated
	// Will use FastCDR or ROS2 serialization utilities
	
	// Stub: Simple serialization for testing
	int32 NumJoints = JointNames.Num();
	Archive << NumJoints;
	
	for (const FString& Name : JointNames)
	{
		Archive << const_cast<FString&>(Name);
	}
	
	for (float Pos : Positions)
	{
		Archive << Pos;
	}
	
	for (float Vel : Velocities)
	{
		Archive << Vel;
	}
	
	for (float Eff : Efforts)
	{
		Archive << Eff;
	}

	Data = MoveTemp(Archive);
	return Data;
}

// ============================================================================
// UROS2TwistMessage
// ============================================================================

TArray<uint8> UROS2TwistMessage::SerializeToBytes() const
{
	TArray<uint8> Data;
	FBufferArchive Archive;

	// Stub: Simple serialization
	Archive << const_cast<FVector&>(Linear);
	Archive << const_cast<FVector&>(Angular);

	Data = MoveTemp(Archive);
	return Data;
}

// ============================================================================
// UROS2OdometryMessage
// ============================================================================

TArray<uint8> UROS2OdometryMessage::SerializeToBytes() const
{
	TArray<uint8> Data;
	FBufferArchive Archive;

	// Stub: Simple serialization
	Archive << const_cast<FString&>(FrameId);
	Archive << const_cast<FString&>(ChildFrameId);
	Archive << const_cast<FVector&>(Position);
	Archive << const_cast<FVector4&>(Orientation);
	Archive << const_cast<FVector&>(LinearVelocity);
	Archive << const_cast<FVector&>(AngularVelocity);

	Data = MoveTemp(Archive);
	return Data;
}

// ============================================================================
// UROS2TransformMessage
// ============================================================================

TArray<uint8> UROS2TransformMessage::SerializeToBytes() const
{
	TArray<uint8> Data;
	FBufferArchive Archive;

	// Stub: Simple serialization
	Archive << const_cast<FVector&>(Translation);
	Archive << const_cast<FVector4&>(Rotation);

	Data = MoveTemp(Archive);
	return Data;
}

// ============================================================================
// UROS2ImageMessage
// ============================================================================

TArray<uint8> UROS2ImageMessage::SerializeToBytes() const
{
	TArray<uint8> SerializedData;
	FBufferArchive Archive;

	// Stub: Simple serialization
	Archive << const_cast<int32&>(Width);
	Archive << const_cast<int32&>(Height);
	Archive << const_cast<FString&>(Encoding);
	
	SerializedData.Append(Archive.GetData(), Archive.Num());
	
	return SerializedData;
}

// ============================================================================
// UROS2ImuMessage
// ============================================================================

TArray<uint8> UROS2ImuMessage::SerializeToBytes() const
{
	TArray<uint8> Data;
	FBufferArchive Archive;

	// Stub: Simple serialization
	Archive << const_cast<FVector4&>(Orientation);
	Archive << const_cast<FVector&>(AngularVelocity);
	Archive << const_cast<FVector&>(LinearAcceleration);

	Data = MoveTemp(Archive);
	return Data;
}
