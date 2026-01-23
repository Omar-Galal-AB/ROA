// Copyright Epic Games, Inc. All Rights Reserved.

#include "ROAXacroProcessor.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformFileManager.h"
#include "Interfaces/IPluginManager.h"

// Cached backend
EXacroBackend FROAXacroProcessor::CachedBackend = EXacroBackend::Unknown;
FString FROAXacroProcessor::CachedCommand;
bool FROAXacroProcessor::bBackendCached = false;
bool FROAXacroProcessor::bEmbeddedPythonSetup = false;

// Helper function to read from pipe
static FString ReadPipeOutput(void* ReadPipe)
{
	FString Output;
	
	if (ReadPipe)
	{
		// Read pipe output using UE5 API
		FString PipeOutput = FPlatformProcess::ReadPipe(ReadPipe);
		Output += PipeOutput;
	}
	
	return Output;
}

bool FROAXacroProcessor::ConvertXacroToURDF(
	const FString& XacroFilePath,
	FString& OutURDFPath,
	FString& OutErrorMessage)
{
	// Validate input file
	if (!ValidateXacroFile(XacroFilePath, OutErrorMessage))
	{
		return false;
	}

	if (OutURDFPath.IsEmpty())
	{
		OutURDFPath = FPaths::GetPath(XacroFilePath) / 
			FPaths::GetBaseFilename(XacroFilePath) + TEXT(".urdf");
	}

	// Try local backends first
	EXacroBackend Backend = GetBestBackend();
	UE_LOG(LogTemp, Log, TEXT("ROA: Converting XACRO with backend: %d"), (int32)Backend);

	bool bSuccess = ConvertXacroToURDFWithBackend(Backend, XacroFilePath, OutURDFPath, OutErrorMessage);

	// If failed and not using embedded Python, try embedded Python fallback
	if (!bSuccess && Backend != EXacroBackend::EmbeddedPython)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA: Primary backend failed, trying embedded Python fallback"));
		
		FString FallbackError;
		bSuccess = ConvertXacroToURDFWithBackend(
			EXacroBackend::EmbeddedPython,
			XacroFilePath,
			OutURDFPath,
			FallbackError
		);

		if (!bSuccess)
		{
			OutErrorMessage = FString::Printf(
				TEXT("Local backends failed:\n%s\n\nEmbedded Python error:\n%s"),
				*OutErrorMessage,
				*FallbackError
			);
		}
	}

	// If all local backends failed, try remote processing
	if (!bSuccess)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA: All local backends failed, trying remote XACRO processing"));
		
		FString RemoteError;
		bSuccess = ConvertXacroToURDFRemote(XacroFilePath, OutURDFPath, RemoteError);
		
		if (!bSuccess)
		{
			OutErrorMessage = FString::Printf(
				TEXT("%s\n\nRemote processing error:\n%s"),
				*OutErrorMessage,
				*RemoteError
			);
		}
		else
		{
			UE_LOG(LogTemp, Log, TEXT("ROA: Successfully converted XACRO using remote processing"));
		}
	}

	if (bSuccess)
	{
		UE_LOG(LogTemp, Log, TEXT("ROA: Successfully converted XACRO to URDF: %s"), *OutURDFPath);
	}

	return bSuccess;
}

bool FROAXacroProcessor::ConvertXacroToURDFWithBackend(
	EXacroBackend Backend,
	const FString& XacroFilePath,
	FString& OutURDFPath,
	FString& OutErrorMessage)
{
	bool bSuccess = false;

	switch (Backend)
	{
	case EXacroBackend::ROS2:
		bSuccess = ExecuteROS2Xacro(XacroFilePath, OutURDFPath, OutErrorMessage);
		break;

	case EXacroBackend::ROS1:
		bSuccess = ExecuteROS1Xacro(XacroFilePath, OutURDFPath, OutErrorMessage);
		break;

	case EXacroBackend::Standalone:
		bSuccess = ExecuteStandaloneXacro(XacroFilePath, OutURDFPath, OutErrorMessage);
		break;

	case EXacroBackend::EmbeddedPython:
		bSuccess = ExecuteEmbeddedPythonXacro(XacroFilePath, OutURDFPath, OutErrorMessage);
		break;

	default:
		OutErrorMessage = TEXT("No XACRO backend available");
		return false;
	}

	if (bSuccess)
	{
		// Validate generated URDF
		if (!ValidateGeneratedURDF(OutURDFPath, OutErrorMessage))
		{
			return false;
		}
	}

	return bSuccess;
}

