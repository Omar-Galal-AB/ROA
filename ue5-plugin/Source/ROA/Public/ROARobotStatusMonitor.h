// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "ROAWidgetBase.h"
#include "Components/TextBlock.h"
#include "Components/ProgressBar.h"
#include "Components/Border.h"
#include "ROARobotStatusMonitor.generated.h"

/**
 * Robot Status Monitor Widget
 * Displays real-time robot state information
 */
UCLASS()
class ROA_API UROARobotStatusMonitor : public UROAWidgetBase
{
	GENERATED_BODY()

public:
	UROARobotStatusMonitor(const FObjectInitializer& ObjectInitializer);

	// UROAWidgetBase interface
	virtual bool InitializeWithRobot(AROARobotActor* InRobotActor) override;
	virtual void UpdateWidgetData() override;

protected:
	// UUserWidget interface
	virtual void NativeConstruct() override;

	/**
	 * Update position display
	 */
	void UpdatePositionDisplay();

	/**
	 * Update joint positions display
	 */
	void UpdateJointDisplay();

	/**
	 * Update end effector display
	 */
	void UpdateEndEffectorDisplay();

	/**
	 * Update collision status
	 */
	void UpdateCollisionStatus();

	/**
	 * Update status indicator color
	 */
	void UpdateStatusIndicator();

public:
	/** Robot ID text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RobotIdText;

	/** Robot type text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RobotTypeText;

	/** Position X text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* PositionXText;

	/** Position Y text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* PositionYText;

	/** Position Z text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* PositionZText;

	/** Rotation Roll text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RotationRollText;

	/** Rotation Pitch text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RotationPitchText;

	/** Rotation Yaw text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RotationYawText;

	/** Joint positions text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* JointPositionsText;

	/** End effector position text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* EndEffectorPositionText;

	/** Collision status text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* CollisionStatusText;

	/** Collision count text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* CollisionCountText;

	/** Status indicator border (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UBorder* StatusIndicator;

protected:
	/** Status indicator colors */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	FLinearColor StatusOkColor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	FLinearColor StatusWarningColor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	FLinearColor StatusErrorColor;

	/** Decimal places for display */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	int32 DecimalPlaces;
};
