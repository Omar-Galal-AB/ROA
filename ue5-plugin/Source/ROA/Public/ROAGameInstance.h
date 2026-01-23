// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "ROAGameInstance.generated.h"

/**
 * ROA Game Instance
 * Manages ROS2 connection lifecycle tied to world/level loading
 * Similar to ROSIntegrationGameInstance pattern
 */
UCLASS()
class ROA_API UROAGameInstance : public UGameInstance
{
GENERATED_BODY()

public:
virtual void Init() override;
virtual void Shutdown() override;

UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ROA|ROS2")
bool bConnectToROS2 = true;

UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ROA|ROS2")
FString ROSBridgeHost = TEXT("127.0.0.1");

UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "ROA|ROS2")
int32 ROSBridgePort = 9090;

UPROPERTY(BlueprintReadOnly, Category = "ROA|ROS2")
bool bConnectedToROS2 = false;
};
