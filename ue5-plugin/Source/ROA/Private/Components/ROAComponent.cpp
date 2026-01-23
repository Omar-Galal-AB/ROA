// Copyright ROA Development Team. All Rights Reserved.

#include "Components/ROAComponent.h"
#include "ROARobotActor.h"
#include "Engine/Engine.h"

UROAComponent::UROAComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	bComponentEnabled = true;
	OwningRobot = nullptr;
	
	// Set default log prefix (will be overridden by derived classes)
	LogPrefix = TEXT("[ROAComponent]");
}

void UROAComponent::InitializeComponent()
{
	Super::InitializeComponent();

	// Get owning robot actor
	OwningRobot = Cast<AROARobotActor>(GetOwner());
	
	if (!OwningRobot)
	{
		LogWarning(TEXT("Component not attached to AROARobotActor!"));
	}

	LogInfo(TEXT("Component initialized"));
}

void UROAComponent::UninitializeComponent()
{
	LogInfo(TEXT("Component uninitialized"));
	
	Super::UninitializeComponent();
}

void UROAComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// Only tick if enabled
	if (!bComponentEnabled)
	{
		return;
	}
}

void UROAComponent::OnAttachedToRobot()
{
	// Base implementation - override in derived classes
	LogInfo(FString::Printf(TEXT("Attached to robot: %s"), 
		OwningRobot ? *OwningRobot->GetName() : TEXT("None")));
}

void UROAComponent::SetComponentEnabled(bool bEnabled)
{
	if (bComponentEnabled != bEnabled)
	{
		bComponentEnabled = bEnabled;
		LogInfo(FString::Printf(TEXT("Component %s"), bEnabled ? TEXT("enabled") : TEXT("disabled")));
	}
}

void UROAComponent::LogInfo(const FString& Message) const
{
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 2.0f, FColor::Green, 
			FString::Printf(TEXT("%s %s"), *LogPrefix, *Message));
	}
	UE_LOG(LogTemp, Log, TEXT("%s %s"), *LogPrefix, *Message);
}

void UROAComponent::LogWarning(const FString& Message) const
{
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 5.0f, FColor::Yellow, 
			FString::Printf(TEXT("%s WARNING: %s"), *LogPrefix, *Message));
	}
	UE_LOG(LogTemp, Warning, TEXT("%s %s"), *LogPrefix, *Message);
}

void UROAComponent::LogError(const FString& Message) const
{
	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.0f, FColor::Red, 
			FString::Printf(TEXT("%s ERROR: %s"), *LogPrefix, *Message));
	}
	UE_LOG(LogTemp, Error, TEXT("%s %s"), *LogPrefix, *Message);
}
