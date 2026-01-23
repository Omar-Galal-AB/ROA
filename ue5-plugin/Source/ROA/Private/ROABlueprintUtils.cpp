// Copyright ROA Development Team. All Rights Reserved.
// ROABlueprintUtils.cpp - Implementation of Blueprint component manipulation utilities

#include "ROABlueprintUtils.h"
#include "Engine/SimpleConstructionScript.h"
#include "Engine/SCS_Node.h"
#include "Engine/StaticMesh.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"
#include "Components/StaticMeshComponent.h"

// Logging category for ROA Blueprint Utils
DEFINE_LOG_CATEGORY_STATIC(LogROABlueprintUtils, Log, All);

// ============================================================================
// CONSTRAINT COMPONENT NAME FUNCTIONS
// ============================================================================

bool UROABlueprintUtils::SetConstraintComponentNames(
	UBlueprint* Blueprint,
	const FString& ConstraintComponentName,
	const FName& ComponentName1,
	const FName& ComponentName2)
{
	if (!Blueprint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintComponentNames: Blueprint is null"));
		return false;
	}

#if WITH_EDITOR
	// Find the SCS node for this constraint
	USCS_Node* ConstraintNode = FindSCSNode(Blueprint, ConstraintComponentName);
	if (!ConstraintNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintComponentNames: Could not find constraint '%s'"), 
			*ConstraintComponentName);
		return false;
	}

	// Get the component template
	UPhysicsConstraintComponent* Constraint = Cast<UPhysicsConstraintComponent>(ConstraintNode->ComponentTemplate);
	if (!Constraint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintComponentNames: '%s' is not a PhysicsConstraintComponent"), 
			*ConstraintComponentName);
		return false;
	}

	// CRITICAL: Call Modify() on the constraint for undo/redo support and persistence
	Constraint->Modify();

	// Set the component names
	// FConstrainComponentPropName has a ComponentName member of type FName
	Constraint->ComponentName1.ComponentName = ComponentName1;
	Constraint->ComponentName2.ComponentName = ComponentName2;

	// Mark the Blueprint as structurally modified - THIS IS THE KEY!
	// This tells the Blueprint system that the SCS has changed and needs to be serialized
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);

	UE_LOG(LogROABlueprintUtils, Log, TEXT("SetConstraintComponentNames: Set '%s' -> [%s, %s]"), 
		*ConstraintComponentName, *ComponentName1.ToString(), *ComponentName2.ToString());

	return true;
#else
	return false;
#endif
}

int32 UROABlueprintUtils::SetAllConstraintComponentNames(
	UBlueprint* Blueprint,
	const TMap<FString, FString>& ParentChildMapping)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	// ParentChildMapping format: "ConstraintName" -> "ParentComponent|ChildComponent"
	for (const auto& Pair : ParentChildMapping)
	{
		const FString& ConstraintName = Pair.Key;
		const FString& ParentChild = Pair.Value;

		// Parse "ParentComponent|ChildComponent"
		FString ParentName, ChildName;
		if (ParentChild.Split(TEXT("|"), &ParentName, &ChildName))
		{
			if (SetConstraintComponentNames(Blueprint, ConstraintName, FName(*ParentName), FName(*ChildName)))
			{
				SuccessCount++;
			}
		}
		else
		{
			UE_LOG(LogROABlueprintUtils, Warning, 
				TEXT("SetAllConstraintComponentNames: Invalid format for '%s', expected 'Parent|Child'"), 
				*ConstraintName);
		}
	}

	// Compile once after all changes
	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	return SuccessCount;
#else
	return 0;
#endif
}

// ============================================================================
// CONSTRAINT POSITION FUNCTIONS
// ============================================================================

bool UROABlueprintUtils::SetConstraintPosition(
	UBlueprint* Blueprint,
	const FString& ConstraintComponentName,
	const FVector& Position)
{
	if (!Blueprint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintPosition: Blueprint is null"));
		return false;
	}

#if WITH_EDITOR
	// Find the SCS node for this constraint
	USCS_Node* ConstraintNode = FindSCSNode(Blueprint, ConstraintComponentName);
	if (!ConstraintNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintPosition: Could not find constraint '%s'"), 
			*ConstraintComponentName);
		return false;
	}

	// Get the component template
	UPhysicsConstraintComponent* Constraint = Cast<UPhysicsConstraintComponent>(ConstraintNode->ComponentTemplate);
	if (!Constraint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintPosition: '%s' is not a PhysicsConstraintComponent"), 
			*ConstraintComponentName);
		return false;
	}

	// Modify for undo/redo
	Constraint->Modify();

	// Set the relative location
	Constraint->SetRelativeLocation(Position);

	// Mark modified
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);

	UE_LOG(LogROABlueprintUtils, Log, TEXT("SetConstraintPosition: '%s' -> (%.1f, %.1f, %.1f)"), 
		*ConstraintComponentName, Position.X, Position.Y, Position.Z);

	return true;
#else
	return false;
#endif
}

int32 UROABlueprintUtils::SetAllConstraintPositions(
	UBlueprint* Blueprint,
	const TMap<FString, FString>& PositionMapping)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	// PositionMapping format: "ConstraintName" -> "X|Y|Z"
	for (const auto& Pair : PositionMapping)
	{
		const FString& ConstraintName = Pair.Key;
		const FString& PosStr = Pair.Value;

		// Parse "X|Y|Z"
		TArray<FString> Parts;
		PosStr.ParseIntoArray(Parts, TEXT("|"));
		
		if (Parts.Num() == 3)
		{
			FVector Position(
				FCString::Atof(*Parts[0]),
				FCString::Atof(*Parts[1]),
				FCString::Atof(*Parts[2])
			);
			
			if (SetConstraintPosition(Blueprint, ConstraintName, Position))
			{
				SuccessCount++;
			}
		}
		else
		{
			UE_LOG(LogROABlueprintUtils, Warning, 
				TEXT("SetAllConstraintPositions: Invalid format for '%s', expected 'X|Y|Z'"), 
				*ConstraintName);
		}
	}

	// Compile once after all changes
	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	return SuccessCount;
#else
	return 0;
#endif
}

// ============================================================================
// MESH-BASED CONSTRAINT POSITIONING (for USD-baked meshes)
// ============================================================================

FVector UROABlueprintUtils::GetMeshComponentOrigin(UBlueprint* Blueprint, const FString& MeshComponentName)
{
	if (!Blueprint)
	{
		return FVector::ZeroVector;
	}

#if WITH_EDITOR
	// Find the mesh component
	USCS_Node* MeshNode = FindSCSNode(Blueprint, MeshComponentName);
	if (!MeshNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("GetMeshComponentOrigin: Could not find '%s'"), *MeshComponentName);
		return FVector::ZeroVector;
	}

	UStaticMeshComponent* MeshComp = Cast<UStaticMeshComponent>(MeshNode->ComponentTemplate);
	if (!MeshComp)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("GetMeshComponentOrigin: '%s' is not a StaticMeshComponent"), *MeshComponentName);
		return FVector::ZeroVector;
	}

	// Get the static mesh asset
	UStaticMesh* StaticMesh = MeshComp->GetStaticMesh();
	if (!StaticMesh)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("GetMeshComponentOrigin: '%s' has no static mesh"), *MeshComponentName);
		return FVector::ZeroVector;
	}

	// Get bounds from the static mesh
	FBoxSphereBounds Bounds = StaticMesh->GetBounds();
	FVector MeshOrigin = Bounds.Origin;
	
	UE_LOG(LogROABlueprintUtils, Log, TEXT("GetMeshComponentOrigin: '%s' -> (%.1f, %.1f, %.1f)"),
		*MeshComponentName, MeshOrigin.X, MeshOrigin.Y, MeshOrigin.Z);

	return MeshOrigin;
#else
	return FVector::ZeroVector;
#endif
}