EXacroBackend FROAXacroProcessor::GetBestBackend()
{
	if (bBackendCached && CachedBackend != EXacroBackend::Unknown)
	{
		return CachedBackend;
	}

	// Try backends in order of preference
	FString DummyCommand;

	// 1. ROS2 (fastest, most features)
	if (DetectROS2Xacro(DummyCommand))
	{
		CachedBackend = EXacroBackend::ROS2;
		CachedCommand = DummyCommand;
		bBackendCached = true;
		UE_LOG(LogTemp, Log, TEXT("ROA: Selected ROS2 XACRO backend"));
		return CachedBackend;
	}

	// 2. ROS1 (fast, stable)
	if (DetectROS1Xacro(DummyCommand))
	{
		CachedBackend = EXacroBackend::ROS1;
		CachedCommand = DummyCommand;
		bBackendCached = true;
		UE_LOG(LogTemp, Log, TEXT("ROA: Selected ROS1 XACRO backend"));
		return CachedBackend;
	}

	// 3. Standalone (simple, if installed)
	if (DetectStandaloneXacro(DummyCommand))
	{
		CachedBackend = EXacroBackend::Standalone;
		CachedCommand = DummyCommand;
		bBackendCached = true;
		UE_LOG(LogTemp, Log, TEXT("ROA: Selected Standalone XACRO backend"));
		return CachedBackend;
	}

	// 4. Embedded Python (always available as fallback)
	if (SetupEmbeddedPython())
	{
		CachedBackend = EXacroBackend::EmbeddedPython;
		bBackendCached = true;
		UE_LOG(LogTemp, Log, TEXT("ROA: Selected Embedded Python XACRO backend"));
		return CachedBackend;
	}

	UE_LOG(LogTemp, Error, TEXT("ROA: No XACRO backend available!"));
	return EXacroBackend::Unknown;
}

void FROAXacroProcessor::RefreshBackendDetection()
{
	bBackendCached = false;
	CachedBackend = EXacroBackend::Unknown;
	CachedCommand.Empty();
	UE_LOG(LogTemp, Log, TEXT("ROA: Backend detection cache cleared"));
}

bool FROAXacroProcessor::IsXacroAvailable()
{
	return GetBestBackend() != EXacroBackend::Unknown;
}

bool FROAXacroProcessor::GetXacroInfo(FString& OutVersion, EXacroBackend& OutBackend)
{
	OutBackend = GetBestBackend();

	if (OutBackend == EXacroBackend::Unknown)
	{
		return false;
	}

	// TODO: Get actual version from each backend
	switch (OutBackend)
	{
	case EXacroBackend::ROS2:
		OutVersion = TEXT("ROS2");
		break;
	case EXacroBackend::ROS1:
		OutVersion = TEXT("ROS1");
		break;
	case EXacroBackend::Standalone:
		OutVersion = TEXT("Standalone");
		break;
	case EXacroBackend::EmbeddedPython:
		OutVersion = TEXT("Embedded Python");
		break;
	default:
		OutVersion = TEXT("Unknown");
		break;
	}

	return true;
}

// Backend Detection Methods

bool FROAXacroProcessor::DetectROS2Xacro(FString& OutCommand)
{
#if PLATFORM_WINDOWS
	// Try: ros2 run xacro xacro
	FString TestCommand = TEXT("ros2");
	
	FString Output;
	FString Errors;
	int32 ReturnCode = -1;
	
	// Try to execute ros2 --version
	void* ReadPipe = nullptr;
	void* WritePipe = nullptr;
	FPlatformProcess::CreatePipe(ReadPipe, WritePipe);
	
	FProcHandle ProcHandle = FPlatformProcess::CreateProc(
		*TestCommand,
		TEXT("--version"),
		true, false, false,
		nullptr, 0,
		nullptr, WritePipe, ReadPipe
	);

	if (ProcHandle.IsValid())
	{
		FPlatformProcess::WaitForProc(ProcHandle);
		FPlatformProcess::GetProcReturnCode(ProcHandle, &ReturnCode);
		Output = ReadPipeOutput(ReadPipe);
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
		FPlatformProcess::CloseProc(ProcHandle);

		if (ReturnCode == 0 || Output.Contains(TEXT("ros2"), ESearchCase::IgnoreCase))
		{
			OutCommand = TEXT("ros2 run xacro xacro");
			UE_LOG(LogTemp, Log, TEXT("ROA: Detected ROS2 XACRO"));
			return true;
		}
	}
	else
	{
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
	}
#elif PLATFORM_LINUX || PLATFORM_MAC
	// Check for ros2 command
	if (FPaths::FileExists(TEXT("/usr/bin/ros2")) ||
		FPaths::FileExists(TEXT("/opt/ros/humble/bin/ros2")) ||
		FPaths::FileExists(TEXT("/opt/ros/iron/bin/ros2")))
	{
		OutCommand = TEXT("ros2 run xacro xacro");
		return true;
	}
#endif

	return false;
}

