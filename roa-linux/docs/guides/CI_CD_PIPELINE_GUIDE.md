# CI/CD Pipeline Guide for ROA
**Date**: 2025-12-13  
**Purpose**: Comprehensive guide to implementing Continuous Integration and Continuous Deployment for ROA

---

## Overview

This guide explains how to set up automated testing, building, and deployment for the ROA (Robot Operator Assistant) system. The CI/CD pipeline will automatically validate code quality, run tests, build components, and prepare deployment artifacts.

---

## CI/CD Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     GITHUB ACTIONS                          │
│                  (CI/CD Orchestration)                      │
└────┬─────────────┬──────────────┬──────────────┬───────────┘
     │             │              │              │
┌────▼────┐   ┌───▼────┐   ┌─────▼─────┐  ┌────▼─────┐
│  Code   │   │ Build  │   │   Test    │  │ Deploy   │
│ Quality │   │        │   │           │  │          │
└─────────┘   └────────┘   └───────────┘  └──────────┘
     │             │              │              │
┌────▼────────────▼──────────────▼──────────────▼───────┐
│         Linting, Building, Testing, Packaging          │
│    Python (Black, Flake8, mypy, pytest)               │
│    C++ (clang-format, clang-tidy, CMake)              │
│    ROS2 (colcon build, ros2 test)                     │
└────────────────────────────────────────────────────────┘
```

---

## Phase 1: Basic CI Pipeline (Start Here)

### Workflow 1: Lint and Format Check

**File:** `.github/workflows/lint.yml`

```yaml
name: Code Quality Check

