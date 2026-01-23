// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Factories/Factory.h"
#include "EditorReimportHandler.h"
#include "ROAURDFFactory.generated.h"

/**
 * Factory for importing URDF files into UE5 Content Browser
 * Enables drag & drop of .urdf files
 */
UCLASS()
class ROA_API UROAURDFFactory : public UFactory, public FReimportHandler
{
	GENERATED_BODY()

public:
	UROAURDFFactory();

	// UFactory interface
	virtual UObject* FactoryCreateFile(UClass* InClass, UObject* InParent, FName InName, EObjectFlags Flags, 
		const FString& Filename, const TCHAR* Parms, FFeedbackContext* Warn, bool& bOutOperationCanceled) override;
	
	virtual bool DoesSupportClass(UClass* Class) override;
	virtual bool FactoryCanImport(const FString& Filename) override;
	virtual FText GetDisplayName() const override;
	
	// FReimportHandler interface
	virtual bool CanReimport(UObject* Obj, TArray<FString>& OutFilenames) override;
	virtual void SetReimportPaths(UObject* Obj, const TArray<FString>& NewReimportPaths) override;
	virtual EReimportResult::Type Reimport(UObject* Obj) override;
	virtual int32 GetPriority() const override;

private:
	// Import robot from URDF file
	UObject* ImportRobotFromURDF(UObject* InParent, FName InName, const FString& URDFPath, FFeedbackContext* Warn);
	
	// Create robot blueprint from parsed URDF
	UObject* CreateRobotBlueprint(UObject* InParent, FName InName, const struct FROARobotDescription& Description);
};

/**
 * Factory for importing XACRO files (XML Macros)
 */
UCLASS()
class ROA_API UROAXacroFactory : public UFactory
{
	GENERATED_BODY()

public:
	UROAXacroFactory();

	virtual UObject* FactoryCreateFile(UClass* InClass, UObject* InParent, FName InName, EObjectFlags Flags, 
		const FString& Filename, const TCHAR* Parms, FFeedbackContext* Warn, bool& bOutOperationCanceled) override;
	
	virtual bool FactoryCanImport(const FString& Filename) override;
	virtual FText GetDisplayName() const override;

private:
	// Process XACRO to URDF, then import
	FString ProcessXacro(const FString& XacroPath);
};
