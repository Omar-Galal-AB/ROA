// Copyright ROA Development Team. All Rights Reserved.

#include "ROAWidgetBase.h"
#include "ROANetworkServer.h"
#include "ROARobotActor.h"

UROAWidgetBase::UROAWidgetBase(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
	, RobotActor(nullptr)
	, bROAEnabled(true)
	, UpdateInterval(0.033f) // ~30 Hz default
	, TimeSinceLastUpdate(0.0f)
{
	// Generate unique widget ID
	WidgetId = FGuid::NewGuid().ToString();
}

bool UROAWidgetBase::InitializeWithRobot(AROARobotActor* InRobotActor)
{
	if (!InRobotActor)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Widget Base: Cannot initialize with null robot actor"));
		return false;
	}

	RobotActor = InRobotActor;
	
	UE_LOG(LogTemp, Log, TEXT("ROA Widget Base: Initialized widget '%s' with robot '%s'"), 
		*WidgetId, *RobotActor->GetRobotId());
	
	return true;
}

FString UROAWidgetBase::GetRobotId() const
{
	return RobotActor ? RobotActor->GetRobotId() : FString();
}

void UROAWidgetBase::SetNetworkServer(TSharedPtr<FROANetworkServer> InNetworkServer)
{
	NetworkServer = InNetworkServer;
}

void UROAWidgetBase::UpdateWidgetData()
{
	// Base implementation - override in derived classes
	// This is called periodically to update widget display
}

void UROAWidgetBase::SetWidgetEnabled(bool bEnabled)
{
	bROAEnabled = bEnabled;
	SetIsEnabled(bEnabled);
}

void UROAWidgetBase::NativeConstruct()
{
	Super::NativeConstruct();
	
	TimeSinceLastUpdate = 0.0f;
	
	UE_LOG(LogTemp, Log, TEXT("ROA Widget Base: Widget '%s' constructed"), *WidgetId);
}

void UROAWidgetBase::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	if (!bROAEnabled || !RobotActor)
	{
		return;
	}

	// Update widget data at specified interval
	TimeSinceLastUpdate += InDeltaTime;
	if (TimeSinceLastUpdate >= UpdateInterval)
	{
		UpdateWidgetData();
		TimeSinceLastUpdate = 0.0f;
	}
}

void UROAWidgetBase::NativeDestruct()
{
	Super::NativeDestruct();
	
	UE_LOG(LogTemp, Log, TEXT("ROA Widget Base: Widget '%s' destructed"), *WidgetId);
}

void UROAWidgetBase::SendWidgetEvent(const FString& EventType, const TSharedPtr<FJsonObject>& EventData)
{
	TSharedPtr<FROANetworkServer> Server = NetworkServer.Pin();
	if (!Server.IsValid())
	{
		return;
	}

	// Create event payload
	TSharedPtr<FJsonObject> Payload = MakeShared<FJsonObject>();
	Payload->SetStringField(TEXT("widget_id"), WidgetId);
	Payload->SetStringField(TEXT("event_type"), EventType);
	
	if (RobotActor)
	{
		Payload->SetStringField(TEXT("robot_id"), RobotActor->GetRobotId());
	}
	
	if (EventData.IsValid())
	{
		Payload->SetObjectField(TEXT("data"), EventData);
	}

	// Create and send event message
	FROAMessage Event = FROAMessageUtils::CreateEvent(TEXT("widget_event"), Payload);
	Server->SendMessage(Event);
	
	UE_LOG(LogTemp, Verbose, TEXT("ROA Widget Base: Sent widget event '%s' from widget '%s'"), 
		*EventType, *WidgetId);
}