FVector UROABlueprintUtils::GetMeshAttachmentPoint(UBlueprint* Blueprint, const FString& ParentMeshName, const FString& ChildMeshName)
{
	if (!Blueprint)
	{
		return FVector::ZeroVector;
	}

#if WITH_EDITOR
	// Get parent mesh bounds
	USCS_Node* ParentNode = FindSCSNode(Blueprint, ParentMeshName);
	USCS_Node* ChildNode = FindSCSNode(Blueprint, ChildMeshName);
	
	if (!ParentNode || !ChildNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("GetMeshAttachmentPoint: Could not find meshes '%s' or '%s'"), 
			*ParentMeshName, *ChildMeshName);
		return FVector::ZeroVector;
	}

	UStaticMeshComponent* ParentComp = Cast<UStaticMeshComponent>(ParentNode->ComponentTemplate);
	UStaticMeshComponent* ChildComp = Cast<UStaticMeshComponent>(ChildNode->ComponentTemplate);
	
	if (!ParentComp || !ChildComp)
	{
		// Fallback to child mesh center if parent isn't a mesh
		if (ChildComp && ChildComp->GetStaticMesh())
		{
			return ChildComp->GetStaticMesh()->GetBounds().Origin;
		}
		return FVector::ZeroVector;
	}

	UStaticMesh* ParentMesh = ParentComp->GetStaticMesh();
	UStaticMesh* ChildMesh = ChildComp->GetStaticMesh();
	
	if (!ParentMesh || !ChildMesh)
	{
		return FVector::ZeroVector;
	}

	FBoxSphereBounds ParentBounds = ParentMesh->GetBounds();
	FBoxSphereBounds ChildBounds = ChildMesh->GetBounds();
	
	FVector ParentCenter = ParentBounds.Origin;
	FVector ChildCenter = ChildBounds.Origin;
	FVector ParentExtent = ParentBounds.BoxExtent;
	FVector ChildExtent = ChildBounds.BoxExtent;
	
	// Find the INTERFACE point between parent and child meshes
	// Strategy: Find which axis has the largest separation, then find the midpoint
	// between the closest faces on that axis
	
	float DX = ChildCenter.X - ParentCenter.X;
	float DY = ChildCenter.Y - ParentCenter.Y;
	float DZ = ChildCenter.Z - ParentCenter.Z;
	
	float AbsDX = FMath::Abs(DX);
	float AbsDY = FMath::Abs(DY);
	float AbsDZ = FMath::Abs(DZ);
	
	FVector JointPos;
	
	if (AbsDX >= AbsDY && AbsDX >= AbsDZ)
	{
		// Connected along X axis
		float ParentFaceX, ChildFaceX;
		if (DX > 0)
		{
			ParentFaceX = ParentCenter.X + ParentExtent.X;
			ChildFaceX = ChildCenter.X - ChildExtent.X;
		}
		else
		{
			ParentFaceX = ParentCenter.X - ParentExtent.X;
			ChildFaceX = ChildCenter.X + ChildExtent.X;
		}
		JointPos.X = (ParentFaceX + ChildFaceX) / 2.0f;
		JointPos.Y = (ParentCenter.Y + ChildCenter.Y) / 2.0f;
		JointPos.Z = (ParentCenter.Z + ChildCenter.Z) / 2.0f;
	}
	else if (AbsDY >= AbsDX && AbsDY >= AbsDZ)
	{
		// Connected along Y axis
		float ParentFaceY, ChildFaceY;
		if (DY > 0)
		{
			ParentFaceY = ParentCenter.Y + ParentExtent.Y;
			ChildFaceY = ChildCenter.Y - ChildExtent.Y;
		}
		else
		{
			ParentFaceY = ParentCenter.Y - ParentExtent.Y;
			ChildFaceY = ChildCenter.Y + ChildExtent.Y;
		}
		JointPos.X = (ParentCenter.X + ChildCenter.X) / 2.0f;
		JointPos.Y = (ParentFaceY + ChildFaceY) / 2.0f;
		JointPos.Z = (ParentCenter.Z + ChildCenter.Z) / 2.0f;
	}
	else
	{
		// Connected along Z axis
		float ParentFaceZ, ChildFaceZ;
		if (DZ > 0)
		{
			ParentFaceZ = ParentCenter.Z + ParentExtent.Z;
			ChildFaceZ = ChildCenter.Z - ChildExtent.Z;
		}
		else
		{
			ParentFaceZ = ParentCenter.Z - ParentExtent.Z;
			ChildFaceZ = ChildCenter.Z + ChildExtent.Z;
		}
		JointPos.X = (ParentCenter.X + ChildCenter.X) / 2.0f;
		JointPos.Y = (ParentCenter.Y + ChildCenter.Y) / 2.0f;
		JointPos.Z = (ParentFaceZ + ChildFaceZ) / 2.0f;
	}
	
	UE_LOG(LogROABlueprintUtils, Log, TEXT("GetMeshAttachmentPoint: '%s'->'%s' = (%.1f, %.1f, %.1f) [midpoint between faces]"),
		*ParentMeshName, *ChildMeshName, JointPos.X, JointPos.Y, JointPos.Z);

	return JointPos;
#else
	return FVector::ZeroVector;
#endif
}

int32 UROABlueprintUtils::AutoPositionConstraintsFromMesh(
	UBlueprint* Blueprint,
	const TMap<FString, FString>& ConstraintParentChildMapping)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	// ConstraintParentChildMapping format: "ConstraintName" -> "ParentMesh|ChildMesh"
	for (const auto& Pair : ConstraintParentChildMapping)
	{
		const FString& ConstraintName = Pair.Key;
		const FString& ParentChild = Pair.Value;

		// Parse "ParentMesh|ChildMesh"
		FString ParentMeshName, ChildMeshName;
		if (!ParentChild.Split(TEXT("|"), &ParentMeshName, &ChildMeshName))
		{
			UE_LOG(LogROABlueprintUtils, Warning, 
				TEXT("AutoPositionConstraint: Invalid format for '%s', expected 'Parent|Child'"), 
				*ConstraintName);
			continue;
		}

		// Get the attachment point - where child mesh connects to parent mesh
		// This finds the closest point on the child's bounding box to the parent's center
		FVector AttachmentPoint = GetMeshAttachmentPoint(Blueprint, ParentMeshName, ChildMeshName);
		
		if (SetConstraintPosition(Blueprint, ConstraintName, AttachmentPoint))
		{
			UE_LOG(LogROABlueprintUtils, Log, TEXT("AutoPositionConstraint: '%s' at attachment point (%.1f, %.1f, %.1f)"),
				*ConstraintName, AttachmentPoint.X, AttachmentPoint.Y, AttachmentPoint.Z);
			SuccessCount++;
		}
	}

	// Compile once after all changes
	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	return SuccessCount;
#else
	return 0;
#endif
}

// ============================================================================
// BLUEPRINT COMPONENT ACCESS FUNCTIONS
// ============================================================================

TArray<UPhysicsConstraintComponent*> UROABlueprintUtils::GetBlueprintConstraints(UBlueprint* Blueprint)
{
	TArray<UPhysicsConstraintComponent*> Constraints;

	if (!Blueprint)
	{
		return Constraints;
	}

#if WITH_EDITOR
	USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
	if (!SCS)
	{
		return Constraints;
	}

	const TArray<USCS_Node*>& AllNodes = SCS->GetAllNodes();
	for (USCS_Node* Node : AllNodes)
	{
		if (Node && Node->ComponentTemplate)
		{
			if (UPhysicsConstraintComponent* Constraint = Cast<UPhysicsConstraintComponent>(Node->ComponentTemplate))
			{
				Constraints.Add(Constraint);
			}
		}
	}
#endif

	return Constraints;
}

TArray<FString> UROABlueprintUtils::GetBlueprintComponentNames(UBlueprint* Blueprint)
{
	TArray<FString> Names;

	if (!Blueprint)
	{
		return Names;
	}

#if WITH_EDITOR
	USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
	if (!SCS)
	{
		return Names;
	}

	const TArray<USCS_Node*>& AllNodes = SCS->GetAllNodes();
	for (USCS_Node* Node : AllNodes)
	{
		if (Node && Node->ComponentTemplate)
		{
			Names.Add(Node->GetVariableName().ToString());
		}
	}
#endif

	return Names;
}

