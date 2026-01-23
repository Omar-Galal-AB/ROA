// DimensionsCollector.cpp
// Implementation of UE5 Dimensions Collector Plugin
// Enhanced with Raycast LIDAR, Obstacle Detection, and FTI Integration
// Version: 2.0

#include "DimensionsCollector.h"
#include "Components/MeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "DrawDebugHelpers.h"
#include "Kismet/KismetMathLibrary.h"

// ============================================================================
// CONSTRUCTOR & LIFECYCLE
// ============================================================================

ADimensionsCollector::ADimensionsCollector()
{
    // Set this actor to call Tick() every frame
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = 1.0f / UpdateRate;  // 60Hz default

    // Initialize collision params
    CollisionParams.bTraceComplex = true;
    CollisionParams.bReturnPhysicalMaterial = false;

    UE_LOG(LogTemp, Log, TEXT("DimensionsCollector v2.0: Initialized with Raycast LIDAR support"));
}

void ADimensionsCollector::BeginPlay()
{
    Super::BeginPlay();
    
    UE_LOG(LogTemp, Log, TEXT("DimensionsCollector: BeginPlay - Ready for robot registration"));
}

void ADimensionsCollector::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);

    TotalTime += DeltaTime;
    TimeSinceLastSensorUpdate += DeltaTime;

    // Update tracking for all registered robots
    for (auto& Pair : TrackedRobots)
    {
        UpdateRobotTracking(Pair.Key, DeltaTime);
    }

    // Update sensor simulations at configured rate
    float SensorInterval = 1.0f / SensorUpdateRate;
    if (TimeSinceLastSensorUpdate >= SensorInterval)
    {
        for (auto& Pair : TrackedRobots)
        {
            UpdateSensorSimulations(Pair.Key);
        }
        TimeSinceLastSensorUpdate = 0.0f;
    }
}

// ============================================================================
// FTI INTEGRATION - ROBOT REGISTRATION
// ============================================================================

bool ADimensionsCollector::RegisterRobotFromFTI(const FDIMCRobotConfig& Config)
{
    if (!Config.RobotActor)
    {
        UE_LOG(LogTemp, Error, TEXT("DIMC: Cannot register robot %s - null actor"), *Config.RobotID);
        return false;
    }

    if (TrackedRobots.Contains(Config.RobotID))
    {
        UE_LOG(LogTemp, Warning, TEXT("DIMC: Robot %s already registered, updating config"), *Config.RobotID);
        UnregisterRobot(Config.RobotID);
    }

    // Create tracking data from FTI config
    FRobotTrackingData TrackingData;
    TrackingData.RobotID = Config.RobotID;
    TrackingData.RobotName = Config.RobotName.IsEmpty() ? Config.RobotID : Config.RobotName;
    TrackingData.Actor = Config.RobotActor;
    TrackingData.RobotType = Config.RobotType;
    TrackingData.DataFlags = Config.DataFlags;

    // Initial position/orientation
    TrackingData.Position = Config.RobotActor->GetActorLocation();
    TrackingData.Orientation = Config.RobotActor->GetActorQuat();
    TrackingData.LastPosition = TrackingData.Position;
    TrackingData.LastUpdateTime = TotalTime;

    // Apply dimensions (from FTI or calculate from mesh)
    if (Config.DataFlags.bHasDimensions)
    {
        TrackingData.Dimensions = Config.Dimensions;
        UE_LOG(LogTemp, Log, TEXT("DIMC: Using URDF dimensions for %s"), *Config.RobotID);
    }
    else
    {
        // Calculate from mesh bounds
        UMeshComponent* MeshComp = Config.RobotActor->FindComponentByClass<UMeshComponent>();
        if (MeshComp)
        {
            TrackingData.Dimensions = CalculateDimensions(MeshComp);
            TrackingData.BoundingBox = CalculateBoundingBox(MeshComp);
            UE_LOG(LogTemp, Log, TEXT("DIMC: Calculated dimensions from mesh for %s"), *Config.RobotID);
        }
    }

    // Apply sensors (from FTI or use defaults)
    if (Config.DataFlags.bHasSensors && Config.Sensors.Num() > 0)
    {
        TrackingData.Sensors = Config.Sensors;
        UE_LOG(LogTemp, Log, TEXT("DIMC: Using %d URDF sensors for %s"), Config.Sensors.Num(), *Config.RobotID);
    }
    else
    {
        TrackingData.Sensors = GetDefaultSensorsForType(Config.RobotType);
        UE_LOG(LogTemp, Log, TEXT("DIMC: Applied default %s sensors (%d) for %s"), 
               *UEnum::GetValueAsString(Config.RobotType), TrackingData.Sensors.Num(), *Config.RobotID);
    }

    // Apply safety zones (from FTI, calculate, or use defaults)
    if (Config.DataFlags.bHasSafetyZones)
    {
        TrackingData.SafetyZones = Config.SafetyZones;
    }
    else if (TrackingData.Dimensions.BoundingRadius > 0.0f)
    {
        TrackingData.SafetyZones = CalculateSafetyZonesFromDimensions(TrackingData.Dimensions);
        UE_LOG(LogTemp, Log, TEXT("DIMC: Calculated safety zones from dimensions for %s"), *Config.RobotID);
    }
    else
    {
        TrackingData.SafetyZones = GetDefaultSafetyZonesForType(Config.RobotType);
    }

    // Store tracking data
    TrackedRobots.Add(Config.RobotID, TrackingData);
    KnownRobotIDs.Add(Config.RobotID);

    UE_LOG(LogTemp, Log, TEXT("DIMC: Successfully registered robot %s (type: %s) at position %s"),
           *Config.RobotID, *UEnum::GetValueAsString(Config.RobotType), *TrackingData.Position.ToString());

    return true;
}

