// ROAFTIImportFactory.cpp
// FTI-based Robot Import Factory Implementation
// ROA - Robot Operations & Automation

#include "ROAFTIImportFactory.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/MessageDialog.h"
#include "Misc/DateTime.h"
#include "Misc/Guid.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformFileManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Engine/Blueprint.h"
#include "IPythonScriptPlugin.h"
#include "Modules/ModuleManager.h"
#include "TimerManager.h"
#include "Containers/Ticker.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "DesktopPlatformModule.h"
#include "Framework/Application/SlateApplication.h"

// Static member initialization
FString UFTIConnection::IPCFolderPath;
FString UFTIConnection::ClientId;
FTSTicker::FDelegateHandle UFTIConnection::HeartbeatTickerHandle;
FTimerHandle UFTIConnection::HeartbeatTimerHandle; // Keep for backward compat

// ═══════════════════════════════════════════════════════════════════════════════
// UFTIConnection Implementation
// ═══════════════════════════════════════════════════════════════════════════════

UFTIConnection::UFTIConnection()
{
}

FString UFTIConnection::GetIPCFolderPath()
{
    if (IPCFolderPath.IsEmpty())
    {
        // Try Windows path first
        FString WindowsPath = TEXT("D:/ROA/.ipc");
        if (FPaths::DirectoryExists(WindowsPath))
        {
            IPCFolderPath = WindowsPath;
        }
        else
        {
            // Fallback to temp folder
            IPCFolderPath = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("FTI_IPC"));
        }
    }
    return IPCFolderPath;
}

bool UFTIConnection::IsServiceAvailable()
{
    // Check if IPC folder exists and has status file
    // The service writes to service.status (not .json) directly in .ipc folder
    FString StatusFile = FPaths::Combine(GetIPCFolderPath(), TEXT("service.status"));
    
    if (!FPaths::FileExists(StatusFile))
    {
        // Also check for JSON version for backwards compatibility
        FString StatusFileJson = FPaths::Combine(GetIPCFolderPath(), TEXT("status"), TEXT("service.status.json"));
        if (!FPaths::FileExists(StatusFileJson))
        {
            UE_LOG(LogTemp, Log, TEXT("FTI: No service status file found at %s"), *StatusFile);
            return false;
        }
        StatusFile = StatusFileJson;
    }
    
    // Read status file
    FString Content;
    if (!FFileHelper::LoadFileToString(Content, *StatusFile))
    {
        UE_LOG(LogTemp, Warning, TEXT("FTI: Could not read service status file"));
        return false;
    }
    
    // Parse JSON
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Content);
    
    if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
    {
        UE_LOG(LogTemp, Warning, TEXT("FTI: Invalid JSON in service status file"));
        return false;
    }
    
    // Check if running - handle both "running" and "status" fields
    bool bRunning = false;
    if (JsonObject->HasField(TEXT("running")))
    {
        bRunning = JsonObject->GetBoolField(TEXT("running"));
    }
    else if (JsonObject->HasField(TEXT("status")))
    {
        FString Status = JsonObject->GetStringField(TEXT("status"));
        bRunning = Status.Equals(TEXT("running"), ESearchCase::IgnoreCase);
    }
    
    // Check last_heartbeat timestamp (must be recent - within last 30 seconds)
    FString LastHeartbeat;
    if (JsonObject->TryGetStringField(TEXT("last_heartbeat"), LastHeartbeat))
    {
        // Parse ISO timestamp - just check if it exists for now
        // In production, parse and compare to current time
        UE_LOG(LogTemp, Log, TEXT("FTI: Service heartbeat: %s"), *LastHeartbeat);
    }
    
    UE_LOG(LogTemp, Log, TEXT("FTI: Service available: %s"), bRunning ? TEXT("Yes") : TEXT("No"));
    return bRunning;
}

bool UFTIConnection::EnsureServiceRunning()
{
    if (IsServiceAvailable())
    {
        return true;
    }
    
    UE_LOG(LogTemp, Log, TEXT("FTI service not running, attempting to auto-start..."));
    
    // Try to auto-start the FTI service via WSL
    bool bAutoStarted = TryAutoStartService();
    
    if (bAutoStarted)
    {
        // Wait for service to initialize with retry loop
        // Service needs time to: WSL init → Python start → Status file create
        const int MaxRetries = 10;
        const float RetryDelay = 1.0f;  // 1 second between retries
        
        for (int Retry = 0; Retry < MaxRetries; Retry++)
        {
            FPlatformProcess::Sleep(RetryDelay);
            
            if (IsServiceAvailable())
            {
                UE_LOG(LogTemp, Log, TEXT("FTI service auto-started successfully (took %d seconds)"), Retry + 1);
                return true;
            }
            
            UE_LOG(LogTemp, Verbose, TEXT("FTI: Waiting for service... attempt %d/%d"), Retry + 1, MaxRetries);
        }
        
        UE_LOG(LogTemp, Warning, TEXT("FTI service did not respond after %d seconds"), MaxRetries);
    }
    
    // Auto-start failed, show manual instructions
    FText Title = FText::FromString(TEXT("FTI Service Required"));
    FText Message = FText::FromString(TEXT(
        "The FTI (File Type Importer) service could not be auto-started.\n\n"
        "To start the service manually:\n"
        "1. Open a terminal in WSL\n"
        "2. Run: cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python\n"
        "3. Run: python3 roa_ipc_service.py --debug --auto-shutdown-delay 300\n\n"
        "Or use the startup script:\n"
        "   bash start_fti_service.sh 300\n\n"
        "Would you like to retry after starting the service?"
    ));
    
    EAppReturnType::Type Result = FMessageDialog::Open(EAppMsgType::YesNo, Message, Title);
    
    if (Result == EAppReturnType::Yes)
    {
        // Retry after user action
        return IsServiceAvailable();
    }
    
    return false;
}

