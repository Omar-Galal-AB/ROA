# Blueprint Creation Guide - WBP_MainDashboard

**Parent Class:** `UserWidget` (standard UMG widget)  
**Size:** Full Screen (1920x1080 recommended, scalable)  
**Purpose:** Main application interface and command center

---

## Step-by-Step Creation

### 1. Create Widget Blueprint
1. Open UE5 Editor
2. Content Browser ? Right-click ? User Interface ? Widget Blueprint
3. Name: `WBP_MainDashboard`
4. Open the blueprint

### 2. Configure Canvas
- Root: Canvas Panel
- Anchors: Full Screen
- Canvas: Fill entire screen

---

## UI Hierarchy

```
Canvas Panel (Root - Full Screen)
??? Overlay (MainOverlay)
?   ?
?   ??? Image (BackgroundImage - Fill)
?   ? ??? Color: #1E1E1E
?   ?
???? Vertical Box (MainLayout - Fill)
?       ?
?       ??? Border (TopBar - Auto Height)
?       ? ??? Horizontal Box
?       ?       ??? Text Block (AppTitle: "ROA - Robot Operator Assistant")
? ?       ??? Spacer (Fill)
?       ?    ??? Border (ConnectionStatusBadge)
?       ?       ?   ??? Text Block (ConnectionStatusText)
?       ?       ??? Border (RobotCountBadge)
?       ?     ?   ??? Horizontal Box
? ?       ?       ??? Text Block ("??")
?       ?       ?       ??? Text Block (RobotCountText)
?    ?       ??? Border (FPSBadge)
??       ?   ??? Text Block (FPSText)
?     ?       ??? Button (MenuButton)
?       ?    ??? Text Block ("?")
?       ?
?       ??? Border (ToolBar - Auto Height)
?       ?   ??? Horizontal Box
?       ?       ??? Button (SpawnRobotButton)
?       ?   ?   ??? Text Block ("? Spawn Robot")
??       ??? Button (ClearSceneButton)
?       ?       ?   ??? Text Block ("??? Clear Scene")
?    ?       ??? Button (EmergencyStopAllButton)
?       ?       ?   ??? Text Block ("?? E-STOP ALL")
?       ?       ??? Spacer (Fill)
?       ?       ??? Button (RefreshButton)
?     ?       ?   ??? Text Block ("??")
??       ??? Button (SettingsButton)
?       ? ??? Text Block ("??")
?       ?
?    ??? Horizontal Box (ContentArea - Fill, Weight: 1.0)
?       ?   ?
?       ?   ??? Border (LeftPanel - Width: 300px)
?       ?   ?   ??? Vertical Box
?       ?   ?  ??? Text Block (Header: "Quick Info")
?       ?   ?       ??? Border (InfoCard)
?       ?   ?       ?   ??? Vertical Box
?       ?   ?       ?       ??? Horizontal Box
?    ?   ?       ?       ?   ??? Text Block ("Server:")
?       ?   ?  ?       ?   ??? Text Block (ServerAddressText)
?       ?   ?       ?       ??? Horizontal Box
?       ?   ?    ?       ?   ??? Text Block ("Port:")
?       ?   ? ?       ? ??? Text Block (ServerPortText)
?       ?   ?       ?       ??? Horizontal Box
?   ?   ?   ?       ?   ??? Text Block ("Session:")
?       ?   ?       ?       ?   ??? Text Block (SessionIdText)
?       ?   ??       ??? Horizontal Box
?   ?   ?     ?           ??? Text Block ("Uptime:")
?       ?   ?       ?      ??? Text Block (UptimeText)
?       ?   ?       ?
?       ?   ?       ??? Spacer (Height: 16)
?       ?   ?       ??? Text Block (Header: "Safety Status")
?       ?   ?  ??? Border (SafetyCard)
?    ?   ?           ??? Vertical Box
? ?   ?        ??? Border (SafetyIndicator)
?       ?   ?        ?   ??? Text Block (SafetyStatusText)
?  ?   ?               ??? Text Block (ActiveAlertsText)
?       ?   ?       ??? Button (ViewAlertsButton)
?       ?   ?         ??? Text Block ("View Alerts ?")
?    ?   ?
?       ?   ??? Border (CenterPanel - Fill, Weight: 1.0)
?       ?   ?   ??? Named Slot (MainContentSlot)
?       ?   ?       ??? [3D Viewport or Multi-Robot Dashboard]
?       ?   ?
?       ?   ??? Border (RightPanel - Width: 350px)
?       ?       ??? Vertical Box
?       ?    ??? Text Block (Header: "Active Robots")
?       ?   ??? Scroll Box (RobotListScrollBox)
?       ?           ?   ??? Vertical Box (RobotListContainer)
?    ?  ?       ??? [Dynamic robot cards]
?       ?         ??? Button (ViewAllRobotsButton)
?       ? ??? Text Block ("View All ?")
?       ?
?       ??? Border (StatusBar - Auto Height)
?   ??? Horizontal Box
?   ??? Text Block (StatusMessageText: "Ready")
?     ??? Spacer (Fill)
?   ??? Text Block (ActiveRobotsStatus)
?     ??? Text Block (" | ")
?      ??? Text Block (SystemStatusText)
?            ??? Text Block (TimestampText)
?
??? Canvas Panel (FloatingWidgetsContainer)
    ??? [Floating widgets added dynamically]
```

