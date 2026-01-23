// Copyright ROA Development Team. All Rights Reserved.

#include "Components/ROS2/ROS2SubscriberComponent.h"
#include "Components/ROS2/ROS2NodeComponent.h"
#include "ROARobotActor.h"

UROS2SubscriberComponent::UROS2SubscriberComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	
	TopicName = TEXT("/robot/joint_commands");
	MessageType = TEXT("trajectory_msgs/msg/JointTrajectory");
	QueueSize = 10;
	bSubscriberReady = false;
	NativeSubscriber = nullptr;
	NodeComponent = nullptr;
	LastMessage = nullptr;
	MessageCount = 0;

	LogPrefix = TEXT("[ROS2Subscriber]");
}

void UROS2SubscriberComponent::InitializeComponent()
{
	Super::InitializeComponent();
}

void UROS2SubscriberComponent::OnAttachedToRobot()
{
	Super::OnAttachedToRobot();

	// Find ROS2 node component on same actor
	if (OwningRobot)
	{
		NodeComponent = OwningRobot->FindComponentByClass<UROS2NodeComponent>();
		
		if (!NodeComponent)
		{
			LogError(TEXT("No ROS2NodeComponent found! Subscriber requires a ROS2 node."));
			return;
		}

		if (!NodeComponent->IsNodeReady())
		{
			LogWarning(TEXT("ROS2 node not ready yet, waiting..."));
			return;
		}

		// Create subscriber
		bool bSuccess = false;
		void* NativeNode = NodeComponent->GetNativeNode();
		
		if (NativeNode)
		{
			bSuccess = CreateNativeSubscriber();
		}
		else
		{
			bSuccess = CreateFallbackSubscriber();
		}

		if (bSuccess)
		{
			bSubscriberReady = true;
			LogInfo(FString::Printf(TEXT("Subscriber created: %s (%s)"), 
				*TopicName, *MessageType));
		}
		else
		{
			LogError(TEXT("Failed to create subscriber"));
		}
	}
}

void UROS2SubscriberComponent::UninitializeComponent()
{
	LogInfo(FString::Printf(TEXT("Shutting down subscriber (received %d messages)"), MessageCount));

	// TODO: Destroy native subscriber when rclcpp is integrated
	// if (NativeSubscriber)
	// {
	//     delete static_cast<rclcpp::Subscription::SharedPtr*>(NativeSubscriber);
	//     NativeSubscriber = nullptr;
	// }

	bSubscriberReady = false;

	Super::UninitializeComponent();
}

bool UROS2SubscriberComponent::CreateNativeSubscriber()
{
	LogInfo(TEXT("Creating native DDS subscriber..."));

	// TODO: Create rclcpp::Subscription when integrated
	// Example:
	// auto node = static_cast<rclcpp::Node::SharedPtr*>(NodeComponent->GetNativeNode());
	// auto callback = [this](const MessageTypeClass::SharedPtr msg) {
	//     TArray<uint8> serialized = SerializeMessage(msg);
	//     this->HandleMessageReceived(serialized);
	// };
	// auto subscription = (*node)->create_subscription<MessageTypeClass>(
	//     TCHAR_TO_UTF8(*TopicName),
	//     QueueSize,
	//     callback
	// );
	// NativeSubscriber = new rclcpp::Subscription::SharedPtr(subscription);

	// Stub: Not implemented yet
	LogWarning(TEXT("Native subscriber creation not yet implemented (stub)"));
	return false;
}

bool UROS2SubscriberComponent::CreateFallbackSubscriber()
{
	LogInfo(TEXT("Creating TCP fallback subscriber..."));

	// Fallback mode: "subscriber" exists but receives via TCP
	// Existing ROANetworkServer handles the actual receiving
	
	LogInfo(TEXT("TCP fallback subscriber ready"));
	return true;
}

void UROS2SubscriberComponent::HandleMessageReceived(const TArray<uint8>& MessageData)
{
	if (!bComponentEnabled)
	{
		return;
	}

	MessageCount++;

	// Deserialize message
	UROS2MessageBase* Message = DeserializeMessage(MessageData);
	
	if (Message)
	{
		LastMessage = Message;
		
		// Broadcast event
		OnMessageReceived.Broadcast(Message);
		
		LogInfo(FString::Printf(TEXT("Received message #%d on %s (%d bytes)"),
			MessageCount, *TopicName, MessageData.Num()));
	}
	else
	{
		LogError(TEXT("Failed to deserialize message"));
	}
}

UROS2MessageBase* UROS2SubscriberComponent::DeserializeMessage(const TArray<uint8>& MessageData)
{
	// TODO: Implement message deserialization when rclcpp is integrated
	// Will use ROS2 serialization libraries (FastCDR)
	
	// Stub: Return nullptr
	return nullptr;
}
