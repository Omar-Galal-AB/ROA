// UFTIImportWidget.h
// UMG Widget wrapper for FTI Import Panel
// Allows Blueprint usage and Editor integration
// ROA - Robot Operations & Automation

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/Button.h"
#include "Components/EditableTextBox.h"
#include "Components/CheckBox.h"
#include "Components/ComboBoxString.h"
#include "Components/TextBlock.h"
#include "Components/ProgressBar.h"
#include "Components/MultiLineEditableTextBox.h"
#include "UFTIImportWidget.generated.h"

// Forward declarations
class SFTIImportPanel;

/**
 * Delegate for import completion
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnFTIImportComplete, bool, bSuccess, FString, OutputPath, FString, ErrorMessage);

/**
 * Delegate for progress updates
 */
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnFTIProgressUpdate, float, Progress, FString, Stage);

/**
 * UMG Widget for FTI Import Panel
 * Provides Blueprint-accessible interface for robot file importing
 */
UCLASS(BlueprintType, Blueprintable, meta = (DisplayName = "FTI Import Widget"))
class FILETYPEIMPORTER_API UFTIImportWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UFTIImportWidget(const FObjectInitializer& ObjectInitializer);

    // ═══════════════════════════════════════════════════════════════════
    // Blueprint Bindable UI Elements
    // ═══════════════════════════════════════════════════════════════════

    /** File path input */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UEditableTextBox* FilePathInput;

    /** Browse button */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UButton* BrowseButton;

    /** Detected format display */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UTextBlock* DetectedFormatText;

    /** Robot name display */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UTextBlock* RobotNameText;

    /** Link count display */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UTextBlock* LinkCountText;

    /** Joint count display */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UTextBlock* JointCountText;

    /** Output format dropdown */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UComboBoxString* OutputFormatCombo;

    /** Mesh handling dropdown */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UComboBoxString* MeshHandlingCombo;

    /** Auto-assemble checkbox */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UCheckBox* AutoAssembleCheckbox;

    /** Generate blueprint checkbox */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UCheckBox* GenerateBlueprintCheckbox;

    /** IPC status display */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UTextBlock* IPCStatusText;

    /** Convert button */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UButton* ConvertButton;

    /** Cancel button */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UButton* CancelButton;

    /** Progress bar */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UProgressBar* ConversionProgressBar;

    /** Log text box */
    UPROPERTY(BlueprintReadOnly, meta = (BindWidget))
    UMultiLineEditableTextBox* LogTextBox;

    // ═══════════════════════════════════════════════════════════════════
    // Events
    // ═══════════════════════════════════════════════════════════════════

    /** Called when import completes */
    UPROPERTY(BlueprintAssignable, Category = "FTI Events")
    FOnFTIImportComplete OnImportComplete;

    /** Called when progress updates */
    UPROPERTY(BlueprintAssignable, Category = "FTI Events")
    FOnFTIProgressUpdate OnProgressUpdate;

    // ═══════════════════════════════════════════════════════════════════
    // Blueprint Callable Functions
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Set the source file path
     * @param FilePath Path to the robot file
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void SetSourceFile(const FString& FilePath);

    /**
     * Start the import process
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void StartImport();

    /**
     * Cancel the current import
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void CancelImport();

    /**
     * Check if an import is in progress
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI Import")
    bool IsImportInProgress() const;

    /**
     * Get IPC service status
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI Import")
    bool IsIPCServiceRunning() const;

    /**
     * Get current progress (0.0 to 1.0)
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI Import")
    float GetProgress() const;

    /**
     * Get current pipeline stage name
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI Import")
    FString GetCurrentStage() const;

    /**
     * Set the IPC folder path
     * @param FolderPath Path to the IPC folder
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void SetIPCFolderPath(const FString& FolderPath);

    /**
     * Add a log entry
     * @param Message Message to log
     * @param bIsError Whether this is an error message
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void AddLogEntry(const FString& Message, bool bIsError = false);

    /**
     * Clear the log
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void ClearLog();

    /**
     * Open file browser
     */
    UFUNCTION(BlueprintCallable, Category = "FTI Import")
    void BrowseForFile();

protected:
    // ═══════════════════════════════════════════════════════════════════
    // UUserWidget Overrides
    // ═══════════════════════════════════════════════════════════════════

    virtual void NativeConstruct() override;
    virtual void NativeDestruct() override;
    virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

    // ═══════════════════════════════════════════════════════════════════
    // Event Handlers
    // ═══════════════════════════════════════════════════════════════════

    UFUNCTION()
    void HandleBrowseClicked();

    UFUNCTION()
    void HandleConvertClicked();

    UFUNCTION()
    void HandleCancelClicked();

    UFUNCTION()
    void HandleFilePathChanged(const FText& Text);

    UFUNCTION()
    void HandleOutputFormatChanged(FString SelectedItem, ESelectInfo::Type SelectionType);

    UFUNCTION()
    void HandleMeshHandlingChanged(FString SelectedItem, ESelectInfo::Type SelectionType);

private:
    // ═══════════════════════════════════════════════════════════════════
    // Internal State
    // ═══════════════════════════════════════════════════════════════════

    /** Source file path */
    FString SourceFilePath;

    /** IPC folder path */
    FString IPCFolderPath;

    /** Current request ID */
    FString CurrentRequestId;

    /** Import in progress */
    bool bImportInProgress;

    /** IPC service running */
    bool bIPCServiceRunning;

    /** Current progress */
    float CurrentProgress;

    /** Current stage */
    FString CurrentStage;

    /** Last IPC check time */
    float LastIPCCheckTime;

    /** IPC check interval */
    static constexpr float IPCCheckInterval = 3.0f;

    // ═══════════════════════════════════════════════════════════════════
    // Internal Functions
    // ═══════════════════════════════════════════════════════════════════

    /** Check IPC service status */
    void CheckIPCServiceStatus();

    /** Submit conversion request */
    FString SubmitConversionRequest();

    /** Poll for progress */
    void PollProgress();

    /** Check for completion */
    bool CheckForCompletion();

    /** Detect file format */
    FString DetectFileFormat(const FString& FilePath);

    /** Parse robot file info */
    void ParseRobotFileInfo(const FString& FilePath);

    /** Update UI elements */
    void UpdateUIState();
};

/**
 * Blueprint function library for FTI utilities
 */
UCLASS()
class FILETYPEIMPORTER_API UFTIBlueprintLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /**
     * Get supported file formats for import
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI")
    static TArray<FString> GetSupportedFormats();

    /**
     * Detect file format from path
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI")
    static FString DetectFileFormat(const FString& FilePath);

    /**
     * Check if a file is a valid robot file
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI")
    static bool IsValidRobotFile(const FString& FilePath);

    /**
     * Get the default IPC folder path
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "FTI")
    static FString GetDefaultIPCFolderPath();

    /**
     * Quick import a robot file (one-liner)
     * @param FilePath Path to the robot file
     * @param bAutoAssemble Whether to auto-assemble the hierarchy
     * @param bGenerateBlueprint Whether to generate a Blueprint
     * @return Request ID for tracking, or empty string on failure
     */
    UFUNCTION(BlueprintCallable, Category = "FTI")
    static FString QuickImport(const FString& FilePath, bool bAutoAssemble = true, bool bGenerateBlueprint = true);
};