bool FROAXacroProcessor::DetectROS1Xacro(FString& OutCommand)
{
#if PLATFORM_WINDOWS
	// ROS1 on Windows is rare
	return false;
#else
	// Check for rosrun on Linux/Mac
	if (FPaths::FileExists(TEXT("/usr/bin/rosrun")) ||
		FPaths::FileExists(TEXT("/opt/ros/noetic/bin/rosrun")) ||
		FPaths::FileExists(TEXT("/opt/ros/melodic/bin/rosrun")))
	{
		OutCommand = TEXT("rosrun xacro xacro");
		return true;
	}
	
	return false;
#endif
}

bool FROAXacroProcessor::DetectStandaloneXacro(FString& OutCommand)
{
	FString TestCommand = TEXT("xacro");
	
	FString Output;
	int32 ReturnCode = -1;
	
	void* ReadPipe = nullptr;
	void* WritePipe = nullptr;
	FPlatformProcess::CreatePipe(ReadPipe, WritePipe);
	
	FProcHandle ProcHandle = FPlatformProcess::CreateProc(
		*TestCommand,
		TEXT("--version"),
		true, false, false,
		nullptr, 0,
		nullptr, WritePipe, ReadPipe
	);

	if (ProcHandle.IsValid())
	{
		FPlatformProcess::WaitForProc(ProcHandle);
		FPlatformProcess::GetProcReturnCode(ProcHandle, &ReturnCode);
		Output = ReadPipeOutput(ReadPipe);
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
		FPlatformProcess::CloseProc(ProcHandle);

		if (ReturnCode == 0 || Output.Contains(TEXT("xacro"), ESearchCase::IgnoreCase))
		{
			OutCommand = TEXT("xacro");
			UE_LOG(LogTemp, Log, TEXT("ROA: Detected standalone XACRO"));
			return true;
		}
	}
	else
	{
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
	}

	return false;
}

bool FROAXacroProcessor::SetupEmbeddedPython()
{
	if (bEmbeddedPythonSetup)
	{
		return true;
	}

	// Extract embedded Python runtime and XACRO package
	if (!ExtractEmbeddedPythonResources())
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA: Failed to extract embedded Python resources"));
		return false;
	}

	bEmbeddedPythonSetup = true;
	UE_LOG(LogTemp, Log, TEXT("ROA: Embedded Python XACRO setup complete"));
	return true;
}

// Execution Methods

bool FROAXacroProcessor::ExecuteROS2Xacro(const FString& XacroFile, const FString& OutputFile, FString& OutError)
{
	return ExecuteXacroCommand(TEXT("ros2 run xacro xacro"), XacroFile, OutputFile, OutError);
}

bool FROAXacroProcessor::ExecuteROS1Xacro(const FString& XacroFile, const FString& OutputFile, FString& OutError)
{
	return ExecuteXacroCommand(TEXT("rosrun xacro xacro"), XacroFile, OutputFile, OutError);
}

bool FROAXacroProcessor::ExecuteStandaloneXacro(const FString& XacroFile, const FString& OutputFile, FString& OutError)
{
	return ExecuteXacroCommand(TEXT("xacro"), XacroFile, OutputFile, OutError);
}

