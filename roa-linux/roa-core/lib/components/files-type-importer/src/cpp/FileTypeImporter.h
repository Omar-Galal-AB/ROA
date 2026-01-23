// FileTypeImporter.h
// Main UE5 plugin for Files Type Importer
// Integrates with Unreal Engine's import pipeline

#pragma once

#include "CoreMinimal.h"
#include "UObject/ObjectMacros.h"
#include "UObject/Object.h"
#include "FileTypeImporter.generated.h"

/**
 * Import mode enumeration
 */
UENUM(BlueprintType)
enum class EImportMode : uint8
{
    Parts      UMETA(DisplayName = "Parts Only"),
    Assembly   UMETA(DisplayName = "Assembly Only"),
    Both       UMETA(DisplayName = "Both Parts and Assembly")
};

/**
 * Import result structure
 */
USTRUCT(BlueprintType)
struct FImportResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    bool bSuccess = false;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    FString RobotName;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    FString ContentPath;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    int32 PartsCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    TArray<FString> PartsPaths;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    FString AssemblyPath;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    FString ErrorMessage;

    UPROPERTY(BlueprintReadOnly, Category = "Import Result")
    TArray<FString> Warnings;
};

/**
 * Main File Type Importer class for UE5
 * Handles import of robot 3D models into Unreal Engine
 */
UCLASS(BlueprintType)
class FILETYPEIMPORTER_API UFileTypeImporter : public UObject
{
    GENERATED_BODY()

public:
    /**
     * Import a robot model from a 3D file
     * 
     * @param FilePath Path to the 3D model file
     * @param RobotName Name for the robot (optional, auto-generated if empty)
     * @param ImportMode Import mode (Parts, Assembly, or Both)
     * @return Import result with status and details
     */
    UFUNCTION(BlueprintCallable, Category = "File Type Importer")
    FImportResult ImportRobotModel(
        const FString& FilePath,
        const FString& RobotName,
        EImportMode ImportMode
    );

    /**
     * Get list of supported file formats
     * 
     * @return Array of supported format names (e.g., "urdf", "stl", "obj")
     */
    UFUNCTION(BlueprintCallable, Category = "File Type Importer")
    TArray<FString> GetSupportedFormats();

    /**
     * Validate a 3D model file without importing
     * 
     * @param FilePath Path to the file
     * @param OutFormat Detected format name
     * @param OutFileSize File size in bytes
     * @return True if valid, false otherwise
     */
    UFUNCTION(BlueprintCallable, Category = "File Type Importer")
    bool ValidateFile(
        const FString& FilePath,
        FString& OutFormat,
        int64& OutFileSize
    );

private:
    /**
     * Detect the format of a 3D model file
     * 
     * @param FilePath Path to the file
     * @return Format name or empty string if unknown
     */
    FString DetectFormat(const FString& FilePath);

    /**
     * Generate a robot name from the file path
     * 
     * @param FilePath Path to the file
     * @return Generated robot name
     */
    FString GenerateRobotName(const FString& FilePath);

    /**
     * Execute the actual import operation
     * 
     * @param FilePath Path to the source file
     * @param Format Detected format
     * @param RobotName Name for the robot
     * @param ImportMode Import mode
     * @return Import result
     */
    FImportResult ExecuteImport(
        const FString& FilePath,
        const FString& Format,
        const FString& RobotName,
        EImportMode ImportMode
    );
};
