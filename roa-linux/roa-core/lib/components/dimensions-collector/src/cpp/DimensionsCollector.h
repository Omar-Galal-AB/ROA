// DimensionsCollector.h
// UE5 Plugin for real-time spatial data collection
// Enhanced with Raycast LIDAR, Obstacle Detection, and FTI Integration
// Version: 2.0

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/World.h"
#include "CollisionQueryParams.h"
#include "DimensionsCollector.generated.h"

// ============================================================================
// ENUMERATIONS
// ============================================================================

/**
 * Sensor type enumeration
 */
UENUM(BlueprintType)
enum class ESensorType : uint8
{
    LIDAR           UMETA(DisplayName = "LIDAR"),
    DepthCamera     UMETA(DisplayName = "Depth Camera"),
    Ultrasonic      UMETA(DisplayName = "Ultrasonic"),
    IMU             UMETA(DisplayName = "IMU"),
    Encoder         UMETA(DisplayName = "Encoder"),
    ProximitySensor UMETA(DisplayName = "Proximity Sensor"),
    ContactSensor   UMETA(DisplayName = "Contact Sensor")
};

/**
 * Robot type enumeration for default profile selection
 */
UENUM(BlueprintType)
enum class ERobotType : uint8
{
    IndustrialArm   UMETA(DisplayName = "Industrial Arm"),
    MobileRobot     UMETA(DisplayName = "Mobile Robot"),
    Humanoid        UMETA(DisplayName = "Humanoid"),
    Drone           UMETA(DisplayName = "Drone"),
    SingleActuator  UMETA(DisplayName = "Single Actuator"),
    Collaborative   UMETA(DisplayName = "Collaborative Robot"),
    Generic         UMETA(DisplayName = "Generic")
};

/**
 * Obstacle type classification
 */
UENUM(BlueprintType)
enum class EObstacleType : uint8
{
    Static          UMETA(DisplayName = "Static"),      // Walls, structures
    Dynamic         UMETA(DisplayName = "Dynamic"),     // Moving objects (not robots)
    Robot           UMETA(DisplayName = "Robot"),       // Other robots in system
    Boundary        UMETA(DisplayName = "Boundary"),    // Work area boundaries
    Unknown         UMETA(DisplayName = "Unknown")
};

// ============================================================================
// DATA STRUCTURES
// ============================================================================

/**
 * Robot dimensions structure
 */
USTRUCT(BlueprintType)
struct FRobotDimensions
{
    GENERATED_BODY()

    // All values in centimeters (UE5 native units)
    UPROPERTY(BlueprintReadWrite, Category = "Dimensions")
    float Width = 0.0f;     // Y axis

    UPROPERTY(BlueprintReadWrite, Category = "Dimensions")
    float Height = 0.0f;    // Z axis

    UPROPERTY(BlueprintReadWrite, Category = "Dimensions")
    float Length = 0.0f;    // X axis

    UPROPERTY(BlueprintReadWrite, Category = "Dimensions")
    float BoundingRadius = 0.0f;  // For sphere checks

    UPROPERTY(BlueprintReadWrite, Category = "Dimensions")
    float Volume = 0.0f;

    // True if extracted from URDF, false if calculated from mesh
    UPROPERTY(BlueprintReadWrite, Category = "Dimensions")
    bool bFromURDF = false;
};

/**
 * Bounding box structure
 */
USTRUCT(BlueprintType)
struct FBoundingBox
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, Category = "BoundingBox")
    FVector Min = FVector::ZeroVector;

    UPROPERTY(BlueprintReadWrite, Category = "BoundingBox")
    FVector Max = FVector::ZeroVector;

    UPROPERTY(BlueprintReadWrite, Category = "BoundingBox")
    FVector Center = FVector::ZeroVector;

    UPROPERTY(BlueprintReadWrite, Category = "BoundingBox")
    FVector Extent = FVector::ZeroVector;
};

/**
 * Safety zone configuration
 */
USTRUCT(BlueprintType)
struct FSafetyZoneConfig
{
    GENERATED_BODY()

    // All values in centimeters (UE5 native units)
    UPROPERTY(BlueprintReadWrite, Category = "Safety")
    float WarningZone = 50.0f;    // Yellow zone (50cm default)

