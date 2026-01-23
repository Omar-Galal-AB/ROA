// Copyright ROA Development Team. All Rights Reserved.
// ROSBridge Client for TCP fallback mode
// Implements rosbridge protocol for ROS2 communication

#pragma once

#include "CoreMinimal.h"
#include "HAL/Runnable.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Containers/Queue.h"

DECLARE_LOG_CATEGORY_EXTERN(LogROSBridge, Log, All);

/**
 * ROSBridge Client - Connects to rosbridge server for ROS2 communication
 * Used in TCP fallback mode when native ROS2 libraries are not available
 */
class ROA_API FROSBridgeClient : public FRunnable
{
public:
    FROSBridgeClient();
    virtual ~FROSBridgeClient();

    // Connect to rosbridge server
    bool Connect(const FString& Host, int32 Port);
    void Disconnect();
    bool IsConnected() const;

    // rosbridge operations
    bool Advertise(const FString& Topic, const FString& Type);
    bool Unadvertise(const FString& Topic);
    bool Publish(const FString& Topic, TSharedPtr<FJsonObject> Message);
    bool Subscribe(const FString& Topic, const FString& Type, TFunction<void(TSharedPtr<FJsonObject>)> Callback);
    bool Unsubscribe(const FString& Topic);

    // FRunnable interface
    virtual bool Init() override;
    virtual uint32 Run() override;
    virtual void Stop() override;
    virtual void Exit() override;

private:
    bool SendJson(TSharedPtr<FJsonObject> JsonObj);
    void ProcessIncomingData();
    void HandleMessage(const FString& JsonString);

    FSocket* Socket;
    FRunnableThread* Thread;
    FThreadSafeBool bIsRunning;
    FThreadSafeBool bStopRequested;
    FThreadSafeBool bConnected;

    FString ServerHost;
    int32 ServerPort;

    // Outgoing message queue
    TQueue<FString> OutgoingMessages;
    
    // Subscription callbacks
    TMap<FString, TFunction<void(TSharedPtr<FJsonObject>)>> SubscriptionCallbacks;
    FCriticalSection CallbackLock;

    // Receive buffer
    FString ReceiveBuffer;
};
