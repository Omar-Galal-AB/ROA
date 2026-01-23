// Copyright ROA Development Team. All Rights Reserved.

#include "ROAMessageTypes.h"
#include "Json.h"
#include "JsonUtilities.h"

// FROAMessage Implementation

FString FROAMessage::ToJsonString() const
{
	TSharedPtr<FJsonObject> JsonObject = MakeShared<FJsonObject>();
	
	JsonObject->SetStringField(TEXT("message_id"), MessageId);
	JsonObject->SetNumberField(TEXT("timestamp"), Timestamp);
	JsonObject->SetStringField(TEXT("message_type"), FROAMessageUtils::MessageTypeToString(MessageType));
	JsonObject->SetStringField(TEXT("command"), Command);
	
	if (Payload.IsValid())
	{
		JsonObject->SetObjectField(TEXT("payload"), Payload);
	}
	else
	{
		JsonObject->SetObjectField(TEXT("payload"), MakeShared<FJsonObject>());
	}
	
	FString OutputString;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
	FJsonSerializer::Serialize(JsonObject.ToSharedRef(), Writer);
	
	return OutputString;
}

bool FROAMessage::FromJsonString(const FString& JsonString, FROAMessage& OutMessage)
{
	TSharedPtr<FJsonObject> JsonObject;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);
	
	if (!FJsonSerializer::Deserialize(Reader, JsonObject) || !JsonObject.IsValid())
	{
		return false;
	}
	
	// Parse required fields
	if (!JsonObject->TryGetStringField(TEXT("message_id"), OutMessage.MessageId))
	{
		return false;
	}
	
	if (!JsonObject->TryGetNumberField(TEXT("timestamp"), OutMessage.Timestamp))
	{
		return false;
	}
	
	FString MessageTypeStr;
	if (!JsonObject->TryGetStringField(TEXT("message_type"), MessageTypeStr))
	{
		return false;
	}
	OutMessage.MessageType = FROAMessageUtils::StringToMessageType(MessageTypeStr);
	
	if (!JsonObject->TryGetStringField(TEXT("command"), OutMessage.Command))
	{
		return false;
	}
	
	// Parse payload
	const TSharedPtr<FJsonObject>* PayloadPtr;
	if (JsonObject->TryGetObjectField(TEXT("payload"), PayloadPtr))
	{
		OutMessage.Payload = *PayloadPtr;
	}
	
	return true;
}

// FROAVector3D Implementation

TSharedPtr<FJsonObject> FROAVector3D::ToJson() const
{
	TSharedPtr<FJsonObject> JsonObj = MakeShared<FJsonObject>();
	JsonObj->SetNumberField(TEXT("x"), X);
	JsonObj->SetNumberField(TEXT("y"), Y);
	JsonObj->SetNumberField(TEXT("z"), Z);
	return JsonObj;
}

FROAVector3D FROAVector3D::FromJson(const TSharedPtr<FJsonObject>& JsonObj)
{
	FROAVector3D Result;
	if (JsonObj.IsValid())
	{
		JsonObj->TryGetNumberField(TEXT("x"), Result.X);
		JsonObj->TryGetNumberField(TEXT("y"), Result.Y);
		JsonObj->TryGetNumberField(TEXT("z"), Result.Z);
	}
	return Result;
}

// FROARotation Implementation

TSharedPtr<FJsonObject> FROARotation::ToJson() const
{
	TSharedPtr<FJsonObject> JsonObj = MakeShared<FJsonObject>();
	JsonObj->SetNumberField(TEXT("roll"), Roll);
	JsonObj->SetNumberField(TEXT("pitch"), Pitch);
	JsonObj->SetNumberField(TEXT("yaw"), Yaw);
	return JsonObj;
}