---

## Detailed Component Setup

### **Top Bar**

#### Border (TopBar)
- Background Color: #2D2D2D
- Padding: 12, 12, 12, 12
- Height: 60px (fixed)
- ZOrder: 10

#### AppTitle
- Text: "ROA - Robot Operator Assistant v1.0"
- Font: Roboto Bold, 20
- Color: #FFFFFF

#### ConnectionStatusBadge (Border)
- Background Color: #4CAF50 (Green when connected)
- Padding: 6, 10, 6, 10
- Border Radius: 12px
- Minimum Width: 120px

#### ConnectionStatusText
- Text: "? Connected"
- Font: Roboto Medium, 12
- Color: #FFFFFF
- Alignment: Center

#### RobotCountBadge (Border)
- Background Color: #2196F3
- Padding: 6, 10, 6, 10
- Border Radius: 12px

#### RobotCountText
- Text: "0"
- Font: Roboto Bold, 14
- Color: #FFFFFF

#### FPSBadge (Border)
- Background Color: #3D3D3D
- Padding: 6, 10, 6, 10
- Border Radius: 12px

#### FPSText
- Text: "60 FPS"
- Font: Roboto Mono, 12
- Color: #00BCD4

---

### **Tool Bar**

#### Border (ToolBar)
- Background Color: #3D3D3D
- Padding: 8, 8, 8, 8
- Height: 56px (fixed)
- Border Bottom: 2px, #404040

#### SpawnRobotButton
- Size: 150 x 40
- Style:
  - Normal: #2196F3
  - Hovered: #42A5F5
  - Pressed: #1976D2
- Border Radius: 4px
- **Event:** OnClicked ? Open Spawn Dialog

#### ClearSceneButton
- Size: 150 x 40
- Style:
  - Normal: #FFC107
  - Hovered: #FFD54F
  - Pressed: #FFA000
- Border Radius: 4px
- **Event:** OnClicked ? Clear all robots

#### EmergencyStopAllButton
- Size: 170 x 40
- Style:
  - Normal: #F44336
  - Hovered: #E57373
  - Pressed: #D32F2F
- Border Radius: 4px
- Font: Roboto Bold, 14
- **Event:** OnClicked ? Emergency stop all robots

---

### **Content Area**

#### LeftPanel (Border)
- Background Color: #2D2D2D
- Width: 300px (fixed)
- Padding: 16, 16, 16, 16
- Border Right: 1px, #404040

