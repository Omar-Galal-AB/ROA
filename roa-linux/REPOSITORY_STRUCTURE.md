# ROA Repository Organization Guide

This document explains how the ROA repository is organized and where to find things.

## 📁 Repository Structure Options

ROA can be organized in GitHub in two ways:

### Option A: Monorepo (Recommended for Development)

```
ROA/
├── roa-linux/              # Linux core (this folder)
├── ue5-plugin/             # UE5 plugin (renamed from ROA_PlugIn)
├── robot-examples/         # Test robot models (UR5e, UR10e, etc.)
├── docs/                   # Shared documentation
├── .github/
│   ├── workflows/          # CI/CD pipelines
│   └── copilot-instructions.md
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── CHANGELOG.md
```

### Option B: Separate Repos

| Repository | Content |
|------------|---------|
| `ROA-Core` | Linux services, FTI, components |
| `ROA-UE5-Plugin` | Unreal Engine 5 plugin |
| `ROA-Docs` | Shared documentation |

---

## 🗂 Folder Contents

### `/roa-linux/` (Linux Core)

```
roa-linux/
├── roa-core/
│   ├── bin/                    # Entry scripts
│   │   ├── roa                 # Main launcher (Linux)
│   │   └── roa.bat             # Main launcher (Windows)
│   ├── config/
│   │   ├── roa_config.yaml     # Main configuration
│   │   └── robot_template.yaml # Robot config template
│   └── lib/
│       ├── roa_main.py         # Application entry point
│       ├── roa_bridge_server.py
│       ├── roa_command_server.py
│       ├── components/         # Microservices (see below)
│       ├── shared/             # Shared utilities
│       ├── tools/              # CLI tools
│       └── ui/                 # NiceGUI dashboard
│
├── config/
│   └── observability/          # Monitoring stack (Grafana, Loki, etc.)
│
├── docs/                       # Component requirements & analysis
│
├── build/                      # Debian package build (auto-generated)
│
├── data/                       # Runtime data (logs, recordings)
│
├── install.sh                  # Installation script
├── uninstall.sh                # Removal script
├── build_deb.sh                # Package builder
├── .gitignore
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── CHANGELOG.md
```

### `/roa-linux/roa-core/lib/components/` (Microservices)

```
components/
├── files-type-importer/        # ✅ FTI - Production Ready
│   ├── src/python/
│   │   ├── Converters/         # URDF, USD converters
│   │   ├── Parsers/            # File parsers
│   │   ├── Generators/         # Output generators
│   │   └── Config/             # Configuration
│   ├── tests/                  # 30+ tests
│   ├── docs/                   # API documentation
│   ├── requirements.txt
│   ├── setup.py
│   └── README.md
│
├── dimensions-collector/       # 📋 DIMC - Planned
│   └── (structure TBD)
│
├── robot-operator-controller/  # 📋 ROC - Planned
│   └── (structure TBD)
│
├── communication-center/       # 📋 COMC - Planned
│   └── (structure TBD)
│
├── webthread/                  # 🔄 Central Coordinator - Partial
│   └── src/python/
│
└── bridge_manager.py           # Component orchestration
```

### `/ue5-plugin/` (Unreal Engine 5 Plugin)

```
ue5-plugin/  (originally: ROA_PlugIn)
├── ROA.uplugin                 # Plugin descriptor
│
├── Source/ROA/                 # C++ source
│   ├── Public/                 # Headers (.h)
│   │   ├── ROABlueprintUtils.h
│   │   ├── ROANetworkServer.h
│   │   ├── ROARobotActor.h
│   │   ├── ROARobotControlPanel.h
│   │   └── Components/
│   ├── Private/                # Implementation (.cpp)
│   └── ROA.Build.cs            # Build configuration
│
├── Resources/Python/           # Python integration
│   ├── robot_blueprint_factory.py
│   ├── physics_constraint_setup.py
│   ├── ue5_hierarchy_assembler.py
│   ├── urdf_robot_assembler.py
│   └── xacro_processor.py
│
├── Blueprints/                 # UE5 Blueprint assets
│
├── Content/                    # Plugin content
│
├── ThirdParty/                 # Dependencies (NOT in git)
│   ├── INTEGRATION_GUIDE.md    # ✅ Included
│   └── setup_bundled_python.ps1 # ✅ Included
│
└── .gitignore
```

---

## 🔀 What Goes Where

### Code Changes

| Change Type | Location |
|-------------|----------|
| URDF/USD conversion | `components/files-type-importer/src/python/` |
| New robot component | `components/{new-component}/` |
| Blueprint utilities | `ue5-plugin/Source/ROA/Private/ROABlueprintUtils.cpp` |
| Runtime robot control | `ue5-plugin/Source/ROA/` |
| Python robot scripts | `ue5-plugin/Resources/Python/` |
| UI widgets | `ue5-plugin/Source/ROA/` + Blueprints |

### Documentation

| Doc Type | Location |
|----------|----------|
| Architecture | `docs/ARCHITECTURE.md` |
| Component guides | `components/{name}/README.md` |
| UE5 guides | `ue5-plugin/Guides/` (if kept with plugin) |
| AI development context | `.github/copilot-instructions.md` |

---

## 📦 Files NOT to Commit

These are in `.gitignore`:

```
# Build artifacts
Binaries/
Intermediate/
DerivedDataCache/
build/*.deb

# Python cache
__pycache__/
*.pyc
.pytest_cache/

# IDE settings
.vscode/
.vs/
.idea/

# Large dependencies
ThirdParty/FastDDS/
ThirdParty/Python/
ThirdParty/rclcpp/

# Runtime data
*.log
data/logs/
.ipc/
```

---

## 🚀 Getting Started for New Contributors

1. **Read**: `README.md` → `docs/ARCHITECTURE.md` → `CONTRIBUTING.md`
2. **Setup**: Follow installation instructions for your platform
3. **Explore**: Run FTI tests to understand the conversion pipeline
4. **Reference**: Use FTI as the pattern for new components
5. **Ask**: Open an issue if documentation is unclear

---

## 📊 Component Status

| Component | Status | Tests | Coverage | Owner |
|-----------|--------|-------|----------|-------|
| FTI | ✅ Production | 30+ | 80%+ | - |
| DIMC | 📋 Planned | - | - | - |
| ROC | 📋 Planned | - | - | - |
| COMC | 📋 Planned | - | - | - |
| Webthread | 🔄 Partial | - | - | - |
| UE5 Plugin | ✅ Working | 12 | - | - |
