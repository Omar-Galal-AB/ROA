# ?? Robot Files Organization Guide

**Best Practices for Managing Robot URDF/Mesh Files**

---

## ? **Recommended: Keep Robot Files in Project**

### **Why Store Robot Files in Project Folder?**

1. **No Permission Issues** ?
   - Project folder has full read/write access
   - No UAC or admin permission problems
   - UE5 can freely access all files

2. **Portability** ?
   - Move project = move all assets
   - Easy to share with team
   - Version control friendly (Git)

3. **Relative Paths** ?
   - No hardcoded absolute paths
   - Works on any computer
   - FTI can find meshes easily

4. **Organization** ?
   - All project assets in one place
   - Clear folder structure
   - Easy to backup

---

## ?? **Recommended Folder Structure**

```
D:\ROA\UE5_Projects\ROA_V1\
?
??? Content/     (UE5 assets)
?   ??? ROA/
?   ??? UI/
? ??? Widgets/
?
??? RobotDescriptions/    ? CREATE THIS
?   ??? UR5e/
?   ?   ??? ur5e.urdf
?   ?   ??? meshes/
?   ?   ?   ??? visual/
?   ?   ?   ?   ??? base.dae
?   ?   ?   ?   ??? shoulder.dae
?   ?   ?   ?   ??? ...
?   ?   ?   ??? collision/
?   ?   ?  ??? base.stl
?   ?   ?       ??? ...
?   ?   ??? textures/
?   ?       ??? robot_texture.png
?   ?
?   ??? Panda/
?   ?   ??? panda.urdf
?   ?   ??? meshes/
?   ?
?   ??? CustomRobot/
?   ?   ??? my_robot.urdf
?   ?   ??? meshes/
?   ?
?   ??? Examples/
?   ??? test_robot.urdf
? ??? simple_robot.urdf
?
??? Plugins/
??? Config/
??? ROA_V1.uproject
```

---

## ?? **Setup Instructions**

### **Step 1: Create Robot Folder**

```powershell
# In PowerShell, navigate to project root
cd D:\ROA\UE5_Projects\ROA_V1

# Create robot descriptions folder
New-Item -ItemType Directory -Path "RobotDescriptions" -Force
New-Item -ItemType Directory -Path "RobotDescriptions\UR5e" -Force
New-Item -ItemType Directory -Path "RobotDescriptions\Examples" -Force
```

### **Step 2: Transfer Robot Files**

**Option A: Copy from ROS workspace**
```powershell
# Copy UR5e from ROS
Copy-Item -Path "C:\ros_ws\src\universal_robot\ur_description\urdf\ur5e.urdf" `
   -Destination "RobotDescriptions\UR5e\" -Force

# Copy meshes
Copy-Item -Path "C:\ros_ws\src\universal_robot\ur_description\meshes\ur5e\*" `
          -Destination "RobotDescriptions\UR5e\meshes\" -Recurse -Force
```

**Option B: Download from manufacturer**
```
1. Download robot files from manufacturer website
2. Extract to RobotDescriptions\[RobotName]\
3. Organize: .urdf in root, meshes in meshes\
```

**Option C: Create test robot**
```powershell
# Already in project folder
# Just create test files directly
```

---

## ?? **Example: Simple Test Robot**

Create: `RobotDescriptions\Examples\test_robot.urdf`

