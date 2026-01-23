// Copyright Epic Games, Inc. All Rights Reserved.

#include "ROAURDFFactory.h"
#include "ROAURDFParser.h"
#include "ROARobotActor.h"
#include "ROAXacroProcessor.h"
#include "Editor.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Misc/MessageDialog.h"

UROAURDFFactory::UROAURDFFactory()
{
	bCreateNew = false;
	bEditAfterNew = true;
	bEditorImport = true;
	bText = false;
	
	SupportedClass = UBlueprint::StaticClass();
	
	// Register supported file extensions
	Formats.Add(TEXT("urdf;Universal Robot Description Format"));
	Formats.Add(TEXT("URDF;Universal Robot Description Format"));
}

bool UROAURDFFactory::DoesSupportClass(UClass* Class)
{
	return Class == UBlueprint::StaticClass();
}

bool UROAURDFFactory::FactoryCanImport(const FString& Filename)
{
	FString Extension = FPaths::GetExtension(Filename);
	return Extension.Equals(TEXT("urdf"), ESearchCase::IgnoreCase);
}

FText UROAURDFFactory::GetDisplayName() const
{
	return FText::FromString(TEXT("Robot Description (URDF)"));
}

UObject* UROAURDFFactory::FactoryCreateFile(UClass* InClass, UObject* InParent, FName InName, EObjectFlags Flags,
	const FString& Filename, const TCHAR* Parms, FFeedbackContext* Warn, bool& bOutOperationCanceled)
{
	bOutOperationCanceled = false;
	
	UE_LOG(LogTemp, Log, TEXT("ROA: Importing URDF file: %s"), *Filename);
	
	// Show import dialog (optional)
	FText Title = FText::FromString(TEXT("Import Robot URDF"));
	FText Message = FText::Format(
		FText::FromString(TEXT("Import robot from:\n{0}\n\nThis will create a Robot Blueprint actor.")),
		FText::FromString(Filename)
	);
	
	EAppReturnType::Type Result = FMessageDialog::Open(EAppMsgType::OkCancel, Message, Title);
	
	if (Result == EAppReturnType::Cancel)
	{
		bOutOperationCanceled = true;
		return nullptr;
	}
	
	// Import the robot
	UObject* ImportedObject = ImportRobotFromURDF(InParent, InName, Filename, Warn);
	
	if (ImportedObject)
	{
		UE_LOG(LogTemp, Log, TEXT("ROA: Successfully imported robot: %s"), *ImportedObject->GetName());
		
		// Show success message
		FMessageDialog::Open(
			EAppMsgType::Ok,
			FText::FromString(TEXT("Robot imported successfully!\n\nYou can now drag the blueprint into your level.")),
			FText::FromString(TEXT("Import Complete"))
		);
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("ROA: Failed to import URDF file"));
		Warn->Logf(ELogVerbosity::Error, TEXT("Failed to import URDF file: %s"), *Filename);
	}
	
	return ImportedObject;
}

UObject* UROAURDFFactory::ImportRobotFromURDF(UObject* InParent, FName InName, const FString& URDFPath, FFeedbackContext* Warn)
{
	// Parse URDF file
	FROARobotDescription RobotDesc;
	if (!FROAURDFParser::ParseURDF(URDFPath, RobotDesc))
	{
		Warn->Logf(ELogVerbosity::Error, TEXT("Failed to parse URDF file"));
		return nullptr;
	}
	
	// Create robot blueprint
	return CreateRobotBlueprint(InParent, InName, RobotDesc);
}

UObject* UROAURDFFactory::CreateRobotBlueprint(UObject* InParent, FName InName, const FROARobotDescription& Description)
{
	// Create blueprint based on ROARobotActor
	UClass* ParentClass = AROARobotActor::StaticClass();
	
	// Create the blueprint
	UBlueprint* NewBlueprint = FKismetEditorUtilities::CreateBlueprint(
		ParentClass,
		InParent,
		InName,
		BPTYPE_Normal,
		UBlueprint::StaticClass(),
		UBlueprintGeneratedClass::StaticClass(),
		FName("ROAURDFFactory")
	);
	
	if (!NewBlueprint)
	{
		UE_LOG(LogTemp, Error, TEXT("Failed to create blueprint"));
		return nullptr;
	}
	
	// Note: RobotId and RobotType are protected members
	// They can be set via Blueprint editor or runtime initialization
	// For now, we just log the robot information
	UE_LOG(LogTemp, Log, TEXT("Robot blueprint created: %s with %d links and %d joints"),
		*Description.RobotName, Description.Links.Num(), Description.Joints.Num());
	
	// Compile blueprint
	FKismetEditorUtilities::CompileBlueprint(NewBlueprint);
	
	// Mark package as dirty
	NewBlueprint->MarkPackageDirty();
	
	// Notify asset registry
	FAssetRegistryModule::AssetCreated(NewBlueprint);
	
	return NewBlueprint;
}