#### InfoCard
- Background Color: #3D3D3D
- Padding: 12, 12, 12, 12
- Border Radius: 4px
- Border: 1px, #404040

#### SafetyCard
- Background Color: #3D3D3D
- Padding: 12, 12, 12, 12
- Border Radius: 4px
- Border: 1px, #404040

#### SafetyIndicator
- Background Color: #4CAF50 (dynamic)
- Padding: 8, 8, 8, 8
- Border Radius: 4px
- Alignment: Center

#### SafetyStatusText
- Text: "? ALL SYSTEMS OK"
- Font: Roboto Bold, 14
- Color: #FFFFFF
- Alignment: Center

#### CenterPanel (Border)
- Background Color: #1E1E1E
- Fill (Weight: 1.0)
- **Contains:** 3D Viewport or Multi-Robot Dashboard

#### MainContentSlot (Named Slot)
- This allows dynamic content switching
- Can show 3D viewport or multi-robot dashboard

#### RightPanel (Border)
- Background Color: #2D2D2D
- Width: 350px (fixed)
- Padding: 16, 16, 16, 16
- Border Left: 1px, #404040

#### RobotListScrollBox
- Orientation: Vertical
- Scroll Bar Visibility: Visible When Needed
- Fill (Weight: 1.0)

#### RobotListContainer (Vertical Box)
- **Populated dynamically** with robot cards

---

### **Status Bar**

#### Border (StatusBar)
- Background Color: #2D2D2D
- Padding: 8, 12, 8, 12
- Height: 36px (fixed)
- Border Top: 1px, #404040

#### StatusMessageText
- Text: "Ready"
- Font: Roboto Regular, 12
- Color: #B0B0B0

#### ActiveRobotsStatus
- Text: "Active Robots: 0"
- Font: Roboto Regular, 12
- Color: #00BCD4

#### SystemStatusText
- Text: "System OK"
- Font: Roboto Regular, 12
- Color: #4CAF50

#### TimestampText
- Text: "2025-01-15 14:30:45"
- Font: Roboto Mono, 11
- Color: #606060

---

## Blueprint Graph - Essential Functions

### Event Graph

#### Event Construct
```
Event Construct
? Initialize Dashboard
? Start Timer (Update FPS, 1.0s interval, Looping)
? Start Timer (Update Status, 0.5s interval, Looping)
? Bind Button Events
```

#### Function: Update FPS
```
Custom Event: UpdateFPS
? Get Viewport Size
? Get Frame Rate
? Format String "FPS: {FrameRate}"
? Set Text (FPSText)
```

#### Function: Update Robot Count
```
Custom Event: UpdateRobotCount
? Get All Robot Actors (from World)
? Count
? Format String "{Count}"
? Set Text (RobotCountText)
```

#### Function: Update Connection Status
```
Custom Event: UpdateConnectionStatus
? Is Server Connected?
? Branch
  ? True:
    ? Set Text "? Connected"
    ? Set Color (Green)
  ? False:
    ? Set Text "? Disconnected"
    ? Set Color (Red)
```

#### Function: On Spawn Robot Clicked
```
Event: SpawnRobotButton OnClicked
? Create Widget (WBP_RobotSpawnDialog)
? Add to Viewport
? Set ZOrder (100)
```

#### Function: On Clear Scene Clicked
```
Event: ClearSceneButton OnClicked
? Show Confirmation Dialog
? If Confirmed:
  ? Send clear_scene command to network
  ? Clear Robot List Container
  ? Update Robot Count
```

#### Function: On Emergency Stop All Clicked
```
Event: EmergencyStopAllButton OnClicked
? Play Warning Sound
? Flash Screen Red (0.2s)
? Get All Robot Actors
? For Each Robot:
  ? Call Emergency Stop
? Show Notification "All robots stopped"
```

