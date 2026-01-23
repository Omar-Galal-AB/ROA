# VS Code Setup Guide for ROA Development

This guide provides VS Code setup instructions for local development of the ROA (Robot Operator Assistant) system.

---

## Required VS Code Extensions

### Essential Extensions

#### 1. **Python Development**
```
Name: Python
Publisher: Microsoft
ID: ms-python.python
```
**Why:** Core Python support for ROS2 integration and scripting
**Features:**
- IntelliSense (code completion)
- Linting (code quality checks)
- Debugging
- Jupyter notebook support
- Auto-formatting

```
Name: Pylance
Publisher: Microsoft
ID: ms-python.vscode-pylance
```
**Why:** Fast Python language server for better IntelliSense
**Features:**
- Type checking
- Auto-imports
- Faster code completion

#### 2. **C++ Development**
```
Name: C/C++
Publisher: Microsoft
ID: ms-vscode.cpptools
```
**Why:** UE5 plugins and performance-critical components use C++
**Features:**
- IntelliSense for C++
- Debugging support
- Code formatting
- Build task integration

```
Name: C/C++ Extension Pack
Publisher: Microsoft
ID: ms-vscode.cpptools-extension-pack
```
**Why:** Complete C++ development environment
**Includes:**
- C/C++ themes
- CMake tools
- Better IntelliSense

#### 3. **CMake Support**
```
Name: CMake
Publisher: twxs
ID: twxs.cmake
```
**Why:** ROA components use CMake for building
**Features:**
- Syntax highlighting
- Code completion
- Command reference

```
Name: CMake Tools
Publisher: Microsoft
ID: ms-vscode.cmake-tools
```
**Why:** Build and debug CMake projects
**Features:**
- Configure and build projects
- Debug integration
- Kit selection

#### 4. **ROS2 Development**
```
Name: ROS
Publisher: Microsoft
ID: ms-iot.vscode-ros
Status: Currently unavailable in marketplace
```
**Note:** This extension is currently unavailable. Use alternatives below:

**Alternative 1: Work without ROS extension (Recommended for now)**
- ROS2 commands work from VS Code terminal
- Python extension provides IntelliSense for ROS2 Python code
- YAML extension handles launch files
- No special extension needed for basic ROS2 development

**Alternative 2: Manual ROS2 Setup**
- Source ROS2 in VS Code terminal: `source /opt/ros/humble/setup.bash`
- Add to `.vscode/settings.json`:
```json
{
  "terminal.integrated.env.linux": {
    "ROS_DISTRO": "humble"
  }
}
```
- Use command line tools: `ros2`, `colcon`, `rosdep`

**Alternative 3: If extension becomes available later**
- Install when Microsoft republishes it
- For now, system is designed to work without it

#### 5. **Unreal Engine Support**
```
Name: Unreal Engine 4 Snippets
Publisher: Damian Cullotta
ID: damirka.unreal-engine-snippets
```
**Why:** UE5 C++ plugin development
**Features:**
- Code snippets for UE classes
- Quick boilerplate generation

**Note:** UE5 is compatible with UE4 snippets

#### 6. **YAML & JSON**
```
Name: YAML
Publisher: Red Hat
ID: redhat.vscode-yaml
```
**Why:** Configuration files, ROS2 launch files
**Features:**
- Syntax validation
- Auto-completion
- Schema validation

```
Name: JSON Tools
Publisher: Erik Lynd
ID: eriklynd.json-tools
```
**Why:** JSON task definitions, config files
**Features:**
- Pretty print
- Minify
- Sort

#### 7. **Git Integration**
```
Name: GitLens
Publisher: GitKraken
ID: eamodio.gitlens
```
**Why:** Enhanced Git capabilities
**Features:**
- Line blame
- Repository visualization
- Commit search
- History explorer

#### 8. **Markdown**
```
Name: Markdown All in One
Publisher: Yu Zhang
ID: yzhang.markdown-all-in-one
```
**Why:** Documentation editing (README, ARCHITECTURE, etc.)
**Features:**
- Preview
- Table of contents
- Shortcuts
- Auto-completion

#### 9. **Code Formatting**
```
Name: Prettier - Code formatter
Publisher: Prettier
ID: esbenp.prettier-vscode
```
**Why:** Consistent code formatting for JSON, YAML, Markdown
**Features:**
- Auto-format on save
- Consistent style

```
Name: Black Formatter
Publisher: Microsoft
ID: ms-python.black-formatter
```
**Why:** Python code formatting (PEP 8 compliant)
**Features:**
- Auto-format Python files
- Consistent style across team

