// ROCIPCHandler.h - IPC Communication with Linux ROC
//
// Handles TCP socket communication with Linux ROC service.
// Uses dual-port architecture: 9876 for requests, 9877 for responses.

#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Networking.h"
#include "ROCTypes.h"
#include "ROCIPCHandler.generated.h"

// Forward declarations
class UROCSubsystem;

/** Delegate for IPC message received */
DECLARE_DELEGATE_TwoParams(FOnROCIPCMessageReceived, 
    const FString&, /* MessageType */
    const TSharedPtr<FJsonObject>& /* Data */);

/**
 * ROC IPC Handler - Manages communication with Linux ROC.
 * 
 * Provides:
 * - TCP connection management
 * - Message serialization/deserialization
 * - Heartbeat maintenance
 * - Reconnection logic
 */
UCLASS()
class ROA_API UROCIPCHandler : public UObject
{
    GENERATED_BODY()
    
public:
    // =========================================================================
    // Lifecycle
    // =========================================================================
    
    /**
     * Initialize the IPC handler.
     * 
     * @param InSubsystem Parent ROC subsystem
     */
    void Initialize(UROCSubsystem* InSubsystem);
    
    /**
     * Shutdown the IPC handler.
     */
    void Shutdown();
    
    /**
     * Connect to Linux ROC service.
     * 
     * @return True if connection initiated
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    bool Connect();
    
    /**
     * Disconnect from Linux ROC service.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void Disconnect();
    
    /**
     * Check if connected.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    bool IsConnected() const { return bConnected; }
    
    // =========================================================================
    // Configuration
    // =========================================================================
    
    /**
     * Set request port (ROC → Linux).
     * Default: 9876
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SetRequestPort(int32 Port) { RequestPort = Port; }
    
    /**
     * Set response port (Linux → ROC).
     * Default: 9877
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SetResponsePort(int32 Port) { ResponsePort = Port; }
    
    /**
     * Set Linux host address.
     * Default: 127.0.0.1 (localhost via socat relay)
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SetLinuxHost(const FString& Host) { LinuxHost = Host; }
    
    // =========================================================================
    // Message Sending
    // =========================================================================
    
    /**
     * Send joint command for validation.
     * 
     * @param RobotId Robot identifier
     * @param Command Joint command
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendJointCommand(const FString& RobotId, const FROCJointCommand& Command);
    
    /**
     * Send multiple joint commands for validation.
     * 
     * @param RobotId Robot identifier
     * @param Commands Array of joint commands
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendJointCommands(const FString& RobotId, const TArray<FROCJointCommand>& Commands);
    
    /**
     * Send emergency stop request.
     * 
     * @param RobotId Robot identifier (or "all")
     * @param Reason Reason for E-Stop
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendEmergencyStop(const FString& RobotId, const FString& Reason);
    
    /**
     * Send clear emergency stop request.
     * 
     * @param RobotId Robot identifier
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendClearEmergencyStop(const FString& RobotId);
    
    /**
     * Send mode change request.
     * 
     * @param RobotId Robot identifier
     * @param NewMode Requested mode
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendModeChangeRequest(const FString& RobotId, EROCControlMode NewMode);
    
    /**
     * Send robot registration.
     * 
     * @param Config Robot configuration
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendRobotRegistration(const FROCRobotConfig& Config);
    
    /**
     * Send robot unregistration.
     * 
     * @param RobotId Robot identifier
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendRobotUnregistration(const FString& RobotId);
    
    /**
     * Send heartbeat.
     */
    UFUNCTION(BlueprintCallable, Category = "ROC|IPC")
    void SendHeartbeat();
    
    // =========================================================================
    // Message Callback
    // =========================================================================
    
    /** Delegate for message received */
    FOnROCIPCMessageReceived OnMessageReceived;
    
    // =========================================================================
    // Tick
    // =========================================================================
    
    /**
     * Tick the IPC handler.
     * Processes incoming messages, sends heartbeat.
     * 
     * @param DeltaTime Time since last tick
     */
    void Tick(float DeltaTime);
    
protected:
    // =========================================================================
    // Properties
    // =========================================================================
    
    /** Parent subsystem */
    UPROPERTY()
    UROCSubsystem* Subsystem = nullptr;
    
    /** Request port (UE5 → Linux) */
    int32 RequestPort = 9876;
    
    /** Response port (Linux → UE5) */
    int32 ResponsePort = 9877;
    
    /** Linux host address */
    FString LinuxHost = TEXT("127.0.0.1");
    
    /** Request socket */
    FSocket* RequestSocket = nullptr;
    
    /** Response socket (listener) */
    FSocket* ResponseSocket = nullptr;
    
    /** Connected client socket (for response) */
    FSocket* ClientSocket = nullptr;
    
    /** Connection status */
    bool bConnected = false;
    
    /** Last heartbeat time */
    float LastHeartbeatTime = 0.0f;
    
    /** Heartbeat interval (seconds) */
    float HeartbeatInterval = 10.0f;
    
    /** Reconnect delay */
    float ReconnectDelay = 5.0f;
    
    /** Time since disconnection */
    float DisconnectedTime = 0.0f;
    
    /** Receive buffer */
    TArray<uint8> ReceiveBuffer;
    
    /** IPC path for heartbeat files */
    FString IPCPath = TEXT("/mnt/d/ROA/.ipc/heartbeats/");
    
    // =========================================================================
    // Internal Methods
    // =========================================================================
    
    /** Create request socket */
    bool CreateRequestSocket();
    
    /** Create response listener socket */
    bool CreateResponseListener();
    
    /** Accept incoming response connection */
    void AcceptResponseConnection();
    
    /** Process incoming data */
    void ProcessIncomingData();
    
    /** Parse received message */
    void ParseMessage(const FString& JsonString);
    
    /** Send JSON message */
    bool SendJsonMessage(const TSharedPtr<FJsonObject>& Message);
    
    /** Serialize message to JSON string */
    FString SerializeMessage(const TSharedPtr<FJsonObject>& Message);
    
    /** Write heartbeat file */
    void WriteHeartbeatFile();
    
    /** Check connection status */
    void CheckConnectionStatus();
    
    /** Attempt reconnection */
    void AttemptReconnect();
    
    /** Convert FROCJointCommand to JSON */
    TSharedPtr<FJsonObject> JointCommandToJson(const FROCJointCommand& Command);
    
    /** Convert FROCRobotConfig to JSON */
    TSharedPtr<FJsonObject> RobotConfigToJson(const FROCRobotConfig& Config);
};
