// Copyright ROA Development Team. All Rights Reserved.

#include "Components/ROS2/ROS2NodeComponent.h"
#include "Components/ROS2/ROS2Context.h"
#include "ROARobotActor.h"

#if ROA_NATIVE_ROS2
#include <string>
#endif

UROS2NodeComponent::UROS2NodeComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	
	NodeName = TEXT("ue5_robot_node");
	NodeNamespace = TEXT("");
	bUseNativeMode = true;  // Prefer native if available
	bNodeReady = false;
	NativeNode = nullptr;

	LogPrefix = TEXT("[ROS2NodeComponent]");
}

void UROS2NodeComponent::InitializeComponent()
{
	Super::InitializeComponent();

	// Generate unique node name if attached to robot
	if (OwningRobot)
	{
		NodeName = FString::Printf(TEXT("robot_%s"), *OwningRobot->GetName());
	}

	// Check if native mode is available
	bool bNativeAvailable = FROS2Context::Get().IsNativeModeAvailable();
	
	if (bUseNativeMode && !bNativeAvailable)
	{
		LogWarning(TEXT("Native ROS2 mode requested but not available, falling back to TCP mode"));
		bUseNativeMode = false;
	}

	// Create node
	bool bSuccess = false;
	if (bUseNativeMode)
	{
		bSuccess = CreateNativeNode();
	}
	else
	{
		bSuccess = CreateFallbackNode();
	}

	if (bSuccess)
	{
		bNodeReady = true;
		LogInfo(FString::Printf(TEXT("Node created: %s (namespace: %s, mode: %s)"),
			*NodeName,
			NodeNamespace.IsEmpty() ? TEXT("global") : *NodeNamespace,
			bUseNativeMode ? TEXT("native") : TEXT("TCP")));
	}
	else
	{
		LogError(TEXT("Failed to create ROS2 node"));
	}
}

void UROS2NodeComponent::UninitializeComponent()
{
	LogInfo(TEXT("Shutting down node"));

#if ROA_NATIVE_ROS2
	if (NativeNode)
	{
		rcl_node_t* node = static_cast<rcl_node_t*>(NativeNode);
		rcl_ret_t ret = rcl_node_fini(node);
		
		if (ret != RCL_RET_OK)
		{
			LogWarning(TEXT("rcl_node_fini returned error"));
		}
		
		delete node;
		NativeNode = nullptr;
		LogInfo(TEXT("Native node destroyed"));
	}
#endif

	bNodeReady = false;

	Super::UninitializeComponent();
}

void UROS2NodeComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!bComponentEnabled || !bNodeReady)
	{
		return;
	}

	// Spin ROS2 callbacks
	SpinOnce();
}

void UROS2NodeComponent::SpinOnce()
{
#if ROA_NATIVE_ROS2
	if (NativeNode)
	{
		rcl_node_t* node = static_cast<rcl_node_t*>(NativeNode);
		// For rcl C API, spinning is handled differently - we process callbacks in publisher/subscriber
		// This is a no-op for now
	}
#endif
}

bool UROS2NodeComponent::CreateNativeNode()
{
	LogInfo(TEXT("Creating native ROS2 node (C API)..."));

	// Ensure ROS2 context is initialized
	if (!FROS2Context::Get().IsInitialized())
	{
		if (!FROS2Context::Get().Initialize())
		{
			LogError(TEXT("Failed to initialize ROS2 context"));
			return false;
		}
	}

#if ROA_NATIVE_ROS2
	rcl_context_t* context = static_cast<rcl_context_t*>(FROS2Context::Get().GetNativeContext());
	if (!context || !rcl_context_is_valid(context))
	{
		LogError(TEXT("Invalid ROS2 context"));
		return false;
	}

	// Create node
	rcl_node_t* node = new rcl_node_t;
	*node = rcl_get_zero_initialized_node();
	
	rcl_node_options_t node_options = rcl_node_get_default_options();
	// Note: domain_id is set via environment variable ROS_DOMAIN_ID or rcl_init_options
	
	std::string node_name_str = TCHAR_TO_UTF8(*NodeName);
	std::string node_namespace_str = NodeNamespace.IsEmpty() ? "" : TCHAR_TO_UTF8(*NodeNamespace);
	
	rcl_ret_t ret = rcl_node_init(node, node_name_str.c_str(), node_namespace_str.c_str(), context, &node_options);
	
	if (ret != RCL_RET_OK)
	{
		LogError(FString::Printf(TEXT("rcl_node_init failed: %d"), ret));
		delete node;
		return false;
	}
	
	NativeNode = static_cast<void*>(node);
	LogInfo(FString::Printf(TEXT("Native ROS2 node created (C API): %s"), *NodeName));
	return true;
#else
	LogWarning(TEXT("Native ROS2 not available (compiled without ROA_NATIVE_ROS2)"));
	return false;
#endif
}

bool UROS2NodeComponent::CreateFallbackNode()
{
	LogInfo(TEXT("Creating TCP fallback node..."));

	// Fallback mode uses existing ROANetworkServer
	// Node is "created" but communication happens via TCP to Python
	
	LogInfo(TEXT("TCP fallback node ready (using existing ROANetworkServer)"));
	return true;
}