FROARotation FROARotation::FromJson(const TSharedPtr<FJsonObject>& JsonObj)
{
	FROARotation Result;
	if (JsonObj.IsValid())
	{
		JsonObj->TryGetNumberField(TEXT("roll"), Result.Roll);
		JsonObj->TryGetNumberField(TEXT("pitch"), Result.Pitch);
		JsonObj->TryGetNumberField(TEXT("yaw"), Result.Yaw);
	}
	return Result;
}

// FROASpawnRobotRequest Implementation

bool FROASpawnRobotRequest::FromJson(const TSharedPtr<FJsonObject>& JsonObj, FROASpawnRobotRequest& OutRequest)
{
	if (!JsonObj.IsValid())
	{
		return false;
	}
	
	if (!JsonObj->TryGetStringField(TEXT("robot_id"), OutRequest.RobotId))
	{
		return false;
	}
	
	if (!JsonObj->TryGetStringField(TEXT("robot_type"), OutRequest.RobotType))
	{
		return false;
	}
	
	JsonObj->TryGetStringField(TEXT("urdf_path"), OutRequest.UrdfPath);
	
	// Parse spawn location
	const TSharedPtr<FJsonObject>* LocationPtr;
	if (JsonObj->TryGetObjectField(TEXT("spawn_location"), LocationPtr))
	{
		OutRequest.SpawnLocation = FROAVector3D::FromJson(*LocationPtr);
	}
	
	// Parse spawn rotation
	const TSharedPtr<FJsonObject>* RotationPtr;
	if (JsonObj->TryGetObjectField(TEXT("spawn_rotation"), RotationPtr))
	{
		OutRequest.SpawnRotation = FROARotation::FromJson(*RotationPtr);
	}
	
	// Parse initial joint states
	const TArray<TSharedPtr<FJsonValue>>* JointStatesPtr;
	if (JsonObj->TryGetArrayField(TEXT("initial_joint_states"), JointStatesPtr))
	{
		for (const TSharedPtr<FJsonValue>& Value : *JointStatesPtr)
		{
			OutRequest.InitialJointStates.Add(Value->AsNumber());
		}
	}
	
	return true;
}

// FROARobotState Implementation

TSharedPtr<FJsonObject> FROARobotState::ToJson() const
{
	TSharedPtr<FJsonObject> JsonObj = MakeShared<FJsonObject>();
	
	JsonObj->SetStringField(TEXT("robot_id"), RobotId);
	JsonObj->SetObjectField(TEXT("position"), Position.ToJson());
	JsonObj->SetObjectField(TEXT("rotation"), Rotation.ToJson());
	
	// Joint states
	TSharedPtr<FJsonObject> JointStatesObj = MakeShared<FJsonObject>();
	
	TArray<TSharedPtr<FJsonValue>> PositionsArray;
	for (float Pos : JointPositions)
	{
		PositionsArray.Add(MakeShared<FJsonValueNumber>(Pos));
	}
	JointStatesObj->SetArrayField(TEXT("positions"), PositionsArray);
	
	TArray<TSharedPtr<FJsonValue>> VelocitiesArray;
	for (float Vel : JointVelocities)
	{
		VelocitiesArray.Add(MakeShared<FJsonValueNumber>(Vel));
	}
	JointStatesObj->SetArrayField(TEXT("velocities"), VelocitiesArray);
	
	TArray<TSharedPtr<FJsonValue>> EffortsArray;
	for (float Eff : JointEfforts)
	{
		EffortsArray.Add(MakeShared<FJsonValueNumber>(Eff));
	}
	JointStatesObj->SetArrayField(TEXT("efforts"), EffortsArray);
	
	JsonObj->SetObjectField(TEXT("joint_states"), JointStatesObj);
	
	// End effector pose
	TSharedPtr<FJsonObject> EndEffectorObj = MakeShared<FJsonObject>();
	EndEffectorObj->SetObjectField(TEXT("position"), EndEffectorPosition.ToJson());
	EndEffectorObj->SetObjectField(TEXT("rotation"), EndEffectorRotation.ToJson());
	JsonObj->SetObjectField(TEXT("end_effector_pose"), EndEffectorObj);
	
	return JsonObj;
}