bool ADimensionsCollector::RegisterRobot(const FString& RobotID, AActor* RobotActor)
{
    // Legacy registration method - creates minimal config and calls FTI method
    FDIMCRobotConfig Config;
    Config.RobotID = RobotID;
    Config.RobotName = RobotID;
    Config.RobotActor = RobotActor;
    Config.RobotType = ERobotType::Generic;
    // All data flags false - will use calculated/default values
    
    return RegisterRobotFromFTI(Config);
}

bool ADimensionsCollector::UnregisterRobot(const FString& RobotID)
{
    if (!TrackedRobots.Contains(RobotID))
    {
        UE_LOG(LogTemp, Warning, TEXT("DIMC: Cannot unregister unknown robot %s"), *RobotID);
        return false;
    }

    TrackedRobots.Remove(RobotID);
    KnownRobotIDs.Remove(RobotID);
    
    UE_LOG(LogTemp, Log, TEXT("DIMC: Unregistered robot %s"), *RobotID);
    return true;
}

// ============================================================================
// POSITION & ORIENTATION TRACKING
// ============================================================================

FVector ADimensionsCollector::GetRobotPosition(const FString& RobotID) const
{
    const FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    return Data ? Data->Position : FVector::ZeroVector;
}

FQuat ADimensionsCollector::GetRobotOrientation(const FString& RobotID) const
{
    const FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    return Data ? Data->Orientation : FQuat::Identity;
}

FVector ADimensionsCollector::GetRobotVelocity(const FString& RobotID) const
{
    const FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    return Data ? Data->Velocity : FVector::ZeroVector;
}

FRobotDimensions ADimensionsCollector::GetRobotDimensions(const FString& RobotID) const
{
    const FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    return Data ? Data->Dimensions : FRobotDimensions();
}

FBoundingBox ADimensionsCollector::GetRobotBoundingBox(const FString& RobotID) const
{
    const FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    return Data ? Data->BoundingBox : FBoundingBox();
}

float ADimensionsCollector::GetDistanceBetweenRobots(const FString& RobotID1, const FString& RobotID2) const
{
    const FRobotTrackingData* Data1 = TrackedRobots.Find(RobotID1);
    const FRobotTrackingData* Data2 = TrackedRobots.Find(RobotID2);

    if (!Data1 || !Data2)
    {
        return -1.0f;  // Invalid
    }

    return FVector::Dist(Data1->Position, Data2->Position);
}

// ============================================================================
// SENSOR SIMULATION - CPU RAYCAST LIDAR
// ============================================================================