bool FROAXacroProcessor::ExecuteEmbeddedPythonXacro(const FString& XacroFile, const FString& OutputFile, FString& OutError)
{
	FString PythonPath = GetEmbeddedPythonPath();
	FString ScriptPath = GetXacroPythonScriptPath();

	if (!FPaths::FileExists(PythonPath))
	{
		OutError = FString::Printf(TEXT("Embedded Python not found at: %s"), *PythonPath);
		return false;
	}

	if (!FPaths::FileExists(ScriptPath))
	{
		OutError = FString::Printf(TEXT("XACRO Python script not found at: %s"), *ScriptPath);
		return false;
	}

	// Convert input and output paths to absolute paths
	FString AbsoluteXacroFile = FPaths::ConvertRelativePathToFull(XacroFile);
	FPaths::NormalizeFilename(AbsoluteXacroFile);
	
	FString AbsoluteOutputFile = FPaths::ConvertRelativePathToFull(OutputFile);
	FPaths::NormalizeFilename(AbsoluteOutputFile);
	
	UE_LOG(LogTemp, Log, TEXT("ROA: Input XACRO absolute path: %s"), *AbsoluteXacroFile);
	UE_LOG(LogTemp, Log, TEXT("ROA: Output URDF absolute path: %s"), *AbsoluteOutputFile);

	// Execute: python xacro_processor.py input.xacro output.urdf
	FString Arguments = FString::Printf(
		TEXT("\"%s\" \"%s\" \"%s\""),
		*ScriptPath,
		*AbsoluteXacroFile,
		*AbsoluteOutputFile
	);

	UE_LOG(LogTemp, Log, TEXT("ROA: Executing embedded Python XACRO: %s %s"), *PythonPath, *Arguments);

	int32 ReturnCode = -1;
	FString Output;

	void* ReadPipe = nullptr;
	void* WritePipe = nullptr;
	FPlatformProcess::CreatePipe(ReadPipe, WritePipe);
	
	FProcHandle ProcHandle = FPlatformProcess::CreateProc(
		*PythonPath,
		*Arguments,
		true, false, false,
		nullptr, 0,
		*FPaths::GetPath(ScriptPath), // Working directory
		WritePipe, ReadPipe
	);

	if (ProcHandle.IsValid())
	{
		FPlatformProcess::WaitForProc(ProcHandle);
		FPlatformProcess::GetProcReturnCode(ProcHandle, &ReturnCode);
		Output = ReadPipeOutput(ReadPipe);
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
		FPlatformProcess::CloseProc(ProcHandle);

		if (ReturnCode != 0)
		{
			OutError = FString::Printf(
				TEXT("Embedded Python XACRO conversion failed (code %d):\n%s"),
				ReturnCode,
				*Output
			);
			UE_LOG(LogTemp, Error, TEXT("ROA: %s"), *OutError);
			return false;
		}

		return FPaths::FileExists(AbsoluteOutputFile);
	}
	else
	{
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
		OutError = TEXT("Failed to launch embedded Python process");
		return false;
	}
}

bool FROAXacroProcessor::ExecuteXacroCommand(
	const FString& Command,
	const FString& XacroFile,
	const FString& OutputFile,
	FString& OutError)
{
	// Build full command: <command> <xacro_file> -o <output_file>
	FString FullCommand = FString::Printf(
		TEXT("%s \"%s\" -o \"%s\""),
		*Command,
		*XacroFile,
		*OutputFile
	);

	UE_LOG(LogTemp, Log, TEXT("ROA: Executing: %s"), *FullCommand);

	int32 ReturnCode = -1;
	FString Output;

	void* ReadPipe = nullptr;
	void* WritePipe = nullptr;
	FPlatformProcess::CreatePipe(ReadPipe, WritePipe);

#if PLATFORM_WINDOWS
	// Use cmd.exe on Windows for proper PATH resolution
	FProcHandle ProcHandle = FPlatformProcess::CreateProc(
		TEXT("cmd.exe"),
		*FString::Printf(TEXT("/C %s"), *FullCommand),
		true, false, false,
		nullptr, 0,
		nullptr, WritePipe, ReadPipe
	);
#else
	// Use sh on Linux/Mac
	FProcHandle ProcHandle = FPlatformProcess::CreateProc(
		TEXT("/bin/sh"),
		*FString::Printf(TEXT("-c \"%s\""), *FullCommand),
		true, false, false,
		nullptr, 0,
		nullptr, WritePipe, ReadPipe
	);
#endif

	if (ProcHandle.IsValid())
	{
		FPlatformProcess::WaitForProc(ProcHandle);
		FPlatformProcess::GetProcReturnCode(ProcHandle, &ReturnCode);
		Output = ReadPipeOutput(ReadPipe);
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
		FPlatformProcess::CloseProc(ProcHandle);

		if (ReturnCode != 0)
		{
			OutError = FString::Printf(
				TEXT("XACRO conversion failed (code %d):\n%s"),
				ReturnCode,
				*Output
			);
			UE_LOG(LogTemp, Error, TEXT("ROA: %s"), *OutError);
			return false;
		}

		if (!FPaths::FileExists(OutputFile))
		{
			OutError = FString::Printf(
				TEXT("XACRO completed but output file not found: %s"),
				*OutputFile
			);
			UE_LOG(LogTemp, Error, TEXT("ROA: %s"), *OutError);
			return false;
		}

		return true;
	}
	else
	{
		FPlatformProcess::ClosePipe(ReadPipe, WritePipe);
		OutError = TEXT("Failed to launch XACRO process");
		return false;
	}
}