bool UROABlueprintUtils::CompileAndMarkModified(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		return false;
	}

#if WITH_EDITOR
	// Mark as modified
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);

	// Compile
	FKismetEditorUtilities::CompileBlueprint(Blueprint);

	UE_LOG(LogROABlueprintUtils, Log, TEXT("CompileAndMarkModified: Blueprint '%s' compiled"), 
		*Blueprint->GetName());

	return true;
#else
	return false;
#endif
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

UActorComponent* UROABlueprintUtils::FindBlueprintComponent(UBlueprint* Blueprint, const FString& ComponentName)
{
	USCS_Node* Node = FindSCSNode(Blueprint, ComponentName);
	if (Node && Node->ComponentTemplate)
	{
		return Node->ComponentTemplate;
	}
	return nullptr;
}

USCS_Node* UROABlueprintUtils::FindSCSNode(UBlueprint* Blueprint, const FString& ComponentName)
{
	if (!Blueprint)
	{
		return nullptr;
	}

#if WITH_EDITOR
	USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
	if (!SCS)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("FindSCSNode: Blueprint has no SimpleConstructionScript"));
		return nullptr;
	}

	const TArray<USCS_Node*>& AllNodes = SCS->GetAllNodes();
	for (USCS_Node* Node : AllNodes)
	{
		if (Node)
		{
			// Check both variable name and component template name
			FString VarName = Node->GetVariableName().ToString();
			FString TemplateName = Node->ComponentTemplate ? Node->ComponentTemplate->GetName() : TEXT("");

			if (VarName.Contains(ComponentName) || TemplateName.Contains(ComponentName))
			{
				return Node;
			}
		}
	}
#endif

	return nullptr;
}

// ============================================================================
// PHYSICS CONFIGURATION FUNCTIONS (v7.0)
// ============================================================================

bool UROABlueprintUtils::ConfigureConstraintPhysics(
	UBlueprint* Blueprint,
	const FString& ConstraintName,
	const FString& JointType,
	float AxisX,
	float AxisY,
	float AxisZ,
	float LimitLower,
	float LimitUpper,
	float MaxVelocity,
	float MaxEffort)
{
	if (!Blueprint)
	{
		return false;
	}

#if WITH_EDITOR
	USCS_Node* ConstraintNode = FindSCSNode(Blueprint, ConstraintName);
	if (!ConstraintNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("ConfigureConstraintPhysics: Could not find '%s'"), *ConstraintName);
		return false;
	}

	UPhysicsConstraintComponent* Constraint = Cast<UPhysicsConstraintComponent>(ConstraintNode->ComponentTemplate);
	if (!Constraint)
	{
		return false;
	}

	Constraint->Modify();

	// Get constraint instance for modification
	FConstraintInstance& CI = Constraint->ConstraintInstance;

	// Disable collision between constrained bodies
	Constraint->SetDisableCollision(true);

	if (JointType == TEXT("fixed"))
	{
		// Lock all motion for fixed joints
		CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetAngularSwing1Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularSwing2Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularTwistMotion(EAngularConstraintMotion::ACM_Locked);
		
		UE_LOG(LogROABlueprintUtils, Log, TEXT("ConfigureConstraintPhysics: '%s' configured as FIXED"), *ConstraintName);
	}
	else if (JointType == TEXT("revolute") || JointType == TEXT("continuous"))
	{
		// Lock linear motion
		CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);

		// Determine motion type (limited for revolute, free for continuous)
		EAngularConstraintMotion MotionType = (JointType == TEXT("revolute")) 
			? EAngularConstraintMotion::ACM_Limited 
			: EAngularConstraintMotion::ACM_Free;

		// Set angular motion based on axis
		// Default: lock all, then free the rotation axis
		CI.SetAngularSwing1Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularSwing2Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularTwistMotion(EAngularConstraintMotion::ACM_Locked);

		// Determine which axis to free based on largest axis component
		// Z-axis is most common for robot joints
		if (FMath::Abs(AxisZ) >= FMath::Abs(AxisX) && FMath::Abs(AxisZ) >= FMath::Abs(AxisY))
		{
			// Z-axis rotation -> Twist in UE5
			CI.SetAngularTwistMotion(MotionType);
			if (JointType == TEXT("revolute"))
			{
				float LimitDeg = FMath::RadiansToDegrees(FMath::Max(FMath::Abs(LimitLower), FMath::Abs(LimitUpper)));
				LimitDeg = FMath::Clamp(LimitDeg, 0.0f, 180.0f);
				CI.SetAngularTwistLimit(EAngularConstraintMotion::ACM_Limited, LimitDeg);
			}
		}
		else if (FMath::Abs(AxisY) >= FMath::Abs(AxisX))
		{
			// Y-axis rotation -> Swing1
			CI.SetAngularSwing1Motion(MotionType);
			if (JointType == TEXT("revolute"))
			{
				float LimitDeg = FMath::RadiansToDegrees(FMath::Max(FMath::Abs(LimitLower), FMath::Abs(LimitUpper)));
				LimitDeg = FMath::Clamp(LimitDeg, 0.0f, 180.0f);
				CI.SetAngularSwing1Limit(EAngularConstraintMotion::ACM_Limited, LimitDeg);
			}
		}
		else
		{
			// X-axis rotation -> Swing2
			CI.SetAngularSwing2Motion(MotionType);
			if (JointType == TEXT("revolute"))
			{
				float LimitDeg = FMath::RadiansToDegrees(FMath::Max(FMath::Abs(LimitLower), FMath::Abs(LimitUpper)));
				LimitDeg = FMath::Clamp(LimitDeg, 0.0f, 180.0f);
				CI.SetAngularSwing2Limit(EAngularConstraintMotion::ACM_Limited, LimitDeg);
			}
		}

		// Enable angular drive for velocity control
		CI.SetAngularDriveMode(EAngularDriveMode::TwistAndSwing);
		CI.SetOrientationDriveTwistAndSwing(true, true);
		CI.SetAngularVelocityDriveTwistAndSwing(true, true);
		
		// v7.17: Strong drive parameters for robot stability
		// Stiffness = HIGH to hold position, Damping = moderate to prevent oscillation
		float Stiffness = 100000.0f;
		float Damping = 10000.0f;
		float MaxForce = 1000000.0f;
		
		if (MaxEffort > 0)
		{
			Stiffness = FMath::Max(Stiffness, MaxEffort * 1000.0f);
			Damping = FMath::Max(Damping, MaxEffort * 100.0f);
			MaxForce = FMath::Max(MaxForce, MaxEffort * 10000.0f);
		}
		
		CI.SetAngularDriveParams(Stiffness, Damping, MaxForce);
		// Note: In UE5.6+, AngularOrientationTarget and AngularVelocityTarget are set via methods on the component, not on FConstraintInstance
		// These will be initialized to zero by default in the constraint instance

		UE_LOG(LogROABlueprintUtils, Log, TEXT("ConfigureConstraintPhysics: '%s' configured as %s (limit=%.1f°, stiffness=%.0f)"), 
			*ConstraintName, *JointType.ToUpper(),
			FMath::RadiansToDegrees(FMath::Max(FMath::Abs(LimitLower), FMath::Abs(LimitUpper))),
			Stiffness);
	}
	else if (JointType == TEXT("prismatic"))
	{
		// Lock angular motion
		CI.SetAngularSwing1Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularSwing2Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularTwistMotion(EAngularConstraintMotion::ACM_Locked);

		// Set linear motion based on axis
		if (FMath::Abs(AxisX) >= FMath::Abs(AxisY) && FMath::Abs(AxisX) >= FMath::Abs(AxisZ))
		{
			CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Limited);
			CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
			CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
		}
		else if (FMath::Abs(AxisY) >= FMath::Abs(AxisZ))
		{
			CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
			CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Limited);
			CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
		}
		else
		{
			CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
			CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
			CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Limited);
		}

		UE_LOG(LogROABlueprintUtils, Log, TEXT("ConfigureConstraintPhysics: '%s' configured as PRISMATIC"), *ConstraintName);
	}

	// ========== SET CONSTRAINT ROTATION FROM URDF AXIS ==========
	// v7.11: Use the URDF axis to set BOTH the component rotation AND the constraint frame.
	// The axis vector tells us exactly which direction the joint rotates around.
	// 
	// UE5 PhysicsConstraint: Default twist axis is X (1,0,0)
	// We need to rotate the constraint so its twist axis aligns with the URDF axis.
	// 
	// For standard robot joints:
	// - Axis [0,0,1] (Z): vertical spinning joint (e.g., shoulder_pan) → Pitch 90°
	// - Axis [0,1,0] (Y): horizontal bending joint (e.g., elbow) → Yaw 90°  
	// - Axis [1,0,0] (X): already aligned with default → no rotation needed
	// - Axis [0,-1,0] (-Y): same as Y but flipped → Yaw -90°
	
	FVector URDFAxis(AxisX, AxisY, AxisZ);
	FRotator ConstraintRotation = FRotator::ZeroRotator;
	FString RotationSource = TEXT("default");
	
	// Check if we have a valid axis
	if (URDFAxis.SizeSquared() > 0.01f)
	{
		URDFAxis.Normalize();
		
		// Find dominant axis component
		float AbsX = FMath::Abs(URDFAxis.X);
		float AbsY = FMath::Abs(URDFAxis.Y);
		float AbsZ = FMath::Abs(URDFAxis.Z);
		
		UE_LOG(LogROABlueprintUtils, Log, TEXT("ConfigureConstraintPhysics: '%s' URDF_axis=(%.2f, %.2f, %.2f)"),
			*ConstraintName, URDFAxis.X, URDFAxis.Y, URDFAxis.Z);
		
		if (AbsZ >= AbsX && AbsZ >= AbsY)
		{
			// Z-dominant axis: joint rotates around Z (like shoulder_pan)
			// Default twist is X, need to rotate to Z: Pitch +90° (rotate forward)
			ConstraintRotation = FRotator(90.0f, 0.0f, 0.0f);
			RotationSource = FString::Printf(TEXT("URDF Z-axis (%.2f) -> Pitch 90"), URDFAxis.Z);
		}
		else if (AbsY >= AbsX)
		{
			// Y-dominant axis: joint rotates around Y (like elbow, shoulder_lift)
			// Default twist is X, need to rotate to Y: Yaw +90° or -90° based on sign
			float YawAngle = (URDFAxis.Y >= 0) ? 90.0f : -90.0f;
			ConstraintRotation = FRotator(0.0f, YawAngle, 0.0f);
			RotationSource = FString::Printf(TEXT("URDF Y-axis (%.2f) -> Yaw %.0f"), URDFAxis.Y, YawAngle);
		}
		else
		{
			// X-dominant axis: joint rotates around X (rare, but possible)
			// Default twist is already X, no rotation needed - or use Roll for -X
			if (URDFAxis.X < 0)
			{
				ConstraintRotation = FRotator(0.0f, 0.0f, 180.0f);
				RotationSource = FString::Printf(TEXT("URDF -X-axis (%.2f) -> Roll 180"), URDFAxis.X);
			}
			else
			{
				ConstraintRotation = FRotator::ZeroRotator;
				RotationSource = FString::Printf(TEXT("URDF X-axis (%.2f) -> no rotation"), URDFAxis.X);
			}
		}
	}
	else
	{
		// No valid axis provided - this is a FIXED joint or error
		RotationSource = TEXT("no URDF axis (fixed joint?)");
	}
	
	// v7.14: Apply rotation by DIRECTLY setting internal properties that serialize to Blueprint.
	// 
	// The problem with previous versions:
	// - SetRelativeRotation() doesn't persist on Blueprint component templates
	// - SetRefOrientation() is for runtime active constraints, not editor templates
	// - PriAxis/SecAxis are overwritten during constraint initialization
	//
	// Solution: Set the AngularRotationOffset which IS serialized and applied at runtime.
	// This is the proper way to specify constraint frame orientation in Blueprint assets.
	
	Constraint->Modify();
	
	// Method 1: Set AngularRotationOffset on the ConstraintInstance
	// This offset is applied to Frame2 relative to Frame1 during constraint setup
	// For our case, we want the constraint to operate around a specific axis
	CI.AngularRotationOffset = ConstraintRotation;
	
	// Method 2: Also directly set the frame axes (these get serialized as part of ConstraintInstance)
	FQuat FrameQuat = ConstraintRotation.Quaternion();
	FVector PrimaryAxis = FrameQuat.RotateVector(FVector(1, 0, 0));   // Twist axis
	FVector SecondaryAxis = FrameQuat.RotateVector(FVector(0, 1, 0)); // Swing1 axis
	
	CI.PriAxis1 = PrimaryAxis;
	CI.SecAxis1 = SecondaryAxis;
	CI.PriAxis2 = PrimaryAxis;
	CI.SecAxis2 = SecondaryAxis;
	
	// Method 3: Set the component's relative rotation
	// Force the internal cache to be set properly
	Constraint->SetRelativeRotation(ConstraintRotation);
	
	// Also set via the RelativeRotationCache if available
	FTransform NewTransform = Constraint->GetRelativeTransform();
	NewTransform.SetRotation(ConstraintRotation.Quaternion());
	Constraint->SetRelativeTransform(NewTransform);
	
	// Trigger property change notification so the editor knows to update
	Constraint->PostEditChange();
	
	UE_LOG(LogROABlueprintUtils, Log, TEXT("ConfigureConstraintPhysics: '%s' rotation=(P:%.1f, Y:%.1f, R:%.1f) TwistAxis=(%.2f,%.2f,%.2f) AngOffset=(P:%.1f,Y:%.1f,R:%.1f) source=%s"),
		*ConstraintName, ConstraintRotation.Pitch, ConstraintRotation.Yaw, ConstraintRotation.Roll,
		PrimaryAxis.X, PrimaryAxis.Y, PrimaryAxis.Z,
		CI.AngularRotationOffset.Pitch, CI.AngularRotationOffset.Yaw, CI.AngularRotationOffset.Roll,
		*RotationSource);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	return true;
