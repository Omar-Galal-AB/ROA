// Copyright ROA Development Team. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "ROAComponent.generated.h"

// Forward declarations
class AROARobotActor;

/**
 * Base class for all ROA components
 * 
 * ROA v0.2 uses a component-based architecture where functionality is split into
 * modular ActorComponents that can be attached to AROARobotActor.
 * 
 * Examples: ROS2NodeComponent, ROAPhysicsComponent, ROACameraComponent, etc.
 */
UCLASS(ClassGroup=(ROA), Abstract, BlueprintType, meta=(BlueprintSpawnableComponent))
class ROA_API UROAComponent : public UActorComponent
{
	GENERATED_BODY()

public:	
	UROAComponent();

	/** Component lifecycle */
	virtual void InitializeComponent() override;
	virtual void UninitializeComponent() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/**
	 * Called after component is attached to robot actor
	 * Override this to perform initialization that requires the owning robot
	 */
	UFUNCTION(BlueprintCallable, Category="ROA|Component")
	virtual void OnAttachedToRobot();

	/**
	 * Enable/disable this component
	 */
	UFUNCTION(BlueprintCallable, Category="ROA|Component")
	virtual void SetComponentEnabled(bool bEnabled);

	/**
	 * Check if component is enabled
	 */
	UFUNCTION(BlueprintPure, Category="ROA|Component")
	bool IsComponentEnabled() const { return bComponentEnabled; }

	/**
	 * Get the owning robot actor
	 */
	UFUNCTION(BlueprintPure, Category="ROA|Component")
	AROARobotActor* GetOwningRobot() const { return OwningRobot; }

protected:
	/** Reference to owning robot actor (automatically set on attach) */
	UPROPERTY(BlueprintReadOnly, Category="ROA")
	AROARobotActor* OwningRobot;

	/** Component enabled/disabled state */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="ROA|Component")
	bool bComponentEnabled;

	/** Log prefix for this component type */
	UPROPERTY()
	FString LogPrefix;

	/** Helper function to log messages with component context */
	void LogInfo(const FString& Message) const;
	void LogWarning(const FString& Message) const;
	void LogError(const FString& Message) const;
};
