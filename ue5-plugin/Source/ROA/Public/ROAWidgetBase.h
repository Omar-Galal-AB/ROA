// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "ROAMessageTypes.h"
#include "ROAWidgetBase.generated.h"

// Forward declarations
class FROANetworkServer;
class AROARobotActor;

/**
 * Base class for all ROA widgets
 * Provides common functionality for robot monitoring and control
 */
UCLASS(Abstract, Blueprintable)
class ROA_API UROAWidgetBase : public UUserWidget
{
	GENERATED_BODY()

public:
	UROAWidgetBase(const FObjectInitializer& ObjectInitializer);

	/**
	 * Initialize widget with robot actor
	 * @param InRobotActor - Robot actor to monitor/control
	 * @return True if successful
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	virtual bool InitializeWithRobot(AROARobotActor* InRobotActor);

	/**
	 * Get associated robot actor
	 */
	UFUNCTION(BlueprintPure, Category = "ROA")
	AROARobotActor* GetRobotActor() const { return RobotActor; }

	/**
	 * Get robot ID
	 */
	UFUNCTION(BlueprintPure, Category = "ROA")
	FString GetRobotId() const;

	/**
	 * Set network server for sending events
	 */
	void SetNetworkServer(TSharedPtr<FROANetworkServer> InNetworkServer);

	/**
	 * Update widget data (called every frame if needed)
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	virtual void UpdateWidgetData();

	/**
	 * Enable/disable ROA widget functionality
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	virtual void SetWidgetEnabled(bool bEnabled);

	/**
	 * Check if ROA widget is enabled
	 */
	UFUNCTION(BlueprintPure, Category = "ROA")
	bool IsROAWidgetEnabled() const { return bROAEnabled; }

protected:
	// UUserWidget interface
	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;
	virtual void NativeDestruct() override;

	/**
	 * Send widget event to network server
	 */
	void SendWidgetEvent(const FString& EventType, const TSharedPtr<FJsonObject>& EventData);

	/** Associated robot actor */
	UPROPERTY(BlueprintReadOnly, Category = "ROA")
	AROARobotActor* RobotActor;

	/** Widget unique ID */
	UPROPERTY(BlueprintReadOnly, Category = "ROA")
	FString WidgetId;

	/** Is ROA widget enabled */
	UPROPERTY(BlueprintReadOnly, Category = "ROA")
	bool bROAEnabled;

	/** Network server reference */
	TWeakPtr<FROANetworkServer> NetworkServer;

	/** Update interval in seconds */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	float UpdateInterval;

	/** Time since last update */
	float TimeSinceLastUpdate;
};