#else
	return false;
#endif
}

int32 UROABlueprintUtils::ConfigureAllConstraintPhysics(
	UBlueprint* Blueprint,
	const TMap<FString, FString>& ConstraintConfigMapping)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	// Format: "ConstraintName" -> "JointType|AxisX,AxisY,AxisZ|Lower,Upper|Velocity,Effort"
	for (const auto& Pair : ConstraintConfigMapping)
	{
		const FString& ConstraintName = Pair.Key;
		const FString& Config = Pair.Value;

		// Parse config string
		TArray<FString> Parts;
		Config.ParseIntoArray(Parts, TEXT("|"));

		if (Parts.Num() >= 4)
		{
			FString JointType = Parts[0];

			// Parse axis (X,Y,Z)
			TArray<FString> AxisParts;
			Parts[1].ParseIntoArray(AxisParts, TEXT(","));
			float AxisX = AxisParts.Num() > 0 ? FCString::Atof(*AxisParts[0]) : 0.0f;
			float AxisY = AxisParts.Num() > 1 ? FCString::Atof(*AxisParts[1]) : 0.0f;
			float AxisZ = AxisParts.Num() > 2 ? FCString::Atof(*AxisParts[2]) : 1.0f;

			// Parse limits (Lower,Upper)
			TArray<FString> LimitParts;
			Parts[2].ParseIntoArray(LimitParts, TEXT(","));
			float LimitLower = LimitParts.Num() > 0 ? FCString::Atof(*LimitParts[0]) : -3.14159f;
			float LimitUpper = LimitParts.Num() > 1 ? FCString::Atof(*LimitParts[1]) : 3.14159f;

			// Parse velocity and effort (Velocity,Effort)
			TArray<FString> DriveParts;
			Parts[3].ParseIntoArray(DriveParts, TEXT(","));
			float MaxVelocity = DriveParts.Num() > 0 ? FCString::Atof(*DriveParts[0]) : 2.0f;
			float MaxEffort = DriveParts.Num() > 1 ? FCString::Atof(*DriveParts[1]) : 100.0f;

			if (ConfigureConstraintPhysics(Blueprint, ConstraintName, JointType, 
				AxisX, AxisY, AxisZ, LimitLower, LimitUpper, MaxVelocity, MaxEffort))
			{
				SuccessCount++;
			}
		}
		else
		{
			UE_LOG(LogROABlueprintUtils, Warning, TEXT("ConfigureAllConstraintPhysics: Invalid format for '%s'"), *ConstraintName);
		}
	}

	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	return SuccessCount;
