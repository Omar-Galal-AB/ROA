// SFTIImportPanel.cpp
// Slate-based FTI Import Panel implementation for UE5 Editor
// ROA - Robot Operations & Automation

#include "SFTIImportPanel.h"
#include "FTIPostImportHook.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SSeparator.h"
#include "Widgets/Layout/SSplitter.h"
#include "Styling/SlateStyleRegistry.h"
#include "EditorStyleSet.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "XmlParser/Public/XmlParser.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "IPythonScriptPlugin.h"
#include "Modules/ModuleManager.h"

#define LOCTEXT_NAMESPACE "FTIImportPanel"

// ═══════════════════════════════════════════════════════════════════════════════
// SFTIImportPanel Implementation
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::Construct(const FArguments& InArgs)
{
    // Initialize state
    SourceFilePath = TEXT("");
    DetectedFormat = TEXT("Unknown");
    RobotName = TEXT("");
    LinkCount = 0;
    JointCount = 0;
    MeshCount = 0;
    CurrentRequestId = TEXT("");
    CurrentStep = EFTIPipelineStep::Parse;
    bImportInProgress = false;
    bIPCServiceRunning = false;
    ProgressPercent = 0.0f;
    LastIPCCheckTime = 0.0;
    IPCMonitorThread = nullptr;

    // Default options
    OutputFormat = TEXT("USD");
    MeshHandling = TEXT("Embed");
    bAutoAssemble = true;
    bGenerateBlueprint = true;

    // IPC folder path
    IPCFolderPath = InArgs._IPCFolderPath;
    if (IPCFolderPath.IsEmpty())
    {
        // Default to D:/ROA/.ipc on Windows
        IPCFolderPath = TEXT("D:/ROA/.ipc");
    }

    // Python module path - where ue5_import_workflow.py lives
    // This should match the FTI plugin installation structure
    PythonModulePath = FPaths::Combine(FPaths::ProjectPluginsDir(), TEXT("ROA_FTI/Content/Python"));
    if (!FPaths::DirectoryExists(PythonModulePath))
    {
        // Fallback: try project content Python folder
        PythonModulePath = FPaths::Combine(FPaths::ProjectContentDir(), TEXT("Python/ROA"));
    }

    // Setup combo box options
    OutputFormatOptions.Add(MakeShared<FString>(TEXT("USD")));
    OutputFormatOptions.Add(MakeShared<FString>(TEXT("USDA")));
    OutputFormatOptions.Add(MakeShared<FString>(TEXT("USDZ")));

    MeshHandlingOptions.Add(MakeShared<FString>(TEXT("Embed")));
    MeshHandlingOptions.Add(MakeShared<FString>(TEXT("Reference")));
    MeshHandlingOptions.Add(MakeShared<FString>(TEXT("Convert")));

    // Setup pipeline steps
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("Parse"), EFTIPipelineStep::Parse));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("XACRO"), EFTIPipelineStep::XACRO));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("Hierarchy"), EFTIPipelineStep::Hierarchy));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("Meshes"), EFTIPipelineStep::Meshes));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("USD"), EFTIPipelineStep::USD));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("IPC"), EFTIPipelineStep::IPC));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("Import"), EFTIPipelineStep::Import));
    PipelineSteps.Add(MakeShared<FFTIPipelineStepData>(TEXT("Assemble"), EFTIPipelineStep::Assemble));

    // Build the widget
    ChildSlot
    [
        SNew(SBorder)
        .BorderImage(FEditorStyle::GetBrush("ToolPanel.GroupBorder"))
        .Padding(FMargin(8.0f))
        [
            SNew(SScrollBox)
            + SScrollBox::Slot()
            [
                SNew(SVerticalBox)
                
                // Title
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0, 0, 0, 8)
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("Title", "🤖 FTI Robot Import Panel"))
                    .Font(FCoreStyle::GetDefaultFontStyle("Bold", 16))
                ]
                
                // File Selection
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0, 4)
                [
                    CreateFileSelectionSection()
                ]
                
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(SSeparator)
                ]
                
                // Format Detection
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0, 4)
                [
                    CreateFormatDetectionSection()
                ]
                
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(SSeparator)
                ]
                
                // Import Options
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0, 4)
                [
                    CreateImportOptionsSection()
                ]
                
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(SSeparator)
                ]
                
                // IPC Status
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0, 4)
                [
                    CreateIPCStatusSection()
                ]
                
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(SSeparator)
                ]
                
                // Progress Section
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0, 4)
                [
                    CreateProgressSection()
                ]
                
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(SSeparator)
                ]
                
                // Log Section
                + SVerticalBox::Slot()
                .FillHeight(1.0f)
                .Padding(0, 4)
                [
                    CreateLogSection()
                ]
            ]
        ]
    ];

    // Check IPC status immediately
    CheckIPCServiceStatus();
}