// Validation Methods

bool FROAXacroProcessor::ValidateXacroFile(const FString& XacroFilePath, FString& OutError)
{
	if (!FPaths::FileExists(XacroFilePath))
	{
		OutError = FString::Printf(TEXT("XACRO file not found: %s"), *XacroFilePath);
		return false;
	}

	FString Extension = FPaths::GetExtension(XacroFilePath);
	if (!Extension.Equals(TEXT("xacro"), ESearchCase::IgnoreCase))
	{
		OutError = FString::Printf(TEXT("Invalid extension. Expected .xacro, got: .%s"), *Extension);
		return false;
	}

	FString FileContent;
	if (!FFileHelper::LoadFileToString(FileContent, *XacroFilePath))
	{
		OutError = FString::Printf(TEXT("Cannot read XACRO file: %s"), *XacroFilePath);
		return false;
	}

	if (!FileContent.Contains(TEXT("<robot"), ESearchCase::IgnoreCase))
	{
		OutError = TEXT("XACRO file does not contain a robot definition");
		return false;
	}

	return true;
}

bool FROAXacroProcessor::ValidateGeneratedURDF(const FString& URDFFilePath, FString& OutError)
{
	if (!FPaths::FileExists(URDFFilePath))
	{
		OutError = FString::Printf(TEXT("Generated URDF not found: %s"), *URDFFilePath);
		return false;
	}

	int64 FileSize = IFileManager::Get().FileSize(*URDFFilePath);
	if (FileSize <= 0)
	{
		OutError = TEXT("Generated URDF is empty");
		return false;
	}

	FString FileContent;
	if (!FFileHelper::LoadFileToString(FileContent, *URDFFilePath))
	{
		OutError = FString::Printf(TEXT("Cannot read generated URDF: %s"), *URDFFilePath);
		return false;
	}

	if (!FileContent.Contains(TEXT("<robot"), ESearchCase::IgnoreCase))
	{
		OutError = TEXT("Generated URDF does not contain a valid robot definition");
		return false;
	}

	if (FileContent.Contains(TEXT("xacro:"), ESearchCase::IgnoreCase))
	{
		OutError = TEXT("Generated URDF still contains XACRO tags");
		return false;
	}

	return true;
}

// Embedded Python Helpers

FString FROAXacroProcessor::GetEmbeddedPythonPath()
{
	// Get plugin directory - plugin name is "ROA" as defined in ROA.uplugin
	TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("ROA"));
	if (!Plugin.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("ROA: Could not find ROA plugin!"));
		return TEXT("");
	}

	FString PluginDir = Plugin->GetBaseDir();
	
	// Convert to absolute path and normalize
	PluginDir = FPaths::ConvertRelativePathToFull(PluginDir);
	FPaths::NormalizeDirectoryName(PluginDir);
	
	UE_LOG(LogTemp, Log, TEXT("ROA: Plugin absolute directory: %s"), *PluginDir);
	
#if PLATFORM_WINDOWS
	FString PythonPath = FPaths::Combine(PluginDir, TEXT("ThirdParty"), TEXT("Python"), TEXT("python-embed-win64"), TEXT("python.exe"));
#elif PLATFORM_LINUX
	FString PythonPath = FPaths::Combine(PluginDir, TEXT("ThirdParty"), TEXT("Python"), TEXT("bin"), TEXT("python3"));