on:
  push:
    branches: [ main, develop, copilot/* ]
  pull_request:
    branches: [ main, develop ]

jobs:
  python-lint:
    name: Python Code Quality
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install linting tools
      run: |
        python -m pip install --upgrade pip
        pip install black flake8 mypy pylint isort
    
    - name: Check code formatting with Black
      run: |
        black --check --diff components/
    
    - name: Lint with Flake8
      run: |
        flake8 components/ --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 components/ --count --max-complexity=10 --max-line-length=127 --statistics
    
    - name: Type check with mypy
      run: |
        mypy components/ --ignore-missing-imports --no-strict-optional
      continue-on-error: true  # Don't fail build on type errors initially
    
    - name: Check import sorting
      run: |
        isort --check-only --diff components/

  cpp-lint:
    name: C++ Code Quality
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Install clang-format and clang-tidy
      run: |
        sudo apt-get update
        sudo apt-get install -y clang-format clang-tidy
    
    - name: Check C++ formatting
      run: |
        find components/ -name "*.cpp" -o -name "*.h" | xargs clang-format --dry-run --Werror
      continue-on-error: true  # Don't fail initially
    
    - name: Run clang-tidy
      run: |
        find components/ -name "*.cpp" | xargs clang-tidy --checks='-*,readability-*,modernize-*'
      continue-on-error: true  # Don't fail initially
```

### Workflow 2: Unit Tests

**File:** `.github/workflows/test.yml`

```yaml
name: Unit Tests

on:
  push:
    branches: [ main, develop, copilot/* ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test-webthread:
    name: Test Webthread
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        cd components/webthread
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests with coverage
      run: |
        cd components/webthread
        pytest tests/ -v --cov=src/python --cov-report=xml --cov-report=term
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        files: ./components/webthread/coverage.xml
        flags: webthread

  test-roc:
    name: Test Robot Operator Controller
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        cd components/robot-operator-controller
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests with coverage
      run: |
        cd components/robot-operator-controller
        pytest tests/ -v --cov=src/python --cov-report=xml --cov-report=term
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        files: ./components/robot-operator-controller/coverage.xml
        flags: roc

  test-dimc:
    name: Test Dimensions Collector
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        cd components/dimensions-collector
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        cd components/dimensions-collector
        pytest tests/ -v --cov=src/python --cov-report=xml

  test-fti:
    name: Test Files Type Importer
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        cd components/files-type-importer
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        cd components/files-type-importer
        pytest tests/ -v --cov=src/python --cov-report=xml

  test-comc:
    name: Test Communication Center
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        cd components/communication-center
        pip install -e .
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        cd components/communication-center
        pytest tests/ -v --cov=src/python --cov-report=xml
```

### Workflow 3: ROS2 Build

**File:** `.github/workflows/ros2-build.yml`

```yaml
name: ROS2 Build

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  build-ros2:
    name: Build ROS2 Packages
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
      with:
        path: src/ROA
    
    - name: Setup ROS2 Humble
      uses: ros-tooling/setup-ros@v0.7
      with:
        required-ros-distributions: humble
    
    - name: Install dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y python3-colcon-common-extensions
        cd src/ROA
        rosdep update
        rosdep install --from-paths . --ignore-src -r -y
    
    - name: Build with colcon
      run: |
        source /opt/ros/humble/setup.bash
        colcon build --packages-select \
          webthread \
          robot-operator-controller \
          dimensions-collector \
          files-type-importer \
          communication-center
    
    - name: Test with colcon
      run: |
        source /opt/ros/humble/setup.bash
        source install/setup.bash
        colcon test --packages-select \
          webthread \
          communication-center
    
    - name: Show test results
      run: |
        colcon test-result --verbose
```

---

## Phase 2: Advanced CI Features

### Workflow 4: Integration Tests

**File:** `.github/workflows/integration-test.yml`

```yaml
name: Integration Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  integration-test:
    name: End-to-End Integration Tests
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Setup ROS2 Humble
      uses: ros-tooling/setup-ros@v0.7
      with:
        required-ros-distributions: humble
    
    - name: Install all dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y python3-colcon-common-extensions
        for component in components/*/; do
          if [ -f "$component/requirements.txt" ]; then
            pip install -r "$component/requirements.txt"
          fi
        done
        pip install pytest pytest-timeout
    
    - name: Run integration tests
      run: |
        source /opt/ros/humble/setup.bash
        cd tests/integration
        pytest . -v --timeout=60
      timeout-minutes: 10
```

### Workflow 5: Performance Benchmarks

**File:** `.github/workflows/performance.yml`

```yaml
name: Performance Benchmarks

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  benchmark:
    name: Run Performance Benchmarks
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python 3.10
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install pytest pytest-benchmark
        cd components/robot-operator-controller
        pip install -r requirements.txt
    
    - name: Run benchmarks
      run: |
        cd components/robot-operator-controller/tests
        pytest test_performance.py -v --benchmark-only --benchmark-json=benchmark.json
    
    - name: Store benchmark result
      uses: benchmark-action/github-action-benchmark@v1
      with:
        tool: 'pytest'
        output-file-path: components/robot-operator-controller/tests/benchmark.json
        github-token: ${{ secrets.GITHUB_TOKEN }}
        auto-push: true
```

---

## Phase 3: Pre-Commit Hooks (Local Development)

### Setup Pre-commit

**File:** `.pre-commit-config.yaml`

```yaml
repos:
  # Python formatting
  - repo: https://github.com/psf/black
    rev: 23.12.0
    hooks:
      - id: black
        language_version: python3.10
        args: ['--line-length=100']

  # Python import sorting
  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ['--profile', 'black', '--line-length=100']

  # Python linting
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--extend-ignore=E203,W503']

  # C++ formatting
  - repo: https://github.com/pre-commit/mirrors-clang-format
    rev: v17.0.6
    hooks:
      - id: clang-format
        types_or: [c++, c]

  # YAML validation
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
        args: ['--maxkb=1000']

  # Markdown formatting
  - repo: https://github.com/executablebooks/mdformat
    rev: 0.7.17
    hooks:
      - id: mdformat
        additional_dependencies:
          - mdformat-gfm
          - mdformat-black
```

**Installation:**
```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run on all files (first time)
pre-commit run --all-files
```

---

## Configuration Files

### Python Linting Config

**File:** `.flake8`

```ini
[flake8]
max-line-length = 100
extend-ignore = E203, W503
exclude = 
    .git,
    __pycache__,
    build,
    install,
    log,
    .pytest_cache,
    .venv,
    venv
per-file-ignores =
    __init__.py:F401
```

### Python Type Checking Config

**File:** `pyproject.toml`

```toml
[tool.black]
line-length = 100
target-version = ['py310']
include = '\.pyi?$'
exclude = '''
/(
    \.git
  | \.venv
  | build
  | install
  | log
)/
'''

[tool.isort]
profile = "black"
line_length = 100
multi_line_output = 3
include_trailing_comma = true

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = "-v --tb=short --strict-markers"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
]
```

### C++ Linting Config

**File:** `.clang-format`

```yaml
Language: Cpp
BasedOnStyle: Google
IndentWidth: 4
ColumnLimit: 100
AllowShortFunctionsOnASingleLine: Empty
AllowShortIfStatementsOnASingleLine: false
AllowShortLoopsOnASingleLine: false
PointerAlignment: Left
```

**File:** `.clang-tidy`

```yaml
Checks: >
  -*,
  readability-*,
  modernize-*,
  performance-*,
  bugprone-*,
  -modernize-use-trailing-return-type,
  -readability-identifier-length