// FROAJointCommand Implementation

bool FROAJointCommand::FromJson(const TSharedPtr<FJsonObject>& JsonObj, FROAJointCommand& OutCommand)
{
	if (!JsonObj.IsValid())
	{
		return false;
	}
	
	if (!JsonObj->TryGetStringField(TEXT("robot_id"), OutCommand.RobotId))
	{
		return false;
	}
	
	const TArray<TSharedPtr<FJsonValue>>* JointPositionsPtr;
	if (JsonObj->TryGetArrayField(TEXT("joint_positions"), JointPositionsPtr))
	{
		for (const TSharedPtr<FJsonValue>& Value : *JointPositionsPtr)
		{
			OutCommand.JointPositions.Add(Value->AsNumber());
		}
	}
	
	JsonObj->TryGetNumberField(TEXT("duration"), OutCommand.Duration);
	
	return true;
}

// FROACollisionEvent Implementation

TSharedPtr<FJsonObject> FROACollisionEvent::ToJson() const
{
	TSharedPtr<FJsonObject> JsonObj = MakeShared<FJsonObject>();
	
	JsonObj->SetStringField(TEXT("robot_id"), RobotId);
	JsonObj->SetObjectField(TEXT("collision_point"), CollisionPoint.ToJson());
	JsonObj->SetObjectField(TEXT("collision_normal"), CollisionNormal.ToJson());
	JsonObj->SetNumberField(TEXT("collision_force"), CollisionForce);
	JsonObj->SetStringField(TEXT("other_object"), OtherObject);
	
	return JsonObj;
}

// FROAMessageUtils Implementation

FString FROAMessageUtils::MessageTypeToString(EROAMessageType Type)
{
	switch (Type)
	{
	case EROAMessageType::REQUEST:  return TEXT("REQUEST");
	case EROAMessageType::RESPONSE: return TEXT("RESPONSE");
	case EROAMessageType::EVENT:    return TEXT("EVENT");
	case EROAMessageType::ERROR:    return TEXT("ERROR");
	default:             return TEXT("UNKNOWN");
	}
}

EROAMessageType FROAMessageUtils::StringToMessageType(const FString& TypeString)
{
	if (TypeString == TEXT("REQUEST"))  return EROAMessageType::REQUEST;
	if (TypeString == TEXT("RESPONSE")) return EROAMessageType::RESPONSE;
	if (TypeString == TEXT("EVENT")) return EROAMessageType::EVENT;
	if (TypeString == TEXT("ERROR"))    return EROAMessageType::ERROR;
	return EROAMessageType::REQUEST;
}

FString FROAMessageUtils::ErrorCodeToString(EROAErrorCode Code)
{
	switch (Code)
	{
	case EROAErrorCode::ERR_NONE:            return TEXT("ERR_NONE");
	case EROAErrorCode::ERR_CONNECTION_FAILED: return TEXT("ERR_CONNECTION_FAILED");
	case EROAErrorCode::ERR_ROBOT_NOT_FOUND:   return TEXT("ERR_ROBOT_NOT_FOUND");
	case EROAErrorCode::ERR_INVALID_COMMAND:   return TEXT("ERR_INVALID_COMMAND");
	case EROAErrorCode::ERR_INVALID_PAYLOAD:   return TEXT("ERR_INVALID_PAYLOAD");
	case EROAErrorCode::ERR_SPAWN_FAILED:      return TEXT("ERR_SPAWN_FAILED");
	case EROAErrorCode::ERR_PHYSICS_ERROR:     return TEXT("ERR_PHYSICS_ERROR");
	case EROAErrorCode::ERR_FILE_NOT_FOUND:    return TEXT("ERR_FILE_NOT_FOUND");
	case EROAErrorCode::ERR_WIDGET_ERROR:      return TEXT("ERR_WIDGET_ERROR");
	case EROAErrorCode::ERR_COLLISION:         return TEXT("ERR_COLLISION");
	case EROAErrorCode::ERR_JOINT_LIMIT:       return TEXT("ERR_JOINT_LIMIT");
	case EROAErrorCode::ERR_TIMEOUT:         return TEXT("ERR_TIMEOUT");
	default:          return TEXT("ERR_UNKNOWN");
	}
}

