// FTIPostImportHook.cpp
// Post-Import Hook implementation
// ROA - Robot Operations & Automation

#include "FTIPostImportHook.h"
#include "InterchangeManager.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/Blueprint.h"
#include "GameFramework/Actor.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"
#include "Kismet/GameplayStatics.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Factories/BlueprintFactory.h"
#include "KismetCompilerModule.h"

#define LOCTEXT_NAMESPACE "FTIPostImportHook"

// ═══════════════════════════════════════════════════════════════════════════════
// UFTIPostImportHook Implementation
// ═══════════════════════════════════════════════════════════════════════════════

UFTIPostImportHook::UFTIPostImportHook()
    : bIsActive(false)
{
    // Default configuration
    Config.bAutoAssemble = true;
    Config.bAutoPhysics = true;
    Config.bGenerateBlueprint = true;
    Config.ContentPath = TEXT("/Game/Robots");
    Config.bSetupCollision = true;
    Config.bApplyDefaultMaterials = true;
}

UFTIPostImportHook::~UFTIPostImportHook()
{
    if (bIsActive)
    {
        Shutdown();
    }
}

void UFTIPostImportHook::Initialize()
{
    if (bIsActive)
    {
        UE_LOG(LogTemp, Warning, TEXT("FTI PostImportHook already initialized"));
        return;
    }

    UE_LOG(LogTemp, Log, TEXT("Initializing FTI PostImportHook"));

    // Register with Interchange Manager
    // Note: In production, this would hook into the actual Interchange delegate
    // For now, we set up the structure for manual triggering
    
    bIsActive = true;
    
    UE_LOG(LogTemp, Log, TEXT("FTI PostImportHook initialized successfully"));
}

void UFTIPostImportHook::Shutdown()
{
    if (!bIsActive)
    {
        return;
    }

    UE_LOG(LogTemp, Log, TEXT("Shutting down FTI PostImportHook"));

    // Unregister from Interchange
    if (InterchangeDelegateHandle.IsValid())
    {
        // Remove delegate
        InterchangeDelegateHandle.Reset();
    }

    bIsActive = false;
}

void UFTIPostImportHook::SetConfig(const FFTIAssemblyConfig& NewConfig)
{
    Config = NewConfig;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Manual Assembly Trigger
// ═══════════════════════════════════════════════════════════════════════════════

FFTIAssemblyResult UFTIPostImportHook::TriggerAssembly(
    const TArray<FString>& ImportedAssets, 
    const FString& RobotName)
{
    CurrentRobotName = RobotName;
    CurrentResult = FFTIAssemblyResult();
    CurrentResult.RobotName = RobotName;

    if (ImportedAssets.Num() == 0)
    {
        CurrentResult.ErrorMessage = TEXT("No assets provided for assembly");
        return CurrentResult;
    }

    ReportProgress(0.0f, FString::Printf(TEXT("Starting assembly of %s"), *RobotName));

    // Load the imported assets
    TArray<UObject*> LoadedAssets;
    for (const FString& AssetPath : ImportedAssets)
    {
        UObject* Asset = LoadObject<UObject>(nullptr, *AssetPath);
        if (Asset)
        {
            LoadedAssets.Add(Asset);
        }
        else
        {
            CurrentResult.Warnings.Add(FString::Printf(TEXT("Failed to load asset: %s"), *AssetPath));
        }
    }

    if (LoadedAssets.Num() == 0)
    {
        CurrentResult.ErrorMessage = TEXT("No assets could be loaded");
        return CurrentResult;
    }

    ReportProgress(0.1f, TEXT("Assets loaded, building hierarchy..."));

    // Build hierarchy
    BuildHierarchy(LoadedAssets, RobotName);

    // The assembly process creates an actor in the world
    // Find it for further processing
    UWorld* World = GEngine->GetWorldContexts()[0].World();
    if (!World)
    {
        CurrentResult.ErrorMessage = TEXT("No world available");
        return CurrentResult;
    }

    // Find the created actor
    AActor* RobotActor = nullptr;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->GetName().Contains(RobotName))
        {
            RobotActor = *It;
            break;
        }
    }

    if (!RobotActor)
    {
        CurrentResult.ErrorMessage = TEXT("Failed to create robot actor");
        return CurrentResult;
    }

    // Setup physics
    if (Config.bAutoPhysics)
    {
        ReportProgress(0.4f, TEXT("Setting up physics..."));
        SetupPhysics(RobotActor);
    }

    // Setup collision
    if (Config.bSetupCollision)
    {
        ReportProgress(0.5f, TEXT("Setting up collision..."));
        SetupCollision(RobotActor);
    }

    // Apply materials
    if (Config.bApplyDefaultMaterials)
    {
        ReportProgress(0.6f, TEXT("Applying materials..."));
        ApplyMaterials(RobotActor);
    }

    // Create joints
    ReportProgress(0.7f, TEXT("Creating joint components..."));
    CreateJoints(RobotActor);

    // Generate Blueprint
    FString BlueprintPath;
    if (Config.bGenerateBlueprint)
    {
        ReportProgress(0.85f, TEXT("Generating Blueprint..."));
        BlueprintPath = GenerateBlueprint(RobotActor, RobotName);
        CurrentResult.BlueprintPath = BlueprintPath;
    }

    // Complete
    ReportProgress(1.0f, TEXT("Assembly complete!"));

    CurrentResult.bSuccess = true;
    CurrentResult.AssemblyActorPath = RobotActor->GetPathName();

    // Count links and joints (approximate)
    int32 LinkCount = 0;
    int32 JointCount = 0;
    TArray<UActorComponent*> Components;
    RobotActor->GetComponents(Components);
    for (UActorComponent* Component : Components)
    {
        if (Cast<UStaticMeshComponent>(Component) || Cast<USkeletalMeshComponent>(Component))
        {
            LinkCount++;
        }
        if (Cast<UPhysicsConstraintComponent>(Component))
        {
            JointCount++;
        }
    }
    CurrentResult.LinkCount = LinkCount;
    CurrentResult.JointCount = JointCount;

    // Broadcast completion
    OnAssemblyComplete.Broadcast(true, RobotName, CurrentResult.AssemblyActorPath);

    return CurrentResult;
}

