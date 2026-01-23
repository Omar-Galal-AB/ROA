// Copyright ROA Development Team. All Rights Reserved.

#include "ROAModule.h"
#include "ROANetworkServer.h"
#include "ROAWorldManager.h"
#include "ROAWidgetManager.h"
#include "ROAURDFFactory.h"
#include "ROAFTIImportFactory.h"
#include "Components/ROS2/ROS2PublisherComponent.h"
#include "Components/ROS2/ROS2Context.h"
#include "Core.h"
#include "Modules/ModuleManager.h"
#include "Interfaces/IPluginManager.h"
#include "AssetToolsModule.h"
#include "Misc/Paths.h"
#include "HAL/PlatformProcess.h"

// Menu and toolbar includes
#include "ToolMenus.h"
#include "Framework/Commands/UICommandList.h"
#include "Framework/Commands/UIAction.h"
#include "LevelEditor.h"
#include "DesktopPlatformModule.h"
#include "IDesktopPlatform.h"
#include "Styling/AppStyle.h"
#include "Framework/Application/SlateApplication.h"

// Python scripting
#include "IPythonScriptPlugin.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <Windows.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

#define LOCTEXT_NAMESPACE "FROAModule"

// ============================================================================
// FROACommands Implementation
// ============================================================================

void FROACommands::RegisterCommands()
{
	UI_COMMAND(AssembleRobot, "Assemble Robot", "Assemble imported robot from hierarchy JSON", EUserInterfaceActionType::Button, FInputChord());
	UI_COMMAND(ListRobots, "List Robots", "List all robots in the scene", EUserInterfaceActionType::Button, FInputChord());
}

// ============================================================================
// FROAModule Implementation
// ============================================================================

void FROAModule::StartupModule()
{
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Initializing Robot Operator Assistant Plugin"));
	
#if ROA_NATIVE_ROS2
	FString PluginDir = FPaths::Combine(FPaths::ProjectPluginsDir(), TEXT("ROA_PlugIn"));
	FString ROS2BinPath = FPaths::Combine(PluginDir, TEXT("ThirdParty/rclcpp/bin"));
	FString FastDDSBinPath = FPaths::Combine(PluginDir, TEXT("ThirdParty/FastDDS/bin"));
	
	FPaths::NormalizeDirectoryName(ROS2BinPath);
	FPaths::NormalizeDirectoryName(FastDDSBinPath);

#if PLATFORM_WINDOWS
	SetDllDirectoryW(*ROS2BinPath);
	AddDllDirectory(*ROS2BinPath);
	AddDllDirectory(*FastDDSBinPath);
	
	FString CurrentPath = FPlatformMisc::GetEnvironmentVariable(TEXT("PATH"));
	FString NewPath = FString::Printf(TEXT("%s;%s;%s"), *ROS2BinPath, *FastDDSBinPath, *CurrentPath);
	FPlatformMisc::SetEnvironmentVar(TEXT("PATH"), *NewPath);
#endif
	
	UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: NATIVE ROS2 MODE ENABLED"));
#else
	UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: TCP BRIDGE MODE (rosbridge protocol)"));
#endif
	
	// Initialize World Manager
	WorldManager = MakeShared<FROAWorldManager>();
	if (WorldManager.IsValid())
	{
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: World Manager initialized"));
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Plugin: Failed to initialize World Manager"));
		return;
	}

	// Initialize Widget Manager
	WidgetManager = MakeShared<FROAWidgetManager>();
	if (WorldManager.IsValid())
	{
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Widget Manager initialized"));
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Plugin: Failed to initialize Widget Manager"));
		return;
	}
	
	// Initialize Network Server (for receiving commands from external clients)
	NetworkServer = MakeShared<FROANetworkServer>(9876);
	if (NetworkServer.IsValid())
	{
		NetworkServer->SetWorldManager(WorldManager);
		NetworkServer->SetWidgetManager(WidgetManager);
		WidgetManager->SetNetworkServer(NetworkServer);
		UROS2PublisherComponent::SetNetworkServer(NetworkServer);
		
		// Connect to WSL command server (CLIENT MODE)
                if (NetworkServer->ConnectToServer(TEXT("127.0.0.1"), 9876))
                {
                        UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Connected to command server on port 9876"));
                }
                else
                {
                        UE_LOG(LogTemp, Error, TEXT("ROA Plugin: Failed to connect to command server"));
                        UE_LOG(LogTemp, Warning, TEXT("Run in WSL: roa start"));
                }
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Network Server initialized"));
	}
	
	// Initialize ROS2 Context (rosbridge client in TCP mode, native rcl in native mode)
	// Configure bridge server address BEFORE initializing
	FROS2Context::Get().SetBridgeServer(TEXT("127.0.0.1"), 9090);
	
	// Initialize ROS2 context - this connects to rosbridge or initializes native ROS2
	if (FROS2Context::Get().Initialize())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: ROS2 Context initialized successfully"));
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: ROS2 Context initialization failed"));
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: Make sure rosbridge_server is running on WSL:"));
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: ros2 launch rosbridge_server rosbridge_websocket_launch.xml"));
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin:   OR: python3 roa_bridge_server.py"));
	}
	
	// Register FTI (File Type Integration)
	RegisterFileTypeIntegration();
	
	// Register menus and toolbar buttons
	RegisterMenus();
	
	// Start FTI heartbeat for lifecycle management
	// This keeps the FTI IPC service alive while UE5 is running
	UFTIConnection::RegisterClient();
	
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Startup complete"));
}

