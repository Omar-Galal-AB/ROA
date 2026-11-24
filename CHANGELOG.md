# Changelog

All notable changes to ROA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- v7.18: Runtime constraint control functions for ROC integration
  - `SetConstraintTargetAngle()` - Set joint target position
  - `GetConstraintCurrentAngle()` - Read current joint angle
  - `SetConstraintTargetVelocity()` - Velocity control mode
  - `EmergencyStopActorJoints()` - Safety stop
  - `GetActorConstraintNames()` - Discover available joints

### Changed
- v7.17: Strong drive parameters for robot stability (stiffness=100000, damping=10000)
- v7.16: C++ constraint creation with rotation at creation time (fixes rotation persistence)

### Fixed
- v7.17: Robot collapsing during physics simulation (angular drive stiffness was 0)
- v7.16: Constraint rotation not persisting after Blueprint save

---

## [0.2.0] - 2026-01-19

### Added
- **FTI (Files Type Importer)** - Production ready
  - URDF/XACRO to USD conversion
  - Physics schema embedding (UsdPhysics)
  - IPC service for cross-platform communication
  - 30+ tests, 80%+ coverage
  
- **UE5 Plugin**
  - `ROABlueprintUtils` - Blueprint manipulation utilities
  - `ROANetworkServer` - TCP command server (port 9876)
  - `ROARobotActor` - Base robot actor class
  - `ROARobotControlPanel` - UI widget system
  - Python integration via `Resources/Python/`

- **Robot Blueprint Factory**
  - `bp('robot_name')` command for automated Blueprint creation
  - StaticMesh + PhysicsConstraint approach
  - URDF joint limits and physics configuration

- **Documentation**
  - 28 guide documents in `Guides/`
  - Architecture documentation
  - AI context for development assistance

### Changed
- Migrated from Datasmith to USD Interchange pipeline
- 5-strategy actor discovery for name mangling robustness

### Known Issues
- DIMC, ROC, COMC components are planned but not implemented
- Webthread integration layer needs completion

---

## [0.1.0] - 2025-12-01

### Added
- Initial project structure
- Basic URDF parsing
- Proof of concept UE5 integration

---

## Version Naming

- **v7.x** - Internal development versions for Blueprint/constraint fixes
- **0.x.0** - Release versions following semver

[Unreleased]: https://github.com/Omar-Galal-AB/ROA/compare/v0.2.0-alpha...HEAD
[0.2.0]: https://github.com/Omar-Galal-AB/ROA/releases/tag/v0.2.0-alpha
[0.1.0]: https://github.com/Omar-Galal-AB/ROA/releases/tag/v0.1.0