FString UFTIPostImportHook::GenerateBlueprint(AActor* AssemblyActor, const FString& BlueprintName)
{
    if (!AssemblyActor)
    {
        return FString();
    }

    // Construct the Blueprint path
    FString PackagePath = FString::Printf(TEXT("%s/BP_%s"), *Config.ContentPath, *BlueprintName);
    FString PackageName = FPackageName::ObjectPathToPackageName(PackagePath);
    
    // Create package
    UPackage* Package = CreatePackage(*PackageName);
    if (!Package)
    {
        UE_LOG(LogTemp, Error, TEXT("Failed to create package for Blueprint: %s"), *PackageName);
        return FString();
    }

    // Create the Blueprint
    UBlueprintFactory* Factory = NewObject<UBlueprintFactory>();
    Factory->ParentClass = Config.BlueprintBaseClass ? Config.BlueprintBaseClass : AActor::StaticClass();

    FString AssetName = FString::Printf(TEXT("BP_%s"), *BlueprintName);
    UBlueprint* NewBlueprint = Cast<UBlueprint>(Factory->FactoryCreateNew(
        UBlueprint::StaticClass(),
        Package,
        *AssetName,
        RF_Public | RF_Standalone,
        nullptr,
        GWarn
    ));

    if (!NewBlueprint)
    {
        UE_LOG(LogTemp, Error, TEXT("Failed to create Blueprint: %s"), *AssetName);
        return FString();
    }

    // Copy components from the assembly actor to the Blueprint
    // This is a simplified version - production code would properly duplicate
    USimpleConstructionScript* SCS = NewBlueprint->SimpleConstructionScript;
    if (SCS)
    {
        // Get components from source actor
        TArray<UActorComponent*> SourceComponents;
        AssemblyActor->GetComponents(SourceComponents);

        for (UActorComponent* SourceComponent : SourceComponents)
        {
            // Skip root component
            if (SourceComponent == AssemblyActor->GetRootComponent())
            {
                continue;
            }

            // Create node for this component
            // Note: In production, this would properly duplicate components
            USCS_Node* NewNode = SCS->CreateNode(SourceComponent->GetClass(), *SourceComponent->GetName());
            if (NewNode)
            {
                SCS->AddNode(NewNode);
            }
        }
    }

    // Compile the Blueprint
    FKismetEditorUtilities::CompileBlueprint(NewBlueprint);

    // Mark package dirty and save
    Package->MarkPackageDirty();

    // Notify asset registry
    FAssetRegistryModule::AssetCreated(NewBlueprint);

    UE_LOG(LogTemp, Log, TEXT("Generated Blueprint: %s"), *PackagePath);

    return PackagePath;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Assembly Steps
// ═══════════════════════════════════════════════════════════════════════════════

void UFTIPostImportHook::BuildHierarchy(const TArray<UObject*>& ImportedAssets, const FString& RobotName)
{
    UWorld* World = GEngine->GetWorldContexts()[0].World();
    if (!World)
    {
        return;
    }

    // Create root actor
    FActorSpawnParameters SpawnParams;
    SpawnParams.Name = FName(*RobotName);
    AActor* RootActor = World->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
    
    if (!RootActor)
    {
        return;
    }

    // Set root component
    USceneComponent* RootComponent = NewObject<USceneComponent>(RootActor, TEXT("RootComponent"));
    RootActor->SetRootComponent(RootComponent);
    RootComponent->RegisterComponent();

    // Add mesh components from imported assets
    int32 ComponentIndex = 0;
    for (UObject* Asset : ImportedAssets)
    {
        if (UStaticMesh* StaticMesh = Cast<UStaticMesh>(Asset))
        {
            FString ComponentName = FString::Printf(TEXT("Link_%d"), ComponentIndex);
            UStaticMeshComponent* MeshComponent = NewObject<UStaticMeshComponent>(RootActor, *ComponentName);
            MeshComponent->SetStaticMesh(StaticMesh);
            MeshComponent->SetupAttachment(RootComponent);
            MeshComponent->RegisterComponent();
            ComponentIndex++;
        }
        else if (USkeletalMesh* SkeletalMesh = Cast<USkeletalMesh>(Asset))
        {
            FString ComponentName = FString::Printf(TEXT("Link_%d"), ComponentIndex);
            USkeletalMeshComponent* MeshComponent = NewObject<USkeletalMeshComponent>(RootActor, *ComponentName);
            MeshComponent->SetSkeletalMesh(SkeletalMesh);
            MeshComponent->SetupAttachment(RootComponent);
            MeshComponent->RegisterComponent();
            ComponentIndex++;
        }
    }

    ReportProgress(0.3f, FString::Printf(TEXT("Built hierarchy with %d components"), ComponentIndex));
}

void UFTIPostImportHook::SetupPhysics(AActor* RootActor)
{
    if (!RootActor)
    {
        return;
    }

    TArray<UPrimitiveComponent*> PrimitiveComponents;
    RootActor->GetComponents<UPrimitiveComponent>(PrimitiveComponents);

    for (UPrimitiveComponent* Component : PrimitiveComponents)
    {
        // Enable physics simulation
        Component->SetSimulatePhysics(false); // Start with physics off for control
        Component->SetEnableGravity(true);
        Component->SetMassOverrideInKg(NAME_None, 1.0f, true);
    }
}

void UFTIPostImportHook::SetupCollision(AActor* RootActor)
{
    if (!RootActor)
    {
        return;
    }

    TArray<UPrimitiveComponent*> PrimitiveComponents;
    RootActor->GetComponents<UPrimitiveComponent>(PrimitiveComponents);

    for (UPrimitiveComponent* Component : PrimitiveComponents)
    {
        // Setup default collision profile
        Component->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        Component->SetCollisionResponseToAllChannels(ECR_Block);
    }
}

void UFTIPostImportHook::ApplyMaterials(AActor* RootActor)
{
    if (!RootActor)
    {
        return;
    }

    // Load default robot material
    UMaterial* DefaultMaterial = LoadObject<UMaterial>(nullptr, TEXT("/Game/Materials/M_DefaultRobot"));
    
    if (!DefaultMaterial)
    {
        // Use engine default if custom not found
        return;
    }

    TArray<UMeshComponent*> MeshComponents;
    RootActor->GetComponents<UMeshComponent>(MeshComponents);

    for (UMeshComponent* Component : MeshComponents)
    {
        int32 NumMaterials = Component->GetNumMaterials();
        for (int32 i = 0; i < NumMaterials; i++)
        {
            if (!Component->GetMaterial(i))
            {
                Component->SetMaterial(i, DefaultMaterial);
            }
        }
    }
}

void UFTIPostImportHook::CreateJoints(AActor* RootActor)
{
    if (!RootActor)
    {
        return;
    }

    // Get all mesh components (links)
    TArray<UPrimitiveComponent*> Links;
    RootActor->GetComponents<UPrimitiveComponent>(Links);

    // Create physics constraints between consecutive links
    // Note: In production, this would use actual joint data from URDF
    for (int32 i = 1; i < Links.Num(); i++)
    {
        UPrimitiveComponent* ParentLink = Links[i - 1];
        UPrimitiveComponent* ChildLink = Links[i];

        // Create constraint component
        FString ConstraintName = FString::Printf(TEXT("Joint_%d"), i);
        UPhysicsConstraintComponent* Constraint = NewObject<UPhysicsConstraintComponent>(RootActor, *ConstraintName);
        
        // Setup constraint
        Constraint->SetupAttachment(ParentLink);
        Constraint->ComponentName1.ComponentName = ParentLink->GetFName();
        Constraint->ComponentName2.ComponentName = ChildLink->GetFName();
        
        // Default to revolute joint (rotation around Z)
        Constraint->SetAngularSwing1Limit(EAngularConstraintMotion::ACM_Locked, 0);
        Constraint->SetAngularSwing2Limit(EAngularConstraintMotion::ACM_Locked, 0);
        Constraint->SetAngularTwistLimit(EAngularConstraintMotion::ACM_Free, 180);
        
        Constraint->RegisterComponent();
    }

    ReportProgress(0.8f, FString::Printf(TEXT("Created %d joint constraints"), FMath::Max(0, Links.Num() - 1)));
}

void UFTIPostImportHook::ReportProgress(float Progress, const FString& Message)
{
    OnAssemblyProgress.Broadcast(Progress, Message);
    UE_LOG(LogTemp, Log, TEXT("FTI Assembly [%.0f%%]: %s"), Progress * 100.0f, *Message);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Interchange Callbacks
// ═══════════════════════════════════════════════════════════════════════════════

void UFTIPostImportHook::OnInterchangeImportComplete(const FInterchangeImportResult& Result)
{
    // Check if this import is from FTI
    // Note: This is placeholder - actual implementation would check source metadata
    
    if (Result.ImportedObjects.Num() == 0)
    {
        return;
    }

    // Check if auto-assembly is enabled
    if (!Config.bAutoAssemble)
    {
        return;
    }

    // Extract robot name from imported file
    FString RobotName = TEXT("ImportedRobot");
    
    // Trigger assembly
    TArray<FString> AssetPaths;
    for (UObject* Obj : Result.ImportedObjects)
    {
        if (Obj)
        {
            AssetPaths.Add(Obj->GetPathName());
        }
    }

    if (AssetPaths.Num() > 0)
    {
        TriggerAssembly(AssetPaths, RobotName);
    }
}

bool UFTIPostImportHook::IsFTIImport(const UInterchangeSourceData* SourceData) const
{
    if (!SourceData)
    {
        return false;
    }

    // Check if source file is from FTI IPC folder
    FString SourcePath = SourceData->GetFilename();
    return SourcePath.Contains(TEXT(".ipc")) || SourcePath.Contains(TEXT("FTI"));
}

// ═══════════════════════════════════════════════════════════════════════════════
// UFTIPostImportSubsystem Implementation
// ═══════════════════════════════════════════════════════════════════════════════

void UFTIPostImportSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);

    PostImportHook = NewObject<UFTIPostImportHook>(this);
    PostImportHook->Initialize();

    UE_LOG(LogTemp, Log, TEXT("FTI PostImport Subsystem initialized"));
}

void UFTIPostImportSubsystem::Deinitialize()
{
    if (PostImportHook)
    {
        PostImportHook->Shutdown();
        PostImportHook = nullptr;
    }

    Super::Deinitialize();
}

void UFTIPostImportSubsystem::SetAutoAssemblyEnabled(bool bEnabled)
{
    if (PostImportHook)
    {
        FFTIAssemblyConfig Config = PostImportHook->GetConfig();
        Config.bAutoAssemble = bEnabled;
        PostImportHook->SetConfig(Config);
    }
}

bool UFTIPostImportSubsystem::IsAutoAssemblyEnabled() const
{
    if (PostImportHook)
    {
        return PostImportHook->GetConfig().bAutoAssemble;
    }
    return false;
}

#undef LOCTEXT_NAMESPACE
