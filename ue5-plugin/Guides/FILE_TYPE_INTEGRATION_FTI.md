# ?? ROA Plugin - File Type Integration (FTI) System

**Automatic Robot Import & Assembly**

---

## ?? Overview

The FTI (File Type Integration) system allows UE5 to directly import robot files (URDF, XACRO, SDF) and automatically assemble them in the scene. After activating the ROA plugin, UE5 will recognize additional file formats.

---

## ?? Supported File Types

### **After ROA Plugin Activation:**

```
? .urdf   - Universal Robot Description Format
? .xacro  - XML Macros (ROS format)
? .sdf- Simulation Description Format (Gazebo)
? .dae    - COLLADA (3D mesh format)
? .stl    - STereoLithography (mesh format)
? .obj    - Wavefront OBJ (mesh format)
```

---

## ?? How FTI Works

### **Workflow:**

```
1. Activate ROA Plugin
   ?
2. Plugin Registers File Importers
   ?
3. Drag & Drop URDF File into UE5
   ?
4. FTI Parses Robot Description
   ?
5. Creates ROARobotActor Blueprint
   ?
6. Imports Meshes & Materials
   ?
7. Assembles Kinematic Chain
   ?
8. Sets Up Physics & Collisions
   ?
9. Ready to Use in Scene
```

---

## ?? Implementation Status

### **Current Implementation:**

The ROA plugin currently provides the **foundation** for FTI, but manual URDF parsing needs to be added.

### **What's Already Implemented:** ?
- ? ROARobotActor class (robot representation)
- ? Network protocol for robot spawning
- ? Physics integration
- ? Collision system
- ? Joint control system
- ? Mesh loading capability

### **What Needs Implementation:** ??
- ?? URDF file parser
- ?? XACRO preprocessor
- ?? Asset factory for drag-drop
- ?? Automatic material assignment
- ?? Joint limit detection
- ?? Collision mesh generation

---

## ?? Implementation Guide

### **Phase 1: URDF Parser (Next Step)**

I'll create the URDF parser that reads robot description files:

```cpp
// ROAURDFParser.h
class FROAURDFParser
{
public:
    struct FRobotDescription
{
     FString RobotName;
        TArray<FLinkData> Links;
        TArray<FJointData> Joints;
        TArray<FMeshData> Meshes;
    };

    static bool ParseURDF(const FString& URDFFilePath, FRobotDescription& OutDescription);
    static AROARobotActor* ImportRobotFromURDF(UWorld* World, const FString& URDFPath);
};
```

### **Phase 2: Asset Factory**

Register custom asset importer:

```cpp
// ROAURDFFactory.h
class UROAURDFFactory : public UFactory
{
    GENERATED_BODY()

public:
    UROAURDFFactory();

    // UFactory interface
    virtual UObject* FactoryCreateFile(UClass* InClass, UObject* InParent, 
     FName InName, EObjectFlags Flags, const FString& Filename, 
const TCHAR* Parms, FFeedbackContext* Warn, bool& bOutOperationCanceled) override;
 
    virtual bool DoesSupportClass(UClass* Class) override;
    virtual bool FactoryCanImport(const FString& Filename) override;
};
```

### **Phase 3: Editor Integration**

Add content browser integration:

```cpp
void FROAModule::StartupModule()
{
    // ...existing code...

    // Register URDF asset type
    IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools").Get();
    
    TSharedRef<FROAAssetTypeActions> URDFAssetAction = MakeShared<FROAAssetTypeActions>();
    AssetTools.RegisterAssetTypeActions(URDFAssetAction);
}
```

---

## ?? Usage After FTI Implementation

### **Method 1: Drag & Drop (Future)**

```
1. Open Content Browser
2. Navigate to robot URDF file on disk
3. Drag .urdf file into Content Browser
4. FTI automatically:
   - Parses URDF
   - Imports meshes
 - Creates Blueprint
   - Sets up joints
5. Drag Blueprint into viewport
6. Robot ready to use!
```

### **Method 2: Import Dialog (Future)**

```
1. Content Browser ? Right-click
2. Import Asset ? Robot Description
3. Select .urdf, .xacro, or .sdf file
4. Configure import options:
   - Scale factor
   - Material assignment
   - Collision generation
5. Click Import
6. Robot Blueprint created
```

### **Method 3: Python API (Current)**

**This works NOW with current implementation:**

```python
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 9876))

# Spawn robot with URDF path
spawn_msg = {
    "message_id": "import-001",
    "timestamp": 1234567890.0,
    "message_type": "REQUEST",
    "command": "spawn_robot",
    "payload": {
"robot_id": "ur5e_001",
        "robot_type": "ur5e",
      "spawn_location": {"x": 0, "y": 0, "z": 100},
      "urdf_path": "D:/Robots/ur5e/ur5e.urdf"  # ? URDF import
    }
}

sock.send(json.dumps(spawn_msg).encode())
response = sock.recv(4096)
print(response.decode())
```

