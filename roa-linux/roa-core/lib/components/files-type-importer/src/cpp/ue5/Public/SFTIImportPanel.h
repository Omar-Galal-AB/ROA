// SFTIImportPanel.h
// Slate-based FTI Import Panel for UE5 Editor
// ROA - Robot Operations & Automation
// 
// This widget provides:
// - File browsing for robot models (URDF/XACRO/USD)
// - Format detection and preview
// - Import options configuration
// - IPC service status and control
// - Progress monitoring during conversion
// - Automatic pipeline integration

#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SComboBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Notifications/SProgressBar.h"
#include "Widgets/Views/SListView.h"
#include "Widgets/Layout/SScrollBox.h"
#include "HAL/Runnable.h"
#include "HAL/RunnableThread.h"
#include "Misc/FileHelper.h"
#include "DesktopPlatform/Public/IDesktopPlatform.h"
#include "DesktopPlatform/Public/DesktopPlatformModule.h"

// Forward declarations
class UFileTypeImporter;
class FIPCMonitorRunnable;

/**
 * Pipeline step enumeration for progress tracking
 */
enum class EFTIPipelineStep : uint8
{
    Parse,          // Parse input file
    XACRO,          // Process XACRO macros
    Hierarchy,      // Build robot hierarchy
    Meshes,         // Process mesh files
    USD,            // Generate USD
    IPC,            // Transfer via IPC
    Import,         // Import into UE5
    Assemble,       // Assemble hierarchy
    Complete        // All done
};

/**
 * Data for pipeline step UI item
 */
struct FFTIPipelineStepData
{
    FString Name;
    EFTIPipelineStep Step;
    bool bComplete;
    bool bInProgress;
    bool bError;
    FString StatusText;
    
    FFTIPipelineStepData(const FString& InName, EFTIPipelineStep InStep)
        : Name(InName)
        , Step(InStep)
        , bComplete(false)
        , bInProgress(false)
        , bError(false)
        , StatusText(TEXT("Pending"))
    {}
};

/**
 * Slate widget for FTI Import Panel
 * Provides the main UI for robot file import in UE5 Editor
 */
class FILETYPEIMPORTER_API SFTIImportPanel : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SFTIImportPanel)
        : _IPCFolderPath(TEXT(""))
    {}
        /** IPC folder path for communication with WSL service */
        SLATE_ARGUMENT(FString, IPCFolderPath)
    SLATE_END_ARGS()

    /** Constructs this widget */
    void Construct(const FArguments& InArgs);

    /** Destructor - cleans up monitor thread */
    virtual ~SFTIImportPanel();

    // ═══════════════════════════════════════════════════════════════════
    // Public Interface
    // ═══════════════════════════════════════════════════════════════════

    /** Set the source file path */
    void SetSourceFile(const FString& FilePath);

    /** Start the import process */
    void StartImport();

    /** Cancel current import */
    void CancelImport();

    /** Check if an import is in progress */
    bool IsImportInProgress() const { return bImportInProgress; }

    /** Get the current pipeline step */
    EFTIPipelineStep GetCurrentStep() const { return CurrentStep; }

protected:
    // ═══════════════════════════════════════════════════════════════════
    // Widget Tick
    // ═══════════════════════════════════════════════════════════════════

    virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;

