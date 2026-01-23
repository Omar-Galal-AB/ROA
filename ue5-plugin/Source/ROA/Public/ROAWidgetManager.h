// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "ROAWidgetBase.h"
#include "ROARobotActor.h"

// Forward declarations
class FROANetworkServer;
class UROARobotControlPanel;
class UROARobotStatusMonitor;

/**
 * Widget Manager
 * Handles creation and management of ROA widgets
 */
class FROAWidgetManager
{
public:
	FROAWidgetManager();
	~FROAWidgetManager();

	/**
	 * Set network server reference
	 */
	void SetNetworkServer(TSharedPtr<FROANetworkServer> InNetworkServer);

	/**
	 * Create widget for robot
	 * @param WidgetType - Type of widget to create ("control_panel", "status_monitor")
	 * @param RobotActor - Robot to associate with widget
	 * @param WidgetClass - Blueprint class for widget (optional)
	 * @return Widget ID if successful
	 */
	FString CreateWidget(const FString& WidgetType, AROARobotActor* RobotActor, UClass* WidgetClass = nullptr);

	/**
	 * Destroy widget by ID
	 * @param WidgetId - Widget ID to destroy
	 * @return True if successful
	 */
	bool DestroyWidget(const FString& WidgetId);

	/**
	 * Get widget by ID
	 * @param WidgetId - Widget ID
	 * @return Widget pointer or nullptr
	 */
	UROAWidgetBase* GetWidget(const FString& WidgetId) const;

	/**
	 * Get all widgets for a robot
	 * @param RobotId - Robot ID
	 * @return Array of widget pointers
	 */
	TArray<UROAWidgetBase*> GetWidgetsForRobot(const FString& RobotId) const;

	/**
	 * Update widget data by ID
	 * @param WidgetId - Widget ID
	 * @param Data - Data to update
	 * @return True if successful
	 */
	bool UpdateWidgetData(const FString& WidgetId, const TSharedPtr<FJsonObject>& Data);

	/**
	 * Cleanup all widgets
	 */
	void CleanupAllWidgets();

private:
	/** Widget registry (Widget ID ? Widget) */
	TMap<FString, UROAWidgetBase*> Widgets;

	/** Robot to widgets mapping */
	TMap<FString, TArray<FString>> RobotWidgets;

	/** Network server reference */
	TWeakPtr<FROANetworkServer> NetworkServer;

	/** Critical section for thread safety */
	mutable FCriticalSection WidgetMutex;

	/**
	 * Get default widget class for type
	 */
	UClass* GetDefaultWidgetClass(const FString& WidgetType);

	/**
	 * Add widget to viewport
	 */
	bool AddWidgetToViewport(UROAWidgetBase* Widget);
};
