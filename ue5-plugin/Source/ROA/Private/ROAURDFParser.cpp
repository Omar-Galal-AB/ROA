// Copyright Epic Games, Inc. All Rights Reserved.

#include "ROAURDFParser.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"

// Helper: Find link by name
FROAURDFLink* FROARobotDescription::FindLink(const FString& LinkName)
{
	for (FROAURDFLink& Link : Links)
	{
		if (Link.Name.Equals(LinkName, ESearchCase::IgnoreCase))
		{
			return &Link;
		}
	}
	return nullptr;
}

// Helper: Find joint by name
FROAURDFJoint* FROARobotDescription::FindJoint(const FString& JointName)
{
	for (FROAURDFJoint& Joint : Joints)
	{
		if (Joint.Name.Equals(JointName, ESearchCase::IgnoreCase))
		{
			return &Joint;
		}
	}
	return nullptr;
}

bool FROAURDFParser::ParseURDF(const FString& URDFFilePath, FROARobotDescription& OutDescription)
{
	// Validate file exists
	if (!FPaths::FileExists(URDFFilePath))
	{
		UE_LOG(LogTemp, Error, TEXT("URDF file not found: %s"), *URDFFilePath);
		return false;
	}
	
	// Read file content
	FString URDFContent;
	if (!FFileHelper::LoadFileToString(URDFContent, *URDFFilePath))
	{
		UE_LOG(LogTemp, Error, TEXT("Failed to read URDF file: %s"), *URDFFilePath);
		return false;
	}
	
	// Get base directory for resolving relative paths
	FString BaseDirectory = FPaths::GetPath(URDFFilePath);
	
	return ParseURDFContent(URDFContent, BaseDirectory, OutDescription);
}

bool FROAURDFParser::ParseURDFContent(const FString& URDFContent, const FString& BaseDirectory, FROARobotDescription& OutDescription)
{
	// Parse XML
	FXmlFile XmlFile(URDFContent, EConstructMethod::ConstructFromBuffer);
	
	if (!XmlFile.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("Invalid URDF XML content"));
		return false;
	}
	
	FXmlNode* RootNode = XmlFile.GetRootNode();
	if (!RootNode || RootNode->GetTag() != TEXT("robot"))
	{
		UE_LOG(LogTemp, Error, TEXT("URDF root node must be <robot>"));
		return false;
	}
	
	OutDescription.BaseDirectory = BaseDirectory;
	return ParseRobot(RootNode, OutDescription);
}

bool FROAURDFParser::ParseRobot(FXmlNode* RobotNode, FROARobotDescription& OutDescription)
{
	// Get robot name
	OutDescription.RobotName = RobotNode->GetAttribute(TEXT("name"));
	
	if (OutDescription.RobotName.IsEmpty())
	{
		UE_LOG(LogTemp, Warning, TEXT("Robot has no name attribute"));
		OutDescription.RobotName = TEXT("UnnamedRobot");
	}
	
	// Parse all child nodes
	const TArray<FXmlNode*>& ChildNodes = RobotNode->GetChildrenNodes();
	
	for (FXmlNode* ChildNode : ChildNodes)
	{
		const FString& Tag = ChildNode->GetTag();
		
		if (Tag == TEXT("link"))
		{
			FROAURDFLink Link;
			if (ParseLink(ChildNode, Link))
			{
				OutDescription.Links.Add(Link);
			}
		}
		else if (Tag == TEXT("joint"))
		{
			FROAURDFJoint Joint;
			if (ParseJoint(ChildNode, Joint))
			{
				OutDescription.Joints.Add(Joint);
			}
		}
	}
	
	UE_LOG(LogTemp, Log, TEXT("Parsed URDF: %s with %d links and %d joints"), 
		*OutDescription.RobotName, OutDescription.Links.Num(), OutDescription.Joints.Num());
	
	return OutDescription.IsValid();
}