#else
	return 0;
#endif
}

bool UROABlueprintUtils::EnableMeshPhysics(
	UBlueprint* Blueprint,
	const FString& MeshName,
	bool bEnablePhysics)
{
	if (!Blueprint)
	{
		return false;
	}

#if WITH_EDITOR
	USCS_Node* MeshNode = FindSCSNode(Blueprint, MeshName);
	if (!MeshNode)
	{
		return false;
	}

	UStaticMeshComponent* MeshComp = Cast<UStaticMeshComponent>(MeshNode->ComponentTemplate);
	if (!MeshComp)
	{
		return false;
	}

	MeshComp->Modify();

	// Set physics simulation
	MeshComp->SetSimulatePhysics(bEnablePhysics);
	
	if (bEnablePhysics)
	{
		// Enable collision for physics
		MeshComp->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		MeshComp->SetCollisionObjectType(ECollisionChannel::ECC_PhysicsBody);
		MeshComp->SetCollisionResponseToAllChannels(ECollisionResponse::ECR_Block);
	}

	// Ensure mobility is Movable for physics
	MeshComp->SetMobility(EComponentMobility::Movable);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);

	UE_LOG(LogROABlueprintUtils, Log, TEXT("EnableMeshPhysics: '%s' physics %s"), 
		*MeshName, bEnablePhysics ? TEXT("ENABLED") : TEXT("DISABLED"));

	return true;
#else
	return false;
#endif
}

int32 UROABlueprintUtils::EnableAllMeshPhysics(
	UBlueprint* Blueprint,
	const TArray<FString>& BaseLinkNames)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
	if (!SCS)
	{
		return 0;
	}

	const TArray<USCS_Node*>& AllNodes = SCS->GetAllNodes();
	for (USCS_Node* Node : AllNodes)
	{
		if (!Node || !Node->ComponentTemplate)
		{
			continue;
		}

		UStaticMeshComponent* MeshComp = Cast<UStaticMeshComponent>(Node->ComponentTemplate);
		if (!MeshComp)
		{
			continue;
		}

		FString MeshName = Node->GetVariableName().ToString();

		// Check if this is a base link (should NOT have physics)
		bool bIsBase = false;
		for (const FString& BaseName : BaseLinkNames)
		{
			if (MeshName.Contains(BaseName))
			{
				bIsBase = true;
				break;
			}
		}

		// Enable physics on non-base links
		if (EnableMeshPhysics(Blueprint, MeshName, !bIsBase))
		{
			SuccessCount++;
		}
	}

	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	return SuccessCount;
#else
	return 0;
#endif
}

// ============================================================================
// CONSTRAINT ROTATION FUNCTIONS (v7.2)
// ============================================================================

bool UROABlueprintUtils::SetConstraintRotationFromGeometry(
	UBlueprint* Blueprint,
	const FString& ConstraintName,
	const FString& ParentMeshName,
	const FString& ChildMeshName)
{
	if (!Blueprint)
	{
		return false;
	}

#if WITH_EDITOR
	// Find the constraint
	USCS_Node* ConstraintNode = FindSCSNode(Blueprint, ConstraintName);
	if (!ConstraintNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintRotationFromGeometry: Constraint '%s' not found"), *ConstraintName);
		return false;
	}

	UPhysicsConstraintComponent* Constraint = Cast<UPhysicsConstraintComponent>(ConstraintNode->ComponentTemplate);
	if (!Constraint)
	{
		return false;
	}

	// Find parent and child meshes
	USCS_Node* ParentNode = FindSCSNode(Blueprint, ParentMeshName);
	USCS_Node* ChildNode = FindSCSNode(Blueprint, ChildMeshName);
	
	if (!ParentNode || !ChildNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintRotationFromGeometry: Parent '%s' or Child '%s' not found"), 
			*ParentMeshName, *ChildMeshName);
		return false;
	}

	UStaticMeshComponent* ParentMesh = Cast<UStaticMeshComponent>(ParentNode->ComponentTemplate);
	UStaticMeshComponent* ChildMesh = Cast<UStaticMeshComponent>(ChildNode->ComponentTemplate);
	
	if (!ParentMesh || !ChildMesh)
	{
		return false;
	}

	// Get mesh bounds
	UStaticMesh* ParentStaticMesh = ParentMesh->GetStaticMesh();
	UStaticMesh* ChildStaticMesh = ChildMesh->GetStaticMesh();
	
	if (!ParentStaticMesh || !ChildStaticMesh)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintRotationFromGeometry: No static mesh on components"));
		return false;
	}

	// Get child mesh center (where the mesh geometry is located)
	FBoxSphereBounds ChildBounds = ChildStaticMesh->GetBounds();
	FVector ChildCenter = ChildBounds.Origin;

	// Get the constraint's current position (the joint position)
	FVector JointPos = Constraint->GetRelativeLocation();

	// ========== EXPANSION DIRECTION ANALYSIS ==========
	// Compute direction from joint position to child mesh center
	// This tells us which way the child part extends from the joint
	float ExpX = ChildCenter.X - JointPos.X;
	float ExpY = ChildCenter.Y - JointPos.Y;
	float ExpZ = ChildCenter.Z - JointPos.Z;

	float AbsX = FMath::Abs(ExpX);
	float AbsY = FMath::Abs(ExpY);
	float AbsZ = FMath::Abs(ExpZ);

	// Determine dominant expansion axis AND direction
	int32 ExpansionAxis = 2; // Default Z
	FString ExpansionLabel = TEXT("Z+");
	
	if (AbsX >= AbsY && AbsX >= AbsZ)
	{
		ExpansionAxis = 0;
		ExpansionLabel = ExpX >= 0 ? TEXT("X+") : TEXT("X-");
	}
	else if (AbsY >= AbsX && AbsY >= AbsZ)
	{
		ExpansionAxis = 1;
		ExpansionLabel = ExpY >= 0 ? TEXT("Y+") : TEXT("Y-");
	}
	else
	{
		ExpansionAxis = 2;
		ExpansionLabel = ExpZ >= 0 ? TEXT("Z+") : TEXT("Z-");
	}

	// ========== COMPUTE CONSTRAINT ROTATION ==========
	// The constraint's twist axis (its local X) must be PERPENDICULAR to the expansion direction!
	// 
	// Key insight: The expansion direction is where the child PART goes, but the joint
	// ROTATES around an axis perpendicular to that. Think of it like a hinge:
	// - The door (child part) swings outward (expansion direction)
	// - But the hinge PIN (rotation axis) is perpendicular to that swing
	//
	// For robot arms:
	// - If part expands along X (forward), rotation is typically around Y (left-right axis)
	// - If part expands along Y (sideways), rotation is typically around Z (vertical) or X
	// - If part expands along Z (up/down), rotation is typically around Z (vertical spin)
	//
	// The constraint's twist axis should align with the rotation axis, not expansion!
	FRotator ConstraintRotation;

	if (ExpansionAxis == 0)  // X dominant - part extends forward/backward
	{
		// Part extends along X → rotation is around Y (perpendicular, horizontal)
		// Constraint twist axis (X) should point along world Y
		if (ExpY >= 0)
		{
			// Child also tends toward +Y → rotation axis is +Y → Yaw 90°
			ConstraintRotation = FRotator(0.0f, 90.0f, 0.0f);
		}
		else
		{
			// Child tends toward -Y → rotation axis is -Y → Yaw -90°
			ConstraintRotation = FRotator(0.0f, -90.0f, 0.0f);
		}
	}
	else if (ExpansionAxis == 1)  // Y dominant - part extends sideways
	{
		// Part extends along Y → rotation is around X or Z
		// For most wrist joints, this means rotation around the local Z
		if (FMath::Abs(ExpZ) >= FMath::Abs(ExpX))
		{
			// Z has secondary influence → rotation around Z
			if (ExpZ >= 0)
			{
				ConstraintRotation = FRotator(90.0f, 0.0f, 0.0f);  // Pitch 90° → twist along Z
			}
			else
			{
				ConstraintRotation = FRotator(-90.0f, 0.0f, 0.0f);  // Pitch -90° → twist along -Z
			}
		}
		else
		{
			// X has secondary influence → rotation around X
			if (ExpX >= 0)
			{
				ConstraintRotation = FRotator(0.0f, 0.0f, 0.0f);  // No rotation → twist along X
			}
			else
			{
				ConstraintRotation = FRotator(0.0f, 180.0f, 0.0f);  // Yaw 180° → twist along -X
			}
		}
	}
	else  // Z dominant - part extends vertically
	{
		// Part extends along Z → rotation is around Z (like shoulder_pan spinning)
		// Constraint twist axis should point along Z
		if (ExpZ >= 0)
		{
			ConstraintRotation = FRotator(90.0f, 0.0f, 0.0f);  // Pitch 90° → twist along +Z
		}
		else
		{
			ConstraintRotation = FRotator(-90.0f, 0.0f, 0.0f);  // Pitch -90° → twist along -Z
		}
	}

	// Apply rotation
	Constraint->Modify();
	Constraint->SetRelativeRotation(ConstraintRotation);

	UE_LOG(LogROABlueprintUtils, Log, TEXT("SetConstraintRotationFromGeometry: '%s' JointPos=(%.1f,%.1f,%.1f) ChildCenter=(%.1f,%.1f,%.1f) Expansion=%s Rotation=(P:%.1f, Y:%.1f, R:%.1f)"),
		*ConstraintName, 
		JointPos.X, JointPos.Y, JointPos.Z,
		ChildCenter.X, ChildCenter.Y, ChildCenter.Z,
		*ExpansionLabel,
		ConstraintRotation.Pitch, ConstraintRotation.Yaw, ConstraintRotation.Roll);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	return true;
