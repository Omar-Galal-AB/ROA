// FTIPostImportHook.h
// Post-Import Hook for FTI Pipeline
// Triggers hierarchy assembly after USD import via Interchange
// ROA - Robot Operations & Automation

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "InterchangeManager.h"
#include "InterchangeSourceData.h"
#include "InterchangeTranslatorBase.h"
#include "FTIPostImportHook.generated.h"

// Forward declarations
class UInterchangeAssetImportData;
class UInterchangePipelineBase;

/**
 * Delegate for post-import assembly completion
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(
    FOnRobotAssemblyComplete, 
    bool, bSuccess, 
    FString, RobotName,
    FString, AssemblyPath
);

/**
 * Delegate for post-import progress
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(
    FOnAssemblyProgress,
    float, Progress,
    FString, Message
);

/**
 * Configuration for post-import assembly
 */
USTRUCT(BlueprintType)
struct FFTIAssemblyConfig
{
    GENERATED_BODY()

    /** Enable automatic hierarchy assembly */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bAutoAssemble = true;

    /** Enable automatic physics setup */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bAutoPhysics = true;

    /** Enable automatic Blueprint generation */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bGenerateBlueprint = true;

    /** Content path for generated assets */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    FString ContentPath = TEXT("/Game/Robots");

    /** Base class for generated Blueprints */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    TSubclassOf<AActor> BlueprintBaseClass;

    /** Apply default collision settings */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bSetupCollision = true;

    /** Apply default materials */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bApplyDefaultMaterials = true;
};

/**
 * Robot assembly result
 */
USTRUCT(BlueprintType)
struct FFTIAssemblyResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    bool bSuccess = false;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    FString RobotName;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    FString AssemblyActorPath;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    FString BlueprintPath;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    int32 LinkCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    int32 JointCount = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    TArray<FString> Warnings;

    UPROPERTY(BlueprintReadOnly, Category = "Result")
    FString ErrorMessage;
};

/**
 * Post-Import Hook for automatic robot assembly
 * 
 * This class hooks into Interchange's import pipeline to:
 * 1. Detect robot USD imports from FTI
 * 2. Trigger hierarchy assembly after import
 * 3. Setup physics and constraints
 * 4. Generate Blueprints
 * 
 * Usage:
 *   // In module startup
 *   UFTIPostImportHook* Hook = NewObject<UFTIPostImportHook>();
 *   Hook->Initialize();
 *   Hook->OnAssemblyComplete.AddDynamic(this, &UMyClass::HandleAssemblyComplete);
 */
UCLASS(BlueprintType)
class FILETYPEIMPORTER_API UFTIPostImportHook : public UObject
{
    GENERATED_BODY()

public:
    UFTIPostImportHook();
    virtual ~UFTIPostImportHook();

    // ═══════════════════════════════════════════════════════════════════
    // Initialization
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Initialize the hook and register with Interchange
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Post Import")
    void Initialize();

    /**
     * Shutdown and unregister
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Post Import")
    void Shutdown();

    /**
     * Check if hook is active
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI Post Import")
    bool IsActive() const { return bIsActive; }

    // ═══════════════════════════════════════════════════════════════════
    // Configuration
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Set assembly configuration
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Post Import")
    void SetConfig(const FFTIAssemblyConfig& NewConfig);

    /**
     * Get current configuration
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI Post Import")
    FFTIAssemblyConfig GetConfig() const { return Config; }

    // ═══════════════════════════════════════════════════════════════════
    // Manual Assembly Trigger
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Manually trigger assembly for imported assets
     * @param ImportedAssets Array of imported asset paths
     * @param RobotName Name for the robot
     * @return Assembly result
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Post Import")
    FFTIAssemblyResult TriggerAssembly(const TArray<FString>& ImportedAssets, const FString& RobotName);

    /**
     * Manually trigger Blueprint generation
     * @param AssemblyActor The assembled robot actor
     * @param BlueprintName Name for the Blueprint
     * @return Path to generated Blueprint
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Post Import")
    FString GenerateBlueprint(AActor* AssemblyActor, const FString& BlueprintName);

    // ═══════════════════════════════════════════════════════════════════
    // Events
    // ═══════════════════════════════════════════════════════════════════

    /** Called when robot assembly completes */
    UPROPERTY(BlueprintAssignable, Category = "FTI Events")
    FOnRobotAssemblyComplete OnAssemblyComplete;

    /** Called with assembly progress updates */
    UPROPERTY(BlueprintAssignable, Category = "FTI Events")
    FOnAssemblyProgress OnAssemblyProgress;

protected:
    // ═══════════════════════════════════════════════════════════════════
    // Interchange Callbacks
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Called when Interchange completes an import
     */
    void OnInterchangeImportComplete(
        const FInterchangeImportResult& Result
    );

    /**
     * Check if this import is from FTI
     */
    bool IsFTIImport(const UInterchangeSourceData* SourceData) const;

    // ═══════════════════════════════════════════════════════════════════
    // Assembly Steps
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Build hierarchy from imported parts
     */
    void BuildHierarchy(const TArray<UObject*>& ImportedAssets, const FString& RobotName);

    /**
     * Setup physics constraints between links
     */
    void SetupPhysics(AActor* RootActor);

    /**
     * Apply collision profiles
     */
    void SetupCollision(AActor* RootActor);

    /**
     * Apply default materials
     */
    void ApplyMaterials(AActor* RootActor);

    /**
     * Create joint components
     */
    void CreateJoints(AActor* RootActor);

    /**
     * Report progress
     */
    void ReportProgress(float Progress, const FString& Message);

private:
    /** Configuration */
    UPROPERTY()
    FFTIAssemblyConfig Config;

    /** Active state */
    bool bIsActive;

    /** Delegate handle for Interchange */
    FDelegateHandle InterchangeDelegateHandle;

    /** Currently processing robot name */
    FString CurrentRobotName;

    /** Current assembly result */
    FFTIAssemblyResult CurrentResult;
};

/**
 * Subsystem for managing FTI post-import hooks
 */
UCLASS()
class FILETYPEIMPORTER_API UFTIPostImportSubsystem : public UEngineSubsystem
{
    GENERATED_BODY()

public:
    /** Initialize and create hook */
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;

    /** Cleanup */
    virtual void Deinitialize() override;

    /**
     * Get the global post-import hook
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    UFTIPostImportHook* GetPostImportHook() const { return PostImportHook; }

    /**
     * Enable/disable auto-assembly
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    void SetAutoAssemblyEnabled(bool bEnabled);

    /**
     * Check if auto-assembly is enabled
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI")
    bool IsAutoAssemblyEnabled() const;

private:
    UPROPERTY()
    UFTIPostImportHook* PostImportHook;
};