void FROAModule::ShutdownModule()
{
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Shutting down"));
	
	// CRITICAL: Unregister menus FIRST (before any other cleanup)
	// This prevents callbacks from trying to access destroyed objects
	UnregisterMenus();
	
	// Stop network server BEFORE ROS2 shutdown
	// Order matters: network might be sending ROS2 messages
	if (NetworkServer.IsValid())
	{
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Disconnecting network server"));
		NetworkServer->DisconnectFromServer();
		NetworkServer.Reset();
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Network server shut down"));
	}
	
	// Clean up widget manager BEFORE world manager
	// Widgets might be displaying world data
	if (WidgetManager.IsValid())
	{
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Cleaning up widgets"));
		WidgetManager->CleanupAllWidgets();
		WidgetManager.Reset();
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Widget manager shut down"));
	}
	
	// Clean up world manager (robots, actors, etc.)
	if (WorldManager.IsValid())
	{
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Cleaning up robots"));
		WorldManager->CleanupAllRobots();
		WorldManager.Reset();
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: World manager shut down"));
	}
	
	// Shutdown ROS2 Context AFTER network and world cleanup
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Shutting down ROS2 Context"));
	FROS2Context::Get().Shutdown();
	
	// Stop WSL bridge if running
	StopWSLBridge();
	
	// Deregister FTI client (removes heartbeat file)
	// Service will auto-shutdown if no other clients are active
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Deregistering FTI client"));
	UFTIConnection::DeregisterClient();
	
	// Unregister file type integration LAST
	// Factory objects might be used by editor until very end
	UnregisterFileTypeIntegration();
	
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Shutdown complete"));
}

void FROAModule::RegisterFileTypeIntegration()
{
#if WITH_EDITOR
	if (GIsEditor && !IsRunningCommandlet())
	{
		IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools").Get();
		
		TObjectPtr<UROAURDFFactory> URDFFactory = NewObject<UROAURDFFactory>();
		if (URDFFactory)
		{
			URDFFactory->AddToRoot();
			RegisteredFactories.Add(URDFFactory);
			UE_LOG(LogTemp, Log, TEXT("ROA Plugin: FTI - URDF file import registered"));
		}
		
		TObjectPtr<UROAXacroFactory> XacroFactory = NewObject<UROAXacroFactory>();
		if (XacroFactory)
		{
			XacroFactory->AddToRoot();
			RegisteredFactories.Add(XacroFactory);
			UE_LOG(LogTemp, Log, TEXT("ROA Plugin: FTI - XACRO file import registered"));
		}
	}
#endif
}

void FROAModule::UnregisterFileTypeIntegration()
{
#if WITH_EDITOR
	for (TObjectPtr<UFactory> Factory : RegisteredFactories)
	{
		if (Factory)
		{
			Factory->RemoveFromRoot();
		}
	}
	RegisteredFactories.Empty();
#endif
}

void FROAModule::StartWSLBridge()
{
	// Not used in TCP mode - user starts bridge manually on WSL
}