bool FROAURDFParser::ParseLink(FXmlNode* LinkNode, FROAURDFLink& OutLink)
{
	OutLink.Name = LinkNode->GetAttribute(TEXT("name"));
	
	if (OutLink.Name.IsEmpty())
	{
		UE_LOG(LogTemp, Warning, TEXT("Link has no name, skipping"));
		return false;
	}
	
	// Default values
	OutLink.Mass = 1.0f;
	OutLink.Inertia = FVector(1.0f, 1.0f, 1.0f);
	
	const TArray<FXmlNode*>& ChildNodes = LinkNode->GetChildrenNodes();
	
	for (FXmlNode* ChildNode : ChildNodes)
	{
		const FString& Tag = ChildNode->GetTag();
		
		if (Tag == TEXT("visual"))
		{
			ParseVisual(ChildNode, OutLink);
		}
		else if (Tag == TEXT("collision"))
		{
			ParseCollision(ChildNode, OutLink);
		}
		else if (Tag == TEXT("inertial"))
		{
			// Parse mass
			FXmlNode* MassNode = ChildNode->FindChildNode(TEXT("mass"));
			if (MassNode)
			{
				FString MassStr = MassNode->GetAttribute(TEXT("value"));
				OutLink.Mass = FCString::Atof(*MassStr);
			}
		}
	}
	
	return true;
}

bool FROAURDFParser::ParseJoint(FXmlNode* JointNode, FROAURDFJoint& OutJoint)
{
	OutJoint.Name = JointNode->GetAttribute(TEXT("name"));
	OutJoint.Type = JointNode->GetAttribute(TEXT("type"));
	
	if (OutJoint.Name.IsEmpty() || OutJoint.Type.IsEmpty())
	{
		UE_LOG(LogTemp, Warning, TEXT("Joint has no name or type, skipping"));
		return false;
	}
	
	// Default values
	OutJoint.Axis = FVector(0, 0, 1); // Z-axis by default
	OutJoint.LowerLimit = -3.14159f;
	OutJoint.UpperLimit = 3.14159f;
	OutJoint.EffortLimit = 100.0f;
	OutJoint.VelocityLimit = 1.0f;
	
	const TArray<FXmlNode*>& ChildNodes = JointNode->GetChildrenNodes();
	
	for (FXmlNode* ChildNode : ChildNodes)
	{
		const FString& Tag = ChildNode->GetTag();
		
		if (Tag == TEXT("parent"))
		{
			OutJoint.ParentLink = ChildNode->GetAttribute(TEXT("link"));
		}
		else if (Tag == TEXT("child"))
		{
			OutJoint.ChildLink = ChildNode->GetAttribute(TEXT("link"));
		}
		else if (Tag == TEXT("origin"))
		{
			ParseOrigin(ChildNode, OutJoint.Origin, OutJoint.Rotation);
		}
		else if (Tag == TEXT("axis"))
		{
			ParseAxis(ChildNode, OutJoint.Axis);
		}
		else if (Tag == TEXT("limit"))
		{
			ParseLimit(ChildNode, OutJoint.LowerLimit, OutJoint.UpperLimit, 
				OutJoint.EffortLimit, OutJoint.VelocityLimit);
		}
	}
	
	return true;
}

bool FROAURDFParser::ParseVisual(FXmlNode* VisualNode, FROAURDFLink& OutLink)
{
	FXmlNode* OriginNode = VisualNode->FindChildNode(TEXT("origin"));
	if (OriginNode)
	{
		ParseOrigin(OriginNode, OutLink.VisualOrigin, OutLink.VisualRotation);
	}
	
	FXmlNode* GeometryNode = VisualNode->FindChildNode(TEXT("geometry"));
	if (GeometryNode)
	{
		ParseGeometry(GeometryNode, OutLink.MeshPath);
	}
	
	return true;
}

bool FROAURDFParser::ParseCollision(FXmlNode* CollisionNode, FROAURDFLink& OutLink)
{
	FXmlNode* OriginNode = CollisionNode->FindChildNode(TEXT("origin"));
	if (OriginNode)
	{
		ParseOrigin(OriginNode, OutLink.CollisionOrigin, OutLink.CollisionRotation);
	}
	
	FXmlNode* GeometryNode = CollisionNode->FindChildNode(TEXT("geometry"));
	if (GeometryNode)
	{
		ParseGeometry(GeometryNode, OutLink.CollisionMeshPath);
	}
	
	return true;
}

bool FROAURDFParser::ParseGeometry(FXmlNode* GeometryNode, FString& OutMeshPath)
{
	FXmlNode* MeshNode = GeometryNode->FindChildNode(TEXT("mesh"));
	if (MeshNode)
	{
		OutMeshPath = MeshNode->GetAttribute(TEXT("filename"));
		return true;
	}
	
	// Handle primitive shapes (box, cylinder, sphere) - could be expanded
	FXmlNode* BoxNode = GeometryNode->FindChildNode(TEXT("box"));
	if (BoxNode)
	{
		OutMeshPath = TEXT("primitive:box");
		return true;
	}
	
	FXmlNode* CylinderNode = GeometryNode->FindChildNode(TEXT("cylinder"));
	if (CylinderNode)
	{
		OutMeshPath = TEXT("primitive:cylinder");
		return true;
	}
	
	FXmlNode* SphereNode = GeometryNode->FindChildNode(TEXT("sphere"));
	if (SphereNode)
	{
		OutMeshPath = TEXT("primitive:sphere");
		return true;
	}
	
	return false;
}

