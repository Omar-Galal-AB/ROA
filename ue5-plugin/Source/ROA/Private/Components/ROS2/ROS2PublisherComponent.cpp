// Copyright ROA Development Team. All Rights Reserved.

#include "Components/ROS2/ROS2PublisherComponent.h"
#include "Components/ROS2/ROS2NodeComponent.h"
#include "Components/ROS2/ROS2Messages.h"
#include "Components/ROS2/ROS2Context.h"
#include "ROSBridgeClient.h"
#include "ROARobotActor.h"
#include "ROANetworkServer.h"
#include "TimerManager.h"
#include "Kismet/GameplayStatics.h"
#include "Serialization/JsonSerializer.h"

#if ROA_NATIVE_ROS2
#ifdef check
#pragma push_macro("check")
#undef check
#define ROA_CHECK_MACRO_PUSHED 1
#endif

#include <string>
#include <rcl/rcl.h>
#include <rcl/publisher.h>
#include <sensor_msgs/msg/joint_state.h>
#include <rosidl_runtime_c/string_functions.h>
#include <rosidl_runtime_c/primitives_sequence_functions.h>

#ifdef ROA_CHECK_MACRO_PUSHED
#pragma pop_macro("check")
#undef ROA_CHECK_MACRO_PUSHED
#endif
#endif // ROA_NATIVE_ROS2

// Static network server reference (legacy, kept for compatibility)
static TWeakPtr<FROANetworkServer> GNetworkServer;

void UROS2PublisherComponent::SetNetworkServer(TSharedPtr<FROANetworkServer> InServer)
{
	GNetworkServer = InServer;
}

UROS2PublisherComponent::UROS2PublisherComponent()
{
	PrimaryComponentTick.bCanEverTick = false;

	TopicName = TEXT("/robot/joint_states");
	MessageType = TEXT("sensor_msgs/msg/JointState");
	QueueSize = 10;
	PublishRateLimit = 0.0f;
	bPublisherReady = false;
	NativePublisher = nullptr;
	NodeComponent = nullptr;
	LastPublishTime = 0.0;

	LogPrefix = TEXT("[ROS2Publisher]");
}

void UROS2PublisherComponent::InitializeComponent()
{
	Super::InitializeComponent();
}

void UROS2PublisherComponent::SetNodeComponent(UROS2NodeComponent* InNodeComponent)
{
	NodeComponent = InNodeComponent;
}

void UROS2PublisherComponent::OnAttachedToRobot()
{
	Super::OnAttachedToRobot();

	if (!OwningRobot)
	{
		LogError(TEXT("No owning robot!"));
		return;
	}

	// Use node component if set, otherwise try to find it
	if (!NodeComponent)
	{
		NodeComponent = OwningRobot->FindComponentByClass<UROS2NodeComponent>();
	}

	if (!NodeComponent)
	{
		LogWarning(TEXT("No ROS2NodeComponent found - creating standalone publisher"));
	}

	// Check which mode we're in
	FROS2Context& Context = FROS2Context::Get();

	if (!Context.IsInitialized())
	{
		// Initialize context on first use
		Context.Initialize();
	}

	bool bSuccess = false;

	if (Context.IsNativeModeAvailable())
	{
		// Native mode: Create ROS2 publisher
		if (NodeComponent && NodeComponent->IsNodeReady())
		{
			bSuccess = CreateNativePublisher();
		}
		else
		{
			LogWarning(TEXT("Node not ready for native publisher"));
		}
	}
	else
	{
		// TCP mode: Use rosbridge client
		bSuccess = CreateBridgePublisher();
	}

	if (bSuccess)
	{
		bPublisherReady = true;
		LogInfo(FString::Printf(TEXT("Publisher ready: %s (%s) [%s mode]"),
			*TopicName, *MessageType,
			Context.IsNativeModeAvailable() ? TEXT("Native") : TEXT("TCP")));
	}
	else
	{
		LogError(TEXT("Failed to create publisher"));
	}
}

void UROS2PublisherComponent::UninitializeComponent()
{
	LogInfo(TEXT("Shutting down publisher"));

#if ROA_NATIVE_ROS2
	if (NativePublisher && NodeComponent)
	{
		rcl_publisher_t* publisher = static_cast<rcl_publisher_t*>(NativePublisher);
		rcl_ret_t ret = rcl_publisher_fini(publisher, static_cast<rcl_node_t*>(NodeComponent->GetNativeNode()));

		if (ret != RCL_RET_OK)
		{
			LogWarning(TEXT("rcl_publisher_fini returned error"));
		}

		delete publisher;
		NativePublisher = nullptr;
		LogInfo(TEXT("Native publisher destroyed"));
	}
#endif

	// Unadvertise from rosbridge
	FROSBridgeClient* Client = FROS2Context::Get().GetBridgeClient();
	if (Client && Client->IsConnected())
	{
		Client->Unadvertise(TopicName);
	}

	bPublisherReady = false;
	Super::UninitializeComponent();
}