    UPROPERTY(BlueprintReadWrite, Category = "Safety")
    float CriticalZone = 20.0f;   // Red zone (20cm default)

    UPROPERTY(BlueprintReadWrite, Category = "Safety")
    float StopZone = 5.0f;        // Emergency stop (5cm default)

    // True if from URDF, false if calculated
    UPROPERTY(BlueprintReadWrite, Category = "Safety")
    bool bFromURDF = false;
};

/**
 * Sensor definition structure
 */
USTRUCT(BlueprintType)
struct FSensorDefinition
{
    GENERATED_BODY()

    // Sensor identification
    UPROPERTY(BlueprintReadWrite, Category = "Sensor")
    FString SensorName;

    UPROPERTY(BlueprintReadWrite, Category = "Sensor")
    ESensorType Type = ESensorType::LIDAR;

    // Mount position (relative to robot base)
    UPROPERTY(BlueprintReadWrite, Category = "Sensor")
    FString MountLinkName = "base_link";

    UPROPERTY(BlueprintReadWrite, Category = "Sensor")
    FTransform MountOffset;

    // ===== LIDAR Parameters =====
    UPROPERTY(BlueprintReadWrite, Category = "Sensor|LIDAR")
    int32 RayCount = 360;

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|LIDAR")
    float RangeMin = 10.0f;      // cm (0.1m)

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|LIDAR")
    float RangeMax = 1000.0f;    // cm (10m)

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|LIDAR")
    float FOVHorizontal = 360.0f;  // degrees

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|LIDAR")
    float FOVVertical = 30.0f;     // degrees

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|LIDAR")
    int32 VerticalLayers = 1;

    // ===== Depth Camera Parameters =====
    UPROPERTY(BlueprintReadWrite, Category = "Sensor|DepthCamera")
    int32 ImageWidth = 640;

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|DepthCamera")
    int32 ImageHeight = 480;

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|DepthCamera")
    float CameraFOV = 60.0f;    // degrees

    // ===== Ultrasonic Parameters =====
    UPROPERTY(BlueprintReadWrite, Category = "Sensor|Ultrasonic")
    float UltrasonicRange = 200.0f;  // cm (2m)

    UPROPERTY(BlueprintReadWrite, Category = "Sensor|Ultrasonic")
    float BeamAngle = 15.0f;    // degrees

    // True if from URDF, false if from default profile
    UPROPERTY(BlueprintReadWrite, Category = "Sensor")
    bool bFromURDF = false;
};

/**
 * LIDAR scan result
 */
USTRUCT(BlueprintType)
struct FLidarScanResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite)
    TArray<float> Ranges;       // Distance per ray in cm

    UPROPERTY(BlueprintReadWrite)
    TArray<float> Intensities;  // Intensity per ray (0-1)

    UPROPERTY(BlueprintReadWrite)
    TArray<FVector> HitPoints;  // World position of hits

    UPROPERTY(BlueprintReadWrite)
    TArray<FString> HitActorNames;  // Names of hit actors

    UPROPERTY(BlueprintReadWrite)
    float AngleMin = -PI;       // radians

    UPROPERTY(BlueprintReadWrite)
    float AngleMax = PI;        // radians

    UPROPERTY(BlueprintReadWrite)
    float AngleIncrement = 0.0f;

    UPROPERTY(BlueprintReadWrite)
    float Timestamp = 0.0f;
};

/**
 * Detected obstacle information
 */
USTRUCT(BlueprintType)
struct FObstacleInfo
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    FVector Position = FVector::ZeroVector;  // World position in cm

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    float Distance = 0.0f;       // Distance from robot in cm

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    EObstacleType Type = EObstacleType::Unknown;

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    float CollisionRisk = 0.0f;  // 0.0 (safe) to 1.0 (imminent collision)

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    FVector ApproachVector = FVector::ZeroVector;  // Direction of approach

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    FString ObstacleName;        // Name of obstacle actor

    UPROPERTY(BlueprintReadWrite, Category = "Obstacle")
    float Timestamp = 0.0f;
};

/**
 * Data flags indicating what was found in URDF
 */
USTRUCT(BlueprintType)
struct FDIMCDataFlags
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadWrite)
    bool bHasDimensions = false;

    UPROPERTY(BlueprintReadWrite)
    bool bHasSensors = false;

    UPROPERTY(BlueprintReadWrite)
    bool bHasSafetyZones = false;

    UPROPERTY(BlueprintReadWrite)
    bool bHasCollisionMesh = false;

    UPROPERTY(BlueprintReadWrite)
    bool bHasJointLimits = false;
};