bool UFTIConnection::TryAutoStartService()
{
    // Try to start FTI IPC service via WSL
    // This launches a background process in WSL
    
    FString WslCommand = TEXT("wsl.exe");
    FString StartScript = TEXT("/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/start_fti_service.sh");
    FString ServiceScript = TEXT("/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/roa_ipc_service.py");
    
    // Method 1: Use startup script (most reliable)
    // Format: wsl.exe -- bash /path/to/start_fti_service.sh 300
    FString Args = FString::Printf(
        TEXT("-- bash %s 300"),
        *StartScript
    );
    
    UE_LOG(LogTemp, Log, TEXT("FTI: Launching service via script: %s %s"), *WslCommand, *Args);
    
    FProcHandle ProcHandle = FPlatformProcess::CreateProc(
        *WslCommand,
        *Args,
        true,   // bLaunchDetached
        false,  // bLaunchHidden - keep visible briefly for debugging
        false,  // bLaunchReallyHidden
        nullptr,// OutProcessID
        0,      // PriorityModifier
        nullptr,// OptionalWorkingDirectory
        nullptr // PipeWriteChild
    );
    
    if (ProcHandle.IsValid())
    {
        FPlatformProcess::CloseProc(ProcHandle);
        UE_LOG(LogTemp, Log, TEXT("FTI: Service startup script launched"));
        return true;
    }
    
    UE_LOG(LogTemp, Warning, TEXT("FTI: Script launch failed - trying direct command"));
    
    // Method 2: Direct python command with proper cd
    Args = FString::Printf(
        TEXT("-- bash -c 'cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python && nohup python3 %s --debug --auto-shutdown-delay 300 > /tmp/fti_ipc.log 2>&1 &'"),
        *ServiceScript
    );
    
    ProcHandle = FPlatformProcess::CreateProc(
        *WslCommand,
        *Args,
        true,   // bLaunchDetached
        false,  // bLaunchHidden
        false,  // bLaunchReallyHidden
        nullptr,// OutProcessID
        0,      // PriorityModifier
        nullptr,// OptionalWorkingDirectory
        nullptr // PipeWriteChild
    );
    
    if (ProcHandle.IsValid())
    {
        FPlatformProcess::CloseProc(ProcHandle);
        UE_LOG(LogTemp, Log, TEXT("FTI: Direct WSL command sent"));
        return true;
    }
    
    UE_LOG(LogTemp, Warning, TEXT("FTI: Direct command failed - trying system() fallback"));
    
    // Method 3: system() as last resort
    FString SystemCmd = TEXT("wsl.exe -- bash -c 'cd /home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python && python3 roa_ipc_service.py --debug --auto-shutdown-delay 300 &'");
    int Result = system(TCHAR_TO_ANSI(*SystemCmd));
    UE_LOG(LogTemp, Log, TEXT("FTI: System command result: %d"), Result);
    
    return Result == 0;
}

void UFTIConnection::WriteHeartbeat()
{
    // Write heartbeat file to keep IPC service alive
    FString HeartbeatFolder = FPaths::Combine(GetIPCFolderPath(), TEXT("heartbeats"));
    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    PlatformFile.CreateDirectoryTree(*HeartbeatFolder);
    
    // Generate client ID if not set
    if (ClientId.IsEmpty())
    {
        FGuid Guid = FGuid::NewGuid();
        ClientId = FString::Printf(TEXT("ue5_%s"), *Guid.ToString(EGuidFormats::Short).Left(8));
    }
    
    // Build heartbeat JSON
    // CRITICAL: Use Unix epoch timestamp (seconds since 1970), NOT FPlatformTime::Seconds()!
    // FPlatformTime::Seconds() returns seconds since app start, which breaks the service's age calculation
    TSharedPtr<FJsonObject> HeartbeatJson = MakeShareable(new FJsonObject);
    HeartbeatJson->SetStringField(TEXT("client_id"), ClientId);
    HeartbeatJson->SetStringField(TEXT("type"), TEXT("ue5_plugin"));
    
    // FIXED: Use Unix epoch timestamp (FDateTime::UtcNow().ToUnixTimestamp())
    // This matches what Python's time.time() returns
    HeartbeatJson->SetNumberField(TEXT("timestamp"), (double)FDateTime::UtcNow().ToUnixTimestamp());
    
    HeartbeatJson->SetStringField(TEXT("project"), FPaths::GetProjectFilePath());
    HeartbeatJson->SetStringField(TEXT("last_activity"), FDateTime::UtcNow().ToIso8601());
    
    // Serialize
    FString HeartbeatContent;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&HeartbeatContent);
    FJsonSerializer::Serialize(HeartbeatJson.ToSharedRef(), Writer);
    
    // Write to file
    FString HeartbeatFile = FPaths::Combine(HeartbeatFolder, FString::Printf(TEXT("%s.heartbeat.json"), *ClientId));
    FFileHelper::SaveStringToFile(HeartbeatContent, *HeartbeatFile);
    
    UE_LOG(LogTemp, Verbose, TEXT("FTI: Heartbeat written for %s (timestamp: %lld)"), *ClientId, FDateTime::UtcNow().ToUnixTimestamp());
}