#### 10. **Database Tools**
```
Name: SQLite Viewer
Publisher: Florian Klampfer
ID: qwtel.sqlite-viewer
```
**Why:** View and query ROA.db (SQLite database for logs)
**Features:**
- Browse database tables
- Run SQL queries
- Export data

---

## Optional but Recommended Extensions

#### Project Management
```
Name: Todo Tree
Publisher: Gruntfuggly
ID: Gruntfuggly.todo-tree
```
**Why:** Track TODO, FIXME, NOTE comments in code

#### Code Quality
```
Name: SonarLint
Publisher: SonarSource
ID: SonarSource.sonarlint-vscode
```
**Why:** Detect bugs and code smells in Python and C++

#### Remote Development
```
Name: Remote - SSH
Publisher: Microsoft
ID: ms-vscode-remote.remote-ssh
```
**Why:** Connect to remote development machines if needed

#### Debugging
```
Name: Python Debugger
Publisher: Microsoft
ID: ms-python.debugpy
```
**Why:** Modern Python debugging

---

## VS Code Settings Configuration

Create or update `.vscode/settings.json` in your ROA repository:

```json
{
  // Python settings
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "100"],
  "python.analysis.typeCheckingMode": "basic",
  
  // C++ settings
  "C_Cpp.default.cppStandard": "c++17",
  "C_Cpp.default.compilerPath": "/usr/bin/g++",
  "C_Cpp.default.intelliSenseMode": "linux-gcc-x64",
  
  // CMake settings
  "cmake.configureOnOpen": false,
  "cmake.buildDirectory": "${workspaceFolder}/build",
  
  // ROS settings
  "ros.distro": "humble",
  
  // Editor settings
  "editor.formatOnSave": true,
  "editor.rulers": [100],
  "editor.tabSize": 4,
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true,
  
  // File associations
  "files.associations": {
    "*.launch": "xml",
    "*.urdf": "xml",
    "*.xacro": "xml",
    "*.msg": "plaintext",
    "*.srv": "plaintext",
    "*.action": "plaintext"
  },
  
  // Exclude from file explorer
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/.pytest_cache": true,
    "**/build": true,
    "**/install": true,
    "**/log": true
  }
}
```

---

## System Requirements & Installation

### Required Software

#### 1. **Python 3.8+**
```bash
# Install Python
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Verify installation
python3 --version
```

#### 2. **C++ Compiler**
```bash
# Install GCC/G++
sudo apt install build-essential cmake

# Verify installation
g++ --version
cmake --version
```

#### 3. **ROS2 Humble** (or later)
```bash
# Follow official ROS2 installation guide for your OS
# https://docs.ros.org/en/humble/Installation.html

# Verify installation
ros2 --version
```

#### 4. **Unreal Engine 5**
```bash
# Download from Epic Games Launcher
# https://www.unrealengine.com/en-US/download

# UE5 requires:
# - 8GB+ RAM
# - NVIDIA/AMD GPU
# - 100GB+ disk space
```

#### 5. **Git**
```bash
# Install Git
sudo apt install git

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

#### 6. **SQLite** (usually pre-installed)
```bash
# Verify installation
sqlite3 --version

# If not installed
sudo apt install sqlite3
```

---

## Python Environment Setup

### Create Virtual Environment

```bash
# Navigate to ROA directory
cd /path/to/ROA

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Upgrade pip
pip install --upgrade pip
```

### Install Python Dependencies

Create `requirements.txt` in project root:

```txt
# ROS2 dependencies
rclpy
std_msgs
geometry_msgs

# Database
# (SQLite is built-in, no package needed)

# Web framework (for Webthread status monitor)
flask
flask-socketio

# Data handling
numpy
pandas

# Logging
python-json-logger

# Testing
pytest
pytest-cov

# Code quality
black
pylint
mypy

# GUI (for standalone controller app)
PyQt5
# or
tkinter  # Usually built-in

# Utilities
pyyaml
python-dotenv
```

Install dependencies:
```bash
pip install -r requirements.txt
```

---

## Workspace Setup

### Recommended Folder Structure in VS Code

```
ROA/                          # Open this folder in VS Code
├── .venv/                    # Python virtual environment (excluded from Git)
├── .vscode/                  # VS Code settings
│   ├── settings.json
│   ├── launch.json          # Debug configurations
│   └── tasks.json           # Build tasks
├── components/              # Main system components
├── shared/                  # Shared libraries
├── ros2-workspace/          # ROS2 workspace
├── ue5-project/            # UE5 project
├── docs/                   # Documentation
├── tests/                  # Tests
├── scripts/                # Utility scripts
├── requirements.txt        # Python dependencies
├── .gitignore
└── README.md
```

### Debug Configuration

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Python: Webthread",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/components/webthread/src/python/webthread_core.py",
      "console": "integratedTerminal"
    },
    {
      "name": "C++: UE5 Plugin",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceFolder}/ue5-project/Binaries/Linux/UnrealEditor",
      "args": [],
      "stopAtEntry": false,
      "cwd": "${workspaceFolder}",
      "environment": [],
      "externalConsole": false,
      "MIMode": "gdb"
    }
  ]
}
```

