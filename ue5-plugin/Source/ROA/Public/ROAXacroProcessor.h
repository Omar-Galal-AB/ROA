// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

/**
 * XACRO Processing Backend Types
 */
enum class EXacroBackend : uint8
{
	Unknown,
	ROS2,          // ros2 run xacro xacro
	ROS1,        // rosrun xacro xacro
	Standalone,    // xacro command
	EmbeddedPython // Embedded Python interpreter with XACRO package
};

/**
 * XACRO Processor - Converts XACRO files to URDF
 * 
 * Supports multiple backends with automatic fallback:
 * 1. ROS2 XACRO (fastest, if ROS2 installed)
 * 2. ROS1 XACRO (fast, if ROS1 installed)
 * 3. Standalone XACRO (medium, if installed via pip)
 * 4. Embedded Python (always works, bundled with plugin)
 */
class ROA_API FROAXacroProcessor
{
public:
	/**
	 * Convert XACRO file to URDF using best available backend
	 * @param XacroFilePath - Full path to .xacro file
	 * @param OutURDFPath - Output path for generated .urdf file (optional, auto-generates if empty)
	 * @param OutErrorMessage - Error message if conversion fails
	 * @return true if conversion succeeded
	 */
	static bool ConvertXacroToURDF(
		const FString& XacroFilePath,
		FString& OutURDFPath,
		FString& OutErrorMessage
	);

	/**
	 * Convert XACRO using specific backend
	 * @param Backend - Which backend to use
	 * @param XacroFilePath - Full path to .xacro file
	 * @param OutURDFPath - Output path
	 * @param OutErrorMessage - Error message if fails
	 * @return true if succeeded
	 */
	static bool ConvertXacroToURDFWithBackend(
		EXacroBackend Backend,
		const FString& XacroFilePath,
		FString& OutURDFPath,
		FString& OutErrorMessage
	);

	/**
	 * Check if XACRO processor is available on system
	 * @return true if any XACRO backend is available
	 */
	static bool IsXacroAvailable();

	/**
	 * Get information about available XACRO processor
	 * @param OutVersion - XACRO version string
	 * @param OutBackend - Backend type being used
	 * @return true if XACRO is available
	 */
	static bool GetXacroInfo(FString& OutVersion, EXacroBackend& OutBackend);

	/**
	 * Get best available backend (with caching)
	 * @return Best backend available, or EmbeddedPython as fallback
	 */
	static EXacroBackend GetBestBackend();

	/**
	 * Force refresh of backend detection (clears cache)
	 */
	static void RefreshBackendDetection();

private:
	// Detection methods
	static bool DetectROS2Xacro(FString& OutCommand);
	static bool DetectROS1Xacro(FString& OutCommand);
	static bool DetectStandaloneXacro(FString& OutCommand);
	static bool SetupEmbeddedPython();

	// Execution methods (one per backend)
	static bool ExecuteROS2Xacro(const FString& XacroFile, const FString& OutputFile, FString& OutError);
	static bool ExecuteROS1Xacro(const FString& XacroFile, const FString& OutputFile, FString& OutError);
	static bool ExecuteStandaloneXacro(const FString& XacroFile, const FString& OutputFile, FString& OutError);
	static bool ExecuteEmbeddedPythonXacro(const FString& XacroFile, const FString& OutputFile, FString& OutError);

	// Remote processing
	static bool ConvertXacroToURDFRemote(const FString& XacroFilePath, FString& OutURDFPath, FString& OutErrorMessage);

	// Generic execution
	static bool ExecuteXacroCommand(
		const FString& Command,
		const FString& XacroFile,
		const FString& OutputFile,
		FString& OutError
	);

	// Validation
	static bool ValidateXacroFile(const FString& XacroFilePath, FString& OutError);
	static bool ValidateGeneratedURDF(const FString& URDFFilePath, FString& OutError);

	// Embedded Python helpers
	static FString GetEmbeddedPythonPath();
	static FString GetXacroPythonScriptPath();
	static bool ExtractEmbeddedPythonResources();
	static bool IsEmbeddedPythonSetup();

	// Cached backend information
	static EXacroBackend CachedBackend;
	static FString CachedCommand;
	static bool bBackendCached;
	static bool bEmbeddedPythonSetup;
};