void UFTIConnection::StartHeartbeat()
{
    // Generate client ID
    if (ClientId.IsEmpty())
    {
        FGuid Guid = FGuid::NewGuid();
        ClientId = FString::Printf(TEXT("ue5_%s"), *Guid.ToString(EGuidFormats::Short).Left(8));
    }
    
    UE_LOG(LogTemp, Log, TEXT("FTI: Starting heartbeat for client %s"), *ClientId);
    
    // Write initial heartbeat
    WriteHeartbeat();
    
    // Set up recurring heartbeat using FTSTicker (works without World context)
    // This is essential for Editor modules like import factories
    if (!HeartbeatTickerHandle.IsValid())
    {
        // Create ticker that fires every 30 seconds
        HeartbeatTickerHandle = FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateLambda([](float DeltaTime) -> bool
            {
                WriteHeartbeat();
                UE_LOG(LogTemp, Verbose, TEXT("FTI: Heartbeat tick"));
                return true;  // Keep ticking
            }),
            30.0f  // Interval: 30 seconds (well under 60 second timeout)
        );
        
        UE_LOG(LogTemp, Log, TEXT("FTI: Heartbeat ticker started (30 second interval). Client ID: %s"), *ClientId);
    }
    else
    {
        UE_LOG(LogTemp, Log, TEXT("FTI: Heartbeat ticker already running. Client ID: %s"), *ClientId);
    }
}

void UFTIConnection::StopHeartbeat()
{
    UE_LOG(LogTemp, Log, TEXT("FTI: Stopping heartbeat for client %s"), *ClientId);
    
    // Stop the ticker
    if (HeartbeatTickerHandle.IsValid())
    {
        FTSTicker::GetCoreTicker().RemoveTicker(HeartbeatTickerHandle);
        HeartbeatTickerHandle.Reset();
        UE_LOG(LogTemp, Log, TEXT("FTI: Heartbeat ticker stopped"));
    }
    
    // Remove heartbeat file to signal clean shutdown
    if (!ClientId.IsEmpty())
    {
        FString HeartbeatFolder = FPaths::Combine(GetIPCFolderPath(), TEXT("heartbeats"));
        FString HeartbeatFile = FPaths::Combine(HeartbeatFolder, FString::Printf(TEXT("%s.heartbeat.json"), *ClientId));
        
        if (FPaths::FileExists(HeartbeatFile))
        {
            IFileManager::Get().Delete(*HeartbeatFile);
            UE_LOG(LogTemp, Log, TEXT("FTI: Heartbeat file removed"));
        }
    }
    
    ClientId.Empty();
}

void UFTIConnection::RegisterClient()
{
    // Start heartbeat and ensure service is running
    StartHeartbeat();
    
    // Try to ensure service is available (will auto-start if needed)
    if (EnsureServiceRunning())
    {
        // Write heartbeat to register
        WriteHeartbeat();
        UE_LOG(LogTemp, Log, TEXT("FTI: Client registered with service"));
    }
}

void UFTIConnection::DeregisterClient()
{
    // Stop heartbeat (removes heartbeat file)
    StopHeartbeat();
    UE_LOG(LogTemp, Log, TEXT("FTI: Client deregistered"));
}

FString UFTIConnection::GenerateRequestId()
{
    FGuid Guid = FGuid::NewGuid();
    return FString::Printf(TEXT("req_%s"), *Guid.ToString(EGuidFormats::Short));
}

bool UFTIConnection::WriteIPCRequest(const FString& RequestId, const FString& JsonContent)
{
    FString RequestFolder = FPaths::Combine(GetIPCFolderPath(), TEXT("requests"));
    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    PlatformFile.CreateDirectoryTree(*RequestFolder);
    
    FString RequestFile = FPaths::Combine(RequestFolder, FString::Printf(TEXT("%s.json"), *RequestId));
    return FFileHelper::SaveStringToFile(JsonContent, *RequestFile);
}

