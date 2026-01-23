// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "HAL/PlatformProcess.h"
#include "SocketSubsystem.h"
#include "Sockets.h"

// Forward declaration
class FROSBridgeClient;

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
#include <rcl/publisher.h>
#include <rcutils/allocator.h>

#ifdef ROA_CHECK_MACRO_PUSHED
#pragma pop_macro("check")
#undef ROA_CHECK_MACRO_PUSHED
#endif
#endif // ROA_NATIVE_ROS2

/**
 * ROS2 Context Manager
 * 
 * Singleton that manages ROS2 communication for the entire plugin.
 * Supports two modes:
 * - Native Mode: Uses embedded ROS2 (rcl) for direct DDS communication (<5ms latency)
 * - TCP Mode: Uses rosbridge protocol for ROS2 communication via TCP (~10-20ms latency)
 */
class ROA_API FROS2Context
{
public:
    /**
     * Get singleton instance
     */
    static FROS2Context& Get();

    /**
     * Initialize ROS2 runtime
     * In Native mode: Initializes rcl context
     * In TCP mode: Connects to rosbridge server
     * 
     * @return True if initialization successful
     */
    bool Initialize();

    /**
     * Shutdown ROS2 runtime
     */
    void Shutdown();

    /**
     * Check if ROS2 is initialized and ready
     */
    bool IsInitialized() const { return bInitialized; }

    /**
     * Get native ROS2 context (rcl_context_t*)
     * Returns nullptr if in TCP mode
     */
    void* GetNativeContext() const { return NativeContext; }

    /**
     * Get rosbridge client for TCP mode
     * Returns nullptr if in Native mode
     */
    FROSBridgeClient* GetBridgeClient() const { return BridgeClient; }

    /**
     * Get ROS2 domain ID (for DDS communication)
     */
    int32 GetDomainID() const { return DomainID; }

    /**
     * Set ROS2 domain ID (must be called before Initialize)
     */
    void SetDomainID(int32 InDomainID);

    /**
     * Set rosbridge server address (for TCP mode)
     */
    void SetBridgeServer(const FString& Host, int32 Port);

    /**
     * Check if ROS2 native mode is available
     */
    bool IsNativeModeAvailable() const;

    /**
     * Check if using TCP fallback mode
     */
    bool IsTCPMode() const { return bInitialized && !IsNativeModeAvailable(); }

private:
    FROS2Context();
    ~FROS2Context();

    // Non-copyable
    FROS2Context(const FROS2Context&) = delete;
    FROS2Context& operator=(const FROS2Context&) = delete;

    /** Initialize native ROS2 (rcl) */
    bool InitializeNative();

    /** Initialize TCP/rosbridge mode */
    bool InitializeTCP();

    /** Initialization state */
    bool bInitialized;

    /** Native ROS2 context (rcl_context_t*) */
    void* NativeContext;

    /** rosbridge client for TCP mode */
    FROSBridgeClient* BridgeClient;

    /** ROS2 domain ID for DDS (default: 0) */
    int32 DomainID;

    /** rosbridge server settings */
    FString BridgeHost;
    int32 BridgePort;

    /** Mutex for thread safety */
    FCriticalSection ContextMutex;
};