WarningsAsErrors: ''
HeaderFilterRegex: '.*'
FormatStyle: file
```

---

## CI/CD Best Practices for ROA

### 1. Fast Feedback Loop
- Run linting first (fastest, catches obvious issues)
- Run unit tests in parallel (independent components)
- Run integration tests last (slowest, requires all components)

### 2. Caching Strategy
```yaml
# Cache pip packages
- name: Cache pip packages
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}

# Cache ROS2 build
- name: Cache ROS2 build
  uses: actions/cache@v3
  with:
    path: |
      build
      install
    key: ${{ runner.os }}-ros2-${{ hashFiles('**/package.xml') }}
```

### 3. Matrix Testing
Test across multiple Python and ROS2 versions:

```yaml
strategy:
  matrix:
    python-version: ['3.8', '3.10', '3.11']
    ros-distro: ['humble', 'iron']
```

### 4. Status Badges
Add to README.md:

```markdown
![CI](https://github.com/Omar-Galal-AB/ROA/workflows/Code%20Quality%20Check/badge.svg)
![Tests](https://github.com/Omar-Galal-AB/ROA/workflows/Unit%20Tests/badge.svg)
![ROS2](https://github.com/Omar-Galal-AB/ROA/workflows/ROS2%20Build/badge.svg)
[![codecov](https://codecov.io/gh/Omar-Galal-AB/ROA/branch/main/graph/badge.svg)](https://codecov.io/gh/Omar-Galal-AB/ROA)
```

---

## Deployment Pipeline (Phase 4 - Future)

When ready for deployment:

### Workflow: Build and Release

**File:** `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build-and-release:
    name: Build and Create Release
    runs-on: ubuntu-22.04
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Setup ROS2
      uses: ros-tooling/setup-ros@v0.7
      with:
        required-ros-distributions: humble
    
    - name: Build packages
      run: |
        source /opt/ros/humble/setup.bash
        colcon build --merge-install
    
    - name: Package release
      run: |
        tar -czf roa-${{ github.ref_name }}.tar.gz install/
    
    - name: Create Release
      uses: softprops/action-gh-release@v1
      with:
        files: roa-${{ github.ref_name }}.tar.gz
        draft: false
        prerelease: false
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Quick Start Guide

### For the ROA Project:

1. **Create workflows directory:**
   ```bash
   mkdir -p .github/workflows
   ```

2. **Add the basic workflows:**
   - Start with `lint.yml` and `test.yml`
   - These will run on every push/PR

3. **Test locally before pushing:**
   ```bash
   # Install and run pre-commit
   pip install pre-commit
   pre-commit install
   pre-commit run --all-files
   ```

4. **Push and watch CI run:**
   - Go to GitHub Actions tab
   - See workflows running automatically
   - Fix any issues that appear

5. **Add status badges to README:**
   - Shows CI status at a glance
   - Increases confidence in code quality

---

## Monitoring and Alerts

### Set up GitHub Actions notifications:
- Email notifications for failed builds
- Slack/Discord integration for team alerts
- Required status checks before merging

### Code coverage requirements:
- Set minimum coverage threshold (e.g., 75%)
- Block PRs that decrease coverage
- Generate coverage reports

---

## Summary

**Benefits of CI/CD for ROA:**
- ✅ Automatic quality checks on every change
- ✅ Catch bugs early before they reach production
- ✅ Consistent build and test process
- ✅ Confidence in code changes
- ✅ Documentation of build/test status
- ✅ Easy collaboration with clear feedback

**Next Steps:**
1. Implement Phase 1 (lint + test workflows)
2. Test workflows with a small PR
3. Add pre-commit hooks for local development
4. Gradually add Phase 2 features
5. Monitor and refine based on team needs

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-13  
**Ready to Implement**: Yes - Start with Phase 1 workflows