bool ADimensionsCollector::RegisterSensor(const FString& RobotID, const FSensorDefinition& SensorDef)
{
    FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    if (!Data)
    {
        UE_LOG(LogTemp, Warning, TEXT("DIMC: Cannot register sensor for unknown robot %s"), *RobotID);
        return false;
    }

    // Check if sensor with same name already exists
    for (int32 i = 0; i < Data->Sensors.Num(); i++)
    {
        if (Data->Sensors[i].SensorName == SensorDef.SensorName)
        {
            Data->Sensors[i] = SensorDef;  // Update existing
            UE_LOG(LogTemp, Log, TEXT("DIMC: Updated sensor %s for robot %s"), *SensorDef.SensorName, *RobotID);
            return true;
        }
    }

    Data->Sensors.Add(SensorDef);
    UE_LOG(LogTemp, Log, TEXT("DIMC: Registered sensor %s for robot %s"), *SensorDef.SensorName, *RobotID);
    return true;
}

FLidarScanResult ADimensionsCollector::PerformLidarScan(const FString& RobotID, const FString& SensorName)
{
    FLidarScanResult Result;
    
    FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    if (!Data)
    {
        UE_LOG(LogTemp, Warning, TEXT("DIMC: Cannot perform LIDAR scan for unknown robot %s"), *RobotID);
        return Result;
    }

    // Find the sensor
    const FSensorDefinition* Sensor = nullptr;
    for (const auto& S : Data->Sensors)
    {
        if (S.SensorName == SensorName && S.Type == ESensorType::LIDAR)
        {
            Sensor = &S;
            break;
        }
    }

    if (!Sensor)
    {
        UE_LOG(LogTemp, Warning, TEXT("DIMC: LIDAR sensor %s not found for robot %s"), *SensorName, *RobotID);
        return Result;
    }

    // Calculate sensor world position
    FVector SensorOrigin = Data->Position + Data->Orientation.RotateVector(Sensor->MountOffset.GetLocation());
    FQuat SensorOrientation = Data->Orientation * Sensor->MountOffset.GetRotation();

    // Perform the scan
    return PerformCustomLidarScan(
        SensorOrigin,
        SensorOrientation,
        Sensor->RayCount,
        Sensor->RangeMax,
        Sensor->FOVHorizontal
    );
}

FLidarScanResult ADimensionsCollector::PerformCustomLidarScan(
    const FVector& Origin,
    const FQuat& Orientation,
    int32 RayCount,
    float RangeMax,
    float FOVHorizontal)
{
    FLidarScanResult Result;
    Result.Timestamp = TotalTime;
    
    if (RayCount <= 0 || RangeMax <= 0.0f)
    {
        return Result;
    }

    // Calculate angle parameters
    float FOVRad = FMath::DegreesToRadians(FOVHorizontal);
    Result.AngleMin = -FOVRad / 2.0f;
    Result.AngleMax = FOVRad / 2.0f;
    Result.AngleIncrement = FOVRad / static_cast<float>(RayCount);

    // Pre-allocate arrays
    Result.Ranges.Reserve(RayCount);
    Result.Intensities.Reserve(RayCount);
    Result.HitPoints.Reserve(RayCount);
    Result.HitActorNames.Reserve(RayCount);

    // Get the forward vector
    FVector Forward = Orientation.GetForwardVector();
    FVector Up = Orientation.GetUpVector();

    // Perform raycasts
    for (int32 i = 0; i < RayCount; i++)
    {
        float Angle = Result.AngleMin + (i * Result.AngleIncrement);
        
        // Rotate the forward vector around the up axis
        FVector RayDirection = Forward.RotateAngleAxis(FMath::RadiansToDegrees(Angle), Up);
        FVector RayEnd = Origin + (RayDirection * RangeMax);

        FHitResult HitResult;
        bool bHit = PerformRaycast(Origin, RayEnd, HitResult, nullptr);

        if (bHit)
        {
            float Distance = HitResult.Distance;
            Result.Ranges.Add(Distance);
            Result.Intensities.Add(1.0f);  // Full intensity on hit
            Result.HitPoints.Add(HitResult.ImpactPoint);
            Result.HitActorNames.Add(HitResult.GetActor() ? HitResult.GetActor()->GetName() : TEXT("Unknown"));

            // Debug draw if enabled
            if (bDrawDebugRays)
            {
                DrawDebugLine(GetWorld(), Origin, HitResult.ImpactPoint, FColor::Red, false, DebugRayDuration, 0, 1.0f);
                DrawDebugPoint(GetWorld(), HitResult.ImpactPoint, 5.0f, FColor::Yellow, false, DebugRayDuration);
            }
        }
        else
        {
            Result.Ranges.Add(RangeMax);  // Max range = no hit
            Result.Intensities.Add(0.0f);
            Result.HitPoints.Add(RayEnd);
            Result.HitActorNames.Add(TEXT(""));

            // Debug draw if enabled
            if (bDrawDebugRays)
            {
                DrawDebugLine(GetWorld(), Origin, RayEnd, FColor::Green, false, DebugRayDuration, 0, 0.5f);
            }
        }
    }

    return Result;
}