EROAErrorCode FROAMessageUtils::StringToErrorCode(const FString& CodeString)
{
	if (CodeString == TEXT("ERR_NONE"))       return EROAErrorCode::ERR_NONE;
	if (CodeString == TEXT("ERR_CONNECTION_FAILED")) return EROAErrorCode::ERR_CONNECTION_FAILED;
	if (CodeString == TEXT("ERR_ROBOT_NOT_FOUND"))   return EROAErrorCode::ERR_ROBOT_NOT_FOUND;
	if (CodeString == TEXT("ERR_INVALID_COMMAND"))   return EROAErrorCode::ERR_INVALID_COMMAND;
	if (CodeString == TEXT("ERR_INVALID_PAYLOAD"))   return EROAErrorCode::ERR_INVALID_PAYLOAD;
	if (CodeString == TEXT("ERR_SPAWN_FAILED"))      return EROAErrorCode::ERR_SPAWN_FAILED;
	if (CodeString == TEXT("ERR_PHYSICS_ERROR"))     return EROAErrorCode::ERR_PHYSICS_ERROR;
	if (CodeString == TEXT("ERR_FILE_NOT_FOUND"))    return EROAErrorCode::ERR_FILE_NOT_FOUND;
	if (CodeString == TEXT("ERR_WIDGET_ERROR"))      return EROAErrorCode::ERR_WIDGET_ERROR;
	if (CodeString == TEXT("ERR_COLLISION"))         return EROAErrorCode::ERR_COLLISION;
	if (CodeString == TEXT("ERR_JOINT_LIMIT"))  return EROAErrorCode::ERR_JOINT_LIMIT;
	if (CodeString == TEXT("ERR_TIMEOUT"))           return EROAErrorCode::ERR_TIMEOUT;
	return EROAErrorCode::ERR_NONE;
}

FROAMessage FROAMessageUtils::CreateSuccessResponse(const FString& Command, const TSharedPtr<FJsonObject>& Payload)
{
	FROAMessage Message;
	Message.MessageType = EROAMessageType::RESPONSE;
	Message.Command = Command;
	
	TSharedPtr<FJsonObject> ResponsePayload = Payload.IsValid() ? Payload : MakeShared<FJsonObject>();
	ResponsePayload->SetStringField(TEXT("status"), TEXT("success"));
	Message.Payload = ResponsePayload;
	
	return Message;
}

FROAMessage FROAMessageUtils::CreateErrorResponse(const FString& Command, EROAErrorCode ErrorCode, const FString& ErrorMessage)
{
	FROAMessage Message;
	Message.MessageType = EROAMessageType::ERROR;
	Message.Command = Command;
	
	TSharedPtr<FJsonObject> ErrorPayload = MakeShared<FJsonObject>();
	ErrorPayload->SetStringField(TEXT("error_code"), ErrorCodeToString(ErrorCode));
	ErrorPayload->SetStringField(TEXT("error_message"), ErrorMessage);
	ErrorPayload->SetObjectField(TEXT("details"), MakeShared<FJsonObject>());
	
	Message.Payload = ErrorPayload;
	
	return Message;
}

FROAMessage FROAMessageUtils::CreateEvent(const FString& EventName, const TSharedPtr<FJsonObject>& Payload)
{
	FROAMessage Message;
	Message.MessageType = EROAMessageType::EVENT;
	Message.Command = EventName;
	Message.Payload = Payload.IsValid() ? Payload : MakeShared<FJsonObject>();
	
	return Message;
}
