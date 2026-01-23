// Copyright ROA Development Team. All Rights Reserved.
// Network CLIENT - Connects to WSL command server using rosbridge-style protocol

#include "ROANetworkServer.h"
#include "ROAWorldManager.h"
#include "ROAWidgetManager.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"

FROANetworkServer::FROANetworkServer(int32 Port)
	: ServerPort(Port)
	, ClientSocket(nullptr)
	, ServerThread(nullptr)
	, bIsRunning(false)
	, bStopRequested(false)
{
	ReceiveBuffer.Reserve(65536);
}

FROANetworkServer::~FROANetworkServer()
{
	DisconnectFromServer();
}

bool FROANetworkServer::ConnectToServer(const FString& Host, int32 Port)
{
	if (bIsRunning.Load())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Network: Already connected"));
		return true;
	}

	ServerHost = Host;
	ServerPort = Port;

	ISocketSubsystem* SocketSubsystem = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!SocketSubsystem)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Network: Failed to get socket subsystem"));
		return false;
	}

	ClientSocket = SocketSubsystem->CreateSocket(NAME_Stream, TEXT("ROAClientSocket"), false);
	if (!ClientSocket)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Network: Failed to create socket"));
		return false;
	}

	TSharedRef<FInternetAddr> Addr = SocketSubsystem->CreateInternetAddr();
	bool bIsValid;
	Addr->SetIp(*Host, bIsValid);
	Addr->SetPort(Port);

	if (!bIsValid)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Network: Invalid host: %s"), *Host);
		SocketSubsystem->DestroySocket(ClientSocket);
		ClientSocket = nullptr;
		return false;
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Network: Connecting to %s:%d..."), *Host, Port);
	
	if (!ClientSocket->Connect(*Addr))
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Network: Connection failed to %s:%d"), *Host, Port);
		SocketSubsystem->DestroySocket(ClientSocket);
		ClientSocket = nullptr;
		return false;
	}

	ClientSocket->SetNonBlocking(true);
	bIsRunning.Store(true);

	ServerThread = FRunnableThread::Create(this, TEXT("ROANetworkClient"), 0, TPri_Normal);

	UE_LOG(LogTemp, Warning, TEXT("ROA Network: Connected to %s:%d"), *Host, Port);
	return true;
}

void FROANetworkServer::DisconnectFromServer()
{
	if (!bIsRunning.Load())
	{
		return;
	}

	bStopRequested.Store(true);

	if (ServerThread)
	{
		ServerThread->WaitForCompletion();
		delete ServerThread;
		ServerThread = nullptr;
	}

	CloseClientConnection();
	bIsRunning.Store(false);
	bStopRequested.Store(false);
	
	UE_LOG(LogTemp, Log, TEXT("ROA Network: Disconnected"));
}

void FROANetworkServer::SetWorldManager(TSharedPtr<FROAWorldManager> InWorldManager)
{
	WorldManager = InWorldManager;
}

void FROANetworkServer::SetWidgetManager(TSharedPtr<FROAWidgetManager> InWidgetManager)
{
	WidgetManager = InWidgetManager;
}

bool FROANetworkServer::SendMessage(const FROAMessage& Message)
{
	OutgoingMessages.Enqueue(Message);
	return true;
}

bool FROANetworkServer::Init()
{
	return true;
}

uint32 FROANetworkServer::Run()
{
	UE_LOG(LogTemp, Log, TEXT("ROA Network: Thread started"));

	while (!bStopRequested.Load())
	{
		if (ClientSocket && ClientSocket->GetConnectionState() == SCS_Connected)
		{
			ReceiveData();
			SendQueuedMessages();
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("ROA Network: Connection lost"));
			break;
		}

		FPlatformProcess::Sleep(0.01f);
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Network: Thread stopped"));
	return 0;
}

void FROANetworkServer::Stop()
{
	bStopRequested.Store(true);
}

void FROANetworkServer::Exit()
{
}