**Current Behavior:**
- Robot spawns at specified location
- Uses built-in UR5e model
- URDF path stored for reference
- **Future:** Will parse URDF and create custom robot

---

## ?? Let Me Implement FTI Now

Would you like me to implement the URDF parser and asset factory **right now**? 

I can create:

1. **ROAURDFParser.h/.cpp** - Parse URDF files
2. **ROAURDFFactory.h/.cpp** - Asset importer
3. **ROAAssetTypeActions.h/.cpp** - Content browser integration
4. **Updated ROAModule** - Register file types

This will enable:
- ? Drag & drop .urdf files into UE5
- ? Automatic robot assembly
- ? Material assignment
- ? Collision setup
- ? Joint configuration

---

## ?? FTI Architecture

```
ROA Plugin (Activated)
?
??? File Type Registration
?   ??? .urdf ? ROAURDFFactory
?   ??? .xacro ? ROAXacroFactory
?   ??? .sdf ? ROASDFFactory
?
??? Parser System
?   ??? XML Parser
?   ??? Link Extractor
?   ??? Joint Extractor
?   ??? Mesh Resolver
?
??? Asset Import Pipeline
?   ??? Mesh Import (.dae, .stl)
?   ??? Material Creation
?   ??? Texture Assignment
?   ??? Physics Setup
?
??? Robot Assembly
    ??? Create ROARobotActor
    ??? Build Kinematic Tree
    ??? Setup Joints
    ??? Configure Collisions
    ??? Apply Initial Pose
```

---

## ?? Example: Import UR5e from URDF

### **URDF File Structure:**
```xml
<?xml version="1.0"?>
<robot name="ur5e">
    <link name="base_link">
        <visual>
    <geometry>
        <mesh filename="package://ur_description/meshes/ur5e/visual/base.dae"/>
            </geometry>
        </visual>
        <collision>
    <geometry>
    <mesh filename="package://ur_description/meshes/ur5e/collision/base.stl"/>
      </geometry>
        </collision>
    </link>
    
    <joint name="shoulder_pan_joint" type="revolute">
 <origin xyz="0 0 0.163" rpy="0 0 0"/>
        <parent link="base_link"/>
        <child link="shoulder_link"/>
 <axis xyz="0 0 1"/>
        <limit lower="-6.28" upper="6.28" effort="150" velocity="3.15"/>
    </joint>
    
    <!-- More links and joints... -->
</robot>
```

### **After FTI Import:**

```
Content/ImportedRobots/ur5e/
??? BP_UR5e (Blueprint)
??? SM_Base (Static Mesh)
??? SM_Shoulder (Static Mesh)
??? SM_Elbow (Static Mesh)
??? SM_Wrist1 (Static Mesh)
??? SM_Wrist2 (Static Mesh)
??? SM_Wrist3 (Static Mesh)
??? M_Robot (Material)
??? T_RobotTexture (Texture)
```

**Blueprint Hierarchy:**
```
BP_UR5e (ROARobotActor)
??? BaseMesh (StaticMeshComponent)
??? ShoulderMesh (StaticMeshComponent)
?   ??? Joint: shoulder_pan [-6.28 to 6.28 rad]
??? ElbowMesh (StaticMeshComponent)
?   ??? Joint: elbow [-6.28 to 6.28 rad]
??? (More components...)
```

---

## ?? Quick Implementation Option

### **Option 1: Full FTI System (2-3 days work)**
- Complete URDF parser
- Asset factory
- Material system
- Collision generation
- **Benefit:** Drag & drop .urdf files

### **Option 2: Python-Based Import (Current + 1 hour)**
- Enhance `import_robot_file` command
- Python parses URDF
- Sends structured data to UE5
- UE5 assembles robot
- **Benefit:** Works immediately

### **Option 3: Hybrid Approach (Recommended)**
- Implement basic URDF parser (4-6 hours)
- Support common robot formats
- Manual mesh assignment first
- Expand over time
- **Benefit:** Best of both worlds

---

## ?? Recommendation

**For Your Current Needs:**

1. **Use Python API** (works now) for robot import:
   ```python
   # Import any robot via Python
   import_robot("ur5e", "path/to/ur5e.urdf")
   ```

2. **I'll implement basic FTI** (today) for common formats:
   - URDF parsing
   - Automatic assembly
   - Material assignment

3. **Drag & drop** will work after implementation

---

## ?? Shall I Implement FTI Now?

**I can create right now:**

1. ? `ROAURDFParser.h/.cpp` (URDF parsing)
2. ? `ROAURDFFactory.h/.cpp` (Asset importer)
3. ? `ROAAssetTypeActions.h/.cpp` (Editor integration)
4. ? Updated network commands for file import
5. ? Example Python script for robot import

**Time:** ~2-3 hours of implementation
**Result:** Drag & drop .urdf files into UE5 ?

**Want me to proceed?** 

Or should I first help you create the blueprints for the widgets?

---

**Guide Version:** 1.0  
**Last Updated:** January 2025  
**Status:** FTI Ready for Implementation