bool UROAURDFFactory::CanReimport(UObject* Obj, TArray<FString>& OutFilenames)
{
	// Check if object is a blueprint derived from ROARobotActor
	if (UBlueprint* Blueprint = Cast<UBlueprint>(Obj))
	{
		if (Blueprint->ParentClass && Blueprint->ParentClass->IsChildOf(AROARobotActor::StaticClass()))
		{
			// TODO: Store original URDF path in blueprint metadata
			return true;
		}
	}
	return false;
}

void UROAURDFFactory::SetReimportPaths(UObject* Obj, const TArray<FString>& NewReimportPaths)
{
	// TODO: Store reimport path in blueprint metadata
}

EReimportResult::Type UROAURDFFactory::Reimport(UObject* Obj)
{
	// TODO: Implement reimport functionality
	return EReimportResult::Failed;
}

int32 UROAURDFFactory::GetPriority() const
{
	// Return default import priority
	return 0;
}

// ============================================================================
// XACRO Factory
// ============================================================================

UROAXacroFactory::UROAXacroFactory()
{
	bCreateNew = false;
	bEditAfterNew = true;
	bEditorImport = true;
	bText = false;
	
	SupportedClass = UBlueprint::StaticClass();
	
	Formats.Add(TEXT("xacro;XML Macros (ROS)"));
	Formats.Add(TEXT("XACRO;XML Macros (ROS)"));
}

bool UROAXacroFactory::FactoryCanImport(const FString& Filename)
{
	FString Extension = FPaths::GetExtension(Filename);
	return Extension.Equals(TEXT("xacro"), ESearchCase::IgnoreCase);
}

FText UROAXacroFactory::GetDisplayName() const
{
	return FText::FromString(TEXT("Robot Description (XACRO)"));
}

UObject* UROAXacroFactory::FactoryCreateFile(UClass* InClass, UObject* InParent, FName InName, EObjectFlags Flags,
	const FString& Filename, const TCHAR* Parms, FFeedbackContext* Warn, bool& bOutOperationCanceled)
{
	bOutOperationCanceled = false;
	
	UE_LOG(LogTemp, Log, TEXT("ROA: Importing XACRO file: %s"), *Filename);
	
	// Check if XACRO processor is available
	if (!FROAXacroProcessor::IsXacroAvailable())
	{
		// Show original message if XACRO not available
		FText Title = FText::FromString(TEXT("XACRO Import"));
		FText Message = FText::FromString(TEXT(
			"XACRO import requires preprocessing.\n\n"
			"XACRO processor not found on system.\n\n"
			"Please install ROS/ROS2 or standalone XACRO:\n"
			"  pip install xacro\n\n"
			"Then restart UE5 Editor."
		));
		
		FMessageDialog::Open(EAppMsgType::Ok, Message, Title);
		bOutOperationCanceled = true;
		return nullptr;
	}

	// Show processing dialog
	FText Title = FText::FromString(TEXT("Processing XACRO"));
	FText Message = FText::Format(
		FText::FromString(TEXT("Converting XACRO to URDF:\n{0}\n\nThis may take a moment...")),
		FText::FromString(Filename)
	);
	
	// In a real implementation, this would be a progress dialog
	// For now, we'll process synchronously
	UE_LOG(LogTemp, Log, TEXT("ROA: Processing XACRO file..."));

	// Convert XACRO to URDF
	FString URDFPath;
	FString ErrorMessage;
	
	if (!FROAXacroProcessor::ConvertXacroToURDF(Filename, URDFPath, ErrorMessage))
	{
		// Conversion failed
		FText ErrorTitle = FText::FromString(TEXT("XACRO Conversion Failed"));
		FText ErrorMsg = FText::Format(
			FText::FromString(TEXT("Failed to convert XACRO to URDF:\n\n{0}\n\nPlease check the XACRO file and try again.")),
			FText::FromString(ErrorMessage)
		);
		
		FMessageDialog::Open(EAppMsgType::Ok, ErrorMsg, ErrorTitle);
		Warn->Logf(ELogVerbosity::Error, TEXT("XACRO conversion failed: %s"), *ErrorMessage);
		
		bOutOperationCanceled = true;
		return nullptr;
	}

	UE_LOG(LogTemp, Log, TEXT("ROA: XACRO converted to URDF: %s"), *URDFPath);

	// Now import the generated URDF using URDF factory
	UROAURDFFactory* URDFFactory = NewObject<UROAURDFFactory>();
	if (!URDFFactory)
	{
		Warn->Logf(ELogVerbosity::Error, TEXT("Failed to create URDF factory"));
		bOutOperationCanceled = true;
		return nullptr;
	}

	// Import the URDF file
	UObject* ImportedObject = URDFFactory->FactoryCreateFile(
		InClass,
		InParent,
		InName,
		Flags,
		URDFPath,
		Parms,
		Warn,
		bOutOperationCanceled
	);

	if (ImportedObject)
	{
		UE_LOG(LogTemp, Log, TEXT("ROA: Successfully imported robot from XACRO"));
		
		// Show success message
		FMessageDialog::Open(
			EAppMsgType::Ok,
			FText::FromString(TEXT("XACRO file converted and imported successfully!\n\nRobot blueprint created.")),
			FText::FromString(TEXT("Import Complete"))
		);
	}

	return ImportedObject;
}