bool FROANetworkServer::ReceiveData()
{
	if (!ClientSocket) return false;

	uint32 PendingDataSize = 0;
	if (ClientSocket->HasPendingData(PendingDataSize) && PendingDataSize > 0)
	{
		TArray<uint8> ReceivedData;
		ReceivedData.SetNumUninitialized(PendingDataSize);
		
		int32 BytesRead = 0;
		if (ClientSocket->Recv(ReceivedData.GetData(), ReceivedData.Num(), BytesRead))
		{
			ReceiveBuffer.Append(ReceivedData.GetData(), BytesRead);
			
			// Parse JSON messages (brace-delimited)
			TArray<uint8> NullTerminated = ReceiveBuffer;
			NullTerminated.Add(0);
			FString BufferString = UTF8_TO_TCHAR(NullTerminated.GetData());
			
			int32 BraceCount = 0;
			int32 MessageStart = -1;
			
			for (int32 i = 0; i < BufferString.Len(); ++i)
			{
				if (BufferString[i] == '{')
				{
					if (BraceCount == 0) MessageStart = i;
					BraceCount++;
				}
				else if (BufferString[i] == '}')
				{
					BraceCount--;
					if (BraceCount == 0 && MessageStart >= 0)
					{
						FString MessageJson = BufferString.Mid(MessageStart, i - MessageStart + 1);
						
						FROAMessage Message;
						if (FROAMessage::FromJsonString(MessageJson, Message))
						{
							ProcessMessage(Message);
						}
						
						int32 BytesToRemove = i + 1;
						if (BytesToRemove <= ReceiveBuffer.Num())
						{
							ReceiveBuffer.RemoveAt(0, BytesToRemove);
						}
						
						NullTerminated = ReceiveBuffer;
						NullTerminated.Add(0);
						BufferString = UTF8_TO_TCHAR(NullTerminated.GetData());
						i = -1;
						MessageStart = -1;
					}
				}
			}
		}
	}
	
	return ClientSocket->GetConnectionState() == ESocketConnectionState::SCS_Connected;
}

void FROANetworkServer::ProcessMessage(const FROAMessage& Message)
{
	UE_LOG(LogTemp, Log, TEXT("ROA Network: Command: %s"), *Message.Command);
	
	if (Message.Command == TEXT("connect")) HandleConnectCommand(Message);
	else if (Message.Command == TEXT("disconnect")) HandleDisconnectCommand(Message);
	else if (Message.Command == TEXT("heartbeat")) HandleHeartbeatCommand(Message);
	else if (Message.Command == TEXT("spawn_robot")) HandleSpawnRobotCommand(Message);
	else if (Message.Command == TEXT("despawn_robot")) HandleDespawnRobotCommand(Message);
	else if (Message.Command == TEXT("get_robot_state")) HandleGetRobotStateCommand(Message);
	else if (Message.Command == TEXT("list_robots")) HandleListRobotsCommand(Message);
	else if (Message.Command == TEXT("set_joint_positions")) HandleSetJointPositionsCommand(Message);
	else if (Message.Command == TEXT("emergency_stop")) HandleEmergencyStopCommand(Message);
	else if (Message.Command == TEXT("clear_scene")) HandleClearSceneCommand(Message);
	else if (Message.Command == TEXT("create_widget")) HandleCreateWidgetCommand(Message);
	else if (Message.Command == TEXT("update_widget_data")) HandleUpdateWidgetDataCommand(Message);
	else if (Message.Command == TEXT("get_system_status")) HandleGetSystemStatusCommand(Message);
	else
	{
		SendError(Message.Command, EROAErrorCode::ERR_INVALID_COMMAND, 
			FString::Printf(TEXT("Unknown command: %s"), *Message.Command));
	}
}

void FROANetworkServer::SendQueuedMessages()
{
	FROAMessage Message;
	while (OutgoingMessages.Dequeue(Message))
	{
		if (ClientSocket && ClientSocket->GetConnectionState() == SCS_Connected)
		{
			FString JsonString = Message.ToJsonString() + TEXT("\n");
			FTCHARToUTF8 Converter(*JsonString);
			
			int32 BytesSent = 0;
			ClientSocket->Send((uint8*)Converter.Get(), Converter.Length(), BytesSent);
			
			if (BytesSent > 0)
			{
				UE_LOG(LogTemp, Verbose, TEXT("ROA Network: Sent %d bytes"), BytesSent);
			}
		}
	}
}

void FROANetworkServer::CloseClientConnection()
{
	if (ClientSocket)
	{
		ClientSocket->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(ClientSocket);
		ClientSocket = nullptr;
		SessionId.Empty();
		ReceiveBuffer.Empty();
	}
}

// ============================================================================
// Command Handlers
// ============================================================================

void FROANetworkServer::HandleConnectCommand(const FROAMessage& Message)
{
	SessionId = FGuid::NewGuid().ToString();
	
	TSharedPtr<FJsonObject> Response = MakeShared<FJsonObject>();
	Response->SetStringField(TEXT("status"), TEXT("success"));
	Response->SetStringField(TEXT("session_id"), SessionId);
	Response->SetStringField(TEXT("server_version"), TEXT("1.0.0"));
	
	SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("connect"), Response));
	UE_LOG(LogTemp, Log, TEXT("ROA Network: Session started: %s"), *SessionId);
}

