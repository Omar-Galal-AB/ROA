// Copyright ROA Development Team. All Rights Reserved.

#include "Components/ROS2/ROS2Context.h"
#include "ROSBridgeClient.h"
#include "HAL/PlatformProcess.h"
#include "Misc/Paths.h"

#if ROA_NATIVE_ROS2
#include <string>
#include <rcl/rcl.h>
#endif

// Singleton instance
static FROS2Context* GRos2Context = nullptr;

FROS2Context& FROS2Context::Get()
{
    if (!GRos2Context)
    {
        GRos2Context = new FROS2Context();
    }
    return *GRos2Context;
}

FROS2Context::FROS2Context()
    : bInitialized(false)
    , NativeContext(nullptr)
    , BridgeClient(nullptr)
    , DomainID(0)
    , BridgeHost(TEXT("127.0.0.1"))
    , BridgePort(9090)  // Standard rosbridge port
{
}

FROS2Context::~FROS2Context()
{
    Shutdown();
}

bool FROS2Context::Initialize()
{
    FScopeLock Lock(&ContextMutex);

    if (bInitialized)
    {
        UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] Already initialized"));
        return true;
    }

    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Initializing ROS2 communication..."));

#if ROA_NATIVE_ROS2
    // Try native mode first
    if (InitializeNative())
    {
        bInitialized = true;
        UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] ✅ Native ROS2 initialized (DDS mode)"));
        return true;
    }
    UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] Native ROS2 failed, falling back to TCP mode"));
#endif

    // Fallback to TCP/rosbridge mode
    if (InitializeTCP())
    {
        bInitialized = true;
        UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] ✅ TCP mode initialized (rosbridge protocol)"));
        return true;
    }

    UE_LOG(LogTemp, Error, TEXT("[ROS2Context] ❌ Failed to initialize ROS2 communication"));
    return false;
}

bool FROS2Context::InitializeNative()
{
#if ROA_NATIVE_ROS2
    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Initializing native ROS2 (rcl)..."));

    // Initialize rcl options
    rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
    rcl_ret_t ret = rcl_init_options_init(&init_options, rcl_get_default_allocator());

    if (ret != RCL_RET_OK)
    {
        UE_LOG(LogTemp, Error, TEXT("[ROS2Context] rcl_init_options_init failed: %d"), ret);
        return false;
    }

    // Create context
    rcl_context_t* context = new rcl_context_t;
    *context = rcl_get_zero_initialized_context();

    // Initialize context
    ret = rcl_init(0, nullptr, &init_options, context);

    // Cleanup options
    rcl_init_options_fini(&init_options);

    if (ret != RCL_RET_OK)
    {
        UE_LOG(LogTemp, Error, TEXT("[ROS2Context] rcl_init failed: %d"), ret);
        delete context;
        return false;
    }

    NativeContext = static_cast<void*>(context);
    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Native ROS2 context created"));
    return true;
#else
    return false;
#endif
}

bool FROS2Context::InitializeTCP()
{
    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Initializing TCP mode (rosbridge at %s:%d)..."), *BridgeHost, BridgePort);

    BridgeClient = new FROSBridgeClient();

    // Try to connect (expects server already running)
    if (!BridgeClient->Connect(BridgeHost, BridgePort))
    {
        UE_LOG(LogTemp, Error, TEXT("[ROS2Context] Failed to connect to rosbridge at %s:%d"), *BridgeHost, BridgePort);
        UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] Make sure bridge server is running. In WSL run: roa start"));
        delete BridgeClient;
        BridgeClient = nullptr;
        return false;
    }

    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Connected to rosbridge server"));
    return true;
}

void FROS2Context::Shutdown()
{
    FScopeLock Lock(&ContextMutex);

    if (!bInitialized)
    {
        return;
    }

    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Shutting down..."));

#if ROA_NATIVE_ROS2
    if (NativeContext)
    {
        rcl_context_t* context = static_cast<rcl_context_t*>(NativeContext);
        rcl_ret_t ret = rcl_shutdown(context);

        if (ret != RCL_RET_OK)
        {
            UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] rcl_shutdown returned error"));
        }

        ret = rcl_context_fini(context);
        if (ret != RCL_RET_OK)
        {
            UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] rcl_context_fini returned error"));
        }

        delete context;
        NativeContext = nullptr;
        UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Native ROS2 context destroyed"));
    }
#endif

    if (BridgeClient)
    {
        BridgeClient->Disconnect();
        delete BridgeClient;
        BridgeClient = nullptr;
        UE_LOG(LogTemp, Log, TEXT("[ROS2Context] rosbridge client destroyed"));
    }

    bInitialized = false;
    UE_LOG(LogTemp, Log, TEXT("[ROS2Context] Shutdown complete"));
}

void FROS2Context::SetDomainID(int32 InDomainID)
{
    if (bInitialized)
    {
        UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] Cannot change domain ID after initialization"));
        return;
    }
    DomainID = InDomainID;
}

void FROS2Context::SetBridgeServer(const FString& Host, int32 Port)
{
    if (bInitialized)
    {
        UE_LOG(LogTemp, Warning, TEXT("[ROS2Context] Cannot change bridge server after initialization"));
        return;
    }
    BridgeHost = Host;
    BridgePort = Port;
}

bool FROS2Context::IsNativeModeAvailable() const
{
#if ROA_NATIVE_ROS2
    return NativeContext != nullptr;
#else
    return false;
#endif
}
