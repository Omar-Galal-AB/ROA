// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ROAComponent.h"
#include "ROS2PublisherComponent.h"
#include "ROS2SubscriberComponent.generated.h"

/**
 * ROS2 Subscriber Callback Delegate
 * Called when a message is received
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnROS2MessageReceived, UROS2MessageBase*, Message);

/**
 * ROS2 Subscriber Component
 * 
 * Subscribes to ROS2 messages from a topic.
 * Requires UROS2NodeComponent on the same actor.
 * 
 * Example: Receiving joint commands, velocity commands, spawn requests
 */
UCLASS(ClassGroup=(ROA), meta=(BlueprintSpawnableComponent))
class ROA_API UROS2SubscriberComponent : public UROAComponent
{
	GENERATED_BODY()

public:
	UROS2SubscriberComponent();

	/** Component lifecycle */
	virtual void InitializeComponent() override;
	virtual void UninitializeComponent() override;
	virtual void OnAttachedToRobot() override;

	/**
	 * Message received event
	 * Bind to this in Blueprint or C++ to handle incoming messages
	 */
	UPROPERTY(BlueprintAssignable, Category="ROA|ROS2|Subscriber")
	FOnROS2MessageReceived OnMessageReceived;

	/**
	 * Check if subscriber is ready
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2|Subscriber")
	bool IsSubscriberReady() const { return bSubscriberReady; }

	/**
	 * Get topic name
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2|Subscriber")
	FString GetTopicName() const { return TopicName; }

	/**
	 * Get last received message
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2|Subscriber")
	UROS2MessageBase* GetLastMessage() const { return LastMessage; }

	/**
	 * Get message count
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2|Subscriber")
	int32 GetMessageCount() const { return MessageCount; }

public:
	/** Topic name to subscribe to */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Subscriber")
	FString TopicName;

	/** Message type (e.g., "trajectory_msgs/msg/JointTrajectory") */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Subscriber")
	FString MessageType;

	/** Queue size for subscriber */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Subscriber", meta=(ClampMin=1, ClampMax=1000))
	int32 QueueSize;

protected:
	/** Subscriber ready state */
	bool bSubscriberReady;

	/** Native ROS2 subscriber (rclcpp::Subscription::SharedPtr) */
	void* NativeSubscriber;

	/** Reference to ROS2 node component */
	UPROPERTY()
	class UROS2NodeComponent* NodeComponent;

	/** Last received message */
	UPROPERTY()
	UROS2MessageBase* LastMessage;

	/** Total messages received */
	int32 MessageCount;

	/** Create native subscriber (when rclcpp is integrated) */
	bool CreateNativeSubscriber();

	/** Create fallback subscriber (TCP mode) */
	bool CreateFallbackSubscriber();

	/**
	 * Callback when message is received
	 * Override in derived classes or bind to OnMessageReceived
	 */
	UFUNCTION()
	virtual void HandleMessageReceived(const TArray<uint8>& MessageData);

	/** Deserialize message from bytes */
	UROS2MessageBase* DeserializeMessage(const TArray<uint8>& MessageData);
};