void FROANetworkServer::HandleDisconnectCommand(const FROAMessage& Message)
{
	SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("disconnect"), nullptr));
}

void FROANetworkServer::HandleHeartbeatCommand(const FROAMessage& Message)
{
	SendResponse(FROAMessageUtils::CreateEvent(TEXT("heartbeat"), Message.Payload));
}

void FROANetworkServer::HandleSpawnRobotCommand(const FROAMessage& Message)
{
	if (!WorldManager.IsValid())
	{
		SendError(TEXT("spawn_robot"), EROAErrorCode::ERR_SPAWN_FAILED, TEXT("World manager unavailable"));
		return;
	}

	FROASpawnRobotRequest Request;
	if (!FROASpawnRobotRequest::FromJson(Message.Payload, Request))
	{
		SendError(TEXT("spawn_robot"), EROAErrorCode::ERR_INVALID_PAYLOAD, TEXT("Invalid request"));
		return;
	}

	FString ErrorMessage;
	if (WorldManager->SpawnRobot(Request, ErrorMessage))
	{
		TSharedPtr<FJsonObject> Response = MakeShared<FJsonObject>();
		Response->SetStringField(TEXT("robot_id"), Request.RobotId);
		SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("spawn_robot"), Response));
	}
	else
	{
		SendError(TEXT("spawn_robot"), EROAErrorCode::ERR_SPAWN_FAILED, ErrorMessage);
	}
}

void FROANetworkServer::HandleDespawnRobotCommand(const FROAMessage& Message)
{
	if (!WorldManager.IsValid() || !Message.Payload.IsValid()) return;

	FString RobotId;
	if (Message.Payload->TryGetStringField(TEXT("robot_id"), RobotId))
	{
		if (WorldManager->DespawnRobot(RobotId))
		{
			SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("despawn_robot"), nullptr));
		}
		else
		{
			SendError(TEXT("despawn_robot"), EROAErrorCode::ERR_ROBOT_NOT_FOUND, TEXT("Robot not found"));
		}
	}
}

void FROANetworkServer::HandleGetRobotStateCommand(const FROAMessage& Message)
{
	if (!WorldManager.IsValid() || !Message.Payload.IsValid()) return;

	FString RobotId;
	if (Message.Payload->TryGetStringField(TEXT("robot_id"), RobotId))
	{
		FROARobotState State;
		if (WorldManager->GetRobotState(RobotId, State))
		{
			SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("get_robot_state"), State.ToJson()));
		}
		else
		{
			SendError(TEXT("get_robot_state"), EROAErrorCode::ERR_ROBOT_NOT_FOUND, TEXT("Robot not found"));
		}
	}
}

void FROANetworkServer::HandleListRobotsCommand(const FROAMessage& Message)
{
	if (!WorldManager.IsValid()) return;

	TArray<FString> RobotIds = WorldManager->GetAllRobotIds();
	
	TSharedPtr<FJsonObject> Response = MakeShared<FJsonObject>();
	TArray<TSharedPtr<FJsonValue>> RobotsArray;
	
	for (const FString& Id : RobotIds)
	{
		TSharedPtr<FJsonObject> Robot = MakeShared<FJsonObject>();
		Robot->SetStringField(TEXT("robot_id"), Id);
		Robot->SetStringField(TEXT("status"), TEXT("active"));
		RobotsArray.Add(MakeShared<FJsonValueObject>(Robot));
	}
	
	Response->SetArrayField(TEXT("robots"), RobotsArray);
	SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("list_robots"), Response));
}

