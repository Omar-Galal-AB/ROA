# Design Clarifications and Decisions

This document captures all design decisions based on user requirements and identifies areas needing further clarification.

## Confirmed Design Decisions

### 1. Files Type Importer for UE5

**Confirmed Requirements:**
- ✅ Support all 3D file formats automatically
- ✅ Enable direct import into UE5 without external tools (Blender, etc.)
- ✅ Specifically designed for robot body designs
- ✅ Must convert unsupported formats to UE5-compatible formats
- ✅ Import materials and colors when available (ignore if no UE5 equivalent)
- ✅ Import both individual parts AND complete assembled robot
- ✅ Auto-create folder in Content Drawer with robot name
- ✅ Display both separate parts and whole robot assembly in Content Drawer

**Design Decisions:**
- Use C++ UE5 plugin architecture
- Support URDF, STL, OBJ, FBX, DAE, STEP, IGES, and other common formats
- Conversion pipeline: Unsupported Format → Intermediate Format → UE5 Format
- Folder structure: `Content/{RobotName}/Parts/` and `Content/{RobotName}/Assembly/`
- Material mapping: Best-effort conversion, default material if no match

---

### 2. Universal Robot Controller

**Confirmed Requirements:**
- ✅ Support ALL robot types (industrial, mobile, hybrid)
- ✅ Adaptive controller with hidden features for all possible part types
- ✅ Enable/disable controls dynamically based on robot capabilities
- ✅ Receive robot info from Dimensions Collector + Type Importer
- ✅ Show only relevant controls to optimize computer usage
- ✅ Slider-based control interface:
  - Left = Minimum/Turn Left
  - Right = Maximum/Turn Right
- ✅ Support multiple robots individually (selectable menu with tabs/titles)
- ✅ Highlight selected robot in menu
- ✅ Control types: Position, Velocity, Torque, Gripper Strength
- ✅ Both real-time manual control AND command queuing
- ✅ Safety features:
  - Sensors on ALL robot parts (not just gripper)
  - Auto-stop on collision
  - Yellow warning sign in title when obstacle detected (inactive control)
  - Entire menu turns yellow when actively controlled and obstacle detected
- ✅ Display above control sliders:
  - Position of part in assembled body
  - Position in world
  - Orientation from origin
  - Movement delta
  - Distance to other robots (if connected via Communication System)

**Design Decisions:**
- Modular controller architecture with plugin-based part controllers
- Dynamic UI generation based on robot capabilities
- C++ UE5 implementation for UI, Python for ROS2 interface
- Safety system uses UE5 collision detection + custom raycasting
- Command queue stored in Webthread for persistence

**Key Insight:**
> "The difference in robot designs is the number and type of body parts or limbs"
> Therefore: Controller has pre-built modules for all body part types, activates only what's needed

**Robot Type Support:**
- Industrial arms (articulated, SCARA, delta, etc.)
- Mobile bases (wheeled, tracked, legged)
- Hybrid systems (mobile + manipulator)
- Any combination of: limbs, shoulders, chest, arms, grippers, etc.

---

### 3. Dimensions Collector for UE5

**Confirmed Requirements:**
- ✅ Collect object sizes (for safety measures)
- ✅ Track positions:
  - Each part in assembled body (local coordinates)
  - Assembled body in world (global coordinates)
- ✅ Track orientations from origin
- ✅ Display movement deltas
- ✅ Show in controller menu (small size above control bars)
- ✅ Calculate and display distance to other robots (if connected via Communication System)
- ✅ Real-time tracking (main objective: track, control, operate robots in real time)
- ✅ Future: Export last locations, last task name, task completion status

**Design Decisions:**
- C++ UE5 plugin for performance
- Update rate: 60Hz (16.6ms) to match UE5 render loop
- Track both visual mesh AND collision mesh
- Data storage: In-memory with periodic export to logs
- Integration with Universal Robot Controller for display

**Clarification Needed:**
❓ **Question 1**: "What is the difference between [collision boundaries vs visual meshes]?"
- **Answer Needed**: Should safety calculations use:
  - Visual mesh (what you see)
  - Collision mesh (simplified physics representation)
  - Both?
  - Custom safety envelope?

