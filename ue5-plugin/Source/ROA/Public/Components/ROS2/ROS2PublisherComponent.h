// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "Components/ROAComponent.h"

#if ROA_NATIVE_ROS2
// Fix Windows macro conflicts
#ifdef check
#pragma push_macro("check")
#undef check
#define ROA_CHECK_MACRO_PUSHED 1
#endif

// Standard includes needed by ROS2 headers
#include <cassert>
#include <string>
#include <memory>

// Use ROS2 C API for better Windows compatibility
#include <rcl/rcl.h>
#include <rcl/node.h>
#include <rcl/publisher.h>

// Restore Windows check macro
#ifdef ROA_CHECK_MACRO_PUSHED
#pragma pop_macro("check")
#undef ROA_CHECK_MACRO_PUSHED
#endif
#endif // ROA_NATIVE_ROS2

#include "ROS2PublisherComponent.generated.h"

// Forward declarations
class FROANetworkServer;
class UROS2NodeComponent;

/**
 * ROS2 Message Interface
 * Base class for all ROS2 message types
 */
UCLASS(Abstract, Blueprintable)
class ROA_API UROS2MessageBase : public UObject
{
GENERATED_BODY()

public:
/** Serialize message to bytes for DDS */
virtual TArray<uint8> SerializeToBytes() const { return TArray<uint8>(); }

/** Get message type name (e.g., "sensor_msgs/JointState") */
virtual FString GetMessageType() const { return TEXT(""); }
};

/**
 * ROS2 Publisher Component
 * 
 * Publishes ROS2 messages to a topic.
 * Supports both native ROS2 (rcl) and TCP bridge (rosbridge protocol) modes.
 * 
 * Example: Publishing joint states, odometry, sensor data
 */
UCLASS(ClassGroup=(ROA), meta=(BlueprintSpawnableComponent))
class ROA_API UROS2PublisherComponent : public UROAComponent
{
GENERATED_BODY()

public:
UROS2PublisherComponent();

/** Set the network server for TCP fallback mode (legacy) */
static void SetNetworkServer(TSharedPtr<FROANetworkServer> InServer);

/** Set the node component directly (required for rosbridge mode) */
void SetNodeComponent(UROS2NodeComponent* InNodeComponent);

/** Component lifecycle */
virtual void InitializeComponent() override;
virtual void UninitializeComponent() override;
virtual void OnAttachedToRobot() override;

/**
 * Publish a message - automatically routes to native or bridge
 * 
 * @param Message - Message to publish (must match TopicMessageType)
 * @return True if published successfully
 */
UFUNCTION(BlueprintCallable, Category="ROA|ROS2|Publisher")
bool Publish(UROS2MessageBase* Message);

/**
 * Publish raw data (for custom message types)
 */
bool PublishRaw(const TArray<uint8>& MessageData);

/**
 * Check if publisher is ready
 */
UFUNCTION(BlueprintPure, Category="ROA|ROS2|Publisher")
bool IsPublisherReady() const { return bPublisherReady; }

/**
 * Get topic name
 */
UFUNCTION(BlueprintPure, Category="ROA|ROS2|Publisher")
FString GetTopicName() const { return TopicName; }

public:
/** Topic name to publish on */
UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Publisher")
FString TopicName;

/** Message type (e.g., "sensor_msgs/msg/JointState") */
UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Publisher")
FString MessageType;

/** Queue size for publisher */
UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Publisher", meta=(ClampMin=1, ClampMax=1000))
int32 QueueSize;

/** Publish rate limit (Hz, 0 = unlimited) */
UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Publisher", meta=(ClampMin=0, ClampMax=1000))
float PublishRateLimit;

protected:
/** Publisher ready state */
bool bPublisherReady;

/** Native ROS2 publisher (rcl_publisher_t*) */
void* NativePublisher;

/** Reference to ROS2 node component */
UPROPERTY()
class UROS2NodeComponent* NodeComponent;

/** Last publish time (for rate limiting) */
double LastPublishTime;

/** Create native publisher (when ROS2 is available) */
bool CreateNativePublisher();

/** Create rosbridge publisher (TCP fallback mode) */
bool CreateBridgePublisher();

/** Create fallback publisher (calls CreateBridgePublisher) */
bool CreateFallbackPublisher();

/** Publish via native ROS2 */
bool PublishNative(UROS2MessageBase* Message);

/** Publish via rosbridge protocol */
bool PublishViaBridge(UROS2MessageBase* Message);
};