FString UFTIConnection::ReadIPCResponse(const FString& RequestId, float TimeoutSeconds)
{
    FString ResponseFolder = FPaths::Combine(GetIPCFolderPath(), TEXT("responses"));
    FString ResponseFile = FPaths::Combine(ResponseFolder, FString::Printf(TEXT("%s.response.json"), *RequestId));
    
    double StartTime = FPlatformTime::Seconds();
    
    while ((FPlatformTime::Seconds() - StartTime) < TimeoutSeconds)
    {
        if (FPaths::FileExists(ResponseFile))
        {
            FString Content;
            if (FFileHelper::LoadFileToString(Content, *ResponseFile))
            {
                // Delete response file after reading
                IFileManager::Get().Delete(*ResponseFile);
                return Content;
            }
        }
        
        // Wait a bit before checking again
        FPlatformProcess::Sleep(0.1f);
    }
    
    return FString();  // Timeout
}

FString UFTIConnection::RequestConversion(
    const FString& SourceFile,
    const FString& OutputDir,
    const FFTIImportOptions& Options,
    FString& OutError)
{
    // Generate request ID
    FString RequestId = GenerateRequestId();
    
    // Build request JSON
    TSharedPtr<FJsonObject> RequestJson = MakeShareable(new FJsonObject);
    RequestJson->SetStringField(TEXT("protocol_version"), TEXT("1.0.0"));
    RequestJson->SetStringField(TEXT("request_id"), RequestId);
    RequestJson->SetStringField(TEXT("command"), TEXT("convert"));
    RequestJson->SetStringField(TEXT("source_file"), SourceFile);
    RequestJson->SetStringField(TEXT("output_dir"), OutputDir);
    RequestJson->SetStringField(TEXT("format"), Options.OutputFormat.ToLower());
    RequestJson->SetNumberField(TEXT("timestamp"), FDateTime::UtcNow().ToUnixTimestamp());
    
    // Options
    TSharedPtr<FJsonObject> OptionsJson = MakeShareable(new FJsonObject);
    OptionsJson->SetBoolField(TEXT("embed_hierarchy"), true);
    OptionsJson->SetBoolField(TEXT("generate_ue5_script"), true);
    OptionsJson->SetStringField(TEXT("mesh_handling"), TEXT("embed"));
    RequestJson->SetObjectField(TEXT("options"), OptionsJson);
    
    // Serialize to string
    FString RequestContent;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&RequestContent);
    FJsonSerializer::Serialize(RequestJson.ToSharedRef(), Writer);
    
    // Write request file
    if (!WriteIPCRequest(RequestId, RequestContent))
    {
        OutError = TEXT("Failed to write IPC request file");
        return FString();
    }
    
    UE_LOG(LogTemp, Log, TEXT("FTI: Sent conversion request: %s"), *RequestId);
    
    // Wait for response (with progress updates)
    FString ResponseContent = ReadIPCResponse(RequestId, 120.0f);  // 2 minute timeout
    
    if (ResponseContent.IsEmpty())
    {
        OutError = TEXT("Conversion request timed out. Is FTI service running?");
        return FString();
    }
    
    // Parse response
    TSharedPtr<FJsonObject> ResponseJson;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ResponseContent);
    
    if (!FJsonSerializer::Deserialize(Reader, ResponseJson) || !ResponseJson.IsValid())
    {
        OutError = TEXT("Invalid response from FTI service");
        return FString();
    }
    
    bool bSuccess = ResponseJson->GetBoolField(TEXT("success"));
    
    if (!bSuccess)
    {
        OutError = ResponseJson->GetStringField(TEXT("error"));
        return FString();
    }
    
    return ResponseJson->GetStringField(TEXT("output_file"));
}

float UFTIConnection::GetConversionProgress(const FString& RequestId)
{
    FString ProgressFolder = FPaths::Combine(GetIPCFolderPath(), TEXT("progress"));
    FString ProgressFile = FPaths::Combine(ProgressFolder, FString::Printf(TEXT("%s.progress.json"), *RequestId));
    
    if (!FPaths::FileExists(ProgressFile))
    {
        return 0.0f;
    }
    
    FString Content;
    if (!FFileHelper::LoadFileToString(Content, *ProgressFile))
    {
        return 0.0f;
    }
    
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Content);
    
    if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
    {
        return 0.0f;
    }
    
    return JsonObject->GetNumberField(TEXT("percent")) / 100.0f;
}

// ═══════════════════════════════════════════════════════════════════════════════
// UROAFTIImportFactory Implementation
// ═══════════════════════════════════════════════════════════════════════════════

