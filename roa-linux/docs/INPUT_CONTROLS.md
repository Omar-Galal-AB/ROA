# ROA Input Controls & UI Overlay Specification

Complete keyboard and mouse control mapping for dual control modes (RPM and ADM) with context-sensitive bindings and on-screen UI overlay.

---

## Table of Contents

1. [Control Modes Overview](#control-modes-overview)
2. [Context-Sensitive Input Mapping](#context-sensitive-input-mapping)
3. [RPM Mode Controls](#rpm-mode-controls)
4. [ADM Mode Controls](#adm-mode-controls)
5. [UI Overlay Specification](#ui-overlay-specification)
6. [Customization & Settings](#customization--settings)
7. [Implementation Notes](#implementation-notes)

---

## Control Modes Overview

ROA supports two distinct control modes with context-sensitive keyboard/mouse bindings:

- **RPM (Role Playing Mode)**: Direct manual control of individual robots with real-time keyboard/mouse input
- **ADM (Auto Driven Mode)**: RTS-style strategic control with command menus and autonomous robot execution

**Key Design Principle**: Same physical keys perform different functions depending on active mode, maximizing efficiency and reducing cognitive load.

---

## Context-Sensitive Input Mapping

### Shared Inputs (Same Keys, Different Functions)

| Input | RPM Mode | ADM Mode |
|-------|----------|----------|
| **W** | Move robot forward | Move camera forward |
| **A** | Move robot left | Move camera left |
| **S** | Move robot backward | Move camera backward |
| **D** | Move robot right | Move camera right |
| **↑** | Increase gripper arm height | Navigate to robot above (in menu) |
| **↓** | Decrease gripper arm height | Navigate to robot below (in menu) |
| **←** | Move gripper arm left | Navigate to robot on left (nearest) |
| **→** | Move gripper arm right | Navigate to robot on right (nearest) |
| **Left Click** | Select object/target for gripper | Select robot/object for commands |
| **Right Click** | Alternative gripper arm control (freedom mode) | Open command menu with shortcuts |
| **Mouse Wheel** | Camera zoom in/out | Camera zoom in/out |

---

## RPM Mode Controls

### Robot Movement
**WASD Keys** - Direct robot locomotion control
- **W**: Move robot forward
- **A**: Move robot left (strafe)
- **S**: Move robot backward
- **D**: Move robot right (strafe)

**Behavior**:
- Speed governed by current safety level (Fragile 60%, Standard 100%, Robust 100%+)
- Respects collision boundaries and workspace limits
- Real-time response with <20ms latency

### Gripper Arm Control
**Arrow Keys** - Precision gripper arm positioning
- **↑**: Increase gripper arm height (vertical up)
- **↓**: Decrease gripper arm height (vertical down)
- **←**: Move gripper arm left (horizontal left)
- **→**: Move gripper arm right (horizontal right)

**Right Click + Mouse Movement** - Alternative gripper control
- Hold right mouse button for 6-DOF gripper freedom of movement
- Mouse movement translates to arm position in 3D space
- Release right click to lock position

### Gripper Operations (Configurable Shortcuts)
**Default Key Bindings**:
- **C**: Close gripper on selected object (uses default grip force from settings)
- **V**: Open gripper (release object)
- **E**: Move gripper arm forward (extend reach)
- **Q**: Move gripper arm backward (retract)
- **Y**: Rotate gripper left (counter-clockwise)
- **U**: Rotate gripper right (clockwise)
- **R**: Auto-retreat to origin position (return to start location)
- **T**: Toggle gripper between tool modes (if multi-tool gripper)

### Mouse Controls
- **Left Click**: Select target object or position for gripper
  - Click on object: Highlight and track object for gripping
  - Click on ground: Set movement target for robot
- **Right Click**: Enable gripper arm freedom mode (6-DOF control)
- **Mouse Wheel**: Zoom camera in/out
- **Middle Mouse Button**: Pan camera (hold and drag)

### Camera Controls
- **Mouse Movement**: Rotate camera around robot (orbit)
- **Shift + WASD**: Camera pan (independent of robot movement)
- **Mouse Wheel**: Zoom in/out
- **F**: Focus camera on selected robot

### Quick Actions
- **Space**: Emergency stop (immediate halt)
- **Tab**: Switch between controlled robots (if multiple in RPM)
- **Esc**: Cancel current action / Clear selection
- **1-4**: Quick-select robot slots (if 4 robots loaded)

---

## ADM Mode Controls

### Camera Movement
**WASD Keys** - Free camera navigation
- **W**: Move camera forward (toward focus point)
- **A**: Move camera left (orbit left)
- **S**: Move camera backward (away from focus point)
- **D**: Move camera right (orbit right)

**Mouse Controls**:
- **Left Click + Drag**: Pan camera
- **Right Click + Drag**: Orbit camera around selection
- **Mouse Wheel**: Zoom in/out
- **Middle Click + Drag**: Tilt/pitch camera

### Robot Selection
**Arrow Keys** - Navigate between robots
- **↑**: Select robot above in menu list
- **↓**: Select robot below in menu list
- **←**: Select nearest robot to the left
- **→**: Select nearest robot to the right

**Selection Logic**:
- Vertical arrows: Navigate through alphabetically sorted robot list in UI
- Horizontal arrows: Select based on spatial proximity in 3D workspace
- Wraps around at list boundaries

**Mouse Selection**:
- **Left Click** on robot: Select robot and show status
- **Shift + Left Click**: Add to selection (multi-select)
- **Ctrl + Left Click**: Toggle robot in selection

### Command Menu
**Right Click** - Open contextual command menu
- Shows available commands with keyboard shortcuts
- Commands organized by category:
  - **Movement**: Move to location, Follow path, Patrol area
  - **Manipulation**: Pick object, Place object, Use tool
  - **Coordination**: Form group, Follow robot, Wait for signal
  - **Utility**: Return to base, Charge, Scan area

**Menu Format**:
```
┌─────────────────────────────────────────┐
│ Robot Commands - UR5 Alpha             │
├─────────────────────────────────────────┤
│ [M] Move to Location                    │
│     Navigate to clicked position        │
│                                         │
│ [P] Pick Object                         │
│     Grasp selected object               │
│                                         │
│ [G] Form Group                          │
│     Join robots into coordinated team   │
│                                         │
│ [R] Return to Base                      │
│     Auto-navigate to start position     │
└─────────────────────────────────────────┘
```

### Hotkeys (When Menu Visible)
- **M**: Move to location (click to set target)
- **P**: Pick object (click object to grab)
- **L**: Place object (click location to drop)
- **F**: Follow path (click waypoints)
- **G**: Form group (select multiple robots)
- **R**: Return to base
- **H**: Halt/Stop current task
- **Esc**: Close menu

### Multi-Robot Commands
**Formation Control**:
- **Shift + Drag**: Box select multiple robots
- **Ctrl + Click**: Add/remove from selection
- **Alt + Click**: Select all robots of same type

**Group Actions**:
- **Ctrl + M**: Move formation (maintains relative positions)
- **Ctrl + R**: Rotate formation
- **Ctrl + S**: Spread formation (increase spacing)

### Quick Actions
- **Space**: Pause all selected robots
- **Tab**: Cycle through robots
- **Esc**: Deselect all / Close menus
- **1-4**: Quick-select robot slots
- **Ctrl + A**: Select all robots
- **F**: Focus camera on selected robot(s)

---

## UI Overlay Specification

### On-Screen Shortcuts Panel

**Location**: Customizable corner of screen (default: bottom-right)

**Appearance**:
- Semi-transparent background (60% opacity, adjustable)
- Dynamic content based on active mode (RPM or ADM)
- Foldable/expandable (toggle with **F1** key)
- Draggable to any corner

**Panel Structure**:
```
┌──────────────────────────────────────┐
│ ⓘ RPM Mode Active                   │
├──────────────────────────────────────┤
│ Movement                             │
│  W A S D   Robot movement            │
│  Arrows    Gripper arm control       │
│                                      │
│ Gripper                              │
│  C         Close gripper             │
│            (Default force)           │
│  V         Open gripper              │
│  E / Q     Extend/Retract arm        │
│  Y / U     Rotate left/right         │
│                                      │
│ Quick Actions                        │
│  R         Return to origin          │
│  Space     Emergency stop            │
│  Tab       Switch robot              │
└──────────────────────────────────────┘
```

**Font & Colors**:
- Header: 14pt bold, white text
- Command keys: 12pt bold, yellow highlight
- Descriptions: 10pt regular, light gray
- Subdescriptions: 8pt italic, dark gray

**Visibility Toggle**:
- **F1**: Toggle panel visibility
- **F2**: Toggle panel transparency (60% → 80% → 40% → 60%)
- **F3**: Cycle panel position (corners)

### Mode Indicator

**Always Visible** (top-center of screen):
```
┌─────────────────┐
│  RPM  |  ADM    │
│  ███  |  ___    │
└─────────────────┘
```

- Active mode highlighted
- Click to switch modes (with confirmation)
- Shows current robot name in RPM mode
- Shows selection count in ADM mode

### Context Help
- **F12**: Toggle detailed help overlay (full controls reference)
- Auto-fade after 5 seconds of inactivity
- Reappears on any key press (first 3 times, then stays hidden)

---

## Customization & Settings

### Keybinding Customization

**Settings Menu Path**: Settings → Controls → Key Bindings

**Customizable Actions** (RPM):
- Robot movement (WASD default)
- Gripper arm control (Arrows default)
- Gripper operations (C, V, E, Q, Y, U, R, T)
- Quick actions (Space, Tab, Esc, F, 1-4)

**Customizable Actions** (ADM):
- Camera movement (WASD default)
- Robot selection (Arrows default)
- Command hotkeys (M, P, L, F, G, R, H)
- Multi-select modifiers (Shift, Ctrl, Alt)

**Conflict Detection**:
- System warns if same key assigned to multiple actions
- Suggests alternatives from unused keys
- Allows override with confirmation

### Mouse Sensitivity

**Adjustable Parameters**:
- Camera rotation speed (0.5x - 3.0x, default 1.0x)
- Zoom speed (0.5x - 3.0x, default 1.0x)
- Pan sensitivity (0.5x - 3.0x, default 1.0x)
- Right-click gripper control sensitivity (RPM mode)

### UI Overlay Preferences

**Customization Options**:
- Panel position: 4 corners + center-left/right
- Transparency: 20% - 90% (default 60%)
- Font size: Small (8pt) / Medium (10pt) / Large (12pt)
- Color scheme: Light / Dark / High-contrast
- Auto-hide delay: 3s / 5s / 10s / Never

**Saved Profiles**:
- Default profile
- User can create up to 5 custom profiles
- Switch profiles with **Ctrl + F1** through **Ctrl + F5**

---

## Implementation Notes

### Input Handling Priority

**Event Processing Order**:
1. Emergency stop (Space) - Highest priority
2. Mode-specific shortcuts
3. Mouse input (clicks, wheel)
4. Camera controls
5. Movement/navigation

**Conflict Resolution**:
- Mode toggle has cooldown (0.5s) to prevent accidental switches
- Confirmation required when switching modes with active commands
- Input buffer cleared on mode switch

### Performance Targets

**Input Latency**:
- Keyboard input → action: <10ms
- Mouse click → selection: <15ms
- Command menu open: <50ms
- UI overlay toggle: <30ms

**Update Rates**:
- Input polling: 120 Hz
- UI overlay refresh: 60 Hz
- Context help fade: 30 Hz

### Accessibility Features

**Planned Support**:
- Keyboard-only mode (no mouse required)
- High-contrast UI themes
- Larger font options (up to 16pt)
- Screen reader compatibility (menu text)
- Customizable key hold times
- Single-hand mode (remap all keys to one side)

### Cross-Platform Considerations

**Ubuntu 22.04 (Primary)**:
- Full support for all features
- X11 and Wayland compatible

**Windows 10/11 (Secondary)**:
- Same key bindings
- Alt key may conflict with system shortcuts (remappable)
- Mouse behavior identical

---

## Quick Reference Card

### RPM Mode Essentials
```
Movement:      W A S D
Gripper Arm:   Arrow Keys
Close Grip:    C
Open Grip:     V
Extend/Retract: E / Q
Rotate:        Y / U
Return Home:   R
E-Stop:        Space
```

### ADM Mode Essentials
```
Camera:        W A S D + Mouse
Select Robot:  Arrow Keys / Left Click
Command Menu:  Right Click
Move Command:  M
Pick Object:   P
Group Robots:  G
Return Base:   R
Pause:         Space
```

### Universal
```
Mode Switch:   Click mode indicator (top-center)
Help:          F12
Toggle UI:     F1
Emergency:     Space (any mode)
```

---

## Summary

The ROA input control system provides:
- ✅ Context-sensitive keyboard/mouse mapping
- ✅ Dual-mode support (RPM direct control, ADM strategic commands)
- ✅ Customizable keybindings with conflict detection
- ✅ Semi-transparent on-screen UI overlay
- ✅ Quick reference panel with mode-specific shortcuts
- ✅ <20ms input latency for real-time control
- ✅ Accessible design with customization options

**Design Philosophy**: Maximize efficiency through context-sensitive controls while maintaining clarity through on-screen guidance and customization flexibility.