#else
	return false;
#endif
}

int32 UROABlueprintUtils::AutoRotateAllConstraints(
	UBlueprint* Blueprint,
	const TMap<FString, FString>& ConstraintParentChildMapping)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	for (const auto& Pair : ConstraintParentChildMapping)
	{
		const FString& ConstraintName = Pair.Key;
		const FString& ParentChildStr = Pair.Value;

		// Parse "Parent|Child"
		FString ParentMeshName, ChildMeshName;
		if (ParentChildStr.Split(TEXT("|"), &ParentMeshName, &ChildMeshName))
		{
			if (SetConstraintRotationFromGeometry(Blueprint, ConstraintName, ParentMeshName, ChildMeshName))
			{
				SuccessCount++;
			}
		}
	}

	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	return SuccessCount;
#else
	return 0;
#endif
}

// ============================================================================
// v7.16: CREATE CONSTRAINT WITH ROTATION (like assemble_robot's spawn approach)
// ============================================================================

bool UROABlueprintUtils::CreateConstraintInBlueprint(
	UBlueprint* Blueprint,
	const FString& ConstraintName,
	const FString& ParentComponentName,
	const FVector& Position,
	const FRotator& Rotation,
	const FString& ComponentName1,
	const FString& ComponentName2,
	const FString& JointType,
	float AxisX,
	float AxisY,
	float AxisZ,
	float LimitLower,
	float LimitUpper,
	float MaxVelocity,
	float MaxEffort)
{
	if (!Blueprint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("CreateConstraintInBlueprint: Blueprint is null"));
		return false;
	}

#if WITH_EDITOR
	USimpleConstructionScript* SCS = Blueprint->SimpleConstructionScript;
	if (!SCS)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("CreateConstraintInBlueprint: No SCS in Blueprint"));
		return false;
	}

	// Find the parent node to attach to
	USCS_Node* ParentNode = nullptr;
	if (!ParentComponentName.IsEmpty())
	{
		ParentNode = FindSCSNode(Blueprint, ParentComponentName);
	}
	
	// If no parent specified or not found, use the root
	if (!ParentNode)
	{
		const TArray<USCS_Node*>& RootNodes = SCS->GetRootNodes();
		if (RootNodes.Num() > 0)
		{
			ParentNode = RootNodes[0];
		}
	}

	// Create a new SCS node for the PhysicsConstraintComponent
	// THIS IS THE KEY: We create the node with all properties BEFORE adding it to the SCS
	USCS_Node* NewNode = SCS->CreateNode(UPhysicsConstraintComponent::StaticClass(), FName(*ConstraintName));
	if (!NewNode)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("CreateConstraintInBlueprint: Failed to create SCS node"));
		return false;
	}

	// Get the component template - this is the actual component we can modify
	UPhysicsConstraintComponent* Constraint = Cast<UPhysicsConstraintComponent>(NewNode->ComponentTemplate);
	if (!Constraint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("CreateConstraintInBlueprint: No constraint component template"));
		return false;
	}

	// ========== SET POSITION AND ROTATION ON THE TEMPLATE ==========
	// This is done BEFORE adding to the SCS hierarchy, which is why it persists!
	Constraint->Modify();
	
	// Set transform directly on the template
	Constraint->SetRelativeLocation_Direct(Position);
	Constraint->SetRelativeRotation_Direct(Rotation);
	
	UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateConstraintInBlueprint: '%s' Position=(%.1f, %.1f, %.1f) Rotation=(P:%.1f, Y:%.1f, R:%.1f)"),
		*ConstraintName, Position.X, Position.Y, Position.Z, Rotation.Pitch, Rotation.Yaw, Rotation.Roll);

	// ========== SET CONNECTED COMPONENT NAMES ==========
	Constraint->ComponentName1.ComponentName = FName(*ComponentName1);
	Constraint->ComponentName2.ComponentName = FName(*ComponentName2);
	
	UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateConstraintInBlueprint: '%s' connects [%s] <-> [%s]"),
		*ConstraintName, *ComponentName1, *ComponentName2);

	// ========== CONFIGURE PHYSICS (v7.17: Strong drives for robot stability) ==========
	FConstraintInstance& CI = Constraint->ConstraintInstance;
	Constraint->SetDisableCollision(true);

	if (JointType == TEXT("fixed"))
	{
		CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetAngularSwing1Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularSwing2Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularTwistMotion(EAngularConstraintMotion::ACM_Locked);
		
		UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateConstraintInBlueprint: '%s' configured as FIXED"), *ConstraintName);
	}
	else if (JointType == TEXT("revolute") || JointType == TEXT("continuous"))
	{
		CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);

		EAngularConstraintMotion MotionType = (JointType == TEXT("revolute")) 
			? EAngularConstraintMotion::ACM_Limited 
			: EAngularConstraintMotion::ACM_Free;

		// Lock all angular motion first
		CI.SetAngularSwing1Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularSwing2Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularTwistMotion(EAngularConstraintMotion::ACM_Locked);

		// Free the appropriate axis - TWIST is the primary rotation axis
		// Since we orient the constraint so its X (twist) axis aligns with URDF axis,
		// we always use TWIST for the rotation.
		CI.SetAngularTwistMotion(MotionType);
		
		if (JointType == TEXT("revolute"))
		{
			float LimitDeg = FMath::RadiansToDegrees(FMath::Max(FMath::Abs(LimitLower), FMath::Abs(LimitUpper)));
			LimitDeg = FMath::Clamp(LimitDeg, 0.0f, 180.0f);
			CI.SetAngularTwistLimit(EAngularConstraintMotion::ACM_Limited, LimitDeg);
		}

		// ========== v7.17: STRONG ANGULAR DRIVES FOR ROBOT STABILITY ==========
		// Enable drives for both orientation (position hold) and velocity control
		CI.SetAngularDriveMode(EAngularDriveMode::TwistAndSwing);
		CI.SetOrientationDriveTwistAndSwing(true, true);
		CI.SetAngularVelocityDriveTwistAndSwing(true, true);
		
		// Drive parameters: (Stiffness, Damping, MaxForce)
		// - Stiffness: Spring constant - how strongly it tries to reach target position
		//   HIGH stiffness = robot holds position firmly (like a real servo)
		// - Damping: Resistance to motion - prevents oscillation
		// - MaxForce: Maximum torque the drive can apply
		//
		// For industrial robots like UR10e:
		// - High stiffness to hold position against gravity
		// - Moderate damping to prevent oscillation
		// - High max force for payload capacity
		
		float Stiffness = 100000.0f;  // Very high stiffness - holds position firmly
		float Damping = 10000.0f;     // Moderate damping - prevents oscillation
		float MaxForce = 1000000.0f;  // High max force - can move against gravity + payload
		
		// Scale based on joint effort rating from URDF
		if (MaxEffort > 0)
		{
			Stiffness = FMath::Max(Stiffness, MaxEffort * 1000.0f);
			Damping = FMath::Max(Damping, MaxEffort * 100.0f);
			MaxForce = FMath::Max(MaxForce, MaxEffort * 10000.0f);
		}
		
		CI.SetAngularDriveParams(Stiffness, Damping, MaxForce);
		
		// Note: In UE5.6+, AngularOrientationTarget and AngularVelocityTarget are set via methods on the component, not on FConstraintInstance
		// These will be initialized to zero by default in the constraint instance

		UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateConstraintInBlueprint: '%s' configured as %s (limit=%.1f°, stiffness=%.0f)"), 
			*ConstraintName, *JointType.ToUpper(),
			FMath::RadiansToDegrees(FMath::Max(FMath::Abs(LimitLower), FMath::Abs(LimitUpper))),
			Stiffness);
	}
	else if (JointType == TEXT("prismatic"))
	{
		CI.SetAngularSwing1Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularSwing2Motion(EAngularConstraintMotion::ACM_Locked);
		CI.SetAngularTwistMotion(EAngularConstraintMotion::ACM_Locked);

		// Linear motion along primary axis (X after rotation)
		CI.SetLinearXMotion(ELinearConstraintMotion::LCM_Limited);
		CI.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
		CI.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
		
		// Enable linear drives for prismatic joints
		CI.SetLinearPositionDrive(true, true, true);
		CI.SetLinearVelocityDrive(true, true, true);
		CI.SetLinearDriveParams(100000.0f, 10000.0f, 1000000.0f);

		UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateConstraintInBlueprint: '%s' configured as PRISMATIC"), *ConstraintName);
	}

	// ========== ADD NODE TO SCS HIERARCHY ==========
	if (ParentNode)
	{
		ParentNode->AddChildNode(NewNode);
	}
	else
	{
		SCS->AddNode(NewNode);
	}

	// Mark modified and compile
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);

	UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateConstraintInBlueprint: '%s' created successfully!"), *ConstraintName);
	return true;
