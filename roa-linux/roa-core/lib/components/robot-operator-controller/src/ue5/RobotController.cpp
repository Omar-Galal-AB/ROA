// RobotController.cpp - Implementation of Robot Controller
//
// NOT YET IMPLEMENTED - This is a stub file.
// Full implementation will be done in the implementation phase.

#include "RobotController.h"
#include "JointController.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"
#include "GameFramework/Actor.h"

// =============================================================================
// Initialization
// =============================================================================

void URobotController::Initialize(const FROCRobotConfig& InConfig, AActor* InRobotActor)
{
    Config = InConfig;
    RobotId = Config.RobotId;
    RobotName = Config.RobotName;
    RobotActor = InRobotActor;
    
    // TODO: Create joint controllers
    // CreateJointControllers();
    
    // TODO: Bind physics constraints if actor provided
    // if (RobotActor)
    // {
    //     BindPhysicsConstraints();
    // }
    
    Status = EROCRobotStatus::Ready;
    
    UE_LOG(LogTemp, Log, TEXT("RobotController: Initialized %s with %d joints (NOT IMPLEMENTED)"), 
           *RobotId, Config.Joints.Num());
}

void URobotController::Shutdown()
{
    // TODO: Shutdown all joint controllers
    // for (auto& Pair : JointControllers)
    // {
    //     if (Pair.Value)
    //     {
    //         Pair.Value->Shutdown();
    //     }
    // }
    // JointControllers.Empty();
    
    Status = EROCRobotStatus::Disconnected;
    
    UE_LOG(LogTemp, Log, TEXT("RobotController: Shutdown %s"), *RobotId);
}

void URobotController::SetRobotActor(AActor* InRobotActor)
{
    RobotActor = InRobotActor;
    if (RobotActor)
    {
        // TODO: Rebind physics constraints
        // BindPhysicsConstraints();
    }
}

// =============================================================================
// State Access
// =============================================================================

TArray<FString> URobotController::GetJointNames() const
{
    return JointOrder;
}

// =============================================================================
// Joint Access
// =============================================================================

UJointController* URobotController::GetJointController(const FString& JointName) const
{
    // TODO: Implement lookup
    // return JointControllers.FindRef(JointName);
    return nullptr;
}

FROCJointState URobotController::GetJointState(const FString& JointName) const
{
    UJointController* Controller = GetJointController(JointName);
    if (Controller)
    {
        return Controller->GetState();
    }
    return FROCJointState();
}

TArray<FROCJointState> URobotController::GetAllJointStates() const
{
    TArray<FROCJointState> States;
    // TODO: Implement
    // for (const FString& JointName : JointOrder)
    // {
    //     States.Add(GetJointState(JointName));
    // }
    return States;
}

bool URobotController::SelectJoint(const FString& JointName)
{
    // TODO: Implement joint selection
    // 1. Find joint index
    // 2. Update SelectedJointName and SelectedJointIndex
    
    int32 Index = JointOrder.IndexOfByKey(JointName);
    if (Index != INDEX_NONE)
    {
        SelectedJointName = JointName;
        SelectedJointIndex = Index;
        return true;
    }
    return false;
}

void URobotController::SelectNextJoint()
{
    if (JointOrder.Num() == 0) return;
    
    SelectedJointIndex = (SelectedJointIndex + 1) % JointOrder.Num();
    SelectedJointName = JointOrder[SelectedJointIndex];
}

void URobotController::SelectPreviousJoint()
{
    if (JointOrder.Num() == 0) return;
    
    SelectedJointIndex = (SelectedJointIndex - 1 + JointOrder.Num()) % JointOrder.Num();
    SelectedJointName = JointOrder[SelectedJointIndex];
}

// =============================================================================
// Mode Control
// =============================================================================

void URobotController::SetMode(EROCControlMode NewMode)
{
    if (Mode != NewMode)
    {
        // TODO: Handle mode transition
        // 1. If transitioning to RPM, stop all autonomous movement
        // 2. Update mode
        // 3. Fire mode changed event
        
        Mode = NewMode;
        
        UE_LOG(LogTemp, Log, TEXT("RobotController: %s mode changed to %s"), 
               *RobotId, 
               NewMode == EROCControlMode::RPM ? TEXT("RPM") : TEXT("ADM"));
    }
}

// =============================================================================
// Emergency Stop
// =============================================================================

void URobotController::ActivateEmergencyStop()
{
    // TODO: Implement E-Stop
    // 1. Stop all joints immediately
    // 2. Set E-Stop flag
    // 3. Update status
    
    SafetyStatus.bEStopActive = true;
    Status = EROCRobotStatus::EmergencyStopped;
    
    StopAllJoints();
    
    UE_LOG(LogTemp, Warning, TEXT("RobotController: %s EMERGENCY STOP ACTIVATED"), *RobotId);
}