```xml
<?xml version="1.0"?>
<robot name="test_robot">
  <!-- Base Link -->
  <link name="base_link">
    <visual>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry>
        <box size="0.5 0.5 0.1"/>
      </geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry>
        <box size="0.5 0.5 0.1"/>
      </geometry>
    </collision>
    <inertial>
      <mass value="1.0"/>
   <inertia ixx="1.0" ixy="0.0" ixz="0.0" iyy="1.0" iyz="0.0" izz="1.0"/>
    </inertial>
  </link>

  <!-- Link 1 -->
  <link name="link1">
    <visual>
      <origin xyz="0 0 0.25" rpy="0 0 0"/>
      <geometry>
    <cylinder radius="0.05" length="0.5"/>
      </geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0.25" rpy="0 0 0"/>
      <geometry>
        <cylinder radius="0.05" length="0.5"/>
      </geometry>
    </collision>
    <inertial>
      <mass value="0.5"/>
      <inertia ixx="0.1" ixy="0.0" ixz="0.0" iyy="0.1" iyz="0.0" izz="0.1"/>
  </inertial>
  </link>

  <!-- Joint 1 -->
  <joint name="joint1" type="revolute">
  <parent link="base_link"/>
    <child link="link1"/>
    <origin xyz="0 0 0.05" rpy="0 0 0"/>
    <axis xyz="0 0 1"/>
    <limit lower="-3.14159" upper="3.14159" effort="100.0" velocity="1.0"/>
  </joint>

  <!-- Link 2 -->
<link name="link2">
    <visual>
 <origin xyz="0 0 0.15" rpy="0 0 0"/>
      <geometry>
        <box size="0.1 0.1 0.3"/>
      </geometry>
    </visual>
<collision>
      <origin xyz="0 0 0.15" rpy="0 0 0"/>
      <geometry>
    <box size="0.1 0.1 0.3"/>
      </geometry>
    </collision>
    <inertial>
      <mass value="0.3"/>
      <inertia ixx="0.05" ixy="0.0" ixz="0.0" iyy="0.05" iyz="0.0" izz="0.05"/>
    </inertial>
  </link>

  <!-- Joint 2 -->
  <joint name="joint2" type="revolute">
    <parent link="link1"/>
    <child link="link2"/>
    <origin xyz="0 0 0.5" rpy="0 0 0"/>
    <axis xyz="1 0 0"/>
    <limit lower="-1.57" upper="1.57" effort="50.0" velocity="1.0"/>
  </joint>
</robot>
```

---

## ?? **Using Robot Files from Project Folder**

### **Method 1: FTI Import (Drag & Drop)**

```
1. Open UE5 Editor
2. Content Browser ? Navigate to Content/ROA/Robots/
3. Drag: RobotDescriptions\Examples\test_robot.urdf
4. Drop into Content Browser
5. Import dialog appears
6. Click OK ? Blueprint created!
```

### **Method 2: Python API**

```python
import socket, json, time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 9876))

# Connect first
connect_msg = {
    "message_id": "test-001",
 "timestamp": time.time(),
    "message_type": "REQUEST",
    "command": "connect",
    "payload": {"client_name": "Test", "version": "1.0.0"}
}
sock.send(json.dumps(connect_msg).encode())
sock.recv(4096)

# Spawn robot with relative path
spawn_msg = {
    "message_id": "spawn-001",
    "timestamp": time.time(),
 "message_type": "REQUEST",
    "command": "spawn_robot",
    "payload": {
        "robot_id": "test_robot_001",
        "robot_type": "custom",
        "spawn_location": {"x": 0, "y": 0, "z": 100},
        # Use relative path from project root
     "urdf_path": "RobotDescriptions/Examples/test_robot.urdf"
    }
}
sock.send(json.dumps(spawn_msg).encode())
response = sock.recv(4096)
print(response.decode())
```

---

## ?? **Common Issues & Solutions**

### **Issue 1: URDF References External Meshes**

**Problem:**
```xml
<mesh filename="package://ur_description/meshes/ur5e/visual/base.dae"/>
```

**Solution A: Copy Meshes**
```powershell
# Copy all meshes to project
Copy-Item "C:\ros_ws\src\ur_description\meshes\*" `
          -Destination "RobotDescriptions\UR5e\meshes\" -Recurse