UROAFTIImportFactory::UROAFTIImportFactory()
{
    bCreateNew = false;
    bEditAfterNew = true;
    bEditorImport = true;
    bText = false;
    
    SupportedClass = AActor::StaticClass();
    
    // Register ALL file formats supported by FTI
    // FTI converts all these formats to USD for UE5 import
    
    // Robot Description Formats
    Formats.Add(TEXT("urdf;Robot Description (FTI Pipeline)"));
    Formats.Add(TEXT("URDF;Robot Description (FTI Pipeline)"));
    Formats.Add(TEXT("xacro;Robot Macros (FTI Pipeline)"));
    Formats.Add(TEXT("XACRO;Robot Macros (FTI Pipeline)"));
    Formats.Add(TEXT("sdf;Gazebo SDF (FTI Pipeline)"));
    Formats.Add(TEXT("SDF;Gazebo SDF (FTI Pipeline)"));
    Formats.Add(TEXT("world;Gazebo World (FTI Pipeline)"));
    
    // Mesh Formats
    Formats.Add(TEXT("stl;3D Mesh STL (FTI Pipeline)"));
    Formats.Add(TEXT("STL;3D Mesh STL (FTI Pipeline)"));
    Formats.Add(TEXT("obj;Wavefront OBJ (FTI Pipeline)"));
    Formats.Add(TEXT("OBJ;Wavefront OBJ (FTI Pipeline)"));
    
    // Exchange Formats
    Formats.Add(TEXT("dae;COLLADA (FTI Pipeline)"));
    Formats.Add(TEXT("DAE;COLLADA (FTI Pipeline)"));
    Formats.Add(TEXT("gltf;glTF (FTI Pipeline)"));
    Formats.Add(TEXT("glb;glTF Binary (FTI Pipeline)"));
    
    // CAD Formats
    Formats.Add(TEXT("step;STEP CAD (FTI Pipeline)"));
    Formats.Add(TEXT("stp;STEP CAD (FTI Pipeline)"));
    Formats.Add(TEXT("iges;IGES CAD (FTI Pipeline)"));
    Formats.Add(TEXT("igs;IGES CAD (FTI Pipeline)"));
    
    // Animation/Game Formats
    Formats.Add(TEXT("fbx;FBX (FTI Pipeline)"));
    Formats.Add(TEXT("FBX;FBX (FTI Pipeline)"));
}

bool UROAFTIImportFactory::DoesSupportClass(UClass* Class)
{
    return Class == AActor::StaticClass() || Class == UBlueprint::StaticClass();
}

bool UROAFTIImportFactory::FactoryCanImport(const FString& Filename)
{
    FString Extension = FPaths::GetExtension(Filename).ToLower();
    
    // All formats supported by FTI
    static const TArray<FString> SupportedExtensions = {
        // Robot Description
        TEXT("urdf"), TEXT("xacro"), TEXT("sdf"), TEXT("world"),
        // Mesh
        TEXT("stl"), TEXT("obj"),
        // Exchange
        TEXT("dae"), TEXT("gltf"), TEXT("glb"),
        // CAD
        TEXT("step"), TEXT("stp"), TEXT("iges"), TEXT("igs"),
        // Animation
        TEXT("fbx")
    };
    
    return SupportedExtensions.Contains(Extension);
}

FText UROAFTIImportFactory::GetDisplayName() const
{
    return FText::FromString(TEXT("Robot Description (FTI Pipeline)"));
}

int32 UROAFTIImportFactory::GetPriority() const
{
    // Higher priority than standard factory so this is used first
    return 100;
}

UObject* UROAFTIImportFactory::FactoryCreateFile(
    UClass* InClass,
    UObject* InParent,
    FName InName,
    EObjectFlags Flags,
    const FString& Filename,
    const TCHAR* Parms,
    FFeedbackContext* Warn,
    bool& bOutOperationCanceled)
{
    bOutOperationCanceled = false;
    
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Importing via FTI pipeline: %s"), *Filename);
    
    // Show options dialog
    if (!UFTIImportOptionsDialog::ShowDialog(ImportOptions))
    {
        bOutOperationCanceled = true;
        return nullptr;
    }
    
    // Check if using FTI or direct import
    if (ImportOptions.bUseFTI)
    {
        return ImportViaFTI(InParent, InName, Filename, Warn, bOutOperationCanceled);
    }
    else
    {
        // Fall back to standard URDF import (delegate to existing factory)
        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Using direct import (FTI disabled)"));
        // This would call the original ROAURDFFactory
        return nullptr;
    }
}