bool UROS2PublisherComponent::Publish(UROS2MessageBase* Message)
{
	if (!bPublisherReady || !bComponentEnabled)
	{
		return false;
	}

	if (!Message)
	{
		LogError(TEXT("Null message"));
		return false;
	}

	// Rate limiting
	if (PublishRateLimit > 0.0f)
	{
		double CurrentTime = FPlatformTime::Seconds();
		double MinInterval = 1.0 / PublishRateLimit;

		if ((CurrentTime - LastPublishTime) < MinInterval)
		{
			return false;
		}
		LastPublishTime = CurrentTime;
	}

#if ROA_NATIVE_ROS2
	// Native mode: Publish using ROS2 C API
	if (NativePublisher && FROS2Context::Get().IsNativeModeAvailable())
	{
		return PublishNative(Message);
	}
#endif

	// TCP mode: Publish via rosbridge
	return PublishViaBridge(Message);
}

bool UROS2PublisherComponent::PublishNative(UROS2MessageBase* Message)
{
#if ROA_NATIVE_ROS2
	UROS2JointStateMessage* JointStateMsg = Cast<UROS2JointStateMessage>(Message);
	if (!JointStateMsg)
	{
		LogError(TEXT("Message is not a JointState message"));
		return false;
	}

	// Create and initialize message
	sensor_msgs__msg__JointState msg;
	sensor_msgs__msg__JointState__init(&msg);

	// Set timestamp
	int64 TimeNanos = FDateTime::UtcNow().ToUnixTimestamp() * 1000000000LL;
	msg.header.stamp.sec = static_cast<int32_t>(TimeNanos / 1000000000LL);
	msg.header.stamp.nanosec = static_cast<uint32_t>(TimeNanos % 1000000000LL);
	rosidl_runtime_c__String__assign(&msg.header.frame_id, "base_link");

	// Fill joint data
	size_t num_joints = JointStateMsg->JointNames.Num();
	rosidl_runtime_c__String__Sequence__init(&msg.name, num_joints);
	rosidl_runtime_c__double__Sequence__init(&msg.position, num_joints);
	rosidl_runtime_c__double__Sequence__init(&msg.velocity, num_joints);
	rosidl_runtime_c__double__Sequence__init(&msg.effort, num_joints);

	for (size_t i = 0; i < num_joints; ++i)
	{
		rosidl_runtime_c__String__assign(&msg.name.data[i],
			TCHAR_TO_UTF8(*JointStateMsg->JointNames[i]));
		msg.position.data[i] = JointStateMsg->Positions[i];
		msg.velocity.data[i] = i < JointStateMsg->Velocities.Num() ? JointStateMsg->Velocities[i] : 0.0;
		msg.effort.data[i] = i < JointStateMsg->Efforts.Num() ? JointStateMsg->Efforts[i] : 0.0;
	}

	// Publish
	rcl_publisher_t* publisher = static_cast<rcl_publisher_t*>(NativePublisher);
	rcl_ret_t ret = rcl_publish(publisher, &msg, nullptr);

	// Cleanup
	sensor_msgs__msg__JointState__fini(&msg);

	if (ret != RCL_RET_OK)
	{
		LogError(FString::Printf(TEXT("rcl_publish failed: %d"), ret));
		return false;
	}

	return true;
#else
	return false;
#endif
}

