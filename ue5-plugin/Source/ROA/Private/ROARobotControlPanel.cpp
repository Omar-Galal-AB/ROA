// Copyright ROA Development Team. All Rights Reserved.

#include "ROARobotControlPanel.h"
#include "ROARobotActor.h"
#include "Components/Slider.h"
#include "Components/TextBlock.h"
#include "Components/Button.h"
#include "Components/VerticalBox.h"
#include "Components/HorizontalBox.h"

UROARobotControlPanel::UROARobotControlPanel(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
	, MotionDuration(2.0f)
	, bAutoUpdateSliders(true)
{
	UpdateInterval = 0.1f; // 10 Hz for control panel
}

bool UROARobotControlPanel::InitializeWithRobot(AROARobotActor* InRobotActor)
{
	if (!Super::InitializeWithRobot(InRobotActor))
	{
		return false;
	}

	// Update robot info display
	if (RobotNameText)
	{
		RobotNameText->SetText(FText::FromString(InRobotActor->GetRobotId()));
	}

	if (RobotTypeText)
	{
		RobotTypeText->SetText(FText::FromString(InRobotActor->GetRobotType()));
	}

	// Note: Joint sliders should be created in Blueprint and bound
	// This simplified version expects sliders to be pre-created in blueprint
	
	UE_LOG(LogTemp, Log, TEXT("ROA Control Panel: Initialized for robot '%s' with %d joints"), 
		*InRobotActor->GetRobotId(), InRobotActor->GetJointCount());

	return true;
}

void UROARobotControlPanel::UpdateWidgetData()
{
	Super::UpdateWidgetData();

	if (bAutoUpdateSliders && RobotActor)
	{
		UpdateSlidersFromRobot();
	}
}

void UROARobotControlPanel::NativeConstruct()
{
	Super::NativeConstruct();

	// Bind button events
	if (ApplyButton)
	{
		ApplyButton->OnClicked.AddDynamic(this, &UROARobotControlPanel::ApplyJointPositions);
	}

	if (ResetButton)
	{
		ResetButton->OnClicked.AddDynamic(this, &UROARobotControlPanel::ResetJoints);
	}

	if (EmergencyStopButton)
	{
		EmergencyStopButton->OnClicked.AddDynamic(this, &UROARobotControlPanel::OnEmergencyStopClicked);
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Control Panel: Widget constructed"));
}

void UROARobotControlPanel::CreateJointSliders()
{
	// This function is kept for future use but currently sliders
	// should be created in Blueprint UMG editor
	UE_LOG(LogTemp, Log, TEXT("ROA Control Panel: CreateJointSliders called - use Blueprint UMG editor instead"));
}

void UROARobotControlPanel::OnJointSliderChanged(float Value, int32 JointIndex)
{
	// Update the stored value
	if (JointIndex >= 0 && JointIndex < JointSliders.Num())
	{
		FROAJointSliderData& SliderData = JointSliders[JointIndex];
		SliderData.CurrentValue = Value;
		
		if (SliderData.ValueText)
		{
			SliderData.ValueText->SetText(FText::AsNumber(Value));
		}

		// Send widget event
		TSharedPtr<FJsonObject> EventData = MakeShared<FJsonObject>();
		EventData->SetStringField(TEXT("slider_id"), SliderData.JointName);
		EventData->SetNumberField(TEXT("value"), Value);
		EventData->SetNumberField(TEXT("joint_index"), JointIndex);
		
		SendWidgetEvent(TEXT("slider_changed"), EventData);
	}
}

void UROARobotControlPanel::ApplyJointPositions()
{
	if (!RobotActor)
	{
		UE_LOG(LogTemp, Warning, TEXT("ROA Control Panel: Cannot apply - no robot actor"));
		return;
	}

	// Collect current slider values
	TArray<float> TargetPositions;
	TargetPositions.Reserve(JointSliders.Num());
	
	for (const FROAJointSliderData& SliderData : JointSliders)
	{
		TargetPositions.Add(SliderData.CurrentValue);
	}

	// Apply to robot
	if (RobotActor->SetJointPositions(TargetPositions, MotionDuration))
	{
		UE_LOG(LogTemp, Log, TEXT("ROA Control Panel: Applied joint positions to robot '%s'"), 
			*RobotActor->GetRobotId());

		// Send widget event
		TSharedPtr<FJsonObject> EventData = MakeShared<FJsonObject>();
		TArray<TSharedPtr<FJsonValue>> PositionsArray;
		for (float Pos : TargetPositions)
		{
			PositionsArray.Add(MakeShared<FJsonValueNumber>(Pos));
		}
		EventData->SetArrayField(TEXT("joint_positions"), PositionsArray);
		EventData->SetNumberField(TEXT("duration"), MotionDuration);
		
		SendWidgetEvent(TEXT("apply_positions"), EventData);
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("ROA Control Panel: Failed to apply joint positions"));
	}
}

void UROARobotControlPanel::ResetJoints()
{
	// Reset all sliders to zero
	for (FROAJointSliderData& SliderData : JointSliders)
	{
		SliderData.CurrentValue = 0.0f;
		
		if (SliderData.SliderWidget)
		{
			SliderData.SliderWidget->SetValue(0.0f);
		}
		
		if (SliderData.ValueText)
		{
			SliderData.ValueText->SetText(FText::AsNumber(0.0f));
		}
	}

	// Apply zero positions to robot
	ApplyJointPositions();

	UE_LOG(LogTemp, Log, TEXT("ROA Control Panel: Reset all joints to zero"));

	// Send widget event
	SendWidgetEvent(TEXT("reset_joints"), nullptr);
}

void UROARobotControlPanel::OnEmergencyStopClicked()
{
	if (!RobotActor)
	{
		return;
	}

	RobotActor->EmergencyStop();
	
	UE_LOG(LogTemp, Warning, TEXT("ROA Control Panel: Emergency stop activated for robot '%s'"), 
		*RobotActor->GetRobotId());

	// Send widget event
	SendWidgetEvent(TEXT("emergency_stop"), nullptr);
}

void UROARobotControlPanel::UpdateSlidersFromRobot()
{
	if (!RobotActor)
	{
		return;
	}

	TArray<float> CurrentPositions = RobotActor->GetJointPositions();
	
	for (int32 i = 0; i < JointSliders.Num() && i < CurrentPositions.Num(); ++i)
	{
		FROAJointSliderData& SliderData = JointSliders[i];
		float NewValue = CurrentPositions[i];
		
		// Only update if value changed significantly
		if (FMath::Abs(SliderData.CurrentValue - NewValue) > 0.001f)
		{
			SliderData.CurrentValue = NewValue;
			
			if (SliderData.SliderWidget)
			{
				SliderData.SliderWidget->SetValue(NewValue);
			}
			
			if (SliderData.ValueText)
			{
				SliderData.ValueText->SetText(FText::AsNumber(NewValue));
			}
		}
	}
}
