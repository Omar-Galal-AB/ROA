// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "HAL/Runnable.h"
#include "HAL/RunnableThread.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "Containers/Queue.h"
#include "ROAMessageTypes.h"

// Forward declarations
class FROAWorldManager;
class FROAWidgetManager;

/**
 * Network CLIENT that connects to Python command server in WSL
 * Uses rosbridge-style JSON message protocol over TCP
 */
class ROA_API FROANetworkServer : public FRunnable
{
public:
	FROANetworkServer(int32 Port = 9876);
	virtual ~FROANetworkServer();

	/** Connect to WSL command server */
	bool ConnectToServer(const FString& Host, int32 Port);
	
	/** Disconnect from server */
	void DisconnectFromServer();
	
	/** Check if connected */
	bool IsRunning() const { return bIsRunning.Load(); }
	bool IsConnected() const { return ClientSocket != nullptr && bIsRunning.Load(); }

	/** Set manager references */
	void SetWorldManager(TSharedPtr<FROAWorldManager> InWorldManager);
	void SetWidgetManager(TSharedPtr<FROAWidgetManager> InWidgetManager);

	/** Send message to server */
	bool SendMessage(const FROAMessage& Message);

	// FRunnable interface
	virtual bool Init() override;
	virtual uint32 Run() override;
	virtual void Stop() override;
	virtual void Exit() override;

private:
	FString ServerHost;
	int32 ServerPort;
	FSocket* ClientSocket;
	FRunnableThread* ServerThread;
	TAtomic<bool> bIsRunning;
	TAtomic<bool> bStopRequested;
	
	TSharedPtr<FROAWorldManager> WorldManager;
	TSharedPtr<FROAWidgetManager> WidgetManager;
	
	FString SessionId;
	TArray<uint8> ReceiveBuffer;
	FCriticalSection MessageQueueMutex;
	TQueue<FROAMessage> OutgoingMessages;

	bool ReceiveData();
	void ProcessMessage(const FROAMessage& Message);
	void SendQueuedMessages();
	void CloseClientConnection();

	// Command handlers
	void HandleConnectCommand(const FROAMessage& Message);
	void HandleDisconnectCommand(const FROAMessage& Message);
	void HandleHeartbeatCommand(const FROAMessage& Message);
	void HandleSpawnRobotCommand(const FROAMessage& Message);
	void HandleDespawnRobotCommand(const FROAMessage& Message);
	void HandleGetRobotStateCommand(const FROAMessage& Message);
	void HandleListRobotsCommand(const FROAMessage& Message);
	void HandleMoveRobotCommand(const FROAMessage& Message);
	void HandleSetJointPositionsCommand(const FROAMessage& Message);
	void HandleSetJointVelocitiesCommand(const FROAMessage& Message);
	void HandleEmergencyStopCommand(const FROAMessage& Message);
	void HandleSetPhysicsParametersCommand(const FROAMessage& Message);
	void HandleEnableCollisionCommand(const FROAMessage& Message);
	void HandleGetCollisionStatusCommand(const FROAMessage& Message);
	void HandleAddObstacleCommand(const FROAMessage& Message);
	void HandleRemoveObstacleCommand(const FROAMessage& Message);
	void HandleClearSceneCommand(const FROAMessage& Message);
	void HandleSetCameraViewCommand(const FROAMessage& Message);
	void HandleCaptureScreenshotCommand(const FROAMessage& Message);
	void HandleCreateWidgetCommand(const FROAMessage& Message);
	void HandleUpdateWidgetDataCommand(const FROAMessage& Message);
	void HandleImportRobotFileCommand(const FROAMessage& Message);
	void HandleGetSystemStatusCommand(const FROAMessage& Message);

	void SendResponse(const FROAMessage& Response);
	void SendError(const FString& Command, EROAErrorCode ErrorCode, const FString& ErrorMessage);
};