UObject* UROAFTIImportFactory::ImportViaFTI(
    UObject* InParent,
    FName InName,
    const FString& SourceFile,
    FFeedbackContext* Warn,
    bool& bOutOperationCanceled)
{
    // Write heartbeat to keep service alive during import
    UFTIConnection::WriteHeartbeat();
    
    // Ensure FTI service is running
    if (!UFTIConnection::EnsureServiceRunning())
    {
        Warn->Logf(ELogVerbosity::Error, TEXT("FTI service not available"));
        bOutOperationCanceled = true;
        return nullptr;
    }
    
    // Write heartbeat again after service is confirmed running
    UFTIConnection::WriteHeartbeat();
    
    // Determine output directory - use user-specified or fall back to default
    FString RobotName = FPaths::GetBaseFilename(SourceFile);
    FString OutputDir;
    
    if (!ImportOptions.OutputDir.IsEmpty())
    {
        // Use user-specified output directory
        OutputDir = FPaths::Combine(ImportOptions.OutputDir, RobotName);
        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Using user-specified output: %s"), *OutputDir);
    }
    else
    {
        // Fall back to project saved directory
        OutputDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("FTI_Output"), RobotName);
        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Using default output: %s"), *OutputDir);
    }
    
    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    PlatformFile.CreateDirectoryTree(*OutputDir);
    
    // Convert Windows path for WSL
    FString WslOutputDir = OutputDir;
    if (WslOutputDir.StartsWith(TEXT("D:")))
    {
        WslOutputDir = WslOutputDir.Replace(TEXT("D:"), TEXT("/mnt/d"));
        WslOutputDir = WslOutputDir.Replace(TEXT("\\"), TEXT("/"));
    }
    // Also handle other drive letters
    else if (WslOutputDir.Len() > 1 && WslOutputDir[1] == TEXT(':'))
    {
        TCHAR DriveLetter = FChar::ToLower(WslOutputDir[0]);
        FString DrivePath = FString::Printf(TEXT("/mnt/%c"), DriveLetter);
        WslOutputDir = WslOutputDir.Mid(2);  // Remove "X:"
        WslOutputDir = WslOutputDir.Replace(TEXT("\\"), TEXT("/"));
        WslOutputDir = DrivePath + WslOutputDir;
    }
    
    // Request conversion
    FString Error;
    FString OutputUSD = UFTIConnection::RequestConversion(SourceFile, WslOutputDir, ImportOptions, Error);
    
    if (OutputUSD.IsEmpty())
    {
        Warn->Logf(ELogVerbosity::Error, TEXT("FTI conversion failed: %s"), *Error);
        
        FText Title = FText::FromString(TEXT("FTI Conversion Failed"));
        FMessageDialog::Open(EAppMsgType::Ok, FText::FromString(Error), Title);
        
        bOutOperationCanceled = true;
        return nullptr;
    }
    
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Conversion complete: %s"), *OutputUSD);
    
    // Convert WSL path back to Windows for import
    FString WindowsUSD = OutputUSD;
    if (WindowsUSD.StartsWith(TEXT("/mnt/d")))
    {
        WindowsUSD = WindowsUSD.Replace(TEXT("/mnt/d"), TEXT("D:"));
    }
    
    // Import the USD and assemble
    return ImportUSDAndAssemble(InParent, InName, WindowsUSD, Warn);
}

UObject* UROAFTIImportFactory::ImportUSDAndAssemble(
    UObject* InParent,
    FName InName,
    const FString& USDPath,
    FFeedbackContext* Warn)
{
    FString RobotName = FPaths::GetBaseFilename(USDPath);
    if (RobotName.EndsWith(TEXT("_assembled")))
    {
        RobotName = RobotName.LeftChop(10);  // Remove "_assembled"
    }
    
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Importing USD: %s"), *USDPath);
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Robot name: %s"), *RobotName);
    
    // Create content folder path
    FString ContentFolder = FPaths::Combine(ImportOptions.ContentPath, RobotName);
    
    // Step 1: Run the complete import workflow via Python
    // This handles: USD import, mesh import, hierarchy assembly, and Blueprint generation
    bool bPythonSuccess = RunCompleteImportWorkflow(USDPath, RobotName, ContentFolder);
    
    if (!bPythonSuccess)
    {
        Warn->Logf(ELogVerbosity::Warning, TEXT("Python import workflow had issues - check Output Log"));
    }
    
    // Look for generated Blueprint
    UBlueprint* RobotBlueprint = nullptr;
    FString BlueprintPath = FString::Printf(TEXT("%s/BP_%s.BP_%s"), *ContentFolder, *RobotName, *RobotName);
    RobotBlueprint = Cast<UBlueprint>(StaticLoadObject(UBlueprint::StaticClass(), nullptr, *BlueprintPath));
    
    if (RobotBlueprint)
    {
        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Found generated Blueprint: %s"), *BlueprintPath);
    }
    
    // Show result message
    FText Title = FText::FromString(bPythonSuccess ? TEXT("FTI Import Complete") : TEXT("FTI Import Completed with Warnings"));
    FText Message = FText::Format(
        FText::FromString(TEXT("Robot '{0}' import finished.\n\nContent folder: {1}\n\nCheck Output Log for details.")),
        FText::FromString(RobotName),
        FText::FromString(ContentFolder)
    );
    FMessageDialog::Open(EAppMsgType::Ok, Message, Title);
    
    return RobotBlueprint;
}