void FROAModule::StopWSLBridge()
{
	if (WSLBridgeProcess.IsValid())
	{
		FPlatformProcess::TerminateProc(WSLBridgeProcess, true);
		FPlatformProcess::CloseProc(WSLBridgeProcess);
		WSLBridgeProcess.Reset();
	}
}

// ============================================================================
// Menu Registration - Using static functions to avoid command binding issues
// ============================================================================

void FROAModule::RegisterMenus()
{
#if WITH_EDITOR
	// Register commands (for toolbar icon hints, etc.)
	FROACommands::Register();
	
	// Wait for ToolMenus to be initialized
	UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateLambda([]()
	{
		// Add ROA menu to main menu bar
		UToolMenu* Menu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu");
		FToolMenuSection& Section = Menu->AddSection("ROA", LOCTEXT("ROAMenuLabel", "ROA"));
		
		Section.AddSubMenu(
			"ROAMenu",
			LOCTEXT("ROAMenuTitle", "ROA"),
			LOCTEXT("ROAMenuTooltip", "Robot Operator Assistant tools"),
			FNewToolMenuDelegate::CreateStatic(&FROAModule::BuildROAMenu),
			false,
			FSlateIcon(FAppStyle::GetAppStyleSetName(), "LevelEditor.Tabs.Details")
		);
		
		// Also add to toolbar
		UToolMenu* ToolBar = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar.PlayToolBar");
		FToolMenuSection& ToolBarSection = ToolBar->FindOrAddSection("ROATools");
		
		// Add simple menu entries instead of combo button
		ToolBarSection.AddEntry(FToolMenuEntry::InitMenuEntry(
			"AssembleRobot",
			LOCTEXT("AssembleRobotToolbarLabel", "Assemble Robot"),
			LOCTEXT("AssembleRobotToolbarTooltip", "Assemble imported robot from hierarchy JSON"),
			FSlateIcon(FAppStyle::GetAppStyleSetName(), "LevelEditor.Tabs.Details"),
			FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnAssembleRobotClicked))
		));
		
		ToolBarSection.AddEntry(FToolMenuEntry::InitMenuEntry(
			"ListRobots",
			LOCTEXT("ListRobotsToolbarLabel", "List Robots"),
			LOCTEXT("ListRobotsToolbarTooltip", "List all robots in the scene"),
			FSlateIcon(FAppStyle::GetAppStyleSetName(), "LevelEditor.Tabs.Details"),
			FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnListRobotsClicked))
		));
	}));
	
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Menus registered"));
#endif
}

void FROAModule::BuildROAMenu(UToolMenu* Menu)
{
	// =========================================================================
	// FTI (Files Type Integration) Submenu - Main import and assembly functions
	// =========================================================================
	FToolMenuSection& FTISection = Menu->AddSection("ROAFTI", LOCTEXT("ROAFTISection", "File Type Integration"));

	FTISection.AddSubMenu(
"FTISubmenu",
		LOCTEXT("FTISubmenuLabel", "FTI"),
		LOCTEXT("FTISubmenuTooltip", "Import and assemble robots (URDF, XACRO, DAE, USD)"),
		FNewToolMenuDelegate::CreateStatic(&FROAModule::BuildFTISubmenu),
		false,
		FSlateIcon(FAppStyle::GetAppStyleSetName(), "LevelEditor.Tabs.ContentBrowser")
);

	// =========================================================================
	// Robot Utilities Section - Reset and management
	// =========================================================================
	FToolMenuSection& RobotsSection = Menu->AddSection("ROARobots", LOCTEXT("ROARobotsSection", "Robot Utilities"));

	RobotsSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"ResetRobots",
		LOCTEXT("ResetRobotsMenuLabel", "Reset Robots to Origin"),
		LOCTEXT("ResetRobotsMenuTooltip", "Reset all robot actors to their origin positions"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnResetRobotsClicked))
	));

	// =========================================================================
	// ROC (Robot Operator Console) Section
	// =========================================================================
	FToolMenuSection& ROCSection = Menu->AddSection("ROAROC", LOCTEXT("ROAROCSection", "Robot Operator Console"));

	ROCSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"PrepareForROC",
		LOCTEXT("PrepareForROCMenuLabel", "Prepare for ROC..."),
		LOCTEXT("PrepareForROCMenuTooltip", "Generate ROC specifications for a robot"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnPrepareForROCClicked))
	));
}

