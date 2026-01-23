// ROCIPCHandler.cpp - Implementation of IPC Handler
//
// NOT YET IMPLEMENTED - This is a stub file.
// Full implementation will be done in the implementation phase.

#include "ROCIPCHandler.h"
#include "ROCSubsystem.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Common/TcpSocketBuilder.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFilemanager.h"

// =============================================================================
// Lifecycle
// =============================================================================

void UROCIPCHandler::Initialize(UROCSubsystem* InSubsystem)
{
    Subsystem = InSubsystem;
    
    // Initialize receive buffer
    ReceiveBuffer.SetNum(65536);  // 64KB buffer
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: Initialized (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::Shutdown()
{
    Disconnect();
    Subsystem = nullptr;
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: Shutdown"));
}

bool UROCIPCHandler::Connect()
{
    // TODO: Implement connection
    // 1. Create request socket (connects to Linux:9876)
    // 2. Create response listener socket (listens on 9877)
    // 3. Wait for response connection
    // 4. Start heartbeat
    
    // if (!CreateRequestSocket())
    // {
    //     return false;
    // }
    // 
    // if (!CreateResponseListener())
    // {
    //     return false;
    // }
    // 
    // bConnected = true;
    // WriteHeartbeatFile();
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: Connect called (NOT IMPLEMENTED)"));
    return false;
}

void UROCIPCHandler::Disconnect()
{
    // TODO: Implement disconnection
    // 1. Close sockets
    // 2. Clear connection state
    
    if (RequestSocket)
    {
        RequestSocket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(RequestSocket);
        RequestSocket = nullptr;
    }
    
    if (ClientSocket)
    {
        ClientSocket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
        ClientSocket = nullptr;
    }
    
    if (ResponseSocket)
    {
        ResponseSocket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ResponseSocket);
        ResponseSocket = nullptr;
    }
    
    bConnected = false;
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: Disconnected"));
}

// =============================================================================
// Message Sending
// =============================================================================

void UROCIPCHandler::SendJointCommand(const FString& RobotId, const FROCJointCommand& Command)
{
    // TODO: Implement single command sending
    TArray<FROCJointCommand> Commands;
    Commands.Add(Command);
    SendJointCommands(RobotId, Commands);
}

void UROCIPCHandler::SendJointCommands(const FString& RobotId, const TArray<FROCJointCommand>& Commands)
{
    // TODO: Implement command sending
    // 1. Create JSON message
    // 2. Serialize and send
    
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("joint_commands"));
    Message->SetStringField(TEXT("robot_id"), RobotId);
    
    TArray<TSharedPtr<FJsonValue>> CommandsArray;
    for (const FROCJointCommand& Cmd : Commands)
    {
        CommandsArray.Add(MakeShareable(new FJsonValueObject(JointCommandToJson(Cmd))));
    }
    Message->SetArrayField(TEXT("commands"), CommandsArray);
    
    // SendJsonMessage(Message);
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: SendJointCommands called (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::SendEmergencyStop(const FString& RobotId, const FString& Reason)
{
    // TODO: Implement E-Stop sending
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("emergency_stop"));
    Message->SetStringField(TEXT("robot_id"), RobotId);
    Message->SetStringField(TEXT("reason"), Reason);
    
    // SendJsonMessage(Message);
    
    UE_LOG(LogTemp, Warning, TEXT("ROCIPCHandler: SendEmergencyStop called (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::SendClearEmergencyStop(const FString& RobotId)
{
    // TODO: Implement E-Stop clear sending
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("clear_estop"));
    Message->SetStringField(TEXT("robot_id"), RobotId);
    
    // SendJsonMessage(Message);
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: SendClearEmergencyStop called (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::SendModeChangeRequest(const FString& RobotId, EROCControlMode NewMode)
{
    // TODO: Implement mode change request
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("mode_change"));
    Message->SetStringField(TEXT("robot_id"), RobotId);
    Message->SetStringField(TEXT("mode"), NewMode == EROCControlMode::RPM ? TEXT("RPM") : TEXT("ADM"));
    
    // SendJsonMessage(Message);
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: SendModeChangeRequest called (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::SendRobotRegistration(const FROCRobotConfig& Config)
{
    // TODO: Implement robot registration
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("robot_register"));
    Message->SetObjectField(TEXT("config"), RobotConfigToJson(Config));
    
    // SendJsonMessage(Message);
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: SendRobotRegistration called (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::SendRobotUnregistration(const FString& RobotId)
{
    // TODO: Implement robot unregistration
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("robot_unregister"));
    Message->SetStringField(TEXT("robot_id"), RobotId);
    
    // SendJsonMessage(Message);
    
    UE_LOG(LogTemp, Log, TEXT("ROCIPCHandler: SendRobotUnregistration called (NOT IMPLEMENTED)"));
}

void UROCIPCHandler::SendHeartbeat()
{
    // TODO: Implement heartbeat sending
    TSharedPtr<FJsonObject> Message = MakeShareable(new FJsonObject);
    Message->SetStringField(TEXT("type"), TEXT("heartbeat"));
    Message->SetNumberField(TEXT("timestamp"), FPlatformTime::Seconds());
    
    // SendJsonMessage(Message);
    
    // Also write heartbeat file for service lifecycle
    WriteHeartbeatFile();
}

// =============================================================================
// Tick
// =============================================================================

void UROCIPCHandler::Tick(float DeltaTime)
{
    if (!bConnected)
    {
        // TODO: Attempt reconnection
        DisconnectedTime += DeltaTime;
        if (DisconnectedTime >= ReconnectDelay)
        {
            // AttemptReconnect();
            DisconnectedTime = 0.0f;
        }
        return;
    }
    
    // TODO: Check connection status
    // CheckConnectionStatus();
    
    // TODO: Accept response connections
    // AcceptResponseConnection();
    
    // TODO: Process incoming data
    // ProcessIncomingData();
    
    // TODO: Send heartbeat periodically
    LastHeartbeatTime += DeltaTime;
    if (LastHeartbeatTime >= HeartbeatInterval)
    {
        SendHeartbeat();
        LastHeartbeatTime = 0.0f;
    }
}

// =============================================================================
// Internal Methods
// =============================================================================

bool UROCIPCHandler::CreateRequestSocket()
{
    // TODO: Create TCP socket for requests
    // FSocket* Socket = FTcpSocketBuilder(TEXT("ROCRequest"))
    //     .AsReusable()
    //     .AsBlocking()
    //     .Build();
    // 
    // TSharedPtr<FInternetAddr> Addr = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
    // Addr->SetIp(*LinuxHost, false);
    // Addr->SetPort(RequestPort);
    // 
    // if (!Socket->Connect(*Addr))
    // {
    //     UE_LOG(LogTemp, Error, TEXT("ROCIPCHandler: Failed to connect to Linux"));
    //     return false;
    // }
    // 
    // RequestSocket = Socket;
    return false;
}

bool UROCIPCHandler::CreateResponseListener()
{
    // TODO: Create TCP listener for responses
    // FSocket* Socket = FTcpSocketBuilder(TEXT("ROCResponse"))
    //     .AsReusable()
    //     .AsNonBlocking()
    //     .Listening(8)
    //     .BoundToPort(ResponsePort)
    //     .Build();
    // 
    // ResponseSocket = Socket;
    return false;
}

void UROCIPCHandler::AcceptResponseConnection()
{
    // TODO: Accept incoming connection on response port
    // if (ResponseSocket && ResponseSocket->HasPendingConnection())
    // {
    //     TSharedPtr<FInternetAddr> Addr;
    //     ClientSocket = ResponseSocket->Accept(*Addr, TEXT("ROCClient"));
    // }
}

void UROCIPCHandler::ProcessIncomingData()
{
    // TODO: Read data from client socket
    // if (!ClientSocket)
    // {
    //     return;
    // }
    // 
    // uint32 PendingData = 0;
    // while (ClientSocket->HasPendingData(PendingData))
    // {
    //     int32 BytesRead = 0;
    //     if (ClientSocket->Recv(ReceiveBuffer.GetData(), ReceiveBuffer.Num(), BytesRead))
    //     {
    //         FString JsonString = FString(UTF8_TO_TCHAR(ReceiveBuffer.GetData()));
    //         ParseMessage(JsonString);
    //     }
    // }
}

void UROCIPCHandler::ParseMessage(const FString& JsonString)
{
    // TODO: Parse JSON and dispatch to callback
    // TSharedPtr<FJsonObject> JsonObject;
    // TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);
    // 
    // if (FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
    // {
    //     FString MessageType = JsonObject->GetStringField(TEXT("type"));
    //     OnMessageReceived.ExecuteIfBound(MessageType, JsonObject);
    // }
}

bool UROCIPCHandler::SendJsonMessage(const TSharedPtr<FJsonObject>& Message)
{
    // TODO: Serialize and send message
    // if (!RequestSocket || !bConnected)
    // {
    //     return false;
    // }
    // 
    // FString JsonString = SerializeMessage(Message);
    // TCHAR_TO_UTF8(*JsonString);
    // 
    // int32 BytesSent = 0;
    // return RequestSocket->Send((uint8*)TCHAR_TO_UTF8(*JsonString), JsonString.Len(), BytesSent);
    
    return false;
}

FString UROCIPCHandler::SerializeMessage(const TSharedPtr<FJsonObject>& Message)
{
    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(Message.ToSharedRef(), Writer);
    return OutputString;
}

void UROCIPCHandler::WriteHeartbeatFile()
{
    // TODO: Write heartbeat file to IPC path
    // This is used by Linux service for lifecycle management
    //
    // FString HeartbeatPath = IPCPath + TEXT("ue5_roc.json");
    // 
    // TSharedPtr<FJsonObject> Heartbeat = MakeShareable(new FJsonObject);
    // Heartbeat->SetStringField(TEXT("client_id"), TEXT("ue5_roc"));
    // Heartbeat->SetNumberField(TEXT("timestamp"), FPlatformTime::Seconds());
    // Heartbeat->SetStringField(TEXT("status"), TEXT("active"));
    // 
    // FString HeartbeatJson = SerializeMessage(Heartbeat);
    // FFileHelper::SaveStringToFile(HeartbeatJson, *HeartbeatPath);
}

void UROCIPCHandler::CheckConnectionStatus()
{
    // TODO: Check if connection is still alive
    // Detect disconnection and handle appropriately
}

void UROCIPCHandler::AttemptReconnect()
{
    // TODO: Attempt to reconnect
    // Disconnect();
    // Connect();
}

TSharedPtr<FJsonObject> UROCIPCHandler::JointCommandToJson(const FROCJointCommand& Command)
{
    TSharedPtr<FJsonObject> Json = MakeShareable(new FJsonObject);
    Json->SetStringField(TEXT("joint_name"), Command.JointName);
    Json->SetNumberField(TEXT("target_position"), Command.TargetPosition);
    Json->SetNumberField(TEXT("velocity_limit"), Command.VelocityLimit);
    Json->SetStringField(TEXT("command_id"), Command.CommandId);
    return Json;
}

TSharedPtr<FJsonObject> UROCIPCHandler::RobotConfigToJson(const FROCRobotConfig& Config)
{
    TSharedPtr<FJsonObject> Json = MakeShareable(new FJsonObject);
    Json->SetStringField(TEXT("robot_id"), Config.RobotId);
    Json->SetStringField(TEXT("robot_name"), Config.RobotName);
    
    TArray<TSharedPtr<FJsonValue>> JointsArray;
    for (const FROCJointConfig& Joint : Config.Joints)
    {
        TSharedPtr<FJsonObject> JointJson = MakeShareable(new FJsonObject);
        JointJson->SetStringField(TEXT("joint_name"), Joint.JointName);
        JointJson->SetStringField(TEXT("joint_type"), 
            Joint.JointType == EROCJointType::Revolute ? TEXT("revolute") :
            Joint.JointType == EROCJointType::Prismatic ? TEXT("prismatic") :
            Joint.JointType == EROCJointType::Continuous ? TEXT("continuous") : TEXT("fixed"));
        JointJson->SetNumberField(TEXT("lower_limit"), Joint.Limits.Lower);
        JointJson->SetNumberField(TEXT("upper_limit"), Joint.Limits.Upper);
        JointJson->SetNumberField(TEXT("velocity_limit"), Joint.Limits.Velocity);
        JointJson->SetNumberField(TEXT("effort_limit"), Joint.Limits.Effort);
        JointJson->SetStringField(TEXT("ue5_constraint"), Joint.UE5ConstraintName);
        
        JointsArray.Add(MakeShareable(new FJsonValueObject(JointJson)));
    }
    Json->SetArrayField(TEXT("joints"), JointsArray);
    
    // Capabilities
    TSharedPtr<FJsonObject> CapJson = MakeShareable(new FJsonObject);
    CapJson->SetBoolField(TEXT("has_gripper"), Config.Capabilities.bHasGripper);
    CapJson->SetNumberField(TEXT("max_payload_kg"), Config.Capabilities.MaxPayloadKg);
    CapJson->SetNumberField(TEXT("reach_cm"), Config.Capabilities.ReachCm);
    CapJson->SetNumberField(TEXT("dof"), Config.Capabilities.DOF);
    Json->SetObjectField(TEXT("capabilities"), CapJson);
    
    return Json;
}