/**
 * Complete robot configuration from FTI
 */
USTRUCT(BlueprintType)
struct FDIMCRobotConfig
{
    GENERATED_BODY()

    // ===== REQUIRED FIELDS =====
    UPROPERTY(BlueprintReadWrite, Category = "Required")
    FString RobotID;

    UPROPERTY(BlueprintReadWrite, Category = "Required")
    FString RobotName;

    UPROPERTY(BlueprintReadWrite, Category = "Required")
    AActor* RobotActor = nullptr;

    // ===== OPTIONAL FIELDS =====
    UPROPERTY(BlueprintReadWrite, Category = "Optional")
    FRobotDimensions Dimensions;

    UPROPERTY(BlueprintReadWrite, Category = "Optional")
    TArray<FSensorDefinition> Sensors;

    UPROPERTY(BlueprintReadWrite, Category = "Optional")
    FSafetyZoneConfig SafetyZones;

    UPROPERTY(BlueprintReadWrite, Category = "Optional")
    ERobotType RobotType = ERobotType::Generic;

    UPROPERTY(BlueprintReadWrite, Category = "Optional")
    FDIMCDataFlags DataFlags;
};

// ============================================================================
// MAIN CLASS
// ============================================================================

/**
 * Main Dimensions Collector class
 * Tracks robot positions, orientations, dimensions, and obstacles at 60Hz
 * Includes CPU Raycast LIDAR simulation and obstacle classification
 */
UCLASS(BlueprintType, Blueprintable)
class DIMENSIONSCOLLECTOR_API ADimensionsCollector : public AActor
{
    GENERATED_BODY()

public:
    // Constructor
    ADimensionsCollector();

protected:
    // Called when the game starts
    virtual void BeginPlay() override;

public:
    // Called every frame (60Hz tick)
    virtual void Tick(float DeltaTime) override;

    // ========================================================================
    // FTI INTEGRATION - Robot Registration
    // ========================================================================

