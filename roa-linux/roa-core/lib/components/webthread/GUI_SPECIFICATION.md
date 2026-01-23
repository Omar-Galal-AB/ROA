# Webthread Monitor GUI Specification
**For Figma Design Reference**

## Overview
The Webthread Monitor is a PyQt6 desktop application for monitoring ROA system health. This document describes all UI components, layouts, and visual elements for redesign in Figma.

---

## Window Structure

### Main Window (1400x900px recommended)
- **Type**: Frameless window with custom title bar
- **Background**: Dark theme (#1e1e2e base)
- **Layout**: Vertical stack (title bar → header → content → status bar)

---

## 1. Custom Title Bar
**File**: Lines 461-600 in `webthread_monitor.py`

### Components:
- **Left Side**:
  - Logo/Icon (if available)
  - Title: "ROA Webthread Monitor"
  - Subtitle: Version & connection status

- **Right Side**:
  - Minimize button (−)
  - Maximize/Restore button (□)
  - Close button (×)

### Features:
- Draggable (click and drag to move window)
- Double-click to maximize/restore
- Rounded corners: 8px top corners

### Colors:
- Background: `#2a2a3a`
- Title text: `#8a8aca` (light purple)
- Buttons hover: `#3a3a5a`

---

## 2. Header Section
**File**: Lines 601-767 in `webthread_monitor.py`

### Left Panel - Title & Status:
```
╔════════════════════════════╗
║ ROA Webthread Monitor      ║
║ Status: ACTIVE ● Running   ║
║ Uptime: 02:34:15          ║
╚════════════════════════════╝
```

### Center Panel - Bridge Status:
```
╔═══════════════════════════════════╗
║ 🌉 UE5 Bridge: ● CONNECTED        ║
║ 🔗 ROS2 Bridge: ● CONNECTED       ║
║ 🎮 Gazebo: ○ DISCONNECTED         ║
╚═══════════════════════════════════╝
```

### Right Panel - Controls:
- **Start Button**: Green background `#27ae60`, icon: ▶
- **Stop Button**: Red background `#e74c3c`, icon: ■
- **Copy Report Button**: Blue `#2a4a6a`
- **Test Data Flow Button**: Green `#27ae60`

### Control Button Specs:
- Height: 35px
- Padding: 5px 15px
- Font: Bold, white text
- Border-radius: 5px
- Hover effect: +10% brightness

---

## 3. Health Status Section (Tabbed)
**File**: Lines 800-1296 in `webthread_monitor.py`

### Container:
- **GroupBox**: "Health Status"
- Border: 2px solid `#4a4a6a`, 8px border-radius
- Title color: `#8a8aca`

### Tab 1: 📈 Overview (System Dashboard)
**File**: Lines 945-1169 (Custom gauge widgets)

#### Layout: 2x3 Grid of Circular Gauges

```
┌─────────────────────────────────────────────┐
│  Overall     WSL          Plugin             │
│  Health      Components   Components         │
│   [85%]       [100%]       [66%]            │
│                                              │
│  Response    Active       Errors             │
│  Time        Threads      (24h)              │
│   [45ms]      [12]         [3]              │
└─────────────────────────────────────────────┘
```

#### Circular Gauge Specs:
- **Size**: 120px diameter
- **Arc**: 270° sweep (starting at 225°, ending at -45°)
- **Arc thickness**: 12px
- **Background arc**: `#2d2d2d`
- **Value arc colors**:
  - 80-100%: Green `#4CAF50`
  - 50-79%: Yellow `#FFC107`
  - 30-49%: Orange `#FF9800`
  - 0-29%: Red `#F44336`
- **Center value**: Bold, size 24px, white
- **Unit**: Size 12px below value
- **Label**: Size 9px at bottom

#### Statistics Cards (Below gauges):
```
┌──────────────┬──────────────┬──────────────┐
│ Total: 6     │ Healthy: 5   │ Failed: 1    │
└──────────────┴──────────────┴──────────────┘
```

### Tab 2: 📊 Main Status (Table View)
**File**: Lines 873-943

#### WSL Components Table (4 rows):
```
╔═══════════╦════════╦═══════════╦════════╦═══════════╗
║ Component ║ Status ║ Resp (ms) ║ Errors ║ Last HB   ║
╠═══════════╬════════╬═══════════╬════════╬═══════════╣
║ FTI       ║ 🟢 OK  ║ 45       ║ 0      ║ 2s ago    ║
║ DIMC      ║ 🟢 OK  ║ 52       ║ 0      ║ 1s ago    ║
║ ROC       ║ 🟢 OK  ║ 38       ║ 0      ║ 3s ago    ║
║ COMC      ║ 🟠 SLOW║ 120      ║ 2      ║ 5s ago    ║
╚═══════════╩════════╩═══════════╩════════╩═══════════╝
```

#### UE5 Plugin Components Table (2 rows):
```
╔══════════════════╦════════╦═══════════╦════════╦═══════════╗
║ Component        ║ Status ║ Resp (ms) ║ Errors ║ Last HB   ║
╠══════════════════╬════════╬═══════════╬════════╬═══════════╣
║ ROAModule        ║ 🟢 OK  ║ 28       ║ 0      ║ 1s ago    ║
║ ROANetworkServer ║ 🔴 FAIL║ -        ║ 5      ║ 30s ago   ║
╚══════════════════╩════════╩═══════════╩════════╩═══════════╝
```

#### Table Styling:
- Header: Bold, `#5a9aca`, 18px height
- Row height: 20px
- Status colors:
  - 🟢 OK (Green): `#4CAF50`
  - 🟠 SLOW (Orange): `#FFC107`
  - 🔴 FAIL (Red): `#F44336`
  - ⚪ WAITING (Gray): `#757575`

### Tab 3: 💓 HB Status (Heartbeat Details)
**File**: Lines 1171-1295

#### Detailed Status Cards (6 cards in 2x3 grid):

Each card shows:
```
┌────────────────────────────────────┐
│ FTI                         🟢 OK  │
├────────────────────────────────────┤
│ State: ACTIVE                      │
│ Health: EXCELLENT (100%)           │
│ Alert: NONE                        │
│ Circuit: CLOSED                    │
│ Errors: 0 / Warnings: 0           │
│ Last Beat: 2s ago                  │
└────────────────────────────────────┘
```

Card specs:
- Width: 200px, Height: 150px
- Border: 1px solid `#3a3a5a`, 5px radius
- Background: `#2a2a3a`
- Padding: 10px

### Tab 4: 🤖 FTI Import (Robot Import Control)
**File**: Lines 1297-1452

```
┌──────────────────────────────────────────────────┐
│ Import Robot Model                                │
├──────────────────────────────────────────────────┤
│ File Path:                                        │
│ [____________________________]  [Browse...]       │
│                                                   │
│ Format: [URDF ▼]                                  │
│                                                   │
│ Scale Factor: [1.00]  Preview Mesh: [☑]          │
│                                                   │
│              [Import] [Cancel]                    │
└──────────────────────────────────────────────────┘
```

---

## 4. Bottom Section (Tabbed)
**File**: Lines 1453+ in `webthread_monitor.py`

### Tab Container Styling:
- Border: 1px solid `#3a3a5a`, 5px radius
- Selected tab: `#3a3a5a`, bold
- Tab padding: 6px 15px

### Tab 1: 📋 System Logs
- **Log Filter Widget** (Top):
  ```
  Filter: [search text___] Level: [INFO ▼] [Clear Logs]
  ```
- **Log Display** (Main area):
  - PlainTextEdit, monospace font
  - Color-coded by level:
    - INFO: White `#ffffff`
    - WARNING: Yellow `#FFC107`
    - ERROR: Red `#F44336`
    - DEBUG: Gray `#9e9e9e`
  - Format: `[HH:MM:SS] [LEVEL] message`

### Tab 2: 💬 HB Messages
- Similar to logs but filtered for heartbeat messages
- Shows component name, timestamp, status changes

### Tab 3: 🖥️ Terminal Output
- Raw terminal output from background processes
- Monospace font, scrollable
- Auto-scroll to bottom option

### Tab 4: 📊 Statistics
```
╔══════════════════════════════════════════╗
║ Component Statistics                     ║
╠══════════════════════════════════════════╣
║ Total Components: 6                      ║
║ Healthy: 5  |  Degraded: 0  |  Failed: 1 ║
║ Total Errors: 5                          ║
║ Total Warnings: 12                       ║
║ Uptime: 02:34:15                         ║
║ Messages Processed: 1,234                ║
╚══════════════════════════════════════════╝
```

---

## 5. Status Bar (Bottom)
**File**: Lines 350+ in `webthread_monitor.py`

```
Status: Monitoring | Components: 5/6 Healthy | Errors: 5 | Updated: 2s ago
```

- Height: 25px
- Background: `#2a2a3a`
- Font: 10px
- Separator: `|` between segments

---

## Custom Widgets Library

### 1. CircularGauge
**File**: Lines 117-205

Properties:
- Label, min/max values, current value, unit
- Auto-color based on percentage
- Smooth arc drawing with rounded caps

### 2. StatusIndicator
**File**: Lines 206-263

Properties:
- Colored dot (20px circle)
- Label below
- Pulse animation option
- Active/inactive states

### 3. LogFilterWidget
**File**: Lines 264-351

Components:
- Search text field
- Level dropdown (ALL, INFO, WARNING, ERROR, DEBUG)
- Clear button

---

## Color Palette

### Primary Colors:
- **Background Dark**: `#1e1e2e`
- **Background Medium**: `#2a2a3a`
- **Background Light**: `#3a3a5a`
- **Border**: `#4a4a6a`

### Accent Colors:
- **Primary (Purple)**: `#8a8aca`
- **Secondary (Blue)**: `#5a9aca`
- **Blue Action**: `#2a4a6a`

### Status Colors:
- **Success (Green)**: `#4CAF50`, `#27ae60`
- **Warning (Yellow)**: `#FFC107`
- **Error (Red)**: `#F44336`, `#e74c3c`
- **Info (Blue)**: `#2196F3`
- **Inactive (Gray)**: `#757575`, `#9e9e9e`

### Text Colors:
- **Primary**: `#ffffff`
- **Secondary**: `#b0b0b0`
- **Muted**: `#757575`

---

## Typography

### Font Family:
- Primary: Arial, system default sans-serif
- Monospace: Courier New, monospace (for logs/terminal)

### Font Sizes:
- **Title**: 16px, bold
- **Subtitle**: 12px, normal
- **Labels**: 10px, bold
- **Body**: 10px, normal
- **Gauge Value**: 24px, bold
- **Gauge Unit**: 12px, normal
- **Button**: 11px, bold

---

## Spacing & Layout

### Margins:
- Window padding: 0px (frameless)
- Section padding: 5px
- Widget padding: 3-10px

### Spacing:
- Between sections: 10px
- Between widgets: 5px
- Grid gaps: 10px

### Border Radius:
- Window: 8px (top corners only)
- Cards: 5px
- Buttons: 5px
- GroupBoxes: 8px

---

## Interactive States

### Buttons:
- **Normal**: Specified background color
- **Hover**: +10% brightness
- **Pressed**: -10% brightness, 1px inset shadow
- **Disabled**: 50% opacity, gray

### Tables:
- **Row Hover**: `#3a3a5a` background
- **Selected Row**: `#4a4a6a` background

### Tabs:
- **Normal**: Transparent
- **Hover**: `#2a2a3a`
- **Selected**: `#3a3a5a`, bold text

---

## Animation/Transitions

### Status Indicators:
- Pulse effect when active (optional)
- Color transition: 200ms ease

### Gauges:
- Arc sweep animation: 500ms ease-out
- Color transition: 300ms ease

### Button Hover:
- Brightness transition: 150ms ease

---

## Data Flow Visualization

### Component Health Flow:
```
┌─────────────┐
│ WSL Linux   │
│ Components  │ ──> Heartbeat (2s) ──> Monitor ──> UI Update
│ (4 comps)   │
└─────────────┘

┌─────────────┐
│ UE5 Plugin  │
│ Components  │ ──> Heartbeat (2s) ──> Monitor ──> UI Update
│ (2 comps)   │
└─────────────┘
```

### Update Frequencies:
- Heartbeat check: Every 2 seconds
- UI refresh: Every 500ms
- Log updates: Real-time (as events occur)

---

## Responsive Behavior

### Minimum Window Size: 800x600px
### Recommended Size: 1400x900px

### Resizing Rules:
- Title bar: Fixed height (40px)
- Header: Fixed height (80px)
- Health Status: Minimum 300px height
- Bottom tabs: Flexible, minimum 200px
- Status bar: Fixed height (25px)

### Splitter:
- Between Health Status and Bottom Tabs
- User-draggable vertical divider

---

## File References

All UI code is in a single file:
- **Main File**: `/home/myws/roa/roa_linux/roa-core/lib/components/webthread/standalone/webthread_monitor.py`
- **Total Lines**: 4,969 lines
- **Theme**: `/home/myws/roa/roa_linux/roa-core/lib/ui/dark_theme.py`

### Key Sections:
- **Lines 80-263**: Custom Widgets (DraggableTitleBar, CircularGauge, StatusIndicator, LogFilterWidget)
- **Lines 353-460**: Main Window Class Setup
- **Lines 461-600**: Title Bar Creation
- **Lines 601-767**: Header Section
- **Lines 800-1296**: Health Status Tabs
- **Lines 873-943**: Main Status Panel (Table)
- **Lines 945-1169**: System Overview Panel (Gauges)
- **Lines 1171-1295**: HB Detail Panel
- **Lines 1297-1452**: FTI Import Panel
- **Lines 1453+**: Bottom Tabs (Logs, Messages, Terminal, Stats)

---

## Export for Figma

### Recommended Figma Structure:

```
🎨 ROA Webthread Monitor
├── 📄 Main Window (1400x900 frame)
│   ├── 🎯 Components
│   │   ├── Title Bar
│   │   ├── Header Section
│   │   ├── Health Status Tabs
│   │   └── Bottom Tabs
│   └── 🎨 Variants
│       ├── Connected State
│       ├── Disconnected State
│       └── Error State
├── 🧩 Component Library
│   ├── Buttons (Start, Stop, Action)
│   ├── Circular Gauges (6 types)
│   ├── Status Indicators (4 states)
│   ├── Stat Cards
│   ├── Component Health Cards
│   └── Tables
└── 🎨 Color Styles
    ├── Background Palette
    ├── Status Palette
    └── Text Palette
```

---

## Screenshots/Mockup Notes

### Priority Views:
1. **Main Dashboard** - All tabs visible with healthy components
2. **Error State** - Multiple failed components showing red
3. **Import Dialog** - FTI import tab active
4. **Logs View** - Bottom tab with filtered logs

### Key Interactions to Design:
1. Button hover states (Start/Stop)
2. Table row selection
3. Gauge value animation (0 → target value)
4. Status indicator pulse
5. Tab switching animation

---

## Future Enhancements (Not Currently Implemented)

These are ideas for Figma exploration:
- Dark/Light theme toggle
- Customizable dashboard layouts (drag-drop widgets)
- Alert notification panel
- Historical performance graphs
- Export/import configuration
- Multi-monitor support layouts

---

## Contact/Questions

For design clarification or missing specifications, refer to the source code:
`/home/myws/roa/roa_linux/roa-core/lib/components/webthread/standalone/webthread_monitor.py`

This file contains the complete implementation with all styling, layout logic, and widget specifications.
