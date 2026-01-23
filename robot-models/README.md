# Robot Models

This folder contains 3D robot model files (URDF, meshes, etc.) used for testing and development.

## Contents

- **unitree_quadrupeds/** - Unitree quadruped robots (H1, Laikago, etc.)
- **ur_robots/** - Universal Robots arm series (UR3, UR5, UR10, UR20, UR30, etc.)

## Size Warning

⚠️ This folder is approximately **1 GB** due to mesh files (STL, DAE).

## Git LFS Recommendation

For repositories using Git, these files should be managed with [Git LFS](https://git-lfs.github.com/):

```bash
# Initialize Git LFS
git lfs install

# Track large file types
git lfs track "*.stl"
git lfs track "*.STL"
git lfs track "*.dae"
git lfs track "*.DAE"
git lfs track "*.obj"
git lfs track "*.fbx"
```

## Alternative: Download Separately

You can also exclude this folder from Git and provide a download script:

```bash
# Add to .gitignore
robot-models/

# Users download separately
./scripts/download_robot_models.sh
```

## Source

These robot models are from:
- [Unitree Robotics](https://github.com/unitreerobotics)
- [Universal Robots](https://github.com/UniversalRobots/Universal_Robots_ROS2_Description)