```

**Solution B: Update URDF Paths**
```xml
<!-- Change from package:// to relative path -->
<mesh filename="meshes/visual/base.dae"/>
```

### **Issue 2: Absolute Paths in URDF**

**Problem:**
```xml
<mesh filename="C:\Users\Admin\Documents\robot\mesh.dae"/>
```

**Solution: Make Relative**
```xml
<!-- Change to relative path -->
<mesh filename="meshes/visual/mesh.dae"/>
```

### **Issue 3: Permission Denied**

**Problem:** Can't read files from C:\Program Files\

**Solution:** Already solved by moving to project folder! ?

---

## ?? **Version Control (Git)**

### **.gitignore Recommendations**

```gitignore
# UE5 Generated files
Binaries/
Build/
Intermediate/
Saved/
DerivedDataCache/

# Keep robot descriptions
!RobotDescriptions/
!RobotDescriptions/**/*.urdf
!RobotDescriptions/**/*.xacro

# Ignore large mesh files (optional)
# *.dae
# *.stl
# *.obj

# Keep example robots
!RobotDescriptions/Examples/
```

**Considerations:**
- ? Include `.urdf` files (small, text)
- ? Include `.xacro` files (small, text)
- ?? Large mesh files: Consider Git LFS
- ?? Textures: May need Git LFS

---

## ?? **Quick Setup Script**

Create: `setup_robot_folders.ps1`

```powershell
# Setup Robot Descriptions Folder Structure
$ProjectRoot = "D:\ROA\UE5_Projects\ROA_V1"

Write-Host "Creating robot folder structure..." -ForegroundColor Green

# Create main folder
New-Item -ItemType Directory -Path "$ProjectRoot\RobotDescriptions" -Force | Out-Null

# Create robot-specific folders
$Robots = @("UR3e", "UR5e", "UR10e", "Panda", "CustomRobots", "Examples")

foreach ($Robot in $Robots) {
    New-Item -ItemType Directory -Path "$ProjectRoot\RobotDescriptions\$Robot" -Force | Out-Null
    New-Item -ItemType Directory -Path "$ProjectRoot\RobotDescriptions\$Robot\meshes" -Force | Out-Null
    New-Item -ItemType Directory -Path "$ProjectRoot\RobotDescriptions\$Robot\meshes\visual" -Force | Out-Null
    New-Item -ItemType Directory -Path "$ProjectRoot\RobotDescriptions\$Robot\meshes\collision" -Force | Out-Null
    New-Item -ItemType Directory -Path "$ProjectRoot\RobotDescriptions\$Robot\textures" -Force | Out-Null
    Write-Host "  Created: RobotDescriptions\$Robot" -ForegroundColor Cyan
}

Write-Host "`nFolder structure created successfully!" -ForegroundColor Green
Write-Host "You can now copy your robot files to:" -ForegroundColor Yellow
Write-Host "  $ProjectRoot\RobotDescriptions\" -ForegroundColor White
```

**Run:**
```powershell
cd D:\ROA\UE5_Projects\ROA_V1
.\setup_robot_folders.ps1
```

---

## ? **Benefits Summary**

| Aspect | External Location | Project Folder |
|--------|------------------|----------------|
| **Permissions** | ? May need admin | ? Full access |
| **Portability** | ? Hardcoded paths | ? Relative paths |
| **Version Control** | ? Separate repo | ? Same repo |
| **Team Sharing** | ? Manual sync | ? Automatic |
| **Backup** | ? Separate | ? Included |
| **Organization** | ? Scattered | ? Centralized |
| **FTI Import** | ?? May fail | ? Works great |

---

## ?? **Recommendation**

**DO THIS:**
1. ? Create `RobotDescriptions/` folder in project
2. ? Copy all robot URDF files there
3. ? Copy associated meshes and textures
4. ? Update URDF paths to be relative
5. ? Test FTI import
6. ? Commit to version control

**RESULT:**
- No permission issues
- Easy to share
- Portable project
- Clean organization
- FTI works perfectly

---

**Next Steps:**
1. Run `setup_robot_folders.ps1` script
2. Copy your robot files
3. Test FTI import
4. Enjoy hassle-free robot development! ??

---

**Guide Version:** 1.0  
**Created:** January 2025  
**Status:** Best Practice Recommendations