void FROAModule::BuildFTISubmenu(UToolMenu* Menu)
{
	// =========================================================================
	// Import Section
	// =========================================================================
	FToolMenuSection& ImportSection = Menu->AddSection("FTIImport", LOCTEXT("FTIImportSection", "Import"));

	ImportSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"ImportURDF",
		LOCTEXT("ImportURDFLabel", "Import URDF..."),
		LOCTEXT("ImportURDFTooltip", "Import a URDF robot description file"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnImportURDFClicked))
	));

	ImportSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"ImportXACRO",
		LOCTEXT("ImportXACROLabel", "Import XACRO..."),
		LOCTEXT("ImportXACROTooltip", "Import a XACRO robot description file (processes macros)"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnImportXACROClicked))
	));

	ImportSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"ImportDAE",
		LOCTEXT("ImportDAELabel", "Import DAE/COLLADA..."),
		LOCTEXT("ImportDAETooltip", "Import a COLLADA mesh file"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnImportDAEClicked))
	));

	ImportSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"ImportUSD",
		LOCTEXT("ImportUSDLabel", "Import Robot USD..."),
		LOCTEXT("ImportUSDTooltip", "Import a USD robot scene with hierarchy"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnImportUSDClicked))
	));

        // =========================================================================
        // Blueprint Section - Create reusable robot Blueprints
        // =========================================================================
        FToolMenuSection& BlueprintSection = Menu->AddSection("FTIBlueprint", LOCTEXT("FTIBlueprintSection", "Blueprints"));

        BlueprintSection.AddEntry(FToolMenuEntry::InitMenuEntry(
                "CreateRobotBlueprint",
                LOCTEXT("CreateRobotBlueprintLabel", "Create Robot Blueprint..."),
                LOCTEXT("CreateRobotBlueprintTooltip", "Create a reusable Blueprint from robot hierarchy JSON"),
                FSlateIcon(),
                FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnCreateRobotBlueprintClicked))
        ));

        BlueprintSection.AddEntry(FToolMenuEntry::InitMenuEntry(
                "SpawnRobot",
                LOCTEXT("SpawnRobotLabel", "Spawn Robot..."),
                LOCTEXT("SpawnRobotTooltip", "Spawn a robot from existing Blueprint or hierarchy JSON"),
                FSlateIcon(),
                FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnSpawnRobotClicked))
        ));

        BlueprintSection.AddEntry(FToolMenuEntry::InitMenuEntry(
                "ListBlueprints",
                LOCTEXT("ListBlueprintsLabel", "List Robot Blueprints"),
                LOCTEXT("ListBlueprintsTooltip", "List all registered robot Blueprints"),
                FSlateIcon(),
                FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnListBlueprintsClicked))
        ));

	// =========================================================================
	// Assembly Section
	// =========================================================================
	FToolMenuSection& AssemblySection = Menu->AddSection("FTIAssembly", LOCTEXT("FTIAssemblySection", "Assembly"));

	AssemblySection.AddEntry(FToolMenuEntry::InitMenuEntry(
"AssembleRobot",
		LOCTEXT("AssembleRobotMenuLabel", "Assemble Robot..."),
		LOCTEXT("AssembleRobotMenuTooltip", "Assemble imported robot from hierarchy JSON"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnAssembleRobotClicked))
	));

	AssemblySection.AddEntry(FToolMenuEntry::InitMenuEntry(
"ListRobots",
		LOCTEXT("ListRobotsMenuLabel", "List Robots"),
		LOCTEXT("ListRobotsMenuTooltip", "List all robots in the scene"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnListRobotsClicked))
	));

	AssemblySection.AddEntry(FToolMenuEntry::InitMenuEntry(
"AssembleAll",
		LOCTEXT("AssembleAllMenuLabel", "Assemble All Robots"),
		LOCTEXT("AssembleAllMenuTooltip", "Auto-detect and assemble all robots with hierarchy files"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnAssembleAllClicked))
	));

	// =========================================================================
	// Settings Section
	// =========================================================================
	FToolMenuSection& SettingsSection = Menu->AddSection("FTISettings", LOCTEXT("FTISettingsSection", "Settings"));

	SettingsSection.AddEntry(FToolMenuEntry::InitMenuEntry(
"FTISettings",
		LOCTEXT("FTISettingsLabel", "FTI Settings..."),
		LOCTEXT("FTISettingsTooltip", "Configure File Type Integration settings"),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateStatic(&FROAModule::OnFTISettingsClicked))
	));
}