private:
    // ═══════════════════════════════════════════════════════════════════
    // UI Construction
    // ═══════════════════════════════════════════════════════════════════

    /** Create the file selection section */
    TSharedRef<SWidget> CreateFileSelectionSection();

    /** Create the format detection section */
    TSharedRef<SWidget> CreateFormatDetectionSection();

    /** Create the import options section */
    TSharedRef<SWidget> CreateImportOptionsSection();

    /** Create the IPC status section */
    TSharedRef<SWidget> CreateIPCStatusSection();

    /** Create the progress section */
    TSharedRef<SWidget> CreateProgressSection();

    /** Create the log section */
    TSharedRef<SWidget> CreateLogSection();

    // ═══════════════════════════════════════════════════════════════════
    // Event Handlers
    // ═══════════════════════════════════════════════════════════════════

    /** Handle browse button click */
    FReply OnBrowseButtonClicked();

    /** Handle file path text change */
    void OnFilePathChanged(const FText& NewText);

    /** Handle convert button click */
    FReply OnConvertButtonClicked();

    /** Handle cancel button click */
    FReply OnCancelButtonClicked();

    /** Handle start IPC service button */
    FReply OnStartIPCServiceClicked();

    /** Handle stop IPC service button */
    FReply OnStopIPCServiceClicked();

    /** Handle output format selection */
    void OnOutputFormatChanged(TSharedPtr<FString> NewSelection, ESelectInfo::Type SelectInfo);

    /** Handle mesh handling selection */
    void OnMeshHandlingChanged(TSharedPtr<FString> NewSelection, ESelectInfo::Type SelectInfo);

    // ═══════════════════════════════════════════════════════════════════
    // File Analysis
    // ═══════════════════════════════════════════════════════════════════

    /** Detect file format from path */
    FString DetectFileFormat(const FString& FilePath);

    /** Parse URDF/XACRO file for preview info */
    void ParseRobotFileInfo(const FString& FilePath);

    /** Validate the selected file */
    bool ValidateFile(const FString& FilePath);

    // ═══════════════════════════════════════════════════════════════════
    // IPC Communication
    // ═══════════════════════════════════════════════════════════════════

    /** Check IPC service status */
    void CheckIPCServiceStatus();

    /** Submit conversion request to IPC service */
    FString SubmitConversionRequest();

    /** Poll for progress updates */
    void PollProgressUpdates();

    /** Check for completion response */
    bool CheckForCompletionResponse();

    /** Start the IPC monitor thread */
    void StartIPCMonitor();

    /** Stop the IPC monitor thread */
    void StopIPCMonitor();

    // ═══════════════════════════════════════════════════════════════════
    // Pipeline Control
    // ═══════════════════════════════════════════════════════════════════

    /** Update pipeline step status */
    void UpdatePipelineStep(EFTIPipelineStep Step, bool bComplete, bool bInProgress, bool bError, const FString& StatusText);

    /** Reset all pipeline steps */
    void ResetPipelineSteps();

    /** Get pipeline step index */
    int32 GetPipelineStepIndex(EFTIPipelineStep Step) const;

    /** Map stage name to pipeline step */
    EFTIPipelineStep MapStageToStep(const FString& StageName) const;

    // ═══════════════════════════════════════════════════════════════════
    // Logging
    // ═══════════════════════════════════════════════════════════════════

    /** Add a log entry */
    void AddLogEntry(const FString& Message, bool bIsError = false);

    /** Clear the log */
    void ClearLog();

    // ═══════════════════════════════════════════════════════════════════
    // Post-Import Actions
    // ═══════════════════════════════════════════════════════════════════

    /** Handle successful import completion */
    void OnImportComplete(const FString& OutputFile);

    /** Trigger hierarchy assembly */
    void TriggerHierarchyAssembly(const FString& USDPath);

    /** Generate Blueprint from imported robot */
    void GenerateRobotBlueprint(const FString& RobotName);