bool ADimensionsCollector::ExportData(const FString& Filename, const FString& Format)
{
    UE_LOG(LogTemp, Log, TEXT("DimensionsCollector: Exporting data to %s (format: %s)"), 
           *Filename, *Format);

    // TODO: Call Python export functions via bridge
    // For now, just log the request

    return true;
}

void ADimensionsCollector::UpdateRobotTracking(const FString& RobotID, float DeltaTime)
{
    FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    if (!Data || !Data->Actor)
    {
        return;
    }

    // Update position and orientation
    FVector NewPosition = Data->Actor->GetActorLocation();
    FQuat NewOrientation = Data->Actor->GetActorQuat();

    // Calculate velocity
    if (DeltaTime > 0.0f)
    {
        FVector PositionDelta = NewPosition - Data->LastPosition;
        Data->Velocity = PositionDelta / DeltaTime;
    }

    // Update stored values
    Data->LastPosition = Data->Position;
    Data->Position = NewPosition;
    Data->Orientation = NewOrientation;
    Data->LastUpdateTime = TotalTime;

    // TODO: Publish to ROS2 topics (via Python bridge)
}

FRobotDimensions ADimensionsCollector::CalculateDimensions(UMeshComponent* MeshComponent) const
{
    FRobotDimensions Dimensions;

    if (!MeshComponent)
    {
        return Dimensions;
    }

    // Get bounds
    FBox Bounds = MeshComponent->Bounds.GetBox();
    FVector Extent = Bounds.GetExtent();

    // Calculate dimensions
    Dimensions.Width = Extent.Y * 2.0f;   // Y axis
    Dimensions.Height = Extent.Z * 2.0f;  // Z axis
    Dimensions.Length = Extent.X * 2.0f;  // X axis

    // Bounding sphere radius
    Dimensions.Radius = FMath::Max3(Extent.X, Extent.Y, Extent.Z);

    // Rough volume estimate (box volume)
    Dimensions.Volume = Dimensions.Width * Dimensions.Height * Dimensions.Length;

    return Dimensions;
}

FBoundingBox ADimensionsCollector::CalculateBoundingBox(UMeshComponent* MeshComponent) const
{
    FBoundingBox BoundingBox;

    if (!MeshComponent)
    {
        return BoundingBox;
    }

    // Get bounds
    FBox Bounds = MeshComponent->Bounds.GetBox();

    BoundingBox.Min = Bounds.Min;
    BoundingBox.Max = Bounds.Max;
    BoundingBox.Center = Bounds.GetCenter();
    BoundingBox.Extent = Bounds.GetExtent();

    return BoundingBox;
}

// ============================================================================
// OBSTACLE DETECTION & CLASSIFICATION
// ============================================================================

