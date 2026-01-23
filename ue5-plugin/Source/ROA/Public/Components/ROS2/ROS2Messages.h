// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ROS2/ROS2PublisherComponent.h"
#include "ROS2Messages.generated.h"

/**
 * ROS2 JointState Message (sensor_msgs/msg/JointState)
 * Used to publish robot joint positions, velocities, and efforts
 */
UCLASS(BlueprintType)
class ROA_API UROS2JointStateMessage : public UROS2MessageBase
{
	GENERATED_BODY()

public:
	/** Joint names */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	TArray<FString> JointNames;

	/** Joint positions (radians or meters) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	TArray<float> Positions;

	/** Joint velocities */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	TArray<float> Velocities;

	/** Joint efforts (torques or forces) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	TArray<float> Efforts;

	virtual FString GetMessageType() const override 
	{ 
		return TEXT("sensor_msgs/msg/JointState"); 
	}

	virtual TArray<uint8> SerializeToBytes() const override;
};

/**
 * ROS2 Twist Message (geometry_msgs/msg/Twist)
 * Used for velocity commands
 */
UCLASS(BlueprintType)
class ROA_API UROS2TwistMessage : public UROS2MessageBase
{
	GENERATED_BODY()

public:
	/** Linear velocity (m/s) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector Linear;

	/** Angular velocity (rad/s) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector Angular;

	virtual FString GetMessageType() const override 
	{ 
		return TEXT("geometry_msgs/msg/Twist"); 
	}

	virtual TArray<uint8> SerializeToBytes() const override;
};

/**
 * ROS2 Odometry Message (nav_msgs/msg/Odometry)
 * Used to publish robot position and velocity
 */
UCLASS(BlueprintType)
class ROA_API UROS2OdometryMessage : public UROS2MessageBase
{
	GENERATED_BODY()

public:
	/** Frame ID */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FString FrameId;

	/** Child frame ID */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FString ChildFrameId;

	/** Position */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector Position;

	/** Orientation (Quaternion as Vector4: X,Y,Z,W) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector4 Orientation;

	/** Linear velocity */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector LinearVelocity;

	/** Angular velocity */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector AngularVelocity;

	virtual FString GetMessageType() const override 
	{ 
		return TEXT("nav_msgs/msg/Odometry"); 
	}

	virtual TArray<uint8> SerializeToBytes() const override;
};

/**
 * ROS2 Transform Message (geometry_msgs/msg/Transform)
 */
UCLASS(BlueprintType)
class ROA_API UROS2TransformMessage : public UROS2MessageBase
{
	GENERATED_BODY()

public:
	/** Translation */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector Translation;

	/** Rotation (Quaternion as Vector4: X,Y,Z,W) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector4 Rotation;

	virtual FString GetMessageType() const override 
	{ 
		return TEXT("geometry_msgs/msg/Transform"); 
	}

	virtual TArray<uint8> SerializeToBytes() const override;
};

/**
 * ROS2 Image Message (sensor_msgs/msg/Image)
 * Used for camera data
 */
UCLASS(BlueprintType)
class ROA_API UROS2ImageMessage : public UROS2MessageBase
{
	GENERATED_BODY()

public:
	/** Image width */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	int32 Width;

	/** Image height */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	int32 Height;

	/** Encoding (e.g., "rgb8", "bgr8", "mono8") */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FString Encoding;

	/** Image data */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	TArray<uint8> Data;

	virtual FString GetMessageType() const override 
	{ 
		return TEXT("sensor_msgs/msg/Image"); 
	}

	virtual TArray<uint8> SerializeToBytes() const override;
};

/**
 * ROS2 IMU Message (sensor_msgs/msg/Imu)
 */
UCLASS(BlueprintType)
class ROA_API UROS2ImuMessage : public UROS2MessageBase
{
	GENERATED_BODY()

public:
	/** Orientation (Quaternion as Vector4: X,Y,Z,W) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector4 Orientation;

	/** Angular velocity (rad/s) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector AngularVelocity;

	/** Linear acceleration (m/s²) */
	UPROPERTY(BlueprintReadWrite, Category="ROS2|Message")
	FVector LinearAcceleration;

	virtual FString GetMessageType() const override 
	{ 
		return TEXT("sensor_msgs/msg/Imu"); 
	}

	virtual TArray<uint8> SerializeToBytes() const override;
};
