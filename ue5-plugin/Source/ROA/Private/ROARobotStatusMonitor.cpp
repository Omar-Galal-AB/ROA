// Copyright ROA Development Team. All Rights Reserved.

#include "ROARobotStatusMonitor.h"
#include "ROARobotActor.h"
#include "Components/TextBlock.h"
#include "Components/Border.h"

UROARobotStatusMonitor::UROARobotStatusMonitor(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
	, StatusOkColor(FLinearColor::Green)
	, StatusWarningColor(FLinearColor::Yellow)
	, StatusErrorColor(FLinearColor::Red)
	, DecimalPlaces(2)
{
	UpdateInterval = 0.05f; // 20 Hz for status monitor
}

bool UROARobotStatusMonitor::InitializeWithRobot(AROARobotActor* InRobotActor)
{
	if (!Super::InitializeWithRobot(InRobotActor))
	{
		return false;
	}

	// Update static info
	if (RobotIdText)
	{
		RobotIdText->SetText(FText::FromString(InRobotActor->GetRobotId()));
	}

	if (RobotTypeText)
	{
		RobotTypeText->SetText(FText::FromString(InRobotActor->GetRobotType()));
	}

	UE_LOG(LogTemp, Log, TEXT("ROA Status Monitor: Initialized for robot '%s'"), 
		*InRobotActor->GetRobotId());

	return true;
}

void UROARobotStatusMonitor::UpdateWidgetData()
{
	Super::UpdateWidgetData();

	if (!RobotActor)
	{
		return;
	}

	UpdatePositionDisplay();
	UpdateJointDisplay();
	UpdateEndEffectorDisplay();
	UpdateCollisionStatus();
	UpdateStatusIndicator();
}

void UROARobotStatusMonitor::NativeConstruct()
{
	Super::NativeConstruct();

	UE_LOG(LogTemp, Log, TEXT("ROA Status Monitor: Widget constructed"));
}

void UROARobotStatusMonitor::UpdatePositionDisplay()
{
	FVector Position = RobotActor->GetActorLocation();
	FRotator Rotation = RobotActor->GetActorRotation();

	// Update position texts - use simple string formatting
	if (PositionXText)
	{
		FString ValueStr = FString::Printf(TEXT("%.2f"), Position.X);
		PositionXText->SetText(FText::FromString(ValueStr));
	}

	if (PositionYText)
	{
		FString ValueStr = FString::Printf(TEXT("%.2f"), Position.Y);
		PositionYText->SetText(FText::FromString(ValueStr));
	}

	if (PositionZText)
	{
		FString ValueStr = FString::Printf(TEXT("%.2f"), Position.Z);
		PositionZText->SetText(FText::FromString(ValueStr));
	}

	// Update rotation texts
	if (RotationRollText)
	{
		FString ValueStr = FString::Printf(TEXT("%.2f"), Rotation.Roll);
		RotationRollText->SetText(FText::FromString(ValueStr));
	}

	if (RotationPitchText)
	{
		FString ValueStr = FString::Printf(TEXT("%.2f"), Rotation.Pitch);
		RotationPitchText->SetText(FText::FromString(ValueStr));
	}

	if (RotationYawText)
	{
		FString ValueStr = FString::Printf(TEXT("%.2f"), Rotation.Yaw);
		RotationYawText->SetText(FText::FromString(ValueStr));
	}
}

void UROARobotStatusMonitor::UpdateJointDisplay()
{
	if (!JointPositionsText)
	{
		return;
	}

	TArray<float> JointPositions = RobotActor->GetJointPositions();
	
	FString JointsString;
	for (int32 i = 0; i < JointPositions.Num(); ++i)
	{
		if (i > 0)
		{
			JointsString += TEXT(", ");
		}
		JointsString += FString::Printf(TEXT("J%d: %.2f"), i, FMath::RadiansToDegrees(JointPositions[i]));
	}

	JointPositionsText->SetText(FText::FromString(JointsString));
}

void UROARobotStatusMonitor::UpdateEndEffectorDisplay()
{
	if (!EndEffectorPositionText)
	{
		return;
	}

	FVector EEPosition = RobotActor->GetEndEffectorPosition();
	FString EEString = FString::Printf(TEXT("X: %.2f, Y: %.2f, Z: %.2f"), 
		EEPosition.X, EEPosition.Y, EEPosition.Z);
	
	EndEffectorPositionText->SetText(FText::FromString(EEString));
}

void UROARobotStatusMonitor::UpdateCollisionStatus()
{
	bool bIsColliding = RobotActor->IsColliding();
	int32 CollisionCount = RobotActor->GetCollisionCount();

	if (CollisionStatusText)
	{
		FString StatusString = bIsColliding ? TEXT("COLLIDING") : TEXT("OK");
		CollisionStatusText->SetText(FText::FromString(StatusString));
		
		// Change color based on collision
		FSlateColor TextColor = bIsColliding ? 
			FSlateColor(StatusErrorColor) : FSlateColor(StatusOkColor);
		CollisionStatusText->SetColorAndOpacity(TextColor);
	}

	if (CollisionCountText)
	{
		CollisionCountText->SetText(FText::AsNumber(CollisionCount));
	}
}

void UROARobotStatusMonitor::UpdateStatusIndicator()
{
	if (!StatusIndicator)
	{
		return;
	}

	FLinearColor IndicatorColor;

	if (RobotActor->IsColliding())
	{
		// Red for collision
		IndicatorColor = StatusErrorColor;
	}
	else if (!bROAEnabled)
	{
		// Yellow for disabled
		IndicatorColor = StatusWarningColor;
	}
	else
	{
		// Green for OK
		IndicatorColor = StatusOkColor;
	}

	StatusIndicator->SetBrushColor(IndicatorColor);
}
