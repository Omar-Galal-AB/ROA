// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "ROAWidgetBase.h"
#include "Components/Slider.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "ROARobotControlPanel.generated.h"

/**
 * Joint slider data structure
 */
USTRUCT(BlueprintType)
struct FROAJointSliderData
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	int32 JointIndex;

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	FString JointName;

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	float MinValue;

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	float MaxValue;

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	float CurrentValue;

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	USlider* SliderWidget;

	UPROPERTY(BlueprintReadWrite, Category = "ROA")
	UTextBlock* ValueText;

	FROAJointSliderData()
		: JointIndex(0)
		, MinValue(-3.14159f)
		, MaxValue(3.14159f)
		, CurrentValue(0.0f)
		, SliderWidget(nullptr)
		, ValueText(nullptr)
	{}
};

/**
 * Robot Control Panel Widget
 * Provides sliders for each joint and control buttons
 */
UCLASS()
class ROA_API UROARobotControlPanel : public UROAWidgetBase
{
	GENERATED_BODY()

public:
	UROARobotControlPanel(const FObjectInitializer& ObjectInitializer);

	// UROAWidgetBase interface
	virtual bool InitializeWithRobot(AROARobotActor* InRobotActor) override;
	virtual void UpdateWidgetData() override;

protected:
	// UUserWidget interface
	virtual void NativeConstruct() override;

	/**
	 * Create joint sliders dynamically based on robot
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void CreateJointSliders();

	/**
	 * Handle joint slider value changed
	 */
	UFUNCTION()
	void OnJointSliderChanged(float Value, int32 JointIndex);

	/**
	 * Apply current slider values to robot
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void ApplyJointPositions();

	/**
	 * Reset all joints to zero position
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void ResetJoints();

	/**
	 * Emergency stop button clicked
	 */
	UFUNCTION(BlueprintCallable, Category = "ROA")
	void OnEmergencyStopClicked();

	/**
	 * Update slider positions from robot state
	 */
	void UpdateSlidersFromRobot();

public:
	/** Container for joint sliders (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UVerticalBox* JointSlidersContainer;

	/** Apply button (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UButton* ApplyButton;

	/** Reset button (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UButton* ResetButton;

	/** Emergency stop button (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UButton* EmergencyStopButton;

	/** Robot name text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RobotNameText;

	/** Robot type text (bind in blueprint) */
	UPROPERTY(BlueprintReadWrite, meta = (BindWidget))
	UTextBlock* RobotTypeText;

protected:
	/** Joint slider data array */
	UPROPERTY()
	TArray<FROAJointSliderData> JointSliders;

	/** Motion duration for joint movement */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	float MotionDuration;

	/** Auto-update sliders from robot */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "ROA")
	bool bAutoUpdateSliders;
};