private:
    // ═══════════════════════════════════════════════════════════════════
    // UI State
    // ═══════════════════════════════════════════════════════════════════

    /** Source file path */
    FString SourceFilePath;

    /** Detected format */
    FString DetectedFormat;

    /** Robot name from file */
    FString RobotName;

    /** Number of links */
    int32 LinkCount;

    /** Number of joints */
    int32 JointCount;

    /** Number of meshes */
    int32 MeshCount;

    /** Current request ID */
    FString CurrentRequestId;

    /** Current pipeline step */
    EFTIPipelineStep CurrentStep;

    /** Import in progress flag */
    bool bImportInProgress;

    /** IPC service running flag */
    bool bIPCServiceRunning;

    /** Import options */
    FString OutputFormat;
    FString MeshHandling;
    bool bAutoAssemble;
    bool bGenerateBlueprint;

    // ═══════════════════════════════════════════════════════════════════
    // Widget References
    // ═══════════════════════════════════════════════════════════════════

    /** File path text box */
    TSharedPtr<SEditableTextBox> FilePathTextBox;

    /** Detected format text */
    TSharedPtr<STextBlock> DetectedFormatText;

    /** Robot name text */
    TSharedPtr<STextBlock> RobotNameText;

    /** Link count text */
    TSharedPtr<STextBlock> LinkCountText;

    /** Joint count text */
    TSharedPtr<STextBlock> JointCountText;

    /** Mesh count text */
    TSharedPtr<STextBlock> MeshCountText;

    /** Output format combo box */
    TSharedPtr<SComboBox<TSharedPtr<FString>>> OutputFormatCombo;

    /** Mesh handling combo box */
    TSharedPtr<SComboBox<TSharedPtr<FString>>> MeshHandlingCombo;

    /** Auto-assemble checkbox */
    TSharedPtr<SCheckBox> AutoAssembleCheckbox;

    /** Generate blueprint checkbox */
    TSharedPtr<SCheckBox> GenerateBlueprintCheckbox;

    /** IPC status text */
    TSharedPtr<STextBlock> IPCStatusText;

    /** Convert button */
    TSharedPtr<SButton> ConvertButton;

    /** Cancel button */
    TSharedPtr<SButton> CancelButton;

    /** Progress bar */
    TSharedPtr<SProgressBar> ProgressBar;

    /** Progress percent */
    float ProgressPercent;

    /** Log text box (multiline) */
    TSharedPtr<SScrollBox> LogScrollBox;
    TArray<TSharedPtr<STextBlock>> LogEntries;

    // ═══════════════════════════════════════════════════════════════════
    // Pipeline Steps Data
    // ═══════════════════════════════════════════════════════════════════

    /** Pipeline step list view */
    TSharedPtr<SListView<TSharedPtr<FFTIPipelineStepData>>> PipelineListView;

    /** Pipeline step data array */
    TArray<TSharedPtr<FFTIPipelineStepData>> PipelineSteps;

    // ═══════════════════════════════════════════════════════════════════
    // IPC Communication
    // ═══════════════════════════════════════════════════════════════════

    /** IPC folder path */
    FString IPCFolderPath;

    /** Python module path (for UE5 Python scripts) */
    FString PythonModulePath;

    /** IPC monitor runnable */
    TSharedPtr<FIPCMonitorRunnable> IPCMonitor;

    /** IPC monitor thread */
    FRunnableThread* IPCMonitorThread;

    /** Pending log entries (thread-safe) */
    TQueue<TPair<FString, bool>> PendingLogEntries;

    /** Pending progress updates (thread-safe) */
    TQueue<float> PendingProgressUpdates;

    /** Pending step updates (thread-safe) */
    TQueue<TPair<EFTIPipelineStep, FString>> PendingStepUpdates;

    // ═══════════════════════════════════════════════════════════════════
    // Combo Box Data Sources
    // ═══════════════════════════════════════════════════════════════════

    TArray<TSharedPtr<FString>> OutputFormatOptions;
    TArray<TSharedPtr<FString>> MeshHandlingOptions;

    // ═══════════════════════════════════════════════════════════════════
    // Timing
    // ═══════════════════════════════════════════════════════════════════

    /** Last IPC status check time */
    double LastIPCCheckTime;

    /** IPC check interval (seconds) */
    static constexpr float IPCCheckInterval = 3.0f;
};

/**
 * IPC Monitor Runnable - Background thread for monitoring IPC progress
 */
class FIPCMonitorRunnable : public FRunnable
{
public:
    FIPCMonitorRunnable(const FString& InIPCFolderPath, const FString& InRequestId);
    virtual ~FIPCMonitorRunnable();

    // FRunnable interface
    virtual bool Init() override { return true; }
    virtual uint32 Run() override;
    virtual void Stop() override;

    /** Check if monitor should continue */
    bool ShouldContinue() const { return !bShouldStop; }

    /** Get completion status */
    bool IsComplete() const { return bComplete; }

    /** Get success status */
    bool WasSuccessful() const { return bSuccess; }

    /** Get output file path */
    FString GetOutputFile() const { return OutputFile; }

    /** Get error message */
    FString GetError() const { return ErrorMessage; }

    /** Get latest progress */
    float GetProgress() const { return ProgressPercent; }

    /** Get current stage */
    FString GetCurrentStage() const { return CurrentStage; }

private:
    FString IPCFolderPath;
    FString RequestId;
    
    FThreadSafeBool bShouldStop;
    FThreadSafeBool bComplete;
    FThreadSafeBool bSuccess;
    
    TAtomic<float> ProgressPercent;
    FString CurrentStage;
    FString OutputFile;
    FString ErrorMessage;
    
    FCriticalSection DataLock;
};
