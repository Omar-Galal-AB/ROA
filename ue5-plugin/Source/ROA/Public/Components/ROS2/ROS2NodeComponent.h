// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ROAComponent.h"

#if ROA_NATIVE_ROS2
// Fix Windows macro conflicts with ROS2 headers
#ifdef check
#pragma push_macro("check")
#undef check
#define ROA_CHECK_MACRO_PUSHED 1
#endif

#include <string>
#include <rcl/rcl.h>
#include <rcl/node.h>

#ifdef ROA_CHECK_MACRO_PUSHED
#pragma pop_macro("check")
#undef ROA_CHECK_MACRO_PUSHED
#endif
#endif // ROA_NATIVE_ROS2

#include "ROS2NodeComponent.generated.h"

/**
 * ROS2 Node Component
 * 
 * Creates and manages a ROS2 node for the robot actor.
 * Other ROS2 components (Publisher, Subscriber, Service) require this component.
 * 
 * In native mode, this wraps rclcpp::Node
 * In fallback mode, uses TCP bridge to Python
 */
UCLASS(ClassGroup=(ROA), meta=(BlueprintSpawnableComponent))
class ROA_API UROS2NodeComponent : public UROAComponent
{
	GENERATED_BODY()

public:
	UROS2NodeComponent();

	/** Component lifecycle */
	virtual void InitializeComponent() override;
	virtual void UninitializeComponent() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/**
	 * Get native ROS2 node
	 * 
	 * @return Pointer to rclcpp::Node::SharedPtr (or nullptr if not in native mode)
	 * 
	 * NOTE: Currently returns nullptr (stub)
	 * TODO: Return actual rclcpp::Node::SharedPtr when integrated
	 */
	void* GetNativeNode() const { return NativeNode; }

	/**
	 * Check if node is ready for pub/sub
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2")
	bool IsNodeReady() const { return bNodeReady; }

	/**
	 * Spin ROS2 callbacks (process incoming messages)
	 * Called automatically in TickComponent
	 */
	void SpinOnce();

	/**
	 * Get node name
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2")
	FString GetNodeName() const { return NodeName; }

	/**
	 * Get node namespace
	 */
	UFUNCTION(BlueprintPure, Category="ROA|ROS2")
	FString GetNodeNamespace() const { return NodeNamespace; }

protected:
	/** ROS2 node name */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Node")
	FString NodeName;

	/** ROS2 node namespace (empty = global) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Node")
	FString NodeNamespace;

	/** Use native ROS2 mode (vs TCP fallback) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROS2|Node")
	bool bUseNativeMode;

	/** Node ready state */
	bool bNodeReady;

	/** Native ROS2 node (rclcpp::Node::SharedPtr) */
	void* NativeNode;

	/** Create native ROS2 node (when rclcpp is integrated) */
	bool CreateNativeNode();

	/** Create fallback TCP node */
	bool CreateFallbackNode();
};
