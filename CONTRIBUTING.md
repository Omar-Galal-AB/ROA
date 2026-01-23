# Contributing to ROA

Thank you for your interest in contributing to ROA! This document provides guidelines and information for contributors.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Component Development Pattern](#component-development-pattern)
- [Code Style](#code-style)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)

---

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

---

## Getting Started

### Prerequisites

**For Linux/ROA Core development:**
- Ubuntu 22.04+ (or WSL2)
- Python 3.10+
- ROS2 Humble (optional, for full integration)

**For UE5 Plugin development:**
- Windows 10/11
- Unreal Engine 5.6+
- Visual Studio 2022 with C++ workload

### Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/ROA.git
cd ROA
```

---

## Development Setup

### Linux Core

```bash
cd roa-linux
pip install -r roa-core/requirements.txt

# Install FTI dependencies
cd roa-core/lib/components/files-type-importer
pip install -r requirements.txt
pip install -e .  # Editable install for development
```

### UE5 Plugin

1. Copy the plugin folder to your UE5 project
2. Follow `ThirdParty/INTEGRATION_GUIDE.md`
3. Regenerate project files
4. Build from Visual Studio or UE5 Editor

---

## Component Development Pattern

ROA uses a microservices architecture. New components should follow this structure:

```
components/{component_name}/
├── README.md                      # Component overview, API documentation
├── src/
│   └── python/
│       ├── {component}_main.py    # Primary logic
│       ├── {component}_ros2_node.py  # ROS2 integration (if applicable)
│       └── Config/                # Configuration files
├── tests/
│   ├── test_{component}.py        # Unit tests
│   └── test_{component}_integration.py  # Integration tests
├── requirements.txt               # Python dependencies
├── setup.py                       # Package setup
└── INTEGRATION_GUIDE.md           # How to integrate with other components
```

### Reference Implementation

See `files-type-importer/` (FTI) as the reference implementation:
- 30+ passing tests
- 80%+ code coverage
- Complete documentation
- IPC service pattern

---

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use docstrings (Google style)

```python
def convert_urdf(input_path: str, output_path: str) -> ConversionResult:
    """Convert URDF file to USD format.
    
    Args:
        input_path: Path to the input URDF file.
        output_path: Directory for output files.
        
    Returns:
        ConversionResult with success status and output paths.
        
    Raises:
        ValueError: If input file doesn't exist.
    """
    pass
```

### C++

- Follow Unreal Engine coding standards
- Use `UCLASS`, `UPROPERTY`, `UFUNCTION` macros appropriately
- Prefix classes: `A` for Actors, `U` for UObjects, `F` for structs
- Use `LogTemp` or custom log categories

```cpp
UFUNCTION(BlueprintCallable, Category = "ROA|Runtime")
static bool SetConstraintTargetAngle(
    AActor* Actor,
    const FString& ConstraintName,
    float TargetAngle);
```

---

## Testing Requirements

### Minimum Coverage

- **New features**: 80% code coverage
- **Bug fixes**: Include regression test

### Running Tests

**Python (FTI and components):**
```bash
cd roa-core/lib/components/files-type-importer
python -m pytest tests/ -v --cov=src --cov-report=html
```

**UE5 Plugin:**
- Use the built-in test framework
- Integration tests via Python scripts

### Test Categories

1. **Unit tests**: Test individual functions/classes
2. **Integration tests**: Test component interactions
3. **End-to-end tests**: Test full pipeline (URDF → USD → UE5)

---

## Pull Request Process

### Before Submitting

1. ✅ Tests pass locally
2. ✅ Code follows style guidelines
3. ✅ Documentation updated (if applicable)
4. ✅ No large binary files added
5. ✅ Commit messages are descriptive

### PR Template

```markdown
## Description
[Brief description of changes]

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Component(s) Affected
- [ ] FTI
- [ ] DIMC
- [ ] ROC
- [ ] COMC
- [ ] Webthread
- [ ] UE5 Plugin

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Documentation
- [ ] README updated
- [ ] API docs updated
- [ ] Changelog entry added
```

### Review Process

1. Submit PR to `develop` branch
2. Automated tests run
3. Code review by maintainer
4. Address feedback
5. Merge when approved

---

## Questions?

- Open an issue for bugs or feature requests
- Check existing documentation in `docs/`
- Review similar PRs for patterns

Thank you for contributing! 🤖