TArray<FObstacleInfo> ADimensionsCollector::DetectObstacles(const FString& RobotID, float DetectionRadius)
{
    TArray<FObstacleInfo> Obstacles;

    FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    if (!Data)
    {
        UE_LOG(LogTemp, Warning, TEXT("DIMC: Cannot detect obstacles for unknown robot %s"), *RobotID);
        return Obstacles;
    }

    // Get all overlapping actors within detection radius
    TArray<FOverlapResult> OverlapResults;
    FCollisionShape SphereShape = FCollisionShape::MakeSphere(DetectionRadius);
    
    bool bHasOverlaps = GetWorld()->OverlapMultiByChannel(
        OverlapResults,
        Data->Position,
        FQuat::Identity,
        ECollisionChannel::ECC_Visibility,
        SphereShape
    );

    if (!bHasOverlaps)
    {
        return Obstacles;
    }

    // Process each overlapping actor
    for (const FOverlapResult& Overlap : OverlapResults)
    {
        AActor* HitActor = Overlap.GetActor();
        if (!HitActor || HitActor == Data->Actor)
        {
            continue;  // Skip self
        }

        // Check if it's another tracked robot
        bool bIsRobot = false;
        FString OtherRobotID;
        for (const auto& KV : TrackedRobots)
        {
            if (KV.Value.Actor == HitActor)
            {
                bIsRobot = true;
                OtherRobotID = KV.Key;
                break;
            }
        }

        FObstacleInfo Obstacle;
        Obstacle.ObstacleID = FString::Printf(TEXT("OBS_%s_%d"), *RobotID, Obstacles.Num());
        Obstacle.Position = HitActor->GetActorLocation();
        Obstacle.Distance = FVector::Dist(Data->Position, Obstacle.Position);
        Obstacle.RelativeVelocity = FVector::ZeroVector;  // Will be calculated if dynamic
        Obstacle.Timestamp = TotalTime;
        Obstacle.ActorName = HitActor->GetName();

        // Calculate bounding box
        UMeshComponent* ObstacleMesh = HitActor->FindComponentByClass<UMeshComponent>();
        if (ObstacleMesh)
        {
            Obstacle.BoundingBox = CalculateBoundingBox(ObstacleMesh);
        }

        // Classify the obstacle
        if (bIsRobot)
        {
            Obstacle.Type = EObstacleType::Robot;
            Obstacle.AssociatedRobotID = OtherRobotID;
            // Calculate relative velocity
            const FRobotTrackingData* OtherData = TrackedRobots.Find(OtherRobotID);
            if (OtherData)
            {
                Obstacle.RelativeVelocity = OtherData->Velocity - Data->Velocity;
            }
        }
        else
        {
            Obstacle.Type = ClassifyObstacle(HitActor);
        }

        // Calculate collision risk
        float SafetyDistance = 100.0f;  // Default 1 meter in cm
        for (const auto& Zone : Data->SafetyZones)
        {
            SafetyDistance = FMath::Max(SafetyDistance, Zone.WarningRadius);
        }
        Obstacle.CollisionRisk = CalculateCollisionRisk(Data, Obstacle, SafetyDistance);

        Obstacles.Add(Obstacle);
    }

    // Sort by distance
    Obstacles.Sort([](const FObstacleInfo& A, const FObstacleInfo& B) {
        return A.Distance < B.Distance;
    });

    // Debug visualization
    if (bDrawDebugRays)
    {
        for (const auto& Obs : Obstacles)
        {
            FColor DebugColor = (Obs.CollisionRisk > 0.7f) ? FColor::Red :
                                (Obs.CollisionRisk > 0.3f) ? FColor::Yellow : FColor::Green;
            DrawDebugSphere(GetWorld(), Obs.Position, 20.0f, 8, DebugColor, false, DebugRayDuration);
        }
    }

    return Obstacles;
}

FObstacleInfo ADimensionsCollector::GetNearestObstacle(const FString& RobotID) const
{
    FObstacleInfo NearestObstacle;
    NearestObstacle.Distance = FLT_MAX;

    // Use the non-const version to detect obstacles
    ADimensionsCollector* MutableThis = const_cast<ADimensionsCollector*>(this);
    TArray<FObstacleInfo> Obstacles = MutableThis->DetectObstacles(RobotID, 1000.0f);

    if (Obstacles.Num() > 0)
    {
        return Obstacles[0];  // Already sorted by distance
    }

    return NearestObstacle;
}

bool ADimensionsCollector::IsPathClear(const FVector& Start, const FVector& End, float PathWidth)
{
    FHitResult HitResult;
    
    // Use a sphere sweep for path width
    FCollisionQueryParams QueryParams;
    QueryParams.bTraceComplex = false;
    QueryParams.AddIgnoredActor(this);

    // Ignore all tracked robots
    for (const auto& KV : TrackedRobots)
    {
        if (KV.Value.Actor)
        {
            QueryParams.AddIgnoredActor(KV.Value.Actor);
        }
    }

    FCollisionShape SphereShape = FCollisionShape::MakeSphere(PathWidth / 2.0f);

    bool bHit = GetWorld()->SweepSingleByChannel(
        HitResult,
        Start,
        End,
        FQuat::Identity,
        ECollisionChannel::ECC_Visibility,
        SphereShape,
        QueryParams
    );

    // Debug visualization
    if (bDrawDebugRays)
    {
        FColor PathColor = bHit ? FColor::Red : FColor::Green;
        DrawDebugCylinder(GetWorld(), Start, End, PathWidth / 2.0f, 12, PathColor, false, DebugRayDuration);
    }

    return !bHit;
}