void FROAModule::UnregisterMenus()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Unregistering menus"));
	
	// Unregister toolmenus startup callback
	UToolMenus::UnRegisterStartupCallback(this);
	
	// Remove the ROA menu if ToolMenus is still valid
	if (UObjectInitialized() && UToolMenus::IsToolMenuUIEnabled())
	{
		if (UToolMenus* ToolMenus = UToolMenus::TryGet())
		{
			ToolMenus->RemoveMenu("LevelEditor.MainMenu.ROA");
			UE_LOG(LogTemp, Log, TEXT("ROA Plugin: ROA menu removed"));
		}
	}
	
	// Unregister commands
	FROACommands::Unregister();
	
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Menus unregistered"));
#endif
}

void FROAModule::OnAssembleRobotClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Assemble Robot clicked"));
	
	// Open file dialog to select hierarchy JSON
	IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
	if (DesktopPlatform)
	{
		TArray<FString> OutFiles;
		const bool bOpened = DesktopPlatform->OpenFileDialog(
			FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
			TEXT("Select Robot Hierarchy JSON"),
			FPaths::ProjectContentDir(),
			TEXT(""),
			TEXT("JSON Files (*.json)|*.json"),
			EFileDialogFlags::None,
			OutFiles
		);
		
		if (bOpened && OutFiles.Num() > 0)
		{
			FString JsonPath = OutFiles[0];
			UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Selected hierarchy JSON: %s"), *JsonPath);
			
			// Convert Windows path to Python-safe path
			JsonPath = JsonPath.Replace(TEXT("\\"), TEXT("/"));
			
			// Execute Python assembler - use function-based API
			FString PythonCode = FString::Printf(
				TEXT("import sys; ")
				TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
				TEXT("from urdf_robot_assembler import assemble_robot; ")
				TEXT("assemble_robot('%s');"),
				*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
				*JsonPath
			);
			
			ExecutePythonCommand(PythonCode);
		}
	}
#endif
}

void FROAModule::OnListRobotsClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: List Robots clicked"));
	
	// Execute Python to list robots - use function-based API
	FString PythonCode = FString::Printf(
		TEXT("import sys; ")
		TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
		TEXT("from urdf_robot_assembler import list_robots; ")
		TEXT("list_robots();"),
		*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/"))
	);
	
	ExecutePythonCommand(PythonCode);
#endif
}

void FROAModule::ExecutePythonCommand(const FString& PythonCode)
{
#if WITH_EDITOR
	// Try to use the Python Script Plugin if available
	if (FModuleManager::Get().IsModuleLoaded("PythonScriptPlugin"))
	{
		IPythonScriptPlugin* PythonPlugin = &FModuleManager::LoadModuleChecked<IPythonScriptPlugin>("PythonScriptPlugin");
		PythonPlugin->ExecPythonCommand(*PythonCode);
		UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Executed Python command"));
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: Python Script Plugin not available"));
		UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: Enable 'Python Editor Script Plugin' in Edit > Plugins"));
	}
#endif
}

void FROAModule::OnAssembleAllClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Assemble All clicked"));
	
	FString PythonCode = FString::Printf(
		TEXT("import sys; ")
		TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
		TEXT("from urdf_robot_assembler import assemble_all; ")
		TEXT("assemble_all();"),
		*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/"))
	);
	
	ExecutePythonCommand(PythonCode);
#endif
}

void FROAModule::OnResetRobotsClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Reset Robots clicked"));
	
	FString PythonCode = FString::Printf(
		TEXT("import sys; ")
		TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
		TEXT("from urdf_robot_assembler import reset_robot; ")
		TEXT("reset_robot();"),
		*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/"))
	);
	
	ExecutePythonCommand(PythonCode);
#endif
}