SFTIImportPanel::~SFTIImportPanel()
{
    StopIPCMonitor();
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI Construction
// ═══════════════════════════════════════════════════════════════════════════════

TSharedRef<SWidget> SFTIImportPanel::CreateFileSelectionSection()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot()
        .AutoHeight()
        [
            SNew(STextBlock)
            .Text(LOCTEXT("FileSelection", "📁 Source File"))
            .Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
        ]
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4, 0, 0)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .FillWidth(1.0f)
            [
                SAssignNew(FilePathTextBox, SEditableTextBox)
                .HintText(LOCTEXT("FilePathHint", "Select URDF, XACRO, or USD file..."))
                .OnTextChanged(this, &SFTIImportPanel::OnFilePathChanged)
            ]
            + SHorizontalBox::Slot()
            .AutoWidth()
            .Padding(4, 0, 0, 0)
            [
                SNew(SButton)
                .Text(LOCTEXT("Browse", "Browse..."))
                .OnClicked(this, &SFTIImportPanel::OnBrowseButtonClicked)
            ]
        ];
}

TSharedRef<SWidget> SFTIImportPanel::CreateFormatDetectionSection()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot()
        .AutoHeight()
        [
            SNew(STextBlock)
            .Text(LOCTEXT("FormatDetection", "📋 File Information"))
            .Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
        ]
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4, 0, 0)
        [
            SNew(SHorizontalBox)
            // Format
            + SHorizontalBox::Slot()
            .FillWidth(0.25f)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("Format", "Format:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(DetectedFormatText, STextBlock)
                    .Text(FText::FromString(DetectedFormat))
                    .ColorAndOpacity(FSlateColor(FLinearColor(0.4f, 0.8f, 1.0f)))
                ]
            ]
            // Robot Name
            + SHorizontalBox::Slot()
            .FillWidth(0.25f)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("RobotName", "Robot:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(RobotNameText, STextBlock)
                    .Text(LOCTEXT("NoRobot", "-"))
                ]
            ]
            // Links
            + SHorizontalBox::Slot()
            .FillWidth(0.15f)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("Links", "Links:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(LinkCountText, STextBlock)
                    .Text(LOCTEXT("Zero", "0"))
                ]
            ]
            // Joints
            + SHorizontalBox::Slot()
            .FillWidth(0.15f)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("Joints", "Joints:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(JointCountText, STextBlock)
                    .Text(LOCTEXT("Zero", "0"))
                ]
            ]
            // Meshes
            + SHorizontalBox::Slot()
            .FillWidth(0.2f)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("Meshes", "Meshes:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(MeshCountText, STextBlock)
                    .Text(LOCTEXT("Zero", "0"))
                ]
            ]
        ];
}

TSharedRef<SWidget> SFTIImportPanel::CreateImportOptionsSection()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot()
        .AutoHeight()
        [
            SNew(STextBlock)
            .Text(LOCTEXT("ImportOptions", "⚙️ Import Options"))
            .Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
        ]
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4, 0, 0)
        [
            SNew(SHorizontalBox)
            // Output Format
            + SHorizontalBox::Slot()
            .FillWidth(0.5f)
            .Padding(0, 0, 8, 0)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("OutputFormat", "Output Format:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(OutputFormatCombo, SComboBox<TSharedPtr<FString>>)
                    .OptionsSource(&OutputFormatOptions)
                    .InitiallySelectedItem(OutputFormatOptions[0])
                    .OnSelectionChanged(this, &SFTIImportPanel::OnOutputFormatChanged)
                    .OnGenerateWidget_Lambda([](TSharedPtr<FString> Item)
                    {
                        return SNew(STextBlock).Text(FText::FromString(*Item));
                    })
                    .Content()
                    [
                        SNew(STextBlock)
                        .Text_Lambda([this]()
                        {
                            return FText::FromString(OutputFormat);
                        })
                    ]
                ]
            ]
            // Mesh Handling
            + SHorizontalBox::Slot()
            .FillWidth(0.5f)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("MeshHandling", "Mesh Handling:"))
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    SAssignNew(MeshHandlingCombo, SComboBox<TSharedPtr<FString>>)
                    .OptionsSource(&MeshHandlingOptions)
                    .InitiallySelectedItem(MeshHandlingOptions[0])
                    .OnSelectionChanged(this, &SFTIImportPanel::OnMeshHandlingChanged)
                    .OnGenerateWidget_Lambda([](TSharedPtr<FString> Item)
                    {
                        return SNew(STextBlock).Text(FText::FromString(*Item));
                    })
                    .Content()
                    [
                        SNew(STextBlock)
                        .Text_Lambda([this]()
                        {
                            return FText::FromString(MeshHandling);
                        })
                    ]
                ]
            ]
        ]
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4, 0, 0)
        [
            SNew(SHorizontalBox)
            // Auto-Assemble
            + SHorizontalBox::Slot()
            .FillWidth(0.5f)
            [
                SNew(SHorizontalBox)
                + SHorizontalBox::Slot()
                .AutoWidth()
                [
                    SAssignNew(AutoAssembleCheckbox, SCheckBox)
                    .IsChecked(bAutoAssemble ? ECheckBoxState::Checked : ECheckBoxState::Unchecked)
                    .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState)
                    {
                        bAutoAssemble = (NewState == ECheckBoxState::Checked);
                    })
                ]
                + SHorizontalBox::Slot()
                .AutoWidth()
                .Padding(4, 0, 0, 0)
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("AutoAssemble", "Auto-Assemble Hierarchy"))
                ]
            ]
            // Generate Blueprint
            + SHorizontalBox::Slot()
            .FillWidth(0.5f)
            [
                SNew(SHorizontalBox)
                + SHorizontalBox::Slot()
                .AutoWidth()
                [
                    SAssignNew(GenerateBlueprintCheckbox, SCheckBox)
                    .IsChecked(bGenerateBlueprint ? ECheckBoxState::Checked : ECheckBoxState::Unchecked)
                    .OnCheckStateChanged_Lambda([this](ECheckBoxState NewState)
                    {
                        bGenerateBlueprint = (NewState == ECheckBoxState::Checked);
                    })
                ]
                + SHorizontalBox::Slot()
                .AutoWidth()
                .Padding(4, 0, 0, 0)
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("GenerateBlueprint", "Generate Blueprint"))
                ]
            ]
        ];
}