bool UROAFTIImportFactory::RunCompleteImportWorkflow(
    const FString& USDPath,
    const FString& RobotName,
    const FString& ContentFolder)
{
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Running complete import workflow"));
    UE_LOG(LogTemp, Log, TEXT("  USD: %s"), *USDPath);
    UE_LOG(LogTemp, Log, TEXT("  Robot: %s"), *RobotName);
    UE_LOG(LogTemp, Log, TEXT("  Content: %s"), *ContentFolder);
    
    // Build Python script that runs the full workflow
    FString PythonModulePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Python/ROA"));
    
    // Escape backslashes for Python string
    FString EscapedUSDPath = USDPath.Replace(TEXT("\\"), TEXT("/"));
    FString EscapedContentFolder = ContentFolder;
    
    FString PythonScript = FString::Printf(
        TEXT(
            "import sys\n"
            "import os\n"
            "\n"
            "# Add ROA module path\n"
            "module_path = r'%s'\n"
            "if module_path not in sys.path:\n"
            "    sys.path.insert(0, module_path)\n"
            "\n"
            "print('ROA FTI: Starting Python import workflow...')\n"
            "print(f'  Module path: {module_path}')\n"
            "\n"
            "try:\n"
            "    from ue5_import_workflow import UE5ImportWorkflow, RobotImportConfig\n"
            "    \n"
            "    # Configure import\n"
            "    config = RobotImportConfig()\n"
            "    config.source_file = r'%s'\n"
            "    config.content_path = '%s'\n"
            "    config.robot_folder = '%s'\n"
            "    config.auto_assemble = %s\n"
            "    config.generate_blueprint = %s\n"
            "    config.setup_physics = %s\n"
            "    \n"
            "    # Run workflow\n"
            "    workflow = UE5ImportWorkflow(config)\n"
            "    result = workflow.import_from_assembled_usd(r'%s')\n"
            "    \n"
            "    if result.success:\n"
            "        print(f'ROA FTI: SUCCESS - Imported {result.mesh_count} meshes, {result.joint_count} joints')\n"
            "        print(f'  Content folder: {result.content_folder}')\n"
            "        if result.blueprint_path:\n"
            "            print(f'  Blueprint: {result.blueprint_path}')\n"
            "    else:\n"
            "        print(f'ROA FTI: FAILED - {result.error_message}')\n"
            "        for warning in result.warnings:\n"
            "            print(f'  Warning: {warning}')\n"
            "\n"
            "except Exception as e:\n"
            "    import traceback\n"
            "    print(f'ROA FTI: Python exception: {e}')\n"
            "    traceback.print_exc()\n"
        ),
        *PythonModulePath,
        *EscapedUSDPath,
        *ImportOptions.ContentPath,
        *RobotName,
        ImportOptions.bAutoAssemble ? TEXT("True") : TEXT("False"),
        ImportOptions.bGenerateBlueprint ? TEXT("True") : TEXT("False"),
        ImportOptions.bSetupPhysics ? TEXT("True") : TEXT("False"),
        *EscapedUSDPath
    );
    
    // Execute Python script
    if (IPythonScriptPlugin* PythonPlugin = FModuleManager::GetModulePtr<IPythonScriptPlugin>("PythonScriptPlugin"))
    {
        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Executing Python workflow..."));
        
        // Log the script for debugging
        UE_LOG(LogTemp, Verbose, TEXT("Python script:\n%s"), *PythonScript);
        
        PythonPlugin->ExecPythonCommand(*PythonScript);
        
        // Note: ExecPythonCommand is synchronous in UE5
        // The script runs to completion before returning
        return true;
    }
    else
    {
        UE_LOG(LogTemp, Error, TEXT("ROA FTI: Python plugin not available! Enable 'Python Editor Script Plugin' in plugins."));
        return false;
    }
}

bool UROAFTIImportFactory::RunHierarchyAssembly(const FString& USDPath, const FString& RobotName)
{
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Running hierarchy assembly for %s"), *RobotName);
    
    // Execute Python script
    FString PythonScript = FString::Printf(
        TEXT("import sys\n")
        TEXT("sys.path.insert(0, r'%s')\n")
        TEXT("import ue5_import_workflow as fti\n")
        TEXT("result = fti.import_robot(r'%s', auto_assemble=True, generate_blueprint=False)\n")
        TEXT("print(f'FTI Import Result: success={result.success}, meshes={result.mesh_count}')\n"),
        *FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Python/ROA")),
        *USDPath
    );
    
    // Try to execute via Python plugin
    if (IPythonScriptPlugin* PythonPlugin = FModuleManager::GetModulePtr<IPythonScriptPlugin>("PythonScriptPlugin"))
    {
        TArray<FString> CommandArgs;
        PythonPlugin->ExecPythonCommand(*PythonScript);
        return true;
    }
    else
    {
        UE_LOG(LogTemp, Warning, TEXT("Python plugin not available"));
        return false;
    }
}

UBlueprint* UROAFTIImportFactory::GenerateRobotBlueprint(const FString& RobotName, const FString& ContentPath)
{
    // TODO: Implement Blueprint generation from assembled robot
    UE_LOG(LogTemp, Log, TEXT("ROA FTI: Blueprint generation for %s at %s"), *RobotName, *ContentPath);
    return nullptr;
}