void FROAModule::OnPrepareForROCClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Prepare for ROC clicked"));
	
	// Open file dialog to select robot
	IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
	if (DesktopPlatform)
	{
		TArray<FString> OutFiles;
		const bool bOpened = DesktopPlatform->OpenFileDialog(
			FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
			TEXT("Select Robot Hierarchy JSON for ROC"),
			FPaths::ProjectContentDir(),
			TEXT(""),
			TEXT("JSON Files (*.json)|*.json"),
			EFileDialogFlags::None,
			OutFiles
		);
		
		if (bOpened && OutFiles.Num() > 0)
		{
			FString JsonPath = OutFiles[0].Replace(TEXT("\\"), TEXT("/"));
			
			FString PythonCode = FString::Printf(
				TEXT("import sys; ")
				TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
				TEXT("from urdf_robot_assembler import prepare_for_roc; ")
				TEXT("prepare_for_roc('%s');"),
				*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
				*JsonPath
			);
			
			ExecutePythonCommand(PythonCode);
		}
	}
#endif
}

void FROAModule::OnImportURDFClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Import URDF clicked"));
	
	IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
	if (DesktopPlatform)
	{
		TArray<FString> OutFiles;
		const bool bOpened = DesktopPlatform->OpenFileDialog(
			FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
			TEXT("Import URDF File"),
			TEXT(""),
			TEXT(""),
			TEXT("URDF Files (*.urdf)|*.urdf|XML Files (*.xml)|*.xml"),
			EFileDialogFlags::None,
			OutFiles
		);
		
		if (bOpened && OutFiles.Num() > 0)
		{
			FString URDFPath = OutFiles[0].Replace(TEXT("\\"), TEXT("/"));
			
			// Import URDF via FTI service
			FString PythonCode = FString::Printf(
				TEXT("import sys; ")
				TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
				TEXT("from ue5_import_workflow import convert_robot; ")
				TEXT("convert_robot('%s');"),
				*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
				*URDFPath
			);
			
			ExecutePythonCommand(PythonCode);
		}
	}
#endif
}

void FROAModule::OnImportXACROClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Import XACRO clicked"));
	
	IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
	if (DesktopPlatform)
	{
		TArray<FString> OutFiles;
		const bool bOpened = DesktopPlatform->OpenFileDialog(
			FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
			TEXT("Import XACRO File"),
			TEXT(""),
			TEXT(""),
			TEXT("XACRO Files (*.xacro;*.urdf.xacro)|*.xacro;*.urdf.xacro"),
			EFileDialogFlags::None,
			OutFiles
		);
		
		if (bOpened && OutFiles.Num() > 0)
		{
			FString XACROPath = OutFiles[0].Replace(TEXT("\\"), TEXT("/"));
			
			// Process XACRO via Python xacro module, then import as URDF
			FString PythonCode = FString::Printf(
				TEXT("import sys; ")
				TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
				TEXT("from ue5_import_workflow import convert_robot; ")
				TEXT("convert_robot('%s');"),
				*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
				*XACROPath
			);
			
			ExecutePythonCommand(PythonCode);
		}
	}
#endif
}

void FROAModule::OnImportDAEClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Import DAE clicked"));
	
	IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
	if (DesktopPlatform)
	{
		TArray<FString> OutFiles;
		const bool bOpened = DesktopPlatform->OpenFileDialog(
			FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
			TEXT("Import COLLADA/DAE File"),
			TEXT(""),
			TEXT(""),
			TEXT("COLLADA Files (*.dae)|*.dae"),
			EFileDialogFlags::None,
			OutFiles
		);
		
		if (bOpened && OutFiles.Num() > 0)
		{
			FString DAEPath = OutFiles[0].Replace(TEXT("\\"), TEXT("/"));
			
			// Import DAE mesh
			UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Selected DAE: %s"), *DAEPath);
			UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: DAE import will use UE5's built-in FBX pipeline"));
			// TODO: Integrate with USD pipeline for DAE
		}
	}
#endif
}

void FROAModule::OnImportUSDClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Import USD clicked"));
	
	IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
	if (DesktopPlatform)
	{
		TArray<FString> OutFiles;
		const bool bOpened = DesktopPlatform->OpenFileDialog(
			FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
			TEXT("Import Robot USD File"),
			TEXT(""),
			TEXT(""),
			TEXT("USD Files (*.usd;*.usda;*.usdc;*.usdz)|*.usd;*.usda;*.usdc;*.usdz"),
			EFileDialogFlags::None,
			OutFiles
		);
		
		if (bOpened && OutFiles.Num() > 0)
		{
			FString USDPath = OutFiles[0].Replace(TEXT("\\"), TEXT("/"));
			
			// Import USD with hierarchy extraction
			FString PythonCode = FString::Printf(
				TEXT("import sys; ")
				TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
				TEXT("from ue5_import_workflow import import_robot; ")
				TEXT("import_robot('%s');"),
				*FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
				*USDPath
			);
			
			ExecutePythonCommand(PythonCode);
		}
	}