---

### 4. Communication System Between Robots

**Confirmed Requirements:**
- ✅ Support ALL communication types:
  - Commands (robot-to-robot instructions)
  - State sharing (positions, status, current tasks)
  - Coordination (work area awareness, task handoffs)
- ✅ Custom protocol (can't predict which protocol each robot will use)
- ✅ Support different robot types communicating with each other
- ✅ Minimum latency possible (as fast as possible without problems)
- ✅ High reliability for safety

**Design Decisions:**
- Python implementation for protocol flexibility
- Custom message protocol with extensible message types
- Support for heterogeneous robot communication
- Message priority system (safety > coordination > status)
- Fallback mechanisms for lost messages

**Communication Content:**
- What each robot is doing (current task/action)
- Work area boundaries (spatial reservation)
- Position and movement (for collision avoidance)
- Task coordination (prevent interference)

---

### 5. Webthread Integration Bridge

**Confirmed Requirements:**
- ✅ Connect ROS2 + Gazebo to UE5
- ✅ **Optional Gazebo**: Only if UE5 physics cannot be customized to match reality
- ✅ ROS2 Interface: Mix of nodes, topics, services, and actions
- ✅ Real-time sync with Gazebo (if used)
- ✅ Bidirectional data flow (ROS2 ↔ UE5)
- ✅ Multi-instance support (simulate several robots simultaneously)
- ✅ Status monitoring interface showing:
  - Connection status for each robot
  - Bridge status (ROS2 ↔ UE5) - Live/Offline
- ✅ Logging system:
  - Track robot operations, commands, responses
  - Debug support when error identifier fails
  - Historical record

**Design Decisions:**
- Mixed Python (ROS2 interface) + C++ (performance-critical parts)
- Separate service/process architecture
- ROS2 messages as primary data format
- Status monitor: Separate UI panel (determine: UE5 widget vs web dashboard)
- Logging: File-based with rotation, real-time viewer

**Data Flow:**
- **ROS2 → UE5**: Robot commands, sensor data, state info
- **UE5 → ROS2**: Simulation feedback, collision data, visual sensor data

**Clarification Needed:**
❓ **Question 2**: "We need somewhere to track the logs of the robots"
- **Answered**: Built-in logging system in Webthread
- **Still Needed**: 
  - Log storage location? (filesystem, database, cloud?)
  - Retention policy?
  - Real-time viewing interface? (web-based, UE5 widget, separate app?)

---

## Technology Stack - CONFIRMED

### Programming Languages
✅ **Mixed Approach**: Python + C++
- **Python**: ROS2 integration, flexible protocols, high-level logic
- **C++**: UE5 plugins, performance-critical components, low-latency control

### Component Implementation Languages
| Component | Primary Language | Secondary | Reason |
|-----------|-----------------|-----------|---------|
| Files Type Importer | C++ | - | UE5 plugin, direct engine access |
| Dimensions Collector | C++ | - | UE5 plugin, 60Hz update rate |
| Universal Robot Controller | C++ | Python | UE5 UI + ROS2 interface |
| Communication System | Python | C++ (optional) | Protocol flexibility |
| Webthread | Python | C++ | ROS2 native + performance modules |

---

## Architecture - CONFIRMED

### Deployment Model
✅ **Microservices / Separate Services/Processes**

**Comparison:**

| Aspect | Monolithic | Microservices (CHOSEN) |
|--------|-----------|------------------------|
| **Structure** | All in one application | Each component separate |
| **Deployment** | Single executable | Multiple services |
| **Scaling** | Scale entire system | Scale components individually |
| **Failure** | One bug crashes all | Component isolation |
| **Technology** | Same tech stack | Best tool per component |
| **Development** | Simpler initially | More complex coordination |
| **Maintenance** | Tight coupling | Independent updates |
| **Testing** | Integration-focused | Unit + integration |

**Why Microservices:**
- ✅ Independent scaling per component
- ✅ Fault isolation (Files Type Importer crash doesn't stop robot control)
- ✅ Technology flexibility (Python for ROS2, C++ for UE5)
- ✅ Easier testing and development
- ✅ Modular updates and maintenance

---

## Data Serialization - CONFIRMED

### Primary Format
✅ **ROS2 Messages**
- Native ROS2 integration
- Type-safe message definitions
- Built-in serialization/deserialization
- Standard for robotics communication

### Secondary Formats
- **JSON**: Configuration files, logging output, debugging
- **YAML**: Configuration files
- **Protocol Buffers**: If performance demands (unlikely with ROS2 msgs)

---

## Performance Requirements - CONFIRMED

### Latency Targets
✅ **As fast as possible** with specific targets:
- Overall goal: < 20ms end-to-end latency
- Control loop: < 10ms (real-time control)
- Communication System: < 5ms (inter-robot coordination)
- Dimensions Collector: < 16.6ms (60 FPS update)
- ROS2 ↔ UE5 Bridge: < 20ms round-trip

### Real-Time Constraints
✅ **Real-time control within simulation**
- Support command mode (pre-programmed sequences)
- Support manual mode (direct operator control)
- Deterministic response for safety-critical operations

---

## Scope - CONFIRMED

### Robot Type Support
✅ **Generic framework** - Support ALL robot types
- No specific robot limitation
- Adaptive to any configuration
- Main difference between robots: number and type of body parts

### Application Domain
✅ **Primary**: Academic research
✅ **Secondary**: Industrial construction robot applications

**Use Case**: Construction robots working on sites
- Multiple robots coordinating
- Real-time control and monitoring
- Safety-critical operations
- Task queuing and automation

---

## Outstanding Clarifications Needed

### 1. Webthread Status Monitor & Universal Robot Controller Interface

✅ **CONFIRMED**: Both interfaces will have dual-mode implementation

**Decision:**
Both the **Universal Robot Controller** and **Webthread Status Monitor** will have:

1. **Standalone Application (Primary Mode)**
   - Complete desktop application with full functionality
   - Can run independently of UE5
   - Lower resource usage
   - Better for production/deployment
   - Remote operation capability

2. **UE5 Widget (Secondary Mode)**
   - Plugin-based widget inside UE5 editor
   - Same functionality as standalone
   - Integrated development workflow
   - Useful during simulation and testing
   - Part of Webthread UE5 plugin

**Technical Approach:**
- Shared core logic between both modes
- Only UI rendering differs
- Both modes use same Webthread API
- Standalone apps built first, UE5 widgets wrap the core

**See CLARIFICATIONS_EXPLAINED.md for detailed architecture diagrams and implementation approach.**

---

### 2. Logging System Details

✅ **CONFIRMED**: Hybrid approach with filesystem and database

**Decision:**
Use a **hybrid approach** combining the benefits of both filesystem and database storage:

**Primary Storage - Filesystem:**
- Write all logs to text files in real-time
- Fast writes with no performance impact on robot control
- Simple and reliable
- Location: `/logs/YYYY-MM-DD/robot_name.log`
- Retention: 30 days or 10GB (whichever comes first)
- Log rotation: Daily files with automatic cleanup

**Secondary Storage - SQLite Database:**
- **Database Software: SQLite** (chosen for ROA system)
- Store important events for searchable queries
- Events stored: errors, collisions, task completions, warnings
- Enables fast searching: "Show me all Robot 2 errors this week"
- File-based database (no server required - runs as part of the application)
- Structured data for analysis and reporting
- Retention: Important events kept for 90 days

**Why SQLite?**
- Lightweight and embedded (no separate database server needed)
- Single file database (easy to backup and manage)
- Fast for read-heavy workloads (perfect for log searching)
- Zero configuration required
- Built-in to Python (no additional installation)
- Cross-platform (works on Windows, Linux, macOS)
- Reliable and battle-tested (used by billions of devices)
- Perfect for applications with moderate data size (up to several GB)

**Real-Time Viewing:**
- Live log tail in web-based interface
- UE5 editor panel for integrated viewing
- Automatic refresh for monitoring

**Benefits:**
- Fast real-time logging (filesystem)
- Easy searching and analysis (database)
- No single point of failure (redundant storage)
- Best of both worlds

**See FILESYSTEM_VS_DATABASE.md for detailed explanation of differences and why hybrid is recommended.**

---

### 3. Control Slider Ranges

✅ **CONFIRMED**: Auto-calculate from robot specifications with user override capability

**Decision:**
- **Automatic Calculation**: Extract limits from URDF/robot specification files
- **Safety Margin**: Apply 10% safety margin by default to prevent mechanical hard stops
- **User Editable**: Allow manual adjustment later for specific tasks or safety requirements
- **Task-Specific**: Support different ranges for different operations

**How it works:**
1. System reads joint limits from URDF (e.g., -180° to +180°)
2. Applies 10% safety margin (e.g., -162° to +162°)
3. Sets these as default slider ranges
4. User can override for specific needs (e.g., limit to -90° to +90° for a task)

**See CLARIFICATIONS_EXPLAINED.md Section 3 for detailed explanation and examples.**

---

### 4. Task Command Queue Format

✅ **CONFIRMED**: Multiple programming interfaces with JSON storage

**Decision:**
- **JSON format** for task storage (human-readable, easy to parse)
- **Multiple programming interfaces:**
  - **GUI Task Builder**: Drag-and-drop interface for simple, repetitive tasks (best for operators)
  - **Python Scripting**: Full programming power for complex logic and AI integration (best for researchers)
  - **UE5 Blueprints**: Visual scripting for UE5 users (Phase 2 enhancement)
- Task priority system with interrupt/cancel capability
- All interfaces generate the same internal JSON format

**Implementation Priority:**
- Phase 1: GUI Builder + Python Scripting (essential)
- Phase 2: UE5 Blueprint integration (enhancement)

**See CLARIFICATIONS_EXPLAINED.md Section 4 for detailed comparison of each interface type.**

---

### 5. Collision Detection Method

✅ **CONFIRMED**: Hybrid approach with collision mesh and configurable safety margin

**Decision:**
- **Primary Method**: Use collision mesh for performance (fast computation)
- **Safety Margin**: Configurable buffer zone (default: 10cm)
- **Precision Mode**: Optional visual mesh for precise operations when needed
- **Adjustable Settings**: User can modify safety margin per robot or per task (range: 0-50cm)

**How it works:**
- Normal operations: Collision mesh + 10cm margin (fast, adequate safety)
- Near human workers: Automatically increase margin to 20cm + switch to visual mesh if needed
- Precise assembly: Reduce margin to 2cm with visual mesh for accuracy

**Benefits:**
- Fast detection for real-time control
- Adequate safety for construction site operations
- Flexibility for different scenarios
- Performance optimization when precision not critical

**See CLARIFICATIONS_EXPLAINED.md Section 5 for diagrams and real-world construction site examples.**

---

### 6. Dimensions Collector Export Format

✅ **CONFIRMED**: Hybrid approach with multiple formats for different purposes

**Decision:**
- **Primary Format**: ROS bag files for complete robot recording
  - Industry standard in robotics
  - Complete data capture (all sensors, states, commands)
  - Can replay entire sessions
  - Retention: 7 days
  
- **Secondary Format**: JSON for task summaries and reports
  - Human-readable task summaries
  - Easy integration with web dashboards
  - Quick analysis without ROS tools
  - Retention: 30 days
  
- **Optional Format**: CSV for position data
  - Opens in Excel/Google Sheets
  - Simple position history analysis
  - For non-technical users

**Export Timing:**
- **Real-time logging** to temporary buffer (in-memory)
- **Auto-save every hour** for safety
- **On-demand export** for specific analysis needs

**Data Included:**
- Timestamps
- Position/orientation history
- Task names and completion status
- Collision events
- Control commands
- Robot state changes

**See CLARIFICATIONS_EXPLAINED.md Section 6 for format comparison and example output.**

---

## Implementation Priority Order

Based on dependencies and user requirements:

### Phase 1: Foundation (Week 1-4)
1. **Webthread** - Basic ROS2 ↔ UE5 bridge
2. **Files Type Importer** - Common formats (STL, OBJ, FBX)
3. **Dimensions Collector** - Position tracking

### Phase 2: Control (Week 5-8)
4. **Universal Robot Controller** - Single robot, basic controls
5. **Webthread** - Status monitor interface
6. **Integration** - Controller using Dimensions Collector data

### Phase 3: Safety & Multi-Robot (Week 9-12)
7. **Dimensions Collector** - Collision detection
8. **Universal Robot Controller** - Safety features, multi-robot UI
9. **Communication System** - Basic inter-robot communication
10. **Integration** - Multi-robot coordination

### Phase 4: Advanced Features (Week 13-16)
11. **Files Type Importer** - Advanced formats (URDF, STEP, IGES)
12. **Universal Robot Controller** - Command queuing
13. **Webthread** - Logging system
14. **Communication System** - Advanced coordination

### Phase 5: Polish & Optimization (Week 17-20)
15. **Performance Tuning** - Latency optimization
16. **UI/UX** - Refinement and user testing
17. **Documentation** - Complete user and developer guides
18. **Testing** - System-level integration tests

---

## Risk Assessment

### High-Risk Items
⚠️ **UE5 Physics Accuracy**: May need Gazebo fallback if UE5 physics insufficient
⚠️ **Real-Time Latency**: Achieving < 20ms with complex scenes may be challenging
⚠️ **Format Conversion**: Some 3D formats may lose data in conversion
⚠️ **Multi-Robot Scaling**: Performance with 5+ robots needs testing

### Medium-Risk Items
⚠️ **Custom Protocol**: Communication System protocol needs careful design
⚠️ **Dynamic UI**: Controller UI generation complexity
⚠️ **Cross-Platform**: Ensuring compatibility across development environments

### Mitigation Strategies
✅ **Prototyping**: Build minimal versions first to validate concepts
✅ **Performance Testing**: Early and frequent performance benchmarking
✅ **Modular Design**: Easy to swap implementations if needed
✅ **Fallback Options**: Gazebo integration, alternative protocols

---

## Next Steps

✅ **All Major Design Decisions Confirmed**

1. ✅ **Setup Repository**: Create folder structure from PROJECT_STRUCTURE.md
2. ✅ **Create Detailed Specs**: Per-component technical specifications
3. ✅ **Define Interfaces**: Create interface definitions between components
4. **Prototype Webthread**: Minimal ROS2 ↔ UE5 bridge
5. **Begin Implementation**: Follow phase-by-phase roadmap

---

## All Design Decisions - Summary

### ✅ CONFIRMED DECISIONS

1. **Interface Architecture**: Both Controller and Webthread have dual-mode (standalone apps + UE5 widgets)
2. **Logging System**: Hybrid approach (filesystem for real-time + SQLite database for searching)
3. **Control Slider Ranges**: Auto-calculate from URDF with 10% safety margin, user-editable
4. **Task Queue Format**: GUI Builder + Python Scripts (Phase 1), Blueprints (Phase 2)
5. **Collision Detection**: Hybrid approach (collision mesh + 10cm configurable safety margin)
6. **Export Format**: Hybrid approach (ROS bags for complete data, JSON for summaries, optional CSV)

### 📋 TECHNOLOGY STACK CONFIRMED

- **Languages**: Mixed Python (ROS2) + C++ (UE5 plugins)
- **Architecture**: Microservices (separate services/processes)
- **Data Format**: ROS2 messages (primary), JSON (config/logging)
- **Latency Target**: < 20ms for real-time control
- **Scope**: Generic framework for all robot types

### 🎯 READY FOR IMPLEMENTATION

All major design decisions confirmed. System architecture fully specified. Ready to begin implementation following the phase-by-phase roadmap.

---

**Last Updated**: Design Phase Complete  
**Status**: ✅ All clarifications addressed - Ready for implementation