bool FROAURDFParser::ParseOrigin(FXmlNode* OriginNode, FVector& OutPosition, FRotator& OutRotation)
{
	FString XYZStr = OriginNode->GetAttribute(TEXT("xyz"));
	FString RPYStr = OriginNode->GetAttribute(TEXT("rpy"));
	
	if (!XYZStr.IsEmpty())
	{
		OutPosition = StringToVector(XYZStr);
		// Convert from meters to centimeters (UE5 units)
		OutPosition *= 100.0f;
	}
	
	if (!RPYStr.IsEmpty())
	{
		OutRotation = RPYToRotator(RPYStr);
	}
	
	return true;
}

bool FROAURDFParser::ParseAxis(FXmlNode* AxisNode, FVector& OutAxis)
{
	FString XYZStr = AxisNode->GetAttribute(TEXT("xyz"));
	if (!XYZStr.IsEmpty())
	{
		OutAxis = StringToVector(XYZStr);
		OutAxis.Normalize();
	}
	return true;
}

bool FROAURDFParser::ParseLimit(FXmlNode* LimitNode, float& OutLower, float& OutUpper, float& OutEffort, float& OutVelocity)
{
	FString LowerStr = LimitNode->GetAttribute(TEXT("lower"));
	FString UpperStr = LimitNode->GetAttribute(TEXT("upper"));
	FString EffortStr = LimitNode->GetAttribute(TEXT("effort"));
	FString VelocityStr = LimitNode->GetAttribute(TEXT("velocity"));
	
	if (!LowerStr.IsEmpty()) OutLower = FCString::Atof(*LowerStr);
	if (!UpperStr.IsEmpty()) OutUpper = FCString::Atof(*UpperStr);
	if (!EffortStr.IsEmpty()) OutEffort = FCString::Atof(*EffortStr);
	if (!VelocityStr.IsEmpty()) OutVelocity = FCString::Atof(*VelocityStr);
	
	return true;
}

FString FROAURDFParser::ResolvePackagePath(const FString& URIPath, const FString& BaseDirectory)
{
	// Handle ROS package:// URIs
	if (URIPath.StartsWith(TEXT("package://")))
	{
		FString RelativePath = URIPath.Replace(TEXT("package://"), TEXT(""));
		// In a real implementation, this would resolve ROS package paths
		// For now, just strip the package:// prefix
		return FPaths::Combine(BaseDirectory, RelativePath);
	}
	
	// Handle file:// URIs
	if (URIPath.StartsWith(TEXT("file://")))
	{
		return URIPath.Replace(TEXT("file://"), TEXT(""));
	}
	
	// Relative path
	return FPaths::Combine(BaseDirectory, URIPath);
}

FVector FROAURDFParser::StringToVector(const FString& VectorString)
{
	TArray<FString> Components;
	VectorString.ParseIntoArray(Components, TEXT(" "), true);
	
	if (Components.Num() >= 3)
	{
		float X = FCString::Atof(*Components[0]);
		float Y = FCString::Atof(*Components[1]);
		float Z = FCString::Atof(*Components[2]);
		return FVector(X, Y, Z);
	}
	
	return FVector::ZeroVector;
}

FRotator FROAURDFParser::RPYToRotator(const FString& RPYString)
{
	TArray<FString> Components;
	RPYString.ParseIntoArray(Components, TEXT(" "), true);
	
	if (Components.Num() >= 3)
	{
		// URDF uses Roll-Pitch-Yaw in radians
		float Roll = FMath::RadiansToDegrees(FCString::Atof(*Components[0]));
		float Pitch = FMath::RadiansToDegrees(FCString::Atof(*Components[1]));
		float Yaw = FMath::RadiansToDegrees(FCString::Atof(*Components[2]));
		
		// Convert to UE5 rotation convention
		return FRotator(Pitch, Yaw, Roll);
	}
	
	return FRotator::ZeroRotator;
}
