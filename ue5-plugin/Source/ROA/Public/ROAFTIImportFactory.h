// ROAFTIImportFactory.h
// Factory for importing robot files via FTI (File Type Importer)
// ROA - Robot Operations & Automation
//
// This factory provides an alternative import path that:
// 1. Uses FTI IPC service for conversion (URDF/XACRO → USD)
// 2. Imports USD via Interchange
// 3. Runs hierarchy assembly to create proper robot structure
// 4. Works WITHOUT the main ROA application running

#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Factories/Factory.h"
#include "EditorReimportHandler.h"
#include "ROAFTIImportFactory.generated.h"

// Forward declarations
class UFTIConnection;

/**
 * Import options for FTI-based robot import
 */
USTRUCT(BlueprintType)
struct FFTIImportOptions
{
    GENERATED_BODY()

    /** Use FTI for conversion (vs. direct URDF parsing) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FTI")
    bool bUseFTI = true;

    /** Output format: USD, USDA, or USDZ */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "FTI")
    FString OutputFormat = TEXT("USD");

    /** Auto-assemble hierarchy after import */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bAutoAssemble = true;

    /** Generate Blueprint from assembled robot */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Assembly")
    bool bGenerateBlueprint = true;

    /** Setup physics constraints */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Physics")
    bool bSetupPhysics = true;

    /** Content path for imported assets (UE5 Content Browser location) */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Output")
    FString ContentPath = TEXT("/Game/Robots");

    /** 
     * External output directory for converted files (USD, hierarchy JSON, etc.)
     * If empty, defaults to {ProjectSaved}/FTI_Output/{RobotName}
     * Example: D:/ROA/Outputs or /home/D/ROA/Outputs
     */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Output")
    FString OutputDir = TEXT("");
};

/**
 * FTI Connection Manager
 * Handles communication with FTI IPC service (can run independently of ROA)
 */
UCLASS()
class ROA_API UFTIConnection : public UObject
{
    GENERATED_BODY()

public:
    UFTIConnection();

    /**
     * Check if FTI service is available
     * Works via file-based IPC (D:/ROA/.ipc or /tmp/roa_ipc)
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static bool IsServiceAvailable();

    /**
     * Start FTI service if not running
     * Launches standalone FTI service process
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static bool EnsureServiceRunning();

    /**
     * Request file conversion via FTI
     * @param SourceFile Path to URDF/XACRO file
     * @param OutputDir Where to write output
     * @param Options Conversion options
     * @param OutError Error message if failed
     * @return Path to output USD file, empty on failure
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static FString RequestConversion(
        const FString& SourceFile,
        const FString& OutputDir,
        const FFTIImportOptions& Options,
        FString& OutError
    );

    /**
     * Poll conversion progress
     * @param RequestId The conversion request ID
     * @return Progress 0.0-1.0, or -1 if error
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static float GetConversionProgress(const FString& RequestId);

    /**
     * Get IPC folder path based on platform
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI")
    static FString GetIPCFolderPath();

    /** Start periodic heartbeat (call on module startup) */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static void StartHeartbeat();
    
    /** Stop periodic heartbeat (call on module shutdown) */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static void StopHeartbeat();
 
    /** Register as active client */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static void RegisterClient();
    
    /** Deregister client (on shutdown) */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static void DeregisterClient();

    /** Write heartbeat to keep service alive */
    static void WriteHeartbeat();

private:
    static FString IPCFolderPath;
    static FString GenerateRequestId();
    static bool WriteIPCRequest(const FString& RequestId, const FString& JsonContent);
    static FString ReadIPCResponse(const FString& RequestId, float TimeoutSeconds = 60.0f);
    
    /** Try to auto-start the FTI IPC service via WSL */
    static bool TryAutoStartService();
    
    /** Client ID for this UE5 instance */
    static FString ClientId;
  
    /** Heartbeat timer handle */
 static FTimerHandle HeartbeatTimerHandle;
    /** Heartbeat ticker handle (for Editor module - works without World context) */
    static FTSTicker::FDelegateHandle HeartbeatTickerHandle;
};

/**
 * FTI-based Robot Import Factory
 * 
 * Handles import of URDF/XACRO files using the FTI conversion pipeline.
 * This allows import to work even when the main ROA application is not running,
 * as long as the FTI IPC service is available.
 * 
 * The import flow:
 * 1. User imports .urdf/.xacro file
 * 2. Factory sends conversion request to FTI IPC service
 * 3. FTI converts to USD with embedded hierarchy metadata
 * 4. Factory imports USD via Interchange
 * 5. Python hierarchy assembly script runs
 * 6. Complete robot actor created in level
 */
UCLASS()
class ROA_API UROAFTIImportFactory : public UFactory, public FReimportHandler
{
    GENERATED_BODY()

public:
    UROAFTIImportFactory();

    // UFactory interface
    virtual bool DoesSupportClass(UClass* Class) override;
    virtual bool FactoryCanImport(const FString& Filename) override;
    virtual FText GetDisplayName() const override;
    virtual UObject* FactoryCreateFile(UClass* InClass, UObject* InParent, FName InName,
        EObjectFlags Flags, const FString& Filename, const TCHAR* Parms,
        FFeedbackContext* Warn, bool& bOutOperationCanceled) override;
    virtual int32 GetPriority() const override;

    // FReimportHandler interface
    virtual bool CanReimport(UObject* Obj, TArray<FString>& OutFilenames) override;
    virtual void SetReimportPaths(UObject* Obj, const TArray<FString>& NewReimportPaths) override;
    virtual EReimportResult::Type Reimport(UObject* Obj) override;

protected:
    /**
     * Import robot via FTI pipeline
     */
    UObject* ImportViaFTI(UObject* InParent, FName InName, const FString& SourceFile,
        FFeedbackContext* Warn, bool& bOutOperationCanceled);

    /**
     * Import USD file and run hierarchy assembly
     */
    UObject* ImportUSDAndAssemble(UObject* InParent, FName InName, const FString& USDPath,
        FFeedbackContext* Warn);

    /**
     * Run complete import workflow via Python
     * This handles USD import, mesh import, hierarchy assembly, and Blueprint generation
     */
    bool RunCompleteImportWorkflow(const FString& USDPath, const FString& RobotName, 
        const FString& ContentFolder);

    /**
     * Run Python hierarchy assembly (deprecated - use RunCompleteImportWorkflow)
     */
    bool RunHierarchyAssembly(const FString& USDPath, const FString& RobotName);

    /**
     * Generate Blueprint from assembled actor
     */
    UBlueprint* GenerateRobotBlueprint(const FString& RobotName, const FString& ContentPath);

    /** Import options */
    FFTIImportOptions ImportOptions;
};

/**
 * FTI Import Options Dialog
 * Shows before import to configure options
 */
UCLASS()
class ROA_API UFTIImportOptionsDialog : public UObject
{
    GENERATED_BODY()

public:
    /**
     * Show import options dialog
     * @return true if user confirmed, false if cancelled
     */
    static bool ShowDialog(FFTIImportOptions& OutOptions);
};