### Build Tasks

Create `.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Build ROS2 Workspace",
      "type": "shell",
      "command": "colcon build",
      "options": {
        "cwd": "${workspaceFolder}/ros2-workspace"
      },
      "group": {
        "kind": "build",
        "isDefault": true
      }
    },
    {
      "label": "Run Tests",
      "type": "shell",
      "command": "pytest",
      "options": {
        "cwd": "${workspaceFolder}"
      },
      "group": "test"
    },
    {
      "label": "Format Python Code",
      "type": "shell",
      "command": "black .",
      "options": {
        "cwd": "${workspaceFolder}"
      }
    }
  ]
}
```

---

## Quick Start Checklist

- [ ] Install VS Code
- [ ] Install all required extensions (see list above)
- [ ] Install Python 3.8+
- [ ] Install C++ compiler (GCC/G++)
- [ ] Install CMake
- [ ] Install ROS2 Humble
- [ ] Install Unreal Engine 5
- [ ] Clone ROA repository
- [ ] Create Python virtual environment
- [ ] Install Python dependencies (`pip install -r requirements.txt`)
- [ ] Configure VS Code settings (`.vscode/settings.json`)
- [ ] Test Python environment (`python --version`)
- [ ] Test ROS2 (`ros2 --version`)
- [ ] Test C++ compiler (`g++ --version`)

---

## Useful VS Code Keyboard Shortcuts

| Action | Shortcut (Linux/Windows) | Shortcut (Mac) |
|--------|-------------------------|----------------|
| Command Palette | `Ctrl+Shift+P` | `Cmd+Shift+P` |
| Quick Open File | `Ctrl+P` | `Cmd+P` |
| Format Document | `Shift+Alt+F` | `Shift+Option+F` |
| Toggle Terminal | `Ctrl+` ` | `Ctrl+` ` |
| Find in Files | `Ctrl+Shift+F` | `Cmd+Shift+F` |
| Go to Definition | `F12` | `F12` |
| Peek Definition | `Alt+F12` | `Option+F12` |
| Rename Symbol | `F2` | `F2` |
| Show All Commands | `Ctrl+Shift+P` | `Cmd+Shift+P` |

---

## Troubleshooting

### Python IntelliSense Not Working
1. Select correct Python interpreter: `Ctrl+Shift+P` → "Python: Select Interpreter"
2. Choose virtual environment: `.venv/bin/python`
3. Reload window: `Ctrl+Shift+P` → "Developer: Reload Window"

### ROS2 Commands Not Found
1. Source ROS2 setup: `source /opt/ros/humble/setup.bash`
2. Add to VS Code terminal: Update `.vscode/settings.json`:
```json
{
  "terminal.integrated.env.linux": {
    "ROS_DISTRO": "humble"
  }
}
```

### CMake Configuration Failed
1. Install CMake Tools extension
2. Select kit: `Ctrl+Shift+P` → "CMake: Select a Kit"
3. Configure: `Ctrl+Shift+P` → "CMake: Configure"

### UE5 IntelliSense Slow
1. Increase memory limit in `.vscode/settings.json`:
```json
{
  "C_Cpp.intelliSenseMemoryLimit": 4096
}
```

---

## Next Steps

1. **Set up development environment** using this guide
2. **Familiarize with repository structure** (see PROJECT_STRUCTURE.md)
3. **Review architecture** (see ARCHITECTURE.md)
4. **Start with Phase 1 implementation** (see roadmap in ARCHITECTURE.md)
5. **Follow coding standards** (to be defined in future)
6. **Write tests** as you develop (see tests/ directory)

---

## Additional Resources

- **VS Code Documentation**: https://code.visualstudio.com/docs
- **Python in VS Code**: https://code.visualstudio.com/docs/python/python-tutorial
- **C++ in VS Code**: https://code.visualstudio.com/docs/cpp/cpp-tutorial
- **ROS2 Documentation**: https://docs.ros.org/en/humble/
- **Unreal Engine Documentation**: https://docs.unrealengine.com/5.0/
- **SQLite Documentation**: https://www.sqlite.org/docs.html
- **CMake Tutorial**: https://cmake.org/cmake/help/latest/guide/tutorial/

---

**Last Updated**: Design Phase  
**Status**: Ready for local development setup