bool URobotController::ClearEmergencyStop()
{
    // TODO: Implement E-Stop clear
    // 1. Check we're in RPM mode
    // 2. Clear E-Stop flag
    // 3. Update status
    
    if (Mode != EROCControlMode::RPM)
    {
        UE_LOG(LogTemp, Warning, TEXT("RobotController: Cannot clear E-Stop - not in RPM mode"));
        return false;
    }
    
    SafetyStatus.bEStopActive = false;
    Status = EROCRobotStatus::Ready;
    
    UE_LOG(LogTemp, Log, TEXT("RobotController: %s E-Stop cleared"), *RobotId);
    return true;
}

// =============================================================================
// Joint Commands
// =============================================================================

void URobotController::ExecuteApprovedCommand(const FROCJointCommand& Command)
{
    // TODO: Implement command execution
    // 1. Get joint controller
    // 2. Set target position with velocity limit
    
    UJointController* Controller = GetJointController(Command.JointName);
    if (Controller)
    {
        Controller->SetTargetPosition(Command.TargetPosition, Command.VelocityLimit);
    }
}

void URobotController::ExecuteApprovedCommands(const TArray<FROCJointCommand>& Commands)
{
    for (const FROCJointCommand& Command : Commands)
    {
        ExecuteApprovedCommand(Command);
    }
}

void URobotController::StopAllJoints()
{
    // TODO: Implement stop all
    // for (auto& Pair : JointControllers)
    // {
    //     if (Pair.Value)
    //     {
    //         Pair.Value->Stop();
    //     }
    // }
    
    UE_LOG(LogTemp, Log, TEXT("RobotController: %s all joints stopped"), *RobotId);
}

// =============================================================================
// State Updates
// =============================================================================

void URobotController::UpdateSafetyStatus(const FROCSafetyStatus& NewSafetyStatus)
{
    SafetyStatus = NewSafetyStatus;
    
    // Check for E-Stop activation
    if (SafetyStatus.bEStopActive && Status != EROCRobotStatus::EmergencyStopped)
    {
        ActivateEmergencyStop();
    }
}

void URobotController::SetStatus(EROCRobotStatus NewStatus)
{
    if (Status != NewStatus)
    {
        Status = NewStatus;
        // TODO: Fire status changed event
    }
}

// =============================================================================
// Tick
// =============================================================================

void URobotController::Tick(float DeltaTime)
{
    // TODO: Tick all joint controllers
    // for (auto& Pair : JointControllers)
    // {
    //     if (Pair.Value)
    //     {
    //         Pair.Value->Tick(DeltaTime);
    //     }
    // }
    
    // TODO: Update moving status
    // UpdateMovingStatus();
}

// =============================================================================
// Internal Methods
// =============================================================================

void URobotController::CreateJointControllers()
{
    // TODO: Create UJointController for each joint in config
    // for (const FROCJointConfig& JointConfig : Config.Joints)
    // {
    //     UJointController* Controller = NewObject<UJointController>(this);
    //     Controller->Initialize(JointConfig);
    //     JointControllers.Add(JointConfig.JointName, Controller);
    //     JointOrder.Add(JointConfig.JointName);
    // }
    
    // Select first joint by default
    if (JointOrder.Num() > 0)
    {
        SelectedJointName = JointOrder[0];
        SelectedJointIndex = 0;
    }
}

void URobotController::BindPhysicsConstraints()
{
    // TODO: Find and bind physics constraints from actor
    // TArray<UPhysicsConstraintComponent*> Constraints;
    // RobotActor->GetComponents<UPhysicsConstraintComponent>(Constraints);
    // 
    // for (UPhysicsConstraintComponent* Constraint : Constraints)
    // {
    //     FString ConstraintName = Constraint->GetName();
    //     // Match to joint controller
    //     for (auto& Pair : JointControllers)
    //     {
    //         if (Pair.Value && Pair.Value->GetUE5ConstraintName() == ConstraintName)
    //         {
    //             Pair.Value->BindPhysicsConstraint(Constraint);
    //             break;
    //         }
    //     }
    // }
}

void URobotController::UpdateMovingStatus()
{
    bool bAnyMoving = false;
    
    // TODO: Check if any joint is moving
    // for (auto& Pair : JointControllers)
    // {
    //     if (Pair.Value && Pair.Value->IsMoving())
    //     {
    //         bAnyMoving = true;
    //         break;
    //     }
    // }
    
    if (bAnyMoving && Status == EROCRobotStatus::Ready)
    {
        SetStatus(EROCRobotStatus::Moving);
    }
    else if (!bAnyMoving && Status == EROCRobotStatus::Moving)
    {
        SetStatus(EROCRobotStatus::Ready);
    }
}