#else
	return false;
#endif
}

int32 UROABlueprintUtils::CreateAllConstraintsInBlueprint(
	UBlueprint* Blueprint,
	const FString& ParentComponentName,
	const TArray<FString>& ConstraintDataArray)
{
	if (!Blueprint)
	{
		return 0;
	}

#if WITH_EDITOR
	int32 SuccessCount = 0;

	// Each entry format: "Name|Pos.X,Pos.Y,Pos.Z|Rot.P,Rot.Y,Rot.R|Comp1|Comp2|Type|Axis.X,Axis.Y,Axis.Z|Lower,Upper|Vel,Effort"
	for (const FString& Data : ConstraintDataArray)
	{
		TArray<FString> Parts;
		Data.ParseIntoArray(Parts, TEXT("|"));

		if (Parts.Num() < 9)
		{
			UE_LOG(LogROABlueprintUtils, Warning, TEXT("CreateAllConstraintsInBlueprint: Invalid format: %s"), *Data);
			continue;
		}

		FString Name = Parts[0];
		
		// Parse position
		TArray<FString> PosParts;
		Parts[1].ParseIntoArray(PosParts, TEXT(","));
		FVector Position(
			PosParts.Num() > 0 ? FCString::Atof(*PosParts[0]) : 0.0f,
			PosParts.Num() > 1 ? FCString::Atof(*PosParts[1]) : 0.0f,
			PosParts.Num() > 2 ? FCString::Atof(*PosParts[2]) : 0.0f
		);

		// Parse rotation
		TArray<FString> RotParts;
		Parts[2].ParseIntoArray(RotParts, TEXT(","));
		FRotator Rotation(
			RotParts.Num() > 0 ? FCString::Atof(*RotParts[0]) : 0.0f,
			RotParts.Num() > 1 ? FCString::Atof(*RotParts[1]) : 0.0f,
			RotParts.Num() > 2 ? FCString::Atof(*RotParts[2]) : 0.0f
		);

		FString Comp1 = Parts[3];
		FString Comp2 = Parts[4];
		FString JointType = Parts[5];

		// Parse axis
		TArray<FString> AxisParts;
		Parts[6].ParseIntoArray(AxisParts, TEXT(","));
		float AxisX = AxisParts.Num() > 0 ? FCString::Atof(*AxisParts[0]) : 0.0f;
		float AxisY = AxisParts.Num() > 1 ? FCString::Atof(*AxisParts[1]) : 0.0f;
		float AxisZ = AxisParts.Num() > 2 ? FCString::Atof(*AxisParts[2]) : 1.0f;

		// Parse limits
		TArray<FString> LimitParts;
		Parts[7].ParseIntoArray(LimitParts, TEXT(","));
		float LimitLower = LimitParts.Num() > 0 ? FCString::Atof(*LimitParts[0]) : -3.14159f;
		float LimitUpper = LimitParts.Num() > 1 ? FCString::Atof(*LimitParts[1]) : 3.14159f;

		// Parse velocity/effort
		TArray<FString> DriveParts;
		Parts[8].ParseIntoArray(DriveParts, TEXT(","));
		float MaxVelocity = DriveParts.Num() > 0 ? FCString::Atof(*DriveParts[0]) : 2.0f;
		float MaxEffort = DriveParts.Num() > 1 ? FCString::Atof(*DriveParts[1]) : 100.0f;

		if (CreateConstraintInBlueprint(Blueprint, Name, ParentComponentName, Position, Rotation,
			Comp1, Comp2, JointType, AxisX, AxisY, AxisZ, LimitLower, LimitUpper, MaxVelocity, MaxEffort))
		{
			SuccessCount++;
		}
	}

	if (SuccessCount > 0)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint);
	}

	UE_LOG(LogROABlueprintUtils, Log, TEXT("CreateAllConstraintsInBlueprint: Created %d constraints"), SuccessCount);
	return SuccessCount;
#else
	return 0;
#endif
}

// ============================================================================
// v7.18: RUNTIME CONSTRAINT CONTROL FUNCTIONS (for ROC integration)
// These work on SPAWNED ACTORS at runtime, not Blueprint templates.
// ============================================================================

UPhysicsConstraintComponent* UROABlueprintUtils::FindConstraintOnActor(AActor* Actor, const FString& ConstraintName)
{
	if (!Actor)
	{
		return nullptr;
	}

	// Get all PhysicsConstraintComponents on the actor
	TArray<UPhysicsConstraintComponent*> Constraints;
	Actor->GetComponents<UPhysicsConstraintComponent>(Constraints);

	for (UPhysicsConstraintComponent* Constraint : Constraints)
	{
		if (Constraint && Constraint->GetName().Contains(ConstraintName))
		{
			return Constraint;
		}
	}

	// Try exact match
	for (UPhysicsConstraintComponent* Constraint : Constraints)
	{
		if (Constraint && Constraint->GetName() == ConstraintName)
		{
			return Constraint;
		}
	}

	return nullptr;
}

