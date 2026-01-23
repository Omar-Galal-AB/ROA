// Copyright ROA Development Team. All Rights Reserved.

#include "ROAWidgetManager.h"
#include "ROANetworkServer.h"
#include "ROARobotControlPanel.h"
#include "ROARobotStatusMonitor.h"
#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"

FROAWidgetManager::FROAWidgetManager()
{
	UE_LOG(LogTemp, Log, TEXT("ROA Widget Manager: Created"));
}

FROAWidgetManager::~FROAWidgetManager()
{
	CleanupAllWidgets();
	UE_LOG(LogTemp, Log, TEXT("ROA Widget Manager: Destroyed"));
}

void FROAWidgetManager::SetNetworkServer(TSharedPtr<FROANetworkServer> InNetworkServer)
{
	NetworkServer = InNetworkServer;
}

FString FROAWidgetManager::CreateWidget(const FString& WidgetType, AROARobotActor* RobotActor, UClass* WidgetClass)
{
	FScopeLock Lock(&WidgetMutex);

	if (!RobotActor)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Widget Manager: Cannot create widget - null robot actor"));
		return FString();
	}

	UWorld* World = RobotActor->GetWorld();
	if (!World)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Widget Manager: Cannot create widget - null world"));
		return FString();
	}

	// Get widget class
	UClass* ClassToUse = WidgetClass ? WidgetClass : GetDefaultWidgetClass(WidgetType);
	if (!ClassToUse)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Widget Manager: Unknown widget type: %s"), *WidgetType);
		return FString();
	}

	// Create widget
	UROAWidgetBase* Widget = ::CreateWidget<UROAWidgetBase>(World, ClassToUse);
	if (!Widget)
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Widget Manager: Failed to create widget of type: %s"), *WidgetType);
		return FString();
	}

	// Initialize widget with robot
	if (!Widget->InitializeWithRobot(RobotActor))
	{
		Widget->RemoveFromParent();
		UE_LOG(LogTemp, Error, TEXT("ROA Widget Manager: Failed to initialize widget with robot"));
		return FString();
	}

	// Set network server
	Widget->SetNetworkServer(NetworkServer.Pin());

	// Add to viewport
	if (!AddWidgetToViewport(Widget))
	{
		Widget->RemoveFromParent();
		UE_LOG(LogTemp, Error, TEXT("ROA Widget Manager: Failed to add widget to viewport"));
		return FString();
	}

	// Store widget
	FString WidgetId = Widget->GetName();
	Widgets.Add(WidgetId, Widget);

	// Add to robot widgets mapping
	FString RobotId = RobotActor->GetRobotId();
	if (!RobotWidgets.Contains(RobotId))
	{
		RobotWidgets.Add(RobotId, TArray<FString>());
	}
	RobotWidgets[RobotId].Add(WidgetId);

	UE_LOG(LogTemp, Log, TEXT("ROA Widget Manager: Created widget '%s' of type '%s' for robot '%s'"),
		*WidgetId, *WidgetType, *RobotId);

	return WidgetId;
}

bool FROAWidgetManager::DestroyWidget(const FString& WidgetId)
{
	FScopeLock Lock(&WidgetMutex);

	UROAWidgetBase** WidgetPtr = Widgets.Find(WidgetId);
	if (!WidgetPtr || !*WidgetPtr)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Widget Manager: Widget '%s' not found"), *WidgetId);
		return false;
	}

	UROAWidgetBase* Widget = *WidgetPtr;
	FString RobotId = Widget->GetRobotId();

	// Remove from viewport
	Widget->RemoveFromParent();

	// Remove from mappings
	Widgets.Remove(WidgetId);
	if (RobotWidgets.Contains(RobotId))
	{
		RobotWidgets[RobotId].Remove(WidgetId);
		if (RobotWidgets[RobotId].Num() == 0)
		{
			RobotWidgets.Remove(RobotId);
		}
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Widget Manager: Destroyed widget '%s'"), *WidgetId);
	return true;
}

UROAWidgetBase* FROAWidgetManager::GetWidget(const FString& WidgetId) const
{
	FScopeLock Lock(&WidgetMutex);

	UROAWidgetBase* const* WidgetPtr = Widgets.Find(WidgetId);
	return WidgetPtr ? *WidgetPtr : nullptr;
}

TArray<UROAWidgetBase*> FROAWidgetManager::GetWidgetsForRobot(const FString& RobotId) const
{
	FScopeLock Lock(&WidgetMutex);

	TArray<UROAWidgetBase*> Result;

	const TArray<FString>* WidgetIds = RobotWidgets.Find(RobotId);
	if (WidgetIds)
	{
		for (const FString& WidgetId : *WidgetIds)
		{
			UROAWidgetBase* Widget = GetWidget(WidgetId);
			if (Widget)
			{
				Result.Add(Widget);
			}
		}
	}

	return Result;
}

bool FROAWidgetManager::UpdateWidgetData(const FString& WidgetId, const TSharedPtr<FJsonObject>& Data)
{
	UROAWidgetBase* Widget = GetWidget(WidgetId);
	if (!Widget || !Data.IsValid())
	{
		return false;
	}

	// Force update widget data
	Widget->UpdateWidgetData();

	UE_LOG(LogTemp, Verbose, TEXT("ROA Widget Manager: Updated widget '%s' data"), *WidgetId);
	return true;
}

void FROAWidgetManager::CleanupAllWidgets()
{
	FScopeLock Lock(&WidgetMutex);

	for (auto& Pair : Widgets)
	{
		if (Pair.Value)
		{
			Pair.Value->RemoveFromParent();
		}
	}

	Widgets.Empty();
	RobotWidgets.Empty();

	UE_LOG(LogTemp, Log, TEXT("ROA Widget Manager: Cleaned up all widgets"));
}

UClass* FROAWidgetManager::GetDefaultWidgetClass(const FString& WidgetType)
{
	// Map widget types to classes
	if (WidgetType == TEXT("control_panel"))
	{
		return UROARobotControlPanel::StaticClass();
	}
	else if (WidgetType == TEXT("status_monitor"))
	{
		return UROARobotStatusMonitor::StaticClass();
	}

	// TODO: Add more widget types as needed

	return nullptr;
}

bool FROAWidgetManager::AddWidgetToViewport(UROAWidgetBase* Widget)
{
	if (!Widget)
	{
		return false;
	}

	// Add to viewport
	Widget->AddToViewport();

	return true;
}