float ADimensionsCollector::GetCollisionRisk(const FString& RobotID) const
{
    const FRobotTrackingData* Data = TrackedRobots.Find(RobotID);
    if (!Data)
    {
        return 0.0f;
    }

    // Get nearest obstacle
    FObstacleInfo Nearest = GetNearestObstacle(RobotID);
    if (Nearest.Distance >= FLT_MAX)
    {
        return 0.0f;  // No obstacles
    }

    // Calculate safety distance based on robot dimensions
    float SafetyDistance = FMath::Max3(
        Data->Dimensions.Length,
        Data->Dimensions.Width,
        Data->Dimensions.Height
    ) * 1.5f;  // 1.5x robot size as safety margin

    // Consider velocity for dynamic risk
    float VelocityFactor = Data->Velocity.Size() / 100.0f;  // Normalize by 1m/s

    return CalculateCollisionRisk(Data, Nearest, SafetyDistance);
}

// ============================================================================
// HELPER METHODS
// ============================================================================

bool ADimensionsCollector::PerformRaycast(const FVector& Start, const FVector& End, 
                                          FHitResult& OutHit, AActor* IgnoreActor)
{
    FCollisionQueryParams QueryParams;
    QueryParams.bTraceComplex = bUseComplexCollision;
    QueryParams.AddIgnoredActor(this);
    
    if (IgnoreActor)
    {
        QueryParams.AddIgnoredActor(IgnoreActor);
    }

    return GetWorld()->LineTraceSingleByChannel(
        OutHit,
        Start,
        End,
        ECollisionChannel::ECC_Visibility,
        QueryParams
    );
}

EObstacleType ADimensionsCollector::ClassifyObstacle(AActor* Actor)
{
    if (!Actor)
    {
        return EObstacleType::Unknown;
    }

    // Check actor tags
    if (Actor->ActorHasTag(TEXT("Robot")))
    {
        return EObstacleType::Robot;
    }
    if (Actor->ActorHasTag(TEXT("Dynamic")) || Actor->ActorHasTag(TEXT("Movable")))
    {
        return EObstacleType::Dynamic;
    }
    if (Actor->ActorHasTag(TEXT("Boundary")) || Actor->ActorHasTag(TEXT("Wall")))
    {
        return EObstacleType::Boundary;
    }
    if (Actor->ActorHasTag(TEXT("Static")))
    {
        return EObstacleType::Static;
    }

    // Check if actor has physics simulation enabled (dynamic)
    UPrimitiveComponent* PrimComp = Actor->FindComponentByClass<UPrimitiveComponent>();
    if (PrimComp && PrimComp->IsSimulatingPhysics())
    {
        return EObstacleType::Dynamic;
    }

    // Check mobility
    USceneComponent* RootComp = Actor->GetRootComponent();
    if (RootComp)
    {
        if (RootComp->Mobility == EComponentMobility::Static)
        {
            return EObstacleType::Static;
        }
        else if (RootComp->Mobility == EComponentMobility::Movable)
        {
            // Could be dynamic, but default to static if not simulating
            return EObstacleType::Static;
        }
    }

    return EObstacleType::Unknown;
}

float ADimensionsCollector::CalculateCollisionRisk(const FRobotTrackingData* RobotData, 
                                                    const FObstacleInfo& Obstacle, 
                                                    float SafetyDistance)
{
    if (!RobotData || Obstacle.Distance <= 0.0f)
    {
        return 0.0f;
    }

    // Base risk from distance
    float DistanceRisk = 0.0f;
    if (Obstacle.Distance < SafetyDistance)
    {
        DistanceRisk = 1.0f - (Obstacle.Distance / SafetyDistance);
    }

    // Velocity risk - are we moving towards the obstacle?
    float VelocityRisk = 0.0f;
    if (RobotData->Velocity.SizeSquared() > 1.0f)
    {
        FVector ToObstacle = (Obstacle.Position - RobotData->Position).GetSafeNormal();
        float DotProduct = FVector::DotProduct(RobotData->Velocity.GetSafeNormal(), ToObstacle);
        
        if (DotProduct > 0.0f)
        {
            // Moving towards obstacle
            VelocityRisk = DotProduct * (RobotData->Velocity.Size() / 100.0f);  // Normalize by 1m/s
        }
    }

    // Obstacle type weight
    float TypeWeight = 1.0f;
    switch (Obstacle.Type)
    {
        case EObstacleType::Robot:
            TypeWeight = 1.5f;  // Higher risk for other robots
            break;
        case EObstacleType::Dynamic:
            TypeWeight = 1.3f;
            break;
        case EObstacleType::Boundary:
            TypeWeight = 1.1f;
            break;
        default:
            TypeWeight = 1.0f;
    }

    // Combined risk
    float CombinedRisk = (DistanceRisk * 0.6f + VelocityRisk * 0.4f) * TypeWeight;

    return FMath::Clamp(CombinedRisk, 0.0f, 1.0f);
}