#### Function: Populate Robot List
```
Custom Event: PopulateRobotList
? Clear RobotListContainer
? Get All Robot Actors
? For Each Robot:
  ? Create Widget (WBP_RobotCard)
  ? Initialize with Robot Data
  ? Add to RobotListContainer
```

---

## Dynamic Updates

### Timers Setup
```
Timer 1: Update FPS (1.0s interval)
Timer 2: Update Robot Count (0.5s interval)
Timer 3: Update Connection Status (1.0s interval)
Timer 4: Update Safety Status (0.5s interval)
Timer 5: Update Timestamp (1.0s interval)
```

### Event Listeners
- Robot Spawned ? Update Robot List
- Robot Despawned ? Update Robot List
- Connection Changed ? Update Connection Badge
- Collision Detected ? Update Safety Status

---

## Responsive Design

### Screen Sizes
- Minimum: 1280x720
- Recommended: 1920x1080
- Maximum: 3840x2160 (4K)

### Scaling Strategy
- Top Bar: Fixed height (60px)
- Tool Bar: Fixed height (56px)
- Status Bar: Fixed height (36px)
- Left Panel: Fixed width (300px)
- Right Panel: Fixed width (350px)
- Center Panel: Fill remaining space

### DPI Scaling
```
DPI Scale Curve:
1920x1080 ? 1.0x
2560x1440 ? 1.25x
3840x2160 ? 1.5x
```

---

## Color States

### Connection Status Badge
- **Green (#4CAF50):** Connected
- **Red (#F44336):** Disconnected
- **Yellow (#FFC107):** Connecting

### Safety Status
- **Green (#4CAF50):** All systems OK
- **Yellow (#FFC107):** Warning detected
- **Red (#F44336):** Error or collision

---

## Testing Checklist

### Visual Testing
- [ ] Top bar displays correctly
- [ ] Tool bar buttons are visible and styled
- [ ] Left panel shows connection info
- [ ] Right panel shows robot list
- [ ] Status bar at bottom
- [ ] All badges display correctly
- [ ] Colors match design system

### Functional Testing
- [ ] FPS updates every second
- [ ] Robot count updates when robots spawn/despawn
- [ ] Connection status updates
- [ ] Spawn button opens dialog
- [ ] Clear scene button works
- [ ] Emergency stop all works
- [ ] Robot list populates dynamically
- [ ] Timers run correctly

### Performance Testing
- [ ] Dashboard loads in < 1 second
- [ ] FPS stays above 60
- [ ] Memory usage < 50 MB
- [ ] Smooth animations

---

## Integration Points

### Network Commands
```python
# From Python to Dashboard
{
    "command": "robot_spawned",
    "payload": {"robot_id": "ur5_001", "robot_type": "ur5e"}
}

{
    "command": "robot_despawned",
    "payload": {"robot_id": "ur5_001"}
}

{
    "command": "connection_status",
 "payload": {"status": "connected", "session_id": "abc123"}
}
```

### To Other Widgets
- Spawn Dialog ? Creates robots ? Updates dashboard
- Robot Cards ? Selected ? Opens Control Panel/Status Monitor
- Safety Monitor ? Alert ? Updates safety badge

---

## Final Checklist

- [ ] Blueprint created with name `WBP_MainDashboard`
- [ ] Parent class is `UserWidget`
- [ ] Full screen layout configured
- [ ] All sections (Top Bar, Tool Bar, Content, Status Bar) present
- [ ] All buttons have event handlers
- [ ] FPS timer implemented
- [ ] Robot count timer implemented
- [ ] Connection status updates
- [ ] Robot list populates dynamically
- [ ] Colors match design system
- [ ] Responsive to different screen sizes
- [ ] Blueprint compiles without errors
- [ ] Tested in PIE (Play In Editor)

---

**Estimated Creation Time:** 3-4 hours  
**Complexity:** High  
**Dependencies:** None (uses standard UserWidget)  
**Priority:** Critical (Main UI)

**This is the primary interface users will interact with!**