bool UROS2PublisherComponent::PublishViaBridge(UROS2MessageBase* Message)
{
	FROSBridgeClient* Client = FROS2Context::Get().GetBridgeClient();
	if (!Client || !Client->IsConnected())
	{
		LogWarning(TEXT("rosbridge client not connected"));
		return false;
	}

	UROS2JointStateMessage* JointStateMsg = Cast<UROS2JointStateMessage>(Message);
	if (!JointStateMsg)
	{
		LogError(TEXT("Message is not a JointState message"));
		return false;
	}

	// Build JSON message in rosbridge format
	TSharedPtr<FJsonObject> MsgObj = MakeShared<FJsonObject>();

	// Header
	TSharedPtr<FJsonObject> Header = MakeShared<FJsonObject>();
	TSharedPtr<FJsonObject> Stamp = MakeShared<FJsonObject>();
	int64 TimeNanos = FDateTime::UtcNow().ToUnixTimestamp() * 1000000000LL;
	Stamp->SetNumberField(TEXT("sec"), TimeNanos / 1000000000LL);
	Stamp->SetNumberField(TEXT("nanosec"), TimeNanos % 1000000000LL);
	Header->SetObjectField(TEXT("stamp"), Stamp);
	Header->SetStringField(TEXT("frame_id"), TEXT("base_link"));
	MsgObj->SetObjectField(TEXT("header"), Header);

	// Joint names
	TArray<TSharedPtr<FJsonValue>> NameArray;
	for (const FString& Name : JointStateMsg->JointNames)
	{
		NameArray.Add(MakeShared<FJsonValueString>(Name));
	}
	MsgObj->SetArrayField(TEXT("name"), NameArray);

	// Positions
	TArray<TSharedPtr<FJsonValue>> PosArray;
	for (float Pos : JointStateMsg->Positions)
	{
		PosArray.Add(MakeShared<FJsonValueNumber>(Pos));
	}
	MsgObj->SetArrayField(TEXT("position"), PosArray);

	// Velocities
	TArray<TSharedPtr<FJsonValue>> VelArray;
	for (float Vel : JointStateMsg->Velocities)
	{
		VelArray.Add(MakeShared<FJsonValueNumber>(Vel));
	}
	MsgObj->SetArrayField(TEXT("velocity"), VelArray);

	// Efforts
	TArray<TSharedPtr<FJsonValue>> EffArray;
	for (float Eff : JointStateMsg->Efforts)
	{
		EffArray.Add(MakeShared<FJsonValueNumber>(Eff));
	}
	MsgObj->SetArrayField(TEXT("effort"), EffArray);

	// Publish via rosbridge
	return Client->Publish(TopicName, MsgObj);
}

bool UROS2PublisherComponent::PublishRaw(const TArray<uint8>& MessageData)
{
	// Not used in current implementation
	return false;
}

bool UROS2PublisherComponent::CreateNativePublisher()
{
	LogInfo(TEXT("Creating native ROS2 publisher..."));

#if ROA_NATIVE_ROS2
	if (!NodeComponent)
	{
		LogError(TEXT("No node component for native publisher"));
		return false;
	}

	rcl_node_t* node = static_cast<rcl_node_t*>(NodeComponent->GetNativeNode());
	if (!node || !rcl_node_is_valid(node))
	{
		LogError(TEXT("Invalid ROS2 node"));
		return false;
	}

	std::string topic_name = TCHAR_TO_UTF8(*TopicName);

	// Create publisher
	rcl_publisher_t* publisher = new rcl_publisher_t;
	*publisher = rcl_get_zero_initialized_publisher();

	rcl_publisher_options_t publisher_options = rcl_publisher_get_default_options();
	publisher_options.qos.depth = QueueSize;

	const rosidl_message_type_support_t* type_support =
		ROSIDL_GET_MSG_TYPE_SUPPORT(sensor_msgs, msg, JointState);

	rcl_ret_t ret = rcl_publisher_init(
		publisher,
		node,
		type_support,
		topic_name.c_str(),
		&publisher_options
	);

	if (ret != RCL_RET_OK)
	{
		LogError(FString::Printf(TEXT("rcl_publisher_init failed: %d"), ret));
		delete publisher;
		return false;
	}

	NativePublisher = static_cast<void*>(publisher);
	LogInfo(FString::Printf(TEXT("Native ROS2 publisher created: %s"), *TopicName));
	return true;
#else
	LogWarning(TEXT("Native ROS2 not available"));
	return false;
#endif
}

bool UROS2PublisherComponent::CreateBridgePublisher()
{
	LogInfo(TEXT("Creating rosbridge publisher..."));

	FROSBridgeClient* Client = FROS2Context::Get().GetBridgeClient();
	if (!Client)
	{
		LogError(TEXT("No rosbridge client available"));
		return false;
	}

	if (!Client->IsConnected())
	{
		LogError(TEXT("rosbridge client not connected"));
		return false;
	}

	// Advertise the topic
	if (!Client->Advertise(TopicName, MessageType))
	{
		LogError(TEXT("Failed to advertise topic"));
		return false;
	}

	LogInfo(FString::Printf(TEXT("rosbridge publisher ready: %s"), *TopicName));
	return true;
}

bool UROS2PublisherComponent::CreateFallbackPublisher()
{
	// Deprecated - use CreateBridgePublisher instead
	return CreateBridgePublisher();
}