#elif PLATFORM_MAC
	FString PythonPath = FPaths::Combine(PluginDir, TEXT("ThirdParty"), TEXT("Python"), TEXT("bin"), TEXT("python3"));
#else
	FString PythonPath = TEXT("");
#endif

	// Normalize the final path
	FPaths::NormalizeFilename(PythonPath);
	UE_LOG(LogTemp, Log, TEXT("ROA: Python executable path: %s"), *PythonPath);
	
	return PythonPath;
}

FString FROAXacroProcessor::GetXacroPythonScriptPath()
{
	TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("ROA"));
	if (!Plugin.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("ROA: Could not find ROA plugin!"));
		return TEXT("");
	}

	FString PluginDir = Plugin->GetBaseDir();
	
	// Convert to absolute path and normalize
	PluginDir = FPaths::ConvertRelativePathToFull(PluginDir);
	FPaths::NormalizeDirectoryName(PluginDir);
	
	FString ScriptPath = FPaths::Combine(PluginDir, TEXT("Resources"), TEXT("Python"), TEXT("xacro_processor.py"));
	FPaths::NormalizeFilename(ScriptPath);
	
	UE_LOG(LogTemp, Log, TEXT("ROA: XACRO script absolute path: %s"), *ScriptPath);
	return ScriptPath;
}

bool FROAXacroProcessor::ExtractEmbeddedPythonResources()
{
	// Check if resources already extracted
	FString PythonPath = GetEmbeddedPythonPath();
	FString ScriptPath = GetXacroPythonScriptPath();

	if (FPaths::FileExists(PythonPath) && FPaths::FileExists(ScriptPath))
	{
		UE_LOG(LogTemp, Log, TEXT("ROA: Embedded Python resources already extracted"));
		return true;
	}

	// Resources will be extracted on first run
	// For now, we'll create placeholder
	UE_LOG(LogTemp, Warning, TEXT("ROA: Embedded Python resources need to be installed"));
	UE_LOG(LogTemp, Warning, TEXT("ROA: Expected locations:"));
	UE_LOG(LogTemp, Warning, TEXT("  Python: %s"), *PythonPath);
	UE_LOG(LogTemp, Warning, TEXT("  Script: %s"), *ScriptPath);

	// TODO: Implement actual extraction from Resources
	return false;
}

bool FROAXacroProcessor::IsEmbeddedPythonSetup()
{
	return bEmbeddedPythonSetup && 
		FPaths::FileExists(GetEmbeddedPythonPath()) && 
		FPaths::FileExists(GetXacroPythonScriptPath());
}