// FReimportHandler interface
bool UROAFTIImportFactory::CanReimport(UObject* Obj, TArray<FString>& OutFilenames)
{
    // TODO: Implement reimport
    return false;
}

void UROAFTIImportFactory::SetReimportPaths(UObject* Obj, const TArray<FString>& NewReimportPaths)
{
    // TODO: Implement
}

EReimportResult::Type UROAFTIImportFactory::Reimport(UObject* Obj)
{
    // TODO: Implement reimport
    return EReimportResult::Failed;
}

// ═══════════════════════════════════════════════════════════════════════════════
// UFTIImportOptionsDialog Implementation
// ═══════════════════════════════════════════════════════════════════════════════

bool UFTIImportOptionsDialog::ShowDialog(FFTIImportOptions& OutOptions)
{
    // Default output directory - can be overridden by config or user selection
    FString DefaultOutputDir = TEXT("");
    
    // Check environment variable first
    FString EnvOutputDir = FPlatformMisc::GetEnvironmentVariable(TEXT("ROA_FTI_OUTPUT_DIR"));
    if (!EnvOutputDir.IsEmpty())
    {
        DefaultOutputDir = EnvOutputDir;
        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Default output from ROA_FTI_OUTPUT_DIR: %s"), *EnvOutputDir);
    }
    else
    {
        // Try loading from config file
        FString ConfigPath = FPaths::Combine(FPaths::ProjectConfigDir(), TEXT("ROASettings.ini"));
        if (FPaths::FileExists(ConfigPath))
        {
            FString ConfigContent;
            if (FFileHelper::LoadFileToString(ConfigContent, *ConfigPath))
            {
                TArray<FString> Lines;
                ConfigContent.ParseIntoArrayLines(Lines);
                for (const FString& Line : Lines)
                {
                    if (Line.StartsWith(TEXT("OutputDir=")))
                    {
                        DefaultOutputDir = Line.Mid(10).TrimQuotes();
                        UE_LOG(LogTemp, Log, TEXT("ROA FTI: Default output from config: %s"), *DefaultOutputDir);
                        break;
                    }
                }
            }
        }
    }
    
    // Check if FTI is available
    if (!UFTIConnection::IsServiceAvailable())
    {
        FText Title = FText::FromString(TEXT("Import Method"));
        FText Message = FText::FromString(TEXT(
            "Choose import method:\n\n"
            "• FTI Pipeline (recommended): Converts to USD, better hierarchy support\n"
            "  Requires: FTI service running in WSL\n\n"
            "• Direct Import: Faster, but limited hierarchy support\n\n"
            "Use FTI Pipeline?"
        ));
        
        EAppReturnType::Type Result = FMessageDialog::Open(EAppMsgType::YesNoCancel, Message, Title);
        
        if (Result == EAppReturnType::Cancel)
        {
            return false;
        }
        
        OutOptions.bUseFTI = (Result == EAppReturnType::Yes);
    }
    else
    {
        OutOptions.bUseFTI = true;
    }
    
    // If using FTI, show folder browser for output destination
    if (OutOptions.bUseFTI)
    {
        // Use Desktop Platform module to show folder picker
        IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
        if (DesktopPlatform)
        {
            // Get the parent window handle
            void* ParentWindowHandle = nullptr;
            if (FSlateApplication::IsInitialized())
            {
                TSharedPtr<SWindow> ParentWindow = FSlateApplication::Get().GetActiveTopLevelWindow();
                if (ParentWindow.IsValid())
                {
                    ParentWindowHandle = ParentWindow->GetNativeWindow()->GetOSWindowHandle();
                }
            }
            
            FString SelectedFolder;
            const FString DialogTitle = TEXT("Select Output Folder for Converted Files");
            
            // Use default path or project saved dir
            FString StartPath = DefaultOutputDir.IsEmpty() 
                ? FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("FTI_Output"))
                : DefaultOutputDir;
            
            // Show folder picker dialog
            bool bFolderSelected = DesktopPlatform->OpenDirectoryDialog(
                ParentWindowHandle,
                DialogTitle,
                StartPath,
                SelectedFolder
            );
            
            if (bFolderSelected && !SelectedFolder.IsEmpty())
            {
                OutOptions.OutputDir = SelectedFolder;
                UE_LOG(LogTemp, Log, TEXT("ROA FTI: User selected output folder: %s"), *SelectedFolder);
            }
            else if (!bFolderSelected)
            {
                // User cancelled folder selection - cancel entire import
                UE_LOG(LogTemp, Log, TEXT("ROA FTI: User cancelled output folder selection"));
                return false;
            }
        }
        else
        {
            // DesktopPlatform not available, use default or config
            OutOptions.OutputDir = DefaultOutputDir;
            UE_LOG(LogTemp, Warning, TEXT("ROA FTI: DesktopPlatform not available, using default output"));
        }
    }
    
    return true;
}