bool UROABlueprintUtils::SetConstraintTargetAngle(AActor* Actor, const FString& ConstraintName, float TargetAngle)
{
	if (!Actor)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintTargetAngle: Actor is null"));
		return false;
	}

	UPhysicsConstraintComponent* Constraint = FindConstraintOnActor(Actor, ConstraintName);
	if (!Constraint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintTargetAngle: Could not find constraint '%s' on actor '%s'"),
			*ConstraintName, *Actor->GetName());
		return false;
	}

	// Convert radians to degrees for UE5
	float AngleDegrees = FMath::RadiansToDegrees(TargetAngle);

	// Set the angular orientation target
	// For revolute joints, we set the twist angle (rotation around the constraint's X axis)
	// The orientation target is relative to the initial constraint frame
	FRotator OrientationTarget = FRotator(0.0f, 0.0f, AngleDegrees);  // Roll = twist around X
	
	Constraint->SetAngularOrientationTarget(OrientationTarget);

	UE_LOG(LogROABlueprintUtils, Verbose, TEXT("SetConstraintTargetAngle: '%s' -> %.2f rad (%.1f deg)"),
		*ConstraintName, TargetAngle, AngleDegrees);

	return true;
}

int32 UROABlueprintUtils::SetAllConstraintTargetAngles(AActor* Actor, const TArray<FString>& JointNames, const TArray<float>& TargetAngles)
{
	if (!Actor)
	{
		return 0;
	}

	int32 MinCount = FMath::Min(JointNames.Num(), TargetAngles.Num());
	int32 SuccessCount = 0;

	for (int32 i = 0; i < MinCount; ++i)
	{
		if (SetConstraintTargetAngle(Actor, JointNames[i], TargetAngles[i]))
		{
			SuccessCount++;
		}
	}

	UE_LOG(LogROABlueprintUtils, Log, TEXT("SetAllConstraintTargetAngles: Set %d/%d joint targets on '%s'"),
		SuccessCount, MinCount, *Actor->GetName());

	return SuccessCount;
}

bool UROABlueprintUtils::GetConstraintCurrentAngle(AActor* Actor, const FString& ConstraintName, float& OutAngle)
{
	OutAngle = 0.0f;

	if (!Actor)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("GetConstraintCurrentAngle: Actor is null"));
		return false;
	}

	UPhysicsConstraintComponent* Constraint = FindConstraintOnActor(Actor, ConstraintName);
	if (!Constraint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("GetConstraintCurrentAngle: Could not find constraint '%s' on actor '%s'"),
			*ConstraintName, *Actor->GetName());
		return false;
	}

	// Get the current twist angle (rotation around the constraint's primary axis)
	// In UE5, we can get this from the constraint's current transform difference
	float CurrentTwist = Constraint->GetCurrentTwist();
	
	// Convert degrees to radians
	OutAngle = FMath::DegreesToRadians(CurrentTwist);

	UE_LOG(LogROABlueprintUtils, Verbose, TEXT("GetConstraintCurrentAngle: '%s' = %.2f rad (%.1f deg)"),
		*ConstraintName, OutAngle, CurrentTwist);

	return true;
}

TArray<float> UROABlueprintUtils::GetAllConstraintCurrentAngles(AActor* Actor, const TArray<FString>& JointNames)
{
	TArray<float> Angles;
	Angles.Reserve(JointNames.Num());

	if (!Actor)
	{
		for (int32 i = 0; i < JointNames.Num(); ++i)
		{
			Angles.Add(0.0f);
		}
		return Angles;
	}

	for (const FString& JointName : JointNames)
	{
		float Angle = 0.0f;
		GetConstraintCurrentAngle(Actor, JointName, Angle);
		Angles.Add(Angle);
	}

	return Angles;
}

bool UROABlueprintUtils::SetConstraintTargetVelocity(AActor* Actor, const FString& ConstraintName, float TargetVelocity)
{
	if (!Actor)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintTargetVelocity: Actor is null"));
		return false;
	}

	UPhysicsConstraintComponent* Constraint = FindConstraintOnActor(Actor, ConstraintName);
	if (!Constraint)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("SetConstraintTargetVelocity: Could not find constraint '%s' on actor '%s'"),
			*ConstraintName, *Actor->GetName());
		return false;
	}

	// Convert radians/sec to degrees/sec for UE5
	float VelocityDegreesPerSec = FMath::RadiansToDegrees(TargetVelocity);

	// Set the angular velocity target
	// For revolute joints, velocity is around the twist axis (X)
	FVector AngularVelocityTarget = FVector(VelocityDegreesPerSec, 0.0f, 0.0f);
	
	Constraint->SetAngularVelocityTarget(AngularVelocityTarget);

	UE_LOG(LogROABlueprintUtils, Verbose, TEXT("SetConstraintTargetVelocity: '%s' -> %.2f rad/s (%.1f deg/s)"),
		*ConstraintName, TargetVelocity, VelocityDegreesPerSec);

	return true;
}

int32 UROABlueprintUtils::SetAllConstraintTargetVelocities(AActor* Actor, const TArray<FString>& JointNames, const TArray<float>& TargetVelocities)
{
	if (!Actor)
	{
		return 0;
	}

	int32 MinCount = FMath::Min(JointNames.Num(), TargetVelocities.Num());
	int32 SuccessCount = 0;

	for (int32 i = 0; i < MinCount; ++i)
	{
		if (SetConstraintTargetVelocity(Actor, JointNames[i], TargetVelocities[i]))
		{
			SuccessCount++;
		}
	}

	UE_LOG(LogROABlueprintUtils, Log, TEXT("SetAllConstraintTargetVelocities: Set %d/%d joint velocities on '%s'"),
		SuccessCount, MinCount, *Actor->GetName());

	return SuccessCount;
}

TArray<FString> UROABlueprintUtils::GetActorConstraintNames(AActor* Actor)
{
	TArray<FString> Names;

	if (!Actor)
	{
		return Names;
	}

	TArray<UPhysicsConstraintComponent*> Constraints;
	Actor->GetComponents<UPhysicsConstraintComponent>(Constraints);

	for (UPhysicsConstraintComponent* Constraint : Constraints)
	{
		if (Constraint)
		{
			Names.Add(Constraint->GetName());
		}
	}

	UE_LOG(LogROABlueprintUtils, Log, TEXT("GetActorConstraintNames: Found %d constraints on '%s'"),
		Names.Num(), *Actor->GetName());

	return Names;
}

TArray<UPhysicsConstraintComponent*> UROABlueprintUtils::GetActorConstraints(AActor* Actor)
{
	TArray<UPhysicsConstraintComponent*> Constraints;

	if (!Actor)
	{
		return Constraints;
	}

	Actor->GetComponents<UPhysicsConstraintComponent>(Constraints);

	return Constraints;
}

bool UROABlueprintUtils::EmergencyStopActorJoints(AActor* Actor)
{
	if (!Actor)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("EmergencyStopActorJoints: Actor is null"));
		return false;
	}

	TArray<UPhysicsConstraintComponent*> Constraints;
	Actor->GetComponents<UPhysicsConstraintComponent>(Constraints);

	if (Constraints.Num() == 0)
	{
		UE_LOG(LogROABlueprintUtils, Warning, TEXT("EmergencyStopActorJoints: No constraints found on actor '%s'"),
			*Actor->GetName());
		return false;
	}

	for (UPhysicsConstraintComponent* Constraint : Constraints)
	{
		if (Constraint)
		{
			// Stop velocity
			Constraint->SetAngularVelocityTarget(FVector::ZeroVector);

			// Get current angle and set as target (hold position)
			float CurrentTwist = Constraint->GetCurrentTwist();
			FRotator HoldPosition = FRotator(0.0f, 0.0f, CurrentTwist);
			Constraint->SetAngularOrientationTarget(HoldPosition);
		}
	}

	UE_LOG(LogROABlueprintUtils, Warning, TEXT("EmergencyStopActorJoints: EMERGENCY STOP - Stopped %d joints on '%s'"),
		Constraints.Num(), *Actor->GetName());

	return true;
}