bool FROAXacroProcessor::ConvertXacroToURDFRemote(
	const FString& XacroFilePath,
	FString& OutURDFPath,
	FString& OutErrorMessage)
{
	// Use FTI IPC service for XACRO conversion
	// The service runs in WSL with full ROS2 support for $(find pkg) resolution
	
	UE_LOG(LogTemp, Log, TEXT("ROA: Attempting remote XACRO conversion via FTI IPC"));
	UE_LOG(LogTemp, Log, TEXT("ROA: Input: %s"), *XacroFilePath);
	UE_LOG(LogTemp, Log, TEXT("ROA: Output: %s"), *OutURDFPath);

	// Get IPC folder path
	FString IPCFolder = TEXT("D:/ROA/.ipc");
	FString RequestsFolder = FPaths::Combine(IPCFolder, TEXT("requests"));
	FString ResponsesFolder = FPaths::Combine(IPCFolder, TEXT("responses"));
	
	// Ensure folders exist
	IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
	PlatformFile.CreateDirectoryTree(*RequestsFolder);
	
	// Generate request ID
	FGuid Guid = FGuid::NewGuid();
	FString RequestId = FString::Printf(TEXT("xacro_%s"), *Guid.ToString(EGuidFormats::Short));
	
	// Convert Windows paths to WSL paths
	FString WslXacroPath = XacroFilePath;
	FString WslOutputPath = OutURDFPath;
	
	// D:\path -> /mnt/d/path
	if (WslXacroPath.Len() > 2 && WslXacroPath[1] == ':')
	{
		TCHAR DriveLetter = FChar::ToLower(WslXacroPath[0]);
		WslXacroPath = FString::Printf(TEXT("/mnt/%c%s"), DriveLetter, *WslXacroPath.RightChop(2));
		WslXacroPath = WslXacroPath.Replace(TEXT("\\"), TEXT("/"));
	}
	if (WslOutputPath.Len() > 2 && WslOutputPath[1] == ':')
	{
		TCHAR DriveLetter = FChar::ToLower(WslOutputPath[0]);
		WslOutputPath = FString::Printf(TEXT("/mnt/%c%s"), DriveLetter, *WslOutputPath.RightChop(2));
		WslOutputPath = WslOutputPath.Replace(TEXT("\\"), TEXT("/"));
	}
	
	// Build request JSON
	TSharedPtr<FJsonObject> RequestJson = MakeShareable(new FJsonObject);
	RequestJson->SetStringField(TEXT("protocol_version"), TEXT("1.0.0"));
	RequestJson->SetStringField(TEXT("request_id"), RequestId);
	RequestJson->SetStringField(TEXT("command"), TEXT("convert_xacro"));
	RequestJson->SetStringField(TEXT("source_file"), WslXacroPath);
	RequestJson->SetStringField(TEXT("output_file"), WslOutputPath);
	RequestJson->SetNumberField(TEXT("timestamp"), FDateTime::UtcNow().ToUnixTimestamp());
	
	// Options
	TSharedPtr<FJsonObject> OptionsJson = MakeShareable(new FJsonObject);
	OptionsJson->SetBoolField(TEXT("resolve_packages"), true);
	RequestJson->SetObjectField(TEXT("options"), OptionsJson);
	
	// Serialize
	FString RequestContent;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&RequestContent);
	FJsonSerializer::Serialize(RequestJson.ToSharedRef(), Writer);
	
	// Write request file
	FString RequestFile = FPaths::Combine(RequestsFolder, FString::Printf(TEXT("%s.json"), *RequestId));
	if (!FFileHelper::SaveStringToFile(RequestContent, *RequestFile))
	{
		OutErrorMessage = TEXT("Failed to write IPC request file");
		return false;
	}
	
	UE_LOG(LogTemp, Log, TEXT("ROA: Sent XACRO conversion request: %s"), *RequestId);
	
	// Wait for response (with timeout)
	FString ResponseFile = FPaths::Combine(ResponsesFolder, FString::Printf(TEXT("%s.response.json"), *RequestId));
	
	double StartTime = FPlatformTime::Seconds();
	const double TimeoutSeconds = 60.0;  // 1 minute timeout
	
	while ((FPlatformTime::Seconds() - StartTime) < TimeoutSeconds)
	{
		if (FPaths::FileExists(ResponseFile))
		{
			FString ResponseContent;
			if (FFileHelper::LoadFileToString(ResponseContent, *ResponseFile))
			{
				// Delete response file
				IFileManager::Get().Delete(*ResponseFile);
				
				// Parse response
				TSharedPtr<FJsonObject> ResponseJson;
				TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ResponseContent);
				
				if (FJsonSerializer::Deserialize(Reader, ResponseJson) && ResponseJson.IsValid())
				{
					bool bSuccess = ResponseJson->GetBoolField(TEXT("success"));
					
					if (bSuccess)
					{
						FString OutputPath = ResponseJson->GetStringField(TEXT("output_file"));
						
						// Convert WSL path back to Windows
						if (OutputPath.StartsWith(TEXT("/mnt/")))
						{
							TCHAR DriveLetter = OutputPath[5];
							OutURDFPath = FString::Printf(TEXT("%c:%s"), FChar::ToUpper(DriveLetter), *OutputPath.RightChop(6));
							OutURDFPath = OutURDFPath.Replace(TEXT("/"), TEXT("\\"));
						}
						
						UE_LOG(LogTemp, Log, TEXT("ROA: XACRO conversion successful: %s"), *OutURDFPath);
						return true;
					}
					else
					{
						OutErrorMessage = ResponseJson->GetStringField(TEXT("error"));
						return false;
					}
				}
			}
		}
		
		// Wait before checking again
		FPlatformProcess::Sleep(0.1f);
	}
	
	OutErrorMessage = TEXT("XACRO conversion timed out. Is FTI IPC service running?\n\n"
		"Start the service with:\n"
		"  python /opt/roa/.../roa_ipc_service.py --start");
	return false;
}