    /**
     * Register a robot from FTI with full configuration
     * This is the primary method FTI should call after importing a robot
     * @param Config Complete robot configuration from FTI
     * @return True if registration successful
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|FTI")
    bool RegisterRobotFromFTI(const FDIMCRobotConfig& Config);

    /**
     * Register a robot for tracking (legacy/simple method)
     * @param RobotID Unique identifier for the robot
     * @param RobotActor The UE5 actor representing the robot
     * @return True if registration successful
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC")
    bool RegisterRobot(const FString& RobotID, AActor* RobotActor);

    /**
     * Unregister a robot from tracking
     * @param RobotID Robot identifier to remove
     * @return True if unregistration successful
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC")
    bool UnregisterRobot(const FString& RobotID);

    // ========================================================================
    // POSITION & ORIENTATION TRACKING
    // ========================================================================

    /**
     * Get current position of a robot
     * @param RobotID Robot identifier
     * @return World position vector in cm
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Tracking")
    FVector GetRobotPosition(const FString& RobotID) const;

    /**
     * Get current orientation of a robot
     * @param RobotID Robot identifier
     * @return Rotation quaternion
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Tracking")
    FQuat GetRobotOrientation(const FString& RobotID) const;

    /**
     * Get velocity of a robot
     * @param RobotID Robot identifier
     * @return Velocity vector in cm/s
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Tracking")
    FVector GetRobotVelocity(const FString& RobotID) const;

    /**
     * Get robot dimensions
     * @param RobotID Robot identifier
     * @return Dimension structure
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Tracking")
    FRobotDimensions GetRobotDimensions(const FString& RobotID) const;

    /**
     * Get bounding box for a robot
     * @param RobotID Robot identifier
     * @return Bounding box structure
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Tracking")
    FBoundingBox GetRobotBoundingBox(const FString& RobotID) const;

    /**
     * Get distance between two robots
     * @param RobotID1 First robot identifier
     * @param RobotID2 Second robot identifier
     * @return Distance in centimeters
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Tracking")
    float GetDistanceBetweenRobots(const FString& RobotID1, const FString& RobotID2) const;

    // ========================================================================
    // SENSOR SIMULATION - CPU RAYCAST LIDAR
    // ========================================================================

    /**
     * Perform a LIDAR scan for a robot using CPU raycasts
     * @param RobotID Robot identifier
     * @param SensorName Name of the sensor to use (must be registered)
     * @return LIDAR scan result with ranges and hit information
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Sensors")
    FLidarScanResult PerformLidarScan(const FString& RobotID, const FString& SensorName);

    /**
     * Perform a LIDAR scan with custom parameters (no sensor registration needed)
     * @param Origin Scan origin position
     * @param Orientation Scan orientation
     * @param RayCount Number of rays
     * @param RangeMax Maximum range in cm
     * @param FOVHorizontal Horizontal field of view in degrees
     * @return LIDAR scan result
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Sensors")
    FLidarScanResult PerformCustomLidarScan(
        const FVector& Origin,
        const FQuat& Orientation,
        int32 RayCount = 360,
        float RangeMax = 1000.0f,
        float FOVHorizontal = 360.0f
    );

    /**
     * Register a sensor for a robot
     * @param RobotID Robot identifier
     * @param SensorDef Sensor definition
     * @return True if registration successful
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Sensors")
    bool RegisterSensor(const FString& RobotID, const FSensorDefinition& SensorDef);

    // ========================================================================
    // OBSTACLE DETECTION & CLASSIFICATION
    // ========================================================================

    /**
     * Detect obstacles around a robot using registered sensors
     * @param RobotID Robot identifier
     * @return Array of detected obstacles
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Obstacles")
    TArray<FObstacleInfo> DetectObstacles(const FString& RobotID);

    /**
     * Get the nearest obstacle to a robot
     * @param RobotID Robot identifier
     * @param OutObstacle Output obstacle info
     * @return True if an obstacle was found
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Obstacles")
    bool GetNearestObstacle(const FString& RobotID, FObstacleInfo& OutObstacle);

    /**
     * Check if a path is clear for a robot
     * @param RobotID Robot identifier
     * @param TargetPosition Target position to check
     * @param OutBlockingObstacle If blocked, the obstacle blocking the path
     * @return True if path is clear
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Obstacles")
    bool IsPathClear(const FString& RobotID, const FVector& TargetPosition, FObstacleInfo& OutBlockingObstacle);

    /**
     * Get collision risk level for a robot (0.0 = safe, 1.0 = collision)
     * @param RobotID Robot identifier
     * @return Collision risk level
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Obstacles")
    float GetCollisionRisk(const FString& RobotID) const;

    // ========================================================================
    // DATA EXPORT
    // ========================================================================

    /**
     * Export tracking data to file
     * @param Filename Output filename
     * @param Format Export format ("json", "csv", "rosbag")
     * @return True if export successful
     */
    UFUNCTION(BlueprintCallable, Category = "DIMC|Export")
    bool ExportData(const FString& Filename, const FString& Format = "json");

    // ========================================================================
    // DEFAULT PROFILES
    // ========================================================================

    /**
     * Get default sensor configuration for a robot type
     * @param RobotType Type of robot
     * @return Array of default sensor definitions
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Defaults")
    static TArray<FSensorDefinition> GetDefaultSensorsForType(ERobotType RobotType);

    /**
     * Get default safety zones for a robot type
     * @param RobotType Type of robot
     * @return Default safety zone configuration
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Defaults")
    static FSafetyZoneConfig GetDefaultSafetyZonesForType(ERobotType RobotType);

    /**
     * Calculate safety zones from robot dimensions
     * @param Dimensions Robot dimensions
     * @return Calculated safety zones
     */
    UFUNCTION(BlueprintCallable, BlueprintPure, Category = "DIMC|Defaults")
    static FSafetyZoneConfig CalculateSafetyZonesFromDimensions(const FRobotDimensions& Dimensions);

protected:
    // ========================================================================
    // INTERNAL METHODS
    // ========================================================================

    /**
     * Update tracking for a single robot
     * @param RobotID Robot identifier
     * @param DeltaTime Time since last update
     */
    void UpdateRobotTracking(const FString& RobotID, float DeltaTime);

    /**
     * Update sensor simulations for a robot
     * @param RobotID Robot identifier
     */
    void UpdateSensorSimulations(const FString& RobotID);