// ============================================================================
// DEFAULT PROFILES - STATIC METHODS
// ============================================================================

TArray<FSensorDefinition> ADimensionsCollector::GetDefaultSensorsForType(ERobotType RobotType)
{
    TArray<FSensorDefinition> Sensors;

    FSensorDefinition LidarSensor;
    LidarSensor.Type = ESensorType::LIDAR;
    LidarSensor.SensorName = TEXT("DefaultLidar");
    LidarSensor.bEnabled = true;

    switch (RobotType)
    {
        case ERobotType::IndustrialArm:
            // Industrial arms need 360-degree coverage at the base
            LidarSensor.MountOffset = FTransform(FVector(0, 0, 50));  // 50cm above base
            LidarSensor.RayCount = 180;
            LidarSensor.RangeMin = 10.0f;
            LidarSensor.RangeMax = 500.0f;  // 5m range
            LidarSensor.FOVHorizontal = 360.0f;
            LidarSensor.UpdateRate = 30.0f;
            break;

        case ERobotType::MobileRobot:
            // Mobile robots need forward-focused LIDAR
            LidarSensor.MountOffset = FTransform(FVector(20, 0, 30));  // Front mounted
            LidarSensor.RayCount = 360;
            LidarSensor.RangeMin = 5.0f;
            LidarSensor.RangeMax = 1200.0f;  // 12m range
            LidarSensor.FOVHorizontal = 270.0f;
            LidarSensor.UpdateRate = 30.0f;
            break;

        case ERobotType::Humanoid:
            // Humanoids need head-mounted LIDAR
            LidarSensor.MountOffset = FTransform(FVector(10, 0, 170));  // Head height
            LidarSensor.RayCount = 240;
            LidarSensor.RangeMin = 10.0f;
            LidarSensor.RangeMax = 800.0f;  // 8m range
            LidarSensor.FOVHorizontal = 180.0f;
            LidarSensor.UpdateRate = 30.0f;
            break;

        case ERobotType::Drone:
            // Drones need downward + forward LIDAR
            LidarSensor.MountOffset = FTransform(FRotator(-30, 0, 0), FVector(10, 0, 0));
            LidarSensor.RayCount = 120;
            LidarSensor.RangeMin = 5.0f;
            LidarSensor.RangeMax = 2000.0f;  // 20m range
            LidarSensor.FOVHorizontal = 90.0f;
            LidarSensor.UpdateRate = 30.0f;
            break;

        case ERobotType::Collaborative:
            // Collaborative robots need close-range high-density coverage
            LidarSensor.MountOffset = FTransform(FVector(0, 0, 30));
            LidarSensor.RayCount = 360;
            LidarSensor.RangeMin = 5.0f;
            LidarSensor.RangeMax = 300.0f;  // 3m range - focus on nearby
            LidarSensor.FOVHorizontal = 360.0f;
            LidarSensor.UpdateRate = 60.0f;  // Higher rate for safety
            break;

        case ERobotType::SingleActuator:
        case ERobotType::Generic:
        default:
            // Basic coverage
            LidarSensor.MountOffset = FTransform(FVector(0, 0, 0));
            LidarSensor.RayCount = 90;
            LidarSensor.RangeMin = 5.0f;
            LidarSensor.RangeMax = 500.0f;
            LidarSensor.FOVHorizontal = 180.0f;
            LidarSensor.UpdateRate = 30.0f;
            break;
    }

    Sensors.Add(LidarSensor);
    return Sensors;
}