TSharedRef<SWidget> SFTIImportPanel::CreateIPCStatusSection()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot()
        .AutoHeight()
        [
            SNew(STextBlock)
            .Text(LOCTEXT("IPCStatus", "📡 IPC Service Status"))
            .Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
        ]
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4, 0, 0)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .AutoWidth()
            [
                SAssignNew(IPCStatusText, STextBlock)
                .Text(LOCTEXT("CheckingIPC", "Checking..."))
            ]
            + SHorizontalBox::Slot()
            .FillWidth(1.0f)
            [
                SNullWidget::NullWidget
            ]
            + SHorizontalBox::Slot()
            .AutoWidth()
            .Padding(8, 0, 0, 0)
            [
                SNew(SButton)
                .Text(LOCTEXT("StartIPC", "Start Service"))
                .OnClicked(this, &SFTIImportPanel::OnStartIPCServiceClicked)
                .IsEnabled_Lambda([this]() { return !bIPCServiceRunning; })
            ]
            + SHorizontalBox::Slot()
            .AutoWidth()
            .Padding(4, 0, 0, 0)
            [
                SNew(SButton)
                .Text(LOCTEXT("StopIPC", "Stop Service"))
                .OnClicked(this, &SFTIImportPanel::OnStopIPCServiceClicked)
                .IsEnabled_Lambda([this]() { return bIPCServiceRunning; })
            ]
        ];
}

TSharedRef<SWidget> SFTIImportPanel::CreateProgressSection()
{
    return SNew(SVerticalBox)
        // Convert button
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .FillWidth(1.0f)
            [
                SAssignNew(ConvertButton, SButton)
                .Text(LOCTEXT("Convert", "🚀 Convert & Import to UE5"))
                .OnClicked(this, &SFTIImportPanel::OnConvertButtonClicked)
                .IsEnabled_Lambda([this]()
                {
                    return !bImportInProgress && 
                           !SourceFilePath.IsEmpty() && 
                           bIPCServiceRunning;
                })
                .HAlign(HAlign_Center)
                .ContentPadding(FMargin(16, 8))
            ]
            + SHorizontalBox::Slot()
            .AutoWidth()
            .Padding(4, 0, 0, 0)
            [
                SAssignNew(CancelButton, SButton)
                .Text(LOCTEXT("Cancel", "Cancel"))
                .OnClicked(this, &SFTIImportPanel::OnCancelButtonClicked)
                .IsEnabled_Lambda([this]() { return bImportInProgress; })
            ]
        ]
        // Progress bar
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4)
        [
            SAssignNew(ProgressBar, SProgressBar)
            .Percent_Lambda([this]() { return ProgressPercent; })
        ]
        // Pipeline steps
        + SVerticalBox::Slot()
        .AutoHeight()
        .Padding(0, 4)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .FillWidth(1.0f)
            [
                SNew(SWrapBox)
                .UseAllottedSize(true)
                + SWrapBox::Slot()
                .Padding(2)
                [
                    SNew(STextBlock).Text_Lambda([this]()
                    {
                        FString Steps;
                        for (const auto& Step : PipelineSteps)
                        {
                            FString Icon = Step->bComplete ? TEXT("✅") : 
                                          (Step->bInProgress ? TEXT("🔄") : 
                                          (Step->bError ? TEXT("❌") : TEXT("⬜")));
                            Steps += FString::Printf(TEXT("%s %s  "), *Icon, *Step->Name);
                        }
                        return FText::FromString(Steps);
                    })
                ]
            ]
        ];
}

TSharedRef<SWidget> SFTIImportPanel::CreateLogSection()
{
    return SNew(SVerticalBox)
        + SVerticalBox::Slot()
        .AutoHeight()
        [
            SNew(STextBlock)
            .Text(LOCTEXT("Log", "📝 Conversion Log"))
            .Font(FCoreStyle::GetDefaultFontStyle("Bold", 12))
        ]
        + SVerticalBox::Slot()
        .FillHeight(1.0f)
        .Padding(0, 4, 0, 0)
        [
            SNew(SBorder)
            .BorderImage(FEditorStyle::GetBrush("ToolPanel.DarkGroupBorder"))
            .Padding(4)
            [
                SAssignNew(LogScrollBox, SScrollBox)
            ]
        ];
}