#endif
}

void FROAModule::OnFTISettingsClicked()
{
#if WITH_EDITOR
	UE_LOG(LogTemp, Log, TEXT("ROA Plugin: FTI Settings clicked"));
	
	// TODO: Open FTI settings dialog
	UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: FTI Settings dialog not yet implemented"));
	UE_LOG(LogTemp, Warning, TEXT("ROA Plugin: Configure settings via Project Settings > Plugins > ROA"));
#endif
}


void FROAModule::OnCreateRobotBlueprintClicked()
{
#if WITH_EDITOR
        UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Create Robot Blueprint clicked"));

        // Open file dialog to select hierarchy JSON
        IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
        if (DesktopPlatform)
        {
                TArray<FString> OutFiles;
                const bool bOpened = DesktopPlatform->OpenFileDialog(
                        FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
                        TEXT("Select Robot Hierarchy JSON"),
                        FPaths::ProjectDir(),
                        TEXT(""),
                        TEXT("JSON Files (*.json)|*.json"),
                        EFileDialogFlags::None,
                        OutFiles
                );

                if (bOpened && OutFiles.Num() > 0)
                {
                        FString SelectedFile = OutFiles[0];
                        UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Selected hierarchy JSON: %s"), *SelectedFile);

                        // Escape backslashes for Python
                        FString EscapedPath = SelectedFile.Replace(TEXT("\\"), TEXT("/"));

                        // Call Python to create Blueprint
                        FString PythonCode = FString::Printf(
                                TEXT("import sys; ")
                                TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
                                TEXT("from robot_blueprint_factory import create_robot_blueprint; ")
                                TEXT("create_robot_blueprint(r'%s')"),
                                *FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
                                *EscapedPath
                        );

                        ExecutePythonCommand(PythonCode);
                }
        }
#endif
}

void FROAModule::OnSpawnRobotClicked()
{
#if WITH_EDITOR
        UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Spawn Robot clicked"));

        // Open file dialog to select hierarchy JSON
        IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
        if (DesktopPlatform)
        {
                TArray<FString> OutFiles;
                const bool bOpened = DesktopPlatform->OpenFileDialog(
                        FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
                        TEXT("Select Robot Hierarchy JSON"),
                        FPaths::ProjectDir(),
                        TEXT(""),
                        TEXT("JSON Files (*.json)|*.json"),
                        EFileDialogFlags::None,
                        OutFiles
                );

                if (bOpened && OutFiles.Num() > 0)
                {
                        FString SelectedFile = OutFiles[0];
                        UE_LOG(LogTemp, Log, TEXT("ROA Plugin: Selected hierarchy JSON: %s"), *SelectedFile);

                        // Escape backslashes for Python
                        FString EscapedPath = SelectedFile.Replace(TEXT("\\"), TEXT("/"));

                        // Call Python to spawn robot (will create BP if needed)
                        FString PythonCode = FString::Printf(
                                TEXT("import sys; ")
                                TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
                                TEXT("from robot_blueprint_factory import spawn_robot; ")
                                TEXT("spawn_robot(r'%s')"),
                                *FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/")),
                                *EscapedPath
                        );

                        ExecutePythonCommand(PythonCode);
                }
        }
#endif
}

void FROAModule::OnListBlueprintsClicked()
{
#if WITH_EDITOR
        UE_LOG(LogTemp, Log, TEXT("ROA Plugin: List Blueprints clicked"));

        // Call Python to list blueprints
        FString PythonCode = FString::Printf(
                TEXT("import sys; ")
                TEXT("sys.path.insert(0, '%s/Plugins/ROA_PlugIn/Resources/Python'); ")
                TEXT("from robot_blueprint_factory import list_robot_blueprints; ")
                TEXT("list_robot_blueprints()"),
                *FPaths::ProjectDir().Replace(TEXT("\\"), TEXT("/"))
        );
        ExecutePythonCommand(PythonCode);
#endif
}

#undef LOCTEXT_NAMESPACE
	
IMPLEMENT_MODULE(FROAModule, ROA)