TArray<FSafetyZoneConfig> ADimensionsCollector::GetDefaultSafetyZonesForType(ERobotType RobotType)
{
    TArray<FSafetyZoneConfig> Zones;

    FSafetyZoneConfig CriticalZone;
    CriticalZone.ZoneName = TEXT("CriticalZone");
    CriticalZone.ZoneColor = FLinearColor::Red;

    FSafetyZoneConfig WarningZone;
    WarningZone.ZoneName = TEXT("WarningZone");
    WarningZone.ZoneColor = FLinearColor::Yellow;

    FSafetyZoneConfig CautionZone;
    CautionZone.ZoneName = TEXT("CautionZone");
    CautionZone.ZoneColor = FLinearColor::Green;

    switch (RobotType)
    {
        case ERobotType::IndustrialArm:
            // Industrial arms have large work envelope
            CriticalZone.WarningRadius = 50.0f;
            CriticalZone.StopRadius = 30.0f;
            WarningZone.WarningRadius = 150.0f;
            WarningZone.StopRadius = 100.0f;
            CautionZone.WarningRadius = 300.0f;
            CautionZone.StopRadius = 200.0f;
            break;

        case ERobotType::MobileRobot:
            CriticalZone.WarningRadius = 30.0f;
            CriticalZone.StopRadius = 15.0f;
            WarningZone.WarningRadius = 80.0f;
            WarningZone.StopRadius = 50.0f;
            CautionZone.WarningRadius = 200.0f;
            CautionZone.StopRadius = 120.0f;
            break;

        case ERobotType::Humanoid:
            CriticalZone.WarningRadius = 40.0f;
            CriticalZone.StopRadius = 20.0f;
            WarningZone.WarningRadius = 100.0f;
            WarningZone.StopRadius = 60.0f;
            CautionZone.WarningRadius = 200.0f;
            CautionZone.StopRadius = 150.0f;
            break;

        case ERobotType::Drone:
            // Drones need 3D safety zones
            CriticalZone.WarningRadius = 100.0f;
            CriticalZone.StopRadius = 50.0f;
            WarningZone.WarningRadius = 300.0f;
            WarningZone.StopRadius = 200.0f;
            CautionZone.WarningRadius = 500.0f;
            CautionZone.StopRadius = 400.0f;
            break;

        case ERobotType::Collaborative:
            // Collaborative robots have tighter safety zones
            CriticalZone.WarningRadius = 20.0f;
            CriticalZone.StopRadius = 10.0f;
            WarningZone.WarningRadius = 50.0f;
            WarningZone.StopRadius = 30.0f;
            CautionZone.WarningRadius = 100.0f;
            CautionZone.StopRadius = 70.0f;
            break;

        default:
            // Generic defaults
            CriticalZone.WarningRadius = 30.0f;
            CriticalZone.StopRadius = 15.0f;
            WarningZone.WarningRadius = 80.0f;
            WarningZone.StopRadius = 50.0f;
            CautionZone.WarningRadius = 150.0f;
            CautionZone.StopRadius = 100.0f;
            break;
    }

    Zones.Add(CriticalZone);
    Zones.Add(WarningZone);
    Zones.Add(CautionZone);

    return Zones;
}

TArray<FSafetyZoneConfig> ADimensionsCollector::CalculateSafetyZonesFromDimensions(const FRobotDimensions& Dimensions)
{
    TArray<FSafetyZoneConfig> Zones;

    // Base the zones on the largest dimension
    float MaxDim = FMath::Max3(Dimensions.Length, Dimensions.Width, Dimensions.Height);

    FSafetyZoneConfig CriticalZone;
    CriticalZone.ZoneName = TEXT("CriticalZone");
    CriticalZone.ZoneColor = FLinearColor::Red;
    CriticalZone.StopRadius = MaxDim * 0.3f;
    CriticalZone.WarningRadius = MaxDim * 0.5f;

    FSafetyZoneConfig WarningZone;
    WarningZone.ZoneName = TEXT("WarningZone");
    WarningZone.ZoneColor = FLinearColor::Yellow;
    WarningZone.StopRadius = MaxDim * 0.8f;
    WarningZone.WarningRadius = MaxDim * 1.2f;

    FSafetyZoneConfig CautionZone;
    CautionZone.ZoneName = TEXT("CautionZone");
    CautionZone.ZoneColor = FLinearColor::Green;
    CautionZone.StopRadius = MaxDim * 1.5f;
    CautionZone.WarningRadius = MaxDim * 2.5f;

    Zones.Add(CriticalZone);
    Zones.Add(WarningZone);
    Zones.Add(CautionZone);

    return Zones;
}