// ═══════════════════════════════════════════════════════════════════════════════
// Widget Tick
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
    SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);

    // Periodic IPC status check
    if (InCurrentTime - LastIPCCheckTime > IPCCheckInterval)
    {
        CheckIPCServiceStatus();
        LastIPCCheckTime = InCurrentTime;
    }

    // Process pending log entries from worker thread
    TPair<FString, bool> LogEntry;
    while (PendingLogEntries.Dequeue(LogEntry))
    {
        AddLogEntry(LogEntry.Key, LogEntry.Value);
    }

    // Process pending progress updates
    float NewProgress;
    while (PendingProgressUpdates.Dequeue(NewProgress))
    {
        ProgressPercent = NewProgress;
    }

    // Process pending step updates
    TPair<EFTIPipelineStep, FString> StepUpdate;
    while (PendingStepUpdates.Dequeue(StepUpdate))
    {
        UpdatePipelineStep(StepUpdate.Key, false, true, false, StepUpdate.Value);
    }

    // Check IPC monitor for completion
    if (IPCMonitor.IsValid() && IPCMonitor->IsComplete())
    {
        bImportInProgress = false;
        
        if (IPCMonitor->WasSuccessful())
        {
            OnImportComplete(IPCMonitor->GetOutputFile());
        }
        else
        {
            AddLogEntry(FString::Printf(TEXT("❌ Conversion failed: %s"), *IPCMonitor->GetError()), true);
        }
        
        StopIPCMonitor();
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Event Handlers
// ═══════════════════════════════════════════════════════════════════════════════

FReply SFTIImportPanel::OnBrowseButtonClicked()
{
    IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
    if (!DesktopPlatform)
    {
        return FReply::Handled();
    }

    TArray<FString> OutFiles;
    const FString FileTypes = TEXT("Robot Files (*.urdf;*.xacro;*.sdf;*.usd;*.usda)|*.urdf;*.xacro;*.sdf;*.usd;*.usda|All Files (*.*)|*.*");

    if (DesktopPlatform->OpenFileDialog(
        FSlateApplication::Get().FindBestParentWindowHandleForDialogs(nullptr),
        TEXT("Select Robot File"),
        FPaths::GetProjectFilePath(),
        TEXT(""),
        FileTypes,
        EFileDialogFlags::None,
        OutFiles))
    {
        if (OutFiles.Num() > 0)
        {
            SetSourceFile(OutFiles[0]);
        }
    }

    return FReply::Handled();
}

void SFTIImportPanel::OnFilePathChanged(const FText& NewText)
{
    FString NewPath = NewText.ToString();
    if (NewPath != SourceFilePath)
    {
        SetSourceFile(NewPath);
    }
}

FReply SFTIImportPanel::OnConvertButtonClicked()
{
    StartImport();
    return FReply::Handled();
}

FReply SFTIImportPanel::OnCancelButtonClicked()
{
    CancelImport();
    return FReply::Handled();
}

FReply SFTIImportPanel::OnStartIPCServiceClicked()
{
    AddLogEntry(TEXT("Requesting IPC service start..."));
    
    // Write start command to IPC folder
    FString CommandFile = FPaths::Combine(IPCFolderPath, TEXT("commands"), TEXT("start.cmd"));
    FString CommandContent = TEXT("{\"command\": \"start\"}");
    FFileHelper::SaveStringToFile(CommandContent, *CommandFile);
    
    return FReply::Handled();
}

FReply SFTIImportPanel::OnStopIPCServiceClicked()
{
    AddLogEntry(TEXT("Requesting IPC service stop..."));
    
    // Write stop command to IPC folder
    FString CommandFile = FPaths::Combine(IPCFolderPath, TEXT("commands"), TEXT("stop.cmd"));
    FString CommandContent = TEXT("{\"command\": \"stop\"}");
    FFileHelper::SaveStringToFile(CommandContent, *CommandFile);
    
    return FReply::Handled();
}

void SFTIImportPanel::OnOutputFormatChanged(TSharedPtr<FString> NewSelection, ESelectInfo::Type SelectInfo)
{
    if (NewSelection.IsValid())
    {
        OutputFormat = *NewSelection;
    }
}

void SFTIImportPanel::OnMeshHandlingChanged(TSharedPtr<FString> NewSelection, ESelectInfo::Type SelectInfo)
{
    if (NewSelection.IsValid())
    {
        MeshHandling = *NewSelection;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Public Interface
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::SetSourceFile(const FString& FilePath)
{
    SourceFilePath = FilePath;
    
    if (FilePathTextBox.IsValid())
    {
        FilePathTextBox->SetText(FText::FromString(FilePath));
    }
    
    // Detect format
    DetectedFormat = DetectFileFormat(FilePath);
    if (DetectedFormatText.IsValid())
    {
        DetectedFormatText->SetText(FText::FromString(DetectedFormat));
    }
    
    // Parse file for preview
    if (FPaths::FileExists(FilePath))
    {
        ParseRobotFileInfo(FilePath);
        AddLogEntry(FString::Printf(TEXT("Selected: %s (%s)"), *FPaths::GetCleanFilename(FilePath), *DetectedFormat));
    }
}

void SFTIImportPanel::StartImport()
{
    if (bImportInProgress)
    {
        AddLogEntry(TEXT("Import already in progress"), true);
        return;
    }

    if (SourceFilePath.IsEmpty())
    {
        AddLogEntry(TEXT("No source file selected"), true);
        return;
    }

    if (!bIPCServiceRunning)
    {
        AddLogEntry(TEXT("IPC service is not running"), true);
        return;
    }

    // Reset UI
    ResetPipelineSteps();
    ClearLog();
    ProgressPercent = 0.0f;
    bImportInProgress = true;

    AddLogEntry(FString::Printf(TEXT("Starting conversion of: %s"), *FPaths::GetCleanFilename(SourceFilePath)));
    AddLogEntry(FString::Printf(TEXT("Options: Format=%s, Mesh=%s, AutoAssemble=%s, Blueprint=%s"),
        *OutputFormat, *MeshHandling,
        bAutoAssemble ? TEXT("Yes") : TEXT("No"),
        bGenerateBlueprint ? TEXT("Yes") : TEXT("No")));

    // Submit request
    CurrentRequestId = SubmitConversionRequest();
    
    if (!CurrentRequestId.IsEmpty())
    {
        AddLogEntry(FString::Printf(TEXT("Request ID: %s"), *CurrentRequestId));
        UpdatePipelineStep(EFTIPipelineStep::Parse, false, true, false, TEXT("Starting..."));
        
        // Start monitoring
        StartIPCMonitor();
    }
    else
    {
        AddLogEntry(TEXT("Failed to submit conversion request"), true);
        bImportInProgress = false;
    }
}

void SFTIImportPanel::CancelImport()
{
    if (!bImportInProgress)
    {
        return;
    }

    AddLogEntry(TEXT("Cancelling conversion..."));
    
    // Write cancel request
    FString CancelFile = FPaths::Combine(IPCFolderPath, TEXT("requests"), 
        FString::Printf(TEXT("cancel_%s.request.json"), *CurrentRequestId));
    FString CancelContent = FString::Printf(
        TEXT("{\"request_type\": \"cancel\", \"target_request_id\": \"%s\"}"),
        *CurrentRequestId);
    FFileHelper::SaveStringToFile(CancelContent, *CancelFile);
    
    StopIPCMonitor();
    bImportInProgress = false;
    AddLogEntry(TEXT("Conversion cancelled"));
}

// ═══════════════════════════════════════════════════════════════════════════════
// File Analysis
// ═══════════════════════════════════════════════════════════════════════════════

FString SFTIImportPanel::DetectFileFormat(const FString& FilePath)
{
    FString Extension = FPaths::GetExtension(FilePath).ToLower();
    
    if (Extension == TEXT("urdf")) return TEXT("URDF");
    if (Extension == TEXT("xacro")) return TEXT("XACRO");
    if (Extension == TEXT("sdf")) return TEXT("SDF");
    if (Extension == TEXT("usd")) return TEXT("USD");
    if (Extension == TEXT("usda")) return TEXT("USDA");
    if (Extension == TEXT("usdz")) return TEXT("USDZ");
    if (Extension == TEXT("stl")) return TEXT("STL");
    if (Extension == TEXT("obj")) return TEXT("OBJ");
    if (Extension == TEXT("fbx")) return TEXT("FBX");
    if (Extension == TEXT("dae")) return TEXT("COLLADA");
    
    return TEXT("Unknown");
}

void SFTIImportPanel::ParseRobotFileInfo(const FString& FilePath)
{
    FString Extension = FPaths::GetExtension(FilePath).ToLower();
    
    if (Extension != TEXT("urdf") && Extension != TEXT("xacro") && Extension != TEXT("sdf"))
    {
        // Not an XML robot format
        RobotName = FPaths::GetBaseFilename(FilePath);
        LinkCount = 0;
        JointCount = 0;
        MeshCount = 0;
        
        // Update UI
        if (RobotNameText.IsValid()) RobotNameText->SetText(FText::FromString(RobotName));
        if (LinkCountText.IsValid()) LinkCountText->SetText(FText::FromString(TEXT("-")));
        if (JointCountText.IsValid()) JointCountText->SetText(FText::FromString(TEXT("-")));
        if (MeshCountText.IsValid()) MeshCountText->SetText(FText::FromString(TEXT("-")));
        return;
    }
    
    // Parse XML
    FString FileContent;
    if (!FFileHelper::LoadFileToString(FileContent, *FilePath))
    {
        return;
    }
    
    // Simple parsing (count occurrences)
    RobotName = FPaths::GetBaseFilename(FilePath);
    
    // Try to extract robot name
    int32 NameStart = FileContent.Find(TEXT("name=\""));
    if (NameStart != INDEX_NONE)
    {
        NameStart += 6;
        int32 NameEnd = FileContent.Find(TEXT("\""), ESearchCase::IgnoreCase, ESearchDir::FromStart, NameStart);
        if (NameEnd != INDEX_NONE)
        {
            RobotName = FileContent.Mid(NameStart, NameEnd - NameStart);
        }
    }
    
    // Count links
    LinkCount = 0;
    int32 SearchPos = 0;
    while ((SearchPos = FileContent.Find(TEXT("<link"), ESearchCase::IgnoreCase, ESearchDir::FromStart, SearchPos)) != INDEX_NONE)
    {
        LinkCount++;
        SearchPos++;
    }
    
    // Count joints
    JointCount = 0;
    SearchPos = 0;
    while ((SearchPos = FileContent.Find(TEXT("<joint"), ESearchCase::IgnoreCase, ESearchDir::FromStart, SearchPos)) != INDEX_NONE)
    {
        JointCount++;
        SearchPos++;
    }
    
    // Count meshes
    MeshCount = 0;
    SearchPos = 0;
    while ((SearchPos = FileContent.Find(TEXT("<mesh"), ESearchCase::IgnoreCase, ESearchDir::FromStart, SearchPos)) != INDEX_NONE)
    {
        MeshCount++;
        SearchPos++;
    }
    
    // Update UI
    if (RobotNameText.IsValid()) RobotNameText->SetText(FText::FromString(RobotName));
    if (LinkCountText.IsValid()) LinkCountText->SetText(FText::FromString(FString::Printf(TEXT("%d"), LinkCount)));
    if (JointCountText.IsValid()) JointCountText->SetText(FText::FromString(FString::Printf(TEXT("%d"), JointCount)));
    if (MeshCountText.IsValid()) MeshCountText->SetText(FText::FromString(FString::Printf(TEXT("%d"), MeshCount)));
}

// ═══════════════════════════════════════════════════════════════════════════════
// IPC Communication
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::CheckIPCServiceStatus()
{
    FString StatusFile = FPaths::Combine(IPCFolderPath, TEXT("service.status"));
    
    if (!FPaths::FileExists(StatusFile))
    {
        bIPCServiceRunning = false;
        if (IPCStatusText.IsValid())
        {
            IPCStatusText->SetText(LOCTEXT("IPCNotRunning", "🔴 Not Running"));
            IPCStatusText->SetColorAndOpacity(FSlateColor(FLinearColor::Red));
        }
        return;
    }
    
    FString StatusContent;
    if (!FFileHelper::LoadFileToString(StatusContent, *StatusFile))
    {
        bIPCServiceRunning = false;
        return;
    }
    
    // Parse JSON
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(StatusContent);
    if (FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
    {
        double Timestamp = JsonObject->GetNumberField(TEXT("timestamp"));
        double Now = FPlatformTime::Seconds();
        
        // Consider running if heartbeat within 10 seconds
        bIPCServiceRunning = (Now - Timestamp) < 10.0;
        
        if (IPCStatusText.IsValid())
        {
            if (bIPCServiceRunning)
            {
                IPCStatusText->SetText(LOCTEXT("IPCRunning", "🟢 Running"));
                IPCStatusText->SetColorAndOpacity(FSlateColor(FLinearColor::Green));
            }
            else
            {
                IPCStatusText->SetText(LOCTEXT("IPCStale", "🟡 Stale"));
                IPCStatusText->SetColorAndOpacity(FSlateColor(FLinearColor::Yellow));
            }
        }
    }
}

FString SFTIImportPanel::SubmitConversionRequest()
{
    // Generate request ID
    FString RequestId = FGuid::NewGuid().ToString();
    
    // Build request JSON
    TSharedPtr<FJsonObject> RequestJson = MakeShared<FJsonObject>();
    RequestJson->SetStringField(TEXT("protocol_version"), TEXT("1.0.0"));
    RequestJson->SetStringField(TEXT("request_id"), RequestId);
    RequestJson->SetNumberField(TEXT("timestamp"), FPlatformTime::Seconds());
    RequestJson->SetStringField(TEXT("request_type"), TEXT("convert"));
    RequestJson->SetStringField(TEXT("source_file"), SourceFilePath);
    
    // Options
    TSharedPtr<FJsonObject> OptionsJson = MakeShared<FJsonObject>();
    OptionsJson->SetStringField(TEXT("output_format"), OutputFormat.ToLower());
    OptionsJson->SetStringField(TEXT("mesh_handling"), MeshHandling.ToLower());
    OptionsJson->SetBoolField(TEXT("auto_assemble"), bAutoAssemble);
    OptionsJson->SetBoolField(TEXT("generate_blueprint"), bGenerateBlueprint);
    RequestJson->SetObjectField(TEXT("options"), OptionsJson);
    
    // Serialize
    FString RequestContent;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&RequestContent);
    FJsonSerializer::Serialize(RequestJson.ToSharedRef(), Writer);
    
    // Write to IPC folder (atomic: write .tmp then rename)
    FString RequestFile = FPaths::Combine(IPCFolderPath, TEXT("requests"), 
        FString::Printf(TEXT("%s.request.json"), *RequestId));
    FString TempFile = RequestFile + TEXT(".tmp");
    
    if (FFileHelper::SaveStringToFile(RequestContent, *TempFile))
    {
        IFileManager::Get().Move(*RequestFile, *TempFile);
        return RequestId;
    }
    
    return FString();
}

void SFTIImportPanel::StartIPCMonitor()
{
    if (IPCMonitor.IsValid())
    {
        StopIPCMonitor();
    }
    
    IPCMonitor = MakeShared<FIPCMonitorRunnable>(IPCFolderPath, CurrentRequestId);
    IPCMonitorThread = FRunnableThread::Create(IPCMonitor.Get(), TEXT("FTI_IPC_Monitor"));
}

void SFTIImportPanel::StopIPCMonitor()
{
    if (IPCMonitor.IsValid())
    {
        IPCMonitor->Stop();
    }
    
    if (IPCMonitorThread)
    {
        IPCMonitorThread->WaitForCompletion();
        delete IPCMonitorThread;
        IPCMonitorThread = nullptr;
    }
    
    IPCMonitor.Reset();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Pipeline Control
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::UpdatePipelineStep(EFTIPipelineStep Step, bool bComplete, bool bInProgress, bool bError, const FString& StatusText)
{
    int32 Index = GetPipelineStepIndex(Step);
    if (Index >= 0 && Index < PipelineSteps.Num())
    {
        PipelineSteps[Index]->bComplete = bComplete;
        PipelineSteps[Index]->bInProgress = bInProgress;
        PipelineSteps[Index]->bError = bError;
        PipelineSteps[Index]->StatusText = StatusText;
        
        // Mark previous steps complete
        if (bInProgress || bComplete)
        {
            for (int32 i = 0; i < Index; i++)
            {
                if (!PipelineSteps[i]->bComplete && !PipelineSteps[i]->bError)
                {
                    PipelineSteps[i]->bComplete = true;
                    PipelineSteps[i]->bInProgress = false;
                }
            }
        }
    }
}

void SFTIImportPanel::ResetPipelineSteps()
{
    for (auto& Step : PipelineSteps)
    {
        Step->bComplete = false;
        Step->bInProgress = false;
        Step->bError = false;
        Step->StatusText = TEXT("Pending");
    }
}

int32 SFTIImportPanel::GetPipelineStepIndex(EFTIPipelineStep Step) const
{
    return static_cast<int32>(Step);
}

EFTIPipelineStep SFTIImportPanel::MapStageToStep(const FString& StageName) const
{
    FString LowerName = StageName.ToLower();
    
    if (LowerName.Contains(TEXT("parse"))) return EFTIPipelineStep::Parse;
    if (LowerName.Contains(TEXT("xacro"))) return EFTIPipelineStep::XACRO;
    if (LowerName.Contains(TEXT("hierarchy"))) return EFTIPipelineStep::Hierarchy;
    if (LowerName.Contains(TEXT("mesh"))) return EFTIPipelineStep::Meshes;
    if (LowerName.Contains(TEXT("usd"))) return EFTIPipelineStep::USD;
    if (LowerName.Contains(TEXT("ipc"))) return EFTIPipelineStep::IPC;
    if (LowerName.Contains(TEXT("import"))) return EFTIPipelineStep::Import;
    if (LowerName.Contains(TEXT("assemble"))) return EFTIPipelineStep::Assemble;
    if (LowerName.Contains(TEXT("complete"))) return EFTIPipelineStep::Complete;
    
    return EFTIPipelineStep::Parse;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Logging
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::AddLogEntry(const FString& Message, bool bIsError)
{
    if (!LogScrollBox.IsValid())
    {
        return;
    }
    
    FString Timestamp = FDateTime::Now().ToString(TEXT("[%H:%M:%S]"));
    FString FullMessage = FString::Printf(TEXT("%s %s"), *Timestamp, *Message);
    
    TSharedPtr<STextBlock> LogText;
    
    LogScrollBox->AddSlot()
    [
        SAssignNew(LogText, STextBlock)
        .Text(FText::FromString(FullMessage))
        .ColorAndOpacity(bIsError ? FSlateColor(FLinearColor::Red) : FSlateColor::UseForeground())
        .AutoWrapText(true)
    ];
    
    LogEntries.Add(LogText);
    
    // Keep only last 100 entries
    while (LogEntries.Num() > 100)
    {
        LogScrollBox->RemoveSlot(LogEntries[0].ToSharedRef());
        LogEntries.RemoveAt(0);
    }
    
    // Scroll to bottom
    LogScrollBox->ScrollToEnd();
}

void SFTIImportPanel::ClearLog()
{
    if (LogScrollBox.IsValid())
    {
        LogScrollBox->ClearChildren();
        LogEntries.Empty();
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Post-Import Actions
// ═══════════════════════════════════════════════════════════════════════════════

void SFTIImportPanel::OnImportComplete(const FString& OutputFile)
{
    AddLogEntry(FString::Printf(TEXT("✅ Conversion complete: %s"), *OutputFile));
    
    // Mark all steps complete
    for (auto& Step : PipelineSteps)
    {
        Step->bComplete = true;
        Step->bInProgress = false;
    }
    
    ProgressPercent = 1.0f;
    
    if (bAutoAssemble)
    {
        TriggerHierarchyAssembly(OutputFile);
    }
    
    if (bGenerateBlueprint)
    {
        GenerateRobotBlueprint(RobotName);
    }
}

void SFTIImportPanel::TriggerHierarchyAssembly(const FString& USDPath)
{
    AddLogEntry(TEXT("🔧 Triggering hierarchy assembly..."));
    AddLogEntry(FString::Printf(TEXT("Assembly target: %s"), *USDPath));
    
    // Execute Python hierarchy assembly workflow
    // The ue5_import_workflow.py module handles:
    // 1. Finding companion hierarchy script (robot_ue5_hierarchy.py)
    // 2. Importing mesh files from meshes/ subfolder
    // 3. Running hierarchy assembly to attach parts
    // 4. Creating proper parent-child relationships
    
    FString PythonScript = FString::Printf(
        TEXT("import sys\n")
        TEXT("sys.path.insert(0, r'%s')\n")
        TEXT("import ue5_import_workflow as fti\n")
        TEXT("result = fti.import_robot(r'%s', auto_assemble=True, generate_blueprint=%s)\n")
        TEXT("if result.success:\n")
        TEXT("    unreal.log('ROA FTI: Hierarchy assembly complete!')\n")
        TEXT("else:\n")
        TEXT("    unreal.log_error(f'ROA FTI: Assembly failed: {result.error_message}')\n"),
        *PythonModulePath,  // Path to UE5/ Python modules
        *USDPath,
        bGenerateBlueprint ? TEXT("True") : TEXT("False")
    );
    
    // Execute via UE5 Python subsystem
    if (IPythonScriptPlugin* PythonPlugin = FModuleManager::GetModulePtr<IPythonScriptPlugin>("PythonScriptPlugin"))
    {
        TArray<FString> CommandArgs;
        PythonPlugin->ExecPythonCommand(*PythonScript);
        AddLogEntry(TEXT("✓ Python hierarchy assembly triggered"));
    }
    else
    {
        AddLogEntry(TEXT("⚠ Python plugin not available - manual assembly required"), true);
        AddLogEntry(TEXT("Run in UE5 Python console:"), false);
        AddLogEntry(FString::Printf(TEXT("  import ue5_import_workflow as fti")), false);
        AddLogEntry(FString::Printf(TEXT("  fti.import_robot(r'%s')"), *USDPath), false);
    }
}

void SFTIImportPanel::GenerateRobotBlueprint(const FString& InRobotName)
{
    AddLogEntry(FString::Printf(TEXT("📘 Generating Blueprint for: %s"), *InRobotName));
    
    FString BlueprintPath = FString::Printf(TEXT("/Game/Robots/%s/BP_%s"), *InRobotName, *InRobotName);
    AddLogEntry(FString::Printf(TEXT("Blueprint path: %s"), *BlueprintPath));
    
    // Find the assembled robot actor in the level
    UWorld* World = GEngine->GetWorldContexts()[0].World();
    if (!World)
    {
        AddLogEntry(TEXT("⚠ No world context available for Blueprint generation"), true);
        return;
    }
    
    AActor* RobotActor = nullptr;
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        FString ActorLabel = It->GetActorLabel();
        if (ActorLabel.Contains(InRobotName))
        {
            RobotActor = *It;
            break;
        }
    }
    
    if (!RobotActor)
    {
        AddLogEntry(FString::Printf(TEXT("⚠ Robot actor '%s' not found in level"), *InRobotName), true);
        return;
    }
    
    // Use the PostImportHook's Blueprint generation
    if (UFTIPostImportSubsystem* Subsystem = GEngine->GetEngineSubsystem<UFTIPostImportSubsystem>())
    {
        if (UFTIPostImportHook* Hook = Subsystem->GetPostImportHook())
        {
            FString GeneratedPath = Hook->GenerateBlueprint(RobotActor, InRobotName);
            if (!GeneratedPath.IsEmpty())
            {
                AddLogEntry(FString::Printf(TEXT("✓ Blueprint generated: %s"), *GeneratedPath));
            }
            else
            {
                AddLogEntry(TEXT("⚠ Blueprint generation failed"), true);
            }
        }
    }
    else
    {
        AddLogEntry(TEXT("⚠ FTI PostImport subsystem not available"), true);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// FIPCMonitorRunnable Implementation
// ═══════════════════════════════════════════════════════════════════════════════

FIPCMonitorRunnable::FIPCMonitorRunnable(const FString& InIPCFolderPath, const FString& InRequestId)
    : IPCFolderPath(InIPCFolderPath)
    , RequestId(InRequestId)
    , bShouldStop(false)
    , bComplete(false)
    , bSuccess(false)
    , ProgressPercent(0.0f)
{
}

FIPCMonitorRunnable::~FIPCMonitorRunnable()
{
}

uint32 FIPCMonitorRunnable::Run()
{
    while (!bShouldStop)
    {
        // Check for response file
        FString ResponseFile = FPaths::Combine(IPCFolderPath, TEXT("responses"),
            FString::Printf(TEXT("%s.response.json"), *RequestId));
        
        if (FPaths::FileExists(ResponseFile))
        {
            FString ResponseContent;
            if (FFileHelper::LoadFileToString(ResponseContent, *ResponseFile))
            {
                TSharedPtr<FJsonObject> JsonObject;
                TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ResponseContent);
                
                if (FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
                {
                    FScopeLock Lock(&DataLock);
                    bSuccess = JsonObject->GetBoolField(TEXT("success"));
                    OutputFile = JsonObject->GetStringField(TEXT("output_file"));
                    ErrorMessage = JsonObject->GetStringField(TEXT("error"));
                    bComplete = true;
                    ProgressPercent = 1.0f;
                    return 0;
                }
            }
        }
        
        // Check for progress file
        FString ProgressFile = FPaths::Combine(IPCFolderPath, TEXT("progress"),
            FString::Printf(TEXT("%s.progress.json"), *RequestId));
        
        if (FPaths::FileExists(ProgressFile))
        {
            FString ProgressContent;
            if (FFileHelper::LoadFileToString(ProgressContent, *ProgressFile))
            {
                TSharedPtr<FJsonObject> JsonObject;
                TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ProgressContent);
                
                if (FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
                {
                    FScopeLock Lock(&DataLock);
                    ProgressPercent = JsonObject->GetNumberField(TEXT("percent")) / 100.0f;
                    CurrentStage = JsonObject->GetStringField(TEXT("stage"));
                }
            }
        }
        
        // Sleep before next check
        FPlatformProcess::Sleep(0.25f);
    }
    
    return 0;
}

void FIPCMonitorRunnable::Stop()
{
    bShouldStop = true;
}

#undef LOCTEXT_NAMESPACE