void FROANetworkServer::HandleMoveRobotCommand(const FROAMessage& Message)
{
	SendError(TEXT("move_robot"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleSetJointPositionsCommand(const FROAMessage& Message)
{
	if (!WorldManager.IsValid() || !Message.Payload.IsValid()) return;

	FROAJointCommand Command;
	if (FROAJointCommand::FromJson(Message.Payload, Command))
	{
		if (WorldManager->SetJointPositions(Command))
		{
			SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("set_joint_positions"), nullptr));
		}
		else
		{
			SendError(TEXT("set_joint_positions"), EROAErrorCode::ERR_ROBOT_NOT_FOUND, TEXT("Robot not found"));
		}
	}
}

void FROANetworkServer::HandleSetJointVelocitiesCommand(const FROAMessage& Message)
{
	SendError(TEXT("set_joint_velocities"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleEmergencyStopCommand(const FROAMessage& Message)
{
	if (!WorldManager.IsValid() || !Message.Payload.IsValid()) return;

	FString RobotId;
	if (Message.Payload->TryGetStringField(TEXT("robot_id"), RobotId))
	{
		if (WorldManager->EmergencyStop(RobotId))
		{
			SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("emergency_stop"), nullptr));
		}
	}
}

void FROANetworkServer::HandleSetPhysicsParametersCommand(const FROAMessage& Message)
{
	SendError(TEXT("set_physics_parameters"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleEnableCollisionCommand(const FROAMessage& Message)
{
	SendError(TEXT("enable_collision"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleGetCollisionStatusCommand(const FROAMessage& Message)
{
	SendError(TEXT("get_collision_status"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleAddObstacleCommand(const FROAMessage& Message)
{
	SendError(TEXT("add_obstacle"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleRemoveObstacleCommand(const FROAMessage& Message)
{
	SendError(TEXT("remove_obstacle"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleClearSceneCommand(const FROAMessage& Message)
{
	if (WorldManager.IsValid())
	{
		WorldManager->ClearScene();
		SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("clear_scene"), nullptr));
	}
}

void FROANetworkServer::HandleSetCameraViewCommand(const FROAMessage& Message)
{
	SendError(TEXT("set_camera_view"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleCaptureScreenshotCommand(const FROAMessage& Message)
{
	SendError(TEXT("capture_screenshot"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleCreateWidgetCommand(const FROAMessage& Message)
{
	if (!WidgetManager.IsValid() || !WorldManager.IsValid() || !Message.Payload.IsValid())
	{
		SendError(TEXT("create_widget"), EROAErrorCode::ERR_WIDGET_ERROR, TEXT("Manager unavailable"));
		return;
	}

	FString WidgetId, WidgetType, RobotId;
	Message.Payload->TryGetStringField(TEXT("widget_id"), WidgetId);
	Message.Payload->TryGetStringField(TEXT("widget_type"), WidgetType);
	Message.Payload->TryGetStringField(TEXT("robot_id"), RobotId);

	AROARobotActor* Robot = WorldManager->GetRobotActor(RobotId);
	if (!Robot)
	{
		SendError(TEXT("create_widget"), EROAErrorCode::ERR_ROBOT_NOT_FOUND, TEXT("Robot not found"));
		return;
	}

	FString CreatedId = WidgetManager->CreateWidget(WidgetType, Robot, nullptr);
	if (!CreatedId.IsEmpty())
	{
		TSharedPtr<FJsonObject> Response = MakeShared<FJsonObject>();
		Response->SetStringField(TEXT("widget_id"), CreatedId);
		SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("create_widget"), Response));
	}
}

void FROANetworkServer::HandleUpdateWidgetDataCommand(const FROAMessage& Message)
{
	if (!WidgetManager.IsValid() || !Message.Payload.IsValid()) return;

	FString WidgetId;
	const TSharedPtr<FJsonObject>* DataPtr;
	
	if (Message.Payload->TryGetStringField(TEXT("widget_id"), WidgetId) &&
		Message.Payload->TryGetObjectField(TEXT("data"), DataPtr))
	{
		if (WidgetManager->UpdateWidgetData(WidgetId, *DataPtr))
		{
			SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("update_widget_data"), nullptr));
		}
	}
}

void FROANetworkServer::HandleImportRobotFileCommand(const FROAMessage& Message)
{
	SendError(TEXT("import_robot_file"), EROAErrorCode::ERR_INVALID_COMMAND, TEXT("Not implemented"));
}

void FROANetworkServer::HandleGetSystemStatusCommand(const FROAMessage& Message)
{
	TSharedPtr<FJsonObject> Response = MakeShared<FJsonObject>();
	Response->SetStringField(TEXT("ue5_version"), TEXT("5.6.0"));
	Response->SetStringField(TEXT("plugin_version"), TEXT("1.0.0"));
	Response->SetNumberField(TEXT("active_robots"), WorldManager.IsValid() ? WorldManager->GetAllRobotIds().Num() : 0);
	Response->SetBoolField(TEXT("ros2_connected"), true);
	
	SendResponse(FROAMessageUtils::CreateSuccessResponse(TEXT("get_system_status"), Response));
}

void FROANetworkServer::SendResponse(const FROAMessage& Response)
{
	SendMessage(Response);
}

void FROANetworkServer::SendError(const FString& Command, EROAErrorCode ErrorCode, const FString& ErrorMessage)
{
	SendMessage(FROAMessageUtils::CreateErrorResponse(Command, ErrorCode, ErrorMessage));
}
