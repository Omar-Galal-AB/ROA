// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"
#include "Factories/Factory.h"
#include "Framework/Commands/Commands.h"
#include "Framework/MultiBox/MultiBoxExtender.h"

// Forward declarations
class FUICommandList;
class FExtender;

/**
 * ROA Editor Commands
 */
class FROACommands : public TCommands<FROACommands>
{
public:
	FROACommands()
		: TCommands<FROACommands>(
			TEXT("ROACommands"),
			NSLOCTEXT("Contexts", "ROACommands", "ROA Plugin"),
			NAME_None,
			FAppStyle::GetAppStyleSetName())
	{
	}

	virtual void RegisterCommands() override;

	TSharedPtr<FUICommandInfo> AssembleRobot;
	TSharedPtr<FUICommandInfo> ListRobots;
};

/**
 * ROA (Robot Operator Assistant) Plugin Module
 * 
 * Main module for the ROA UE5 Plugin that provides:
 * - ROS2 integration via network bridge
 * - Robot spawning and control
 * - Physics simulation
 * - Widget system for robot monitoring
 * - Communication with Python Webthread component
 * - FTI (File Type Integration) for URDF/XACRO import
 */
class FROAModule : public IModuleInterface
{
public:

	/** IModuleInterface implementation */
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
	
	/**
	 * Singleton-like access to this module's interface.
	 * Beware of calling this during the shutdown phase, though. Your module might have been unloaded already.
	 *
	 * @return Returns singleton instance, loading the module on demand if needed
	 */
	static inline FROAModule& Get()
	{
		return FModuleManager::LoadModuleChecked<FROAModule>("ROA");
	}

	/**
	 * Checks to see if this module is loaded and ready.
	 *
	 * @return True if the module is loaded and ready to use
	 */
	static inline bool IsAvailable()
	{
		return FModuleManager::Get().IsModuleLoaded("ROA");
	}

	/**
	 * Get widget manager
	 */
	TSharedPtr<class FROAWidgetManager> GetWidgetManager() const { return WidgetManager; }

public:
	/** Static command handlers - can be called from menus */
	static void OnAssembleRobotClicked();
	static void OnListRobotsClicked();
	static void OnAssembleAllClicked();
	static void OnResetRobotsClicked();
	static void OnPrepareForROCClicked();
	
	/** FTI (File Type Integration) menu handlers */
	static void OnImportURDFClicked();
	static void OnImportXACROClicked();
	static void OnImportDAEClicked();
	static void OnImportUSDClicked();
	static void OnFTISettingsClicked();
	
	// Blueprint factory functions
	static void OnCreateRobotBlueprintClicked();
	static void OnSpawnRobotClicked();
	static void OnListBlueprintsClicked();
	
	static void ExecutePythonCommand(const FString& PythonCode);

private:
	/** Register file type integration (URDF, XACRO import) */
	void RegisterFileTypeIntegration();
	
	/** Unregister file type integration */
	void UnregisterFileTypeIntegration();
	
	/** Register menus and toolbar buttons */
	void RegisterMenus();
	
	/** Unregister menus */
	void UnregisterMenus();
	
	/** Build ROA menu - static to avoid lambda capture issues */
	static void BuildROAMenu(class UToolMenu* Menu);
	
	/** Build FTI submenu */
	static void BuildFTISubmenu(class UToolMenu* Menu);

	
	/** Handle to the network server */
	TSharedPtr<class FROANetworkServer> NetworkServer;
	
	/** Handle to the world manager */
	TSharedPtr<class FROAWorldManager> WorldManager;

	/** Handle to the widget manager */
	TSharedPtr<class FROAWidgetManager> WidgetManager;
	
	/** Registered asset factories for FTI */
	TArray<TObjectPtr<UFactory>> RegisteredFactories;
	
	/** UI Command list */
	
	/** WSL bridge process handle (auto-started on plugin load) */
	FProcHandle WSLBridgeProcess;
	
	/** Start WSL ROS2 bridge automatically */
	void StartWSLBridge();
	
	/** Stop WSL ROS2 bridge */
	void StopWSLBridge();
};
