// FileTypeImporter.cpp
// Main UE5 plugin implementation for Files Type Importer

#include "FileTypeImporter.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"

FImportResult UFileTypeImporter::ImportRobotModel(
    const FString& FilePath,
    const FString& RobotName,
    EImportMode ImportMode
)
{
    FImportResult Result;
    
    // Validate file exists
    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    if (!PlatformFile.FileExists(*FilePath))
    {
        Result.bSuccess = false;
        Result.ErrorMessage = FString::Printf(TEXT("File not found: %s"), *FilePath);
        return Result;
    }

    // Generate robot name if not provided
    FString ActualRobotName = RobotName;
    if (ActualRobotName.IsEmpty())
    {
        ActualRobotName = GenerateRobotName(FilePath);
    }
    Result.RobotName = ActualRobotName;

    // Detect file format
    FString Format = DetectFormat(FilePath);
    if (Format.IsEmpty())
    {
        Result.bSuccess = false;
        Result.ErrorMessage = FString::Printf(
            TEXT("Unknown or unsupported file format: %s"), 
            *FilePath
        );
        return Result;
    }

    // Execute the import
    Result = ExecuteImport(FilePath, Format, ActualRobotName, ImportMode);
    
    return Result;
}

TArray<FString> UFileTypeImporter::GetSupportedFormats()
{
    TArray<FString> Formats;
    Formats.Add(TEXT("urdf"));
    Formats.Add(TEXT("stl"));
    Formats.Add(TEXT("obj"));
    Formats.Add(TEXT("fbx"));
    Formats.Add(TEXT("dae"));
    Formats.Add(TEXT("step"));
    Formats.Add(TEXT("iges"));
    Formats.Add(TEXT("usd"));
    return Formats;
}

bool UFileTypeImporter::ValidateFile(
    const FString& FilePath,
    FString& OutFormat,
    int64& OutFileSize
)
{
    IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
    
    if (!PlatformFile.FileExists(*FilePath))
    {
        return false;
    }

    OutFileSize = PlatformFile.FileSize(*FilePath);
    OutFormat = DetectFormat(FilePath);
    
    return !OutFormat.IsEmpty();
}

FString UFileTypeImporter::DetectFormat(const FString& FilePath)
{
    FString Extension = FPaths::GetExtension(FilePath).ToLower();
    
    // Map extensions to format names
    if (Extension == TEXT("urdf") || Extension == TEXT("xacro"))
    {
        return TEXT("urdf");
    }
    else if (Extension == TEXT("stl"))
    {
        return TEXT("stl");
    }
    else if (Extension == TEXT("obj"))
    {
        return TEXT("obj");
    }
    else if (Extension == TEXT("fbx"))
    {
        return TEXT("fbx");
    }
    else if (Extension == TEXT("dae"))
    {
        return TEXT("dae");
    }
    else if (Extension == TEXT("step") || Extension == TEXT("stp"))
    {
        return TEXT("step");
    }
    else if (Extension == TEXT("iges") || Extension == TEXT("igs"))
    {
        return TEXT("iges");
    }
    else if (Extension == TEXT("usd") || Extension == TEXT("usda") || 
             Extension == TEXT("usdc") || Extension == TEXT("usdz"))
    {
        return TEXT("usd");
    }
    
    // Unknown format
    return FString();
}

FString UFileTypeImporter::GenerateRobotName(const FString& FilePath)
{
    FString FileName = FPaths::GetBaseFilename(FilePath);
    
    // Replace underscores and hyphens with spaces, then title case
    FileName = FileName.Replace(TEXT("_"), TEXT(" "));
    FileName = FileName.Replace(TEXT("-"), TEXT(" "));
    
    // Remove spaces for final name
    FileName = FileName.Replace(TEXT(" "), TEXT(""));
    
    return FileName;
}

FImportResult UFileTypeImporter::ExecuteImport(
    const FString& FilePath,
    const FString& Format,
    const FString& RobotName,
    EImportMode ImportMode
)
{
    FImportResult Result;
    Result.RobotName = RobotName;
    Result.ContentPath = FString::Printf(TEXT("/Game/Robots/%s"), *RobotName);
    
    // TODO: Implement actual import logic
    // This is a placeholder implementation
    // Will integrate with Python converters and USD import pipeline
    
    // For now, return a placeholder success
    Result.bSuccess = false;
    Result.ErrorMessage = TEXT("Import functionality not yet implemented - placeholder only");
    Result.Warnings.Add(TEXT("C++ UE5 plugin is skeleton implementation"));
    Result.Warnings.Add(TEXT("Actual import will integrate with Python conversion pipeline"));
    
    return Result;
}
