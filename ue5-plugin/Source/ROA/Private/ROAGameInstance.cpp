// Copyright ROA Development Team. All Rights Reserved.

#include "ROAGameInstance.h"
#include "Components/ROS2/ROS2Context.h"

void UROAGameInstance::Init()
{
Super::Init();

UE_LOG(LogTemp, Log, TEXT("ROA GameInstance: Initializing..."));

if (bConnectToROS2)
{
// Configure ROS2 bridge server
FROS2Context::Get().SetBridgeServer(ROSBridgeHost, ROSBridgePort);

// Initialize ROS2 connection (expects bridge server already running)
if (FROS2Context::Get().Initialize())
{
bConnectedToROS2 = true;
UE_LOG(LogTemp, Warning, TEXT("ROA GameInstance: ✅ Connected to rosbridge at %s:%d"), *ROSBridgeHost, ROSBridgePort);
}
else
{
bConnectedToROS2 = false;
UE_LOG(LogTemp, Error, TEXT("ROA GameInstance: ❌ Failed to connect to rosbridge at %s:%d"), *ROSBridgeHost, ROSBridgePort);
UE_LOG(LogTemp, Warning, TEXT("ROA GameInstance: Make sure bridge server is running. Run in WSL: roa start"));
}
}
else
{
UE_LOG(LogTemp, Warning, TEXT("ROA GameInstance: ROS2 connection disabled (bConnectToROS2 = false)"));
}
}

void UROAGameInstance::Shutdown()
{
UE_LOG(LogTemp, Log, TEXT("ROA GameInstance: Shutting down..."));

if (bConnectedToROS2)
{
FROS2Context::Get().Shutdown();
bConnectedToROS2 = false;
}

Super::Shutdown();
}