    /**
     * Calculate dimensions from mesh
     * @param MeshComponent Mesh component to measure
     * @return Calculated dimensions
     */
    FRobotDimensions CalculateDimensions(UMeshComponent* MeshComponent) const;

    /**
     * Calculate bounding box from mesh
     * @param MeshComponent Mesh component to measure
     * @return Calculated bounding box
     */
    FBoundingBox CalculateBoundingBox(UMeshComponent* MeshComponent) const;

    /**
     * Perform a single raycast for LIDAR simulation
     * @param Start Ray start position
     * @param End Ray end position
     * @param OutHitResult Hit result if ray hits something
     * @param IgnoreActor Actor to ignore (usually the robot itself)
     * @return True if ray hit something
     */
    bool PerformRaycast(
        const FVector& Start,
        const FVector& End,
        FHitResult& OutHitResult,
        AActor* IgnoreActor = nullptr
    ) const;

    /**
     * Classify an obstacle based on hit result
     * @param HitResult The hit result from raycast
     * @param DetectingRobotID The robot that detected this obstacle
     * @return Classified obstacle type
     */
    EObstacleType ClassifyObstacle(const FHitResult& HitResult, const FString& DetectingRobotID) const;

    /**
     * Calculate collision risk based on distance and velocity
     * @param Distance Distance to obstacle in cm
     * @param RobotVelocity Robot velocity vector
     * @param SafetyZones Safety zone configuration
     * @return Risk level 0.0 to 1.0
     */
    float CalculateCollisionRisk(
        float Distance,
        const FVector& RobotVelocity,
        const FSafetyZoneConfig& SafetyZones
    ) const;

    /**
     * Apply default configuration for missing data
     * @param Config Configuration to fill
     */
    void ApplyDefaultsToConfig(FDIMCRobotConfig& Config);

private:
    // ========================================================================
    // INTERNAL DATA STRUCTURES
    // ========================================================================

    // Extended robot tracking data
    struct FRobotTrackingData
    {
        // Basic info
        FString RobotID;
        FString RobotName;
        AActor* Actor = nullptr;
        ERobotType RobotType = ERobotType::Generic;

        // Position/Orientation
        FVector Position = FVector::ZeroVector;
        FQuat Orientation = FQuat::Identity;
        FVector Velocity = FVector::ZeroVector;
        FVector LastPosition = FVector::ZeroVector;
        float LastUpdateTime = 0.0f;

        // Dimensions
        FRobotDimensions Dimensions;
        FBoundingBox BoundingBox;

        // Sensors
        TArray<FSensorDefinition> Sensors;
        TMap<FString, FLidarScanResult> LastSensorScans;

        // Safety
        FSafetyZoneConfig SafetyZones;

        // Obstacles
        TArray<FObstacleInfo> DetectedObstacles;
        float CurrentCollisionRisk = 0.0f;

        // Data flags
        FDIMCDataFlags DataFlags;
    };

    // ========================================================================
    // MEMBER VARIABLES
    // ========================================================================

    // Map of robot ID to tracking data
    TMap<FString, FRobotTrackingData> TrackedRobots;

    // Set of known robot IDs (for obstacle classification)
    TSet<FString> KnownRobotIDs;

    // Collision query params
    FCollisionQueryParams CollisionParams;

    // ========================================================================
    // CONFIGURATION
    // ========================================================================

    // Update rate configuration
    UPROPERTY(EditAnywhere, Category = "DIMC|Config")
    float UpdateRate = 60.0f;  // Hz

    // Sensor update rate (can be lower than tracking rate)
    UPROPERTY(EditAnywhere, Category = "DIMC|Config")
    float SensorUpdateRate = 30.0f;  // Hz

    // Coordinate system
    UPROPERTY(EditAnywhere, Category = "DIMC|Config")
    FString CoordinateFrame = "World";

    // Enable debug drawing of raycasts
    UPROPERTY(EditAnywhere, Category = "DIMC|Debug")
    bool bDrawDebugRays = false;

    // Debug ray draw duration
    UPROPERTY(EditAnywhere, Category = "DIMC|Debug")
    float DebugRayDuration = 0.1f;

    // Total elapsed time
    float TotalTime = 0.0f;

    // Time since last sensor update
    float TimeSinceLastSensorUpdate = 0.0f;
};
