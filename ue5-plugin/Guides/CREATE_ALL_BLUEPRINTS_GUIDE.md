# ?? CREATE ALL ROA BLUEPRINTS - Step-by-Step Guide

**Complete Blueprint Creation for All 4 Priority Widgets**

---

## ?? Folder Structure Setup

First, ensure your Content folder has the correct structure:

```
Content/
??? ROA/
    ??? UI/
  ??? Widgets/? All widget blueprints go here
        ?   ??? WBP_RobotControlPanel
        ?   ??? WBP_RobotStatusMonitor
        ?   ??? WBP_MainDashboard
        ?   ??? WBP_RobotSpawnDialog
        ?
        ??? Assets/   ? Images, icons, materials
            ??? Icons/
            ??? Textures/
```

**Already created:**  
? `Content/ROA/UI/` folder structure is ready

---

## ?? Blueprint Creation Order

### **Priority 1: Essential Widgets (Create First)**
1. **WBP_RobotControlPanel** (1-2 hours)
2. **WBP_RobotStatusMonitor** (1-2 hours)

### **Priority 2: Main Interface (Create Next)**
3. **WBP_MainDashboard** (3-4 hours)
4. **WBP_RobotSpawnDialog** (2-3 hours)

**Total Time:** 8-12 hours for all 4 widgets

---

## ?? WIDGET 1: Robot Control Panel

### **Step-by-Step Creation**

#### **Step 1: Create Widget Blueprint**
```
1. Content Browser ? Navigate to Content/ROA/UI/Widgets/
2. Right-click ? User Interface ? Widget Blueprint
3. Name: WBP_RobotControlPanel
4. Double-click to open
```

#### **Step 2: Set Parent Class** ? CRITICAL
```
1. Click "Class Settings" button (top toolbar)
2. In Details panel ? "Class Options"
3. Find "Parent Class"
4. Click dropdown ? Search: "ROARobotControlPanel"
5. Select: ROARobotControlPanel (C++ class)
6. Compile (green checkmark icon)
```

#### **Step 3: Design Layout**

**Canvas Panel Setup:**
```
Root: Canvas Panel (default)
Size: 400 x 600
```

**Add Main Container:**
```
1. Drag "Vertical Box" onto Canvas
2. Rename: MainContainer
3. Anchors: Fill (stretch to fill parent)
4. Offsets: 0, 0, 0, 0
```

#### **Step 4: Add Header**
```
1. Drag "Border" into MainContainer
2. Rename: HeaderBorder
3. Background Color: #2D2D2D
4. Padding: 8, 8, 8, 8
```

**Add Header Content:**
```
Inside HeaderBorder:
1. Drag "Horizontal Box"
2. Add "Text Block" ? Name: RobotNameText
   - Variable: ? IS VARIABLE (CRITICAL!)
   - Text: "Robot Name"
   - Font: Roboto Bold, 18
   - Color: #FFFFFF
3. Add "Spacer" (Fill)
4. Add "Text Block" ? Name: RobotTypeText
   - Variable: ? IS VARIABLE (CRITICAL!)
   - Text: "ur5e"
   - Font: Roboto Regular, 14
   - Color: #B0B0B0
```

#### **Step 5: Add Joint Sliders Container** ? CRITICAL
```
1. Drag "Scroll Box" into MainContainer
2. Rename: JointSlidersContainer
3. Variable: ? IS VARIABLE (CRITICAL!)
4. Orientation: Vertical
5. Visibility: Visible When Needed
6. Height: Fill (Weight: 1.0)

NOTE: Joint sliders are created dynamically by C++ code
This container will be populated automatically
```

#### **Step 6: Add Motion Duration Controls**
```
1. Drag "Horizontal Box" into MainContainer
2. Add "Text Block" ? "Motion Duration:"
3. Add "Slider" ? Name: DurationSlider
   - Min: 0.1
   - Max: 10.0
   - Value: 2.0
4. Add "Text Block" ? Name: DurationValueText
   - Text: "2.0s"
   - Font: Roboto Mono, 12
```

#### **Step 7: Add Control Buttons** ? CRITICAL
```
Add 3 Buttons to MainContainer:

1. Button ? Name: ApplyButton
   - Variable: ? IS VARIABLE (CRITICAL!)
   - Size: Fill x 36px
   - Background: #2196F3 (Blue)
   - Text: "Apply Joint Positions"

2. Button ? Name: ResetButton
   - Variable: ? IS VARIABLE (CRITICAL!)
   - Size: Fill x 36px
   - Background: #FFC107 (Yellow)
   - Text: "Reset to Zero"

3. Button ? Name: EmergencyStopButton
   - Variable: ? IS VARIABLE (CRITICAL!)
   - Size: Fill x 48px
   - Background: #F44336 (Red)
   - Text: "?? EMERGENCY STOP"
```

#### **Step 8: Variable Binding Checklist** ? MUST DO

**Verify these 6 variables are marked "Is Variable":**
- [ ] RobotNameText
- [ ] RobotTypeText
- [ ] JointSlidersContainer
- [ ] ApplyButton
- [ ] ResetButton
- [ ] EmergencyStopButton

**How to check:**
```
1. Select each component
2. Details panel ? tick "Is Variable"
3. Name must match exactly (case-sensitive!)
```

#### **Step 9: Compile & Save**
```
1. Click "Compile" (green checkmark)
2. Fix any errors shown
3. Click "Save"
4. Close widget
```

#### **Step 10: Test**
```
1. Drag WBP_RobotControlPanel into viewport
2. Play (PIE)
3. Widget should appear
4. No functionality yet (needs robot assignment)
```

---

## ?? WIDGET 2: Robot Status Monitor

### **Quick Creation Steps**

#### **Create & Setup**
```
1. Content/ROA/UI/Widgets/ ? Right-click ? Widget Blueprint
2. Name: WBP_RobotStatusMonitor
3. Open blueprint
4. Class Settings ? Parent Class ? ROARobotStatusMonitor
5. Compile
```

#### **Layout Structure**
```
Canvas Panel (Root)
??? Vertical Box (MainContainer)
    ??? Border (HeaderBorder)
    ?   ??? Border (StatusIndicator) ? BIND
    ?   ??? Text (RobotIdText) ? BIND
    ?   ??? Text (RobotTypeText) ? BIND
  ?
    ??? Border (PositionSection)
    ?   ??? Text (PositionXText) ? BIND
    ?   ??? Text (PositionYText) ? BIND
    ?   ??? Text (PositionZText) ? BIND
    ?
    ??? Border (RotationSection)
    ?   ??? Text (RotationRollText) ? BIND
    ?   ??? Text (RotationPitchText) ? BIND
    ?   ??? Text (RotationYawText) ? BIND
    ?
    ??? Border (JointsSection)
    ?   ??? Text (JointPositionsText) ? BIND
    ?
    ??? Border (EndEffectorSection)
    ?   ??? Text (EndEffectorPositionText) ? BIND
    ?
    ??? Border (CollisionSection)
        ??? Text (CollisionStatusText) ? BIND
        ??? Text (CollisionCountText) ? BIND
```

#### **13 Variables to Bind** ? CRITICAL
```
1. RobotIdText
2. RobotTypeText
3. PositionXText
4. PositionYText
5. PositionZText
6. RotationRollText
7. RotationPitchText
8. RotationYawText
9. JointPositionsText
10. EndEffectorPositionText
11. CollisionStatusText
12. CollisionCountText
13. StatusIndicator (Border for status color)
```

**See detailed guide:** `Guides/BP_RobotStatusMonitor_Guide.md`

---

## ?? WIDGET 3: Main Dashboard

### **Quick Creation Steps**

```
1. Create: WBP_MainDashboard (Parent: UserWidget)
2. Size: Full Screen (1920x1080)
3. Anchors: Fill
```

#### **5 Main Sections**
```
1. Top Bar (60px) - Status badges
2. Tool Bar (56px) - Action buttons
3. Content Area (Fill)
   - Left Panel (300px)
   - Center Panel (Fill)
   - Right Panel (350px)
4. Status Bar (36px)
5. Floating Widgets Container
```

#### **Key Components**
```
- ConnectionStatusBadge
- RobotCountText
- FPSText
- SpawnRobotButton
- ClearSceneButton
- EmergencyStopAllButton
- RobotListContainer (dynamic)
- MainContentSlot (Named Slot)
```

**See detailed guide:** `Guides/BP_MainDashboard_Guide.md`

---

## ?? WIDGET 4: Robot Spawn Dialog

### **Quick Creation Steps**

```
1. Create: WBP_RobotSpawnDialog (Parent: UserWidget)
2. Size: 500x700 (modal dialog)
3. Add overlay background
```

#### **Form Components**
```
- RobotIDInput (Editable Text Box)
- RobotTypeDropdown (Combo Box)
  - Options: ur3, ur3e, ur5, ur5e, ur10, ur10e, etc.
- PositionXInput (Spin Box)
- PositionYInput (Spin Box)
- PositionZInput (Spin Box)
- RotationRollInput (Spin Box)
- RotationPitchInput (Spin Box)
- RotationYawInput (Spin Box)
- Joint0-5Input (6 Spin Boxes)
- SpawnButton
- CancelButton
```

**See detailed guide:** `Guides/BP_RobotSpawnDialog_Guide.md`

---

## ? Quick Creation Checklist

### **For Each Widget:**

#### **Before Starting**
- [ ] Read detailed guide in `Guides/BP_*.md`
- [ ] Have color palette ready
- [ ] Know variable names

#### **During Creation**
- [ ] Set correct parent class
- [ ] Mark all required variables as "Is Variable"
- [ ] Use exact names (case-sensitive!)
- [ ] Apply correct colors and fonts
- [ ] Set appropriate sizes

#### **After Creation**
- [ ] Compile successfully
- [ ] Save blueprint
- [ ] Test in viewport
- [ ] Verify variables bound
- [ ] Check no errors in log

---

## ?? Design System Quick Reference

### **Colors**
```
Primary Blue:    #2196F3
Success Green:   #4CAF50
Warning Yellow:  #FFC107
Error Red:       #F44336
Background Dark: #1E1E1E
Background Card: #2D2D2D
Background Input:#3D3D3D
Border:        #404040
Text White:      #FFFFFF
Text Gray:       #B0B0B0
```

### **Fonts**
```
Headers: Roboto Bold, 18px
Body:    Roboto Regular, 14px
Labels:  Roboto Medium, 12px
Values:  Roboto Mono, 12px
```

### **Spacing**
```
Small:  8px
Medium: 16px
Large:  24px
```

---

## ?? Common Mistakes to Avoid

### **? Mistake 1: Wrong Parent Class**
```
Wrong: Parent Class = UserWidget
Right: Parent Class = ROARobotControlPanel (for control panel)
```

### **? Mistake 2: Not Marking Variables**
```
Wrong: Component without "Is Variable" checked
Right: Check "Is Variable" for all bound components
```

### **? Mistake 3: Wrong Variable Names**
```
Wrong: robotnametext (lowercase)
Right: RobotNameText (exact match, case-sensitive)
```

### **? Mistake 4: Wrong Container Type**
```
Wrong: JointSlidersContainer = Vertical Box
Right: JointSlidersContainer = Scroll Box
```

---

## ?? Testing Blueprints

### **Test Each Widget:**

```cpp
// In a test Blueprint or Level Blueprint
Event BeginPlay
{
    // Create widget
    Create Widget (Class: WBP_RobotControlPanel)
    ? Add to Viewport
    
    // Optional: Initialize with test robot
    Get All Actors of Class (ROARobotActor)
    ? Get (index 0)
    ? Call "InitializeWithRobot" on widget
}
```

### **Python Test:**

```python
import socket, json, time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 9876))

# Connect first
connect_msg = {
    "message_id": "test-connect",
    "timestamp": time.time(),
    "message_type": "REQUEST",
    "command": "connect",
    "payload": {"client_name": "Widget_Test", "version": "1.0.0"}
}
sock.send(json.dumps(connect_msg).encode())
sock.recv(4096)

# Create widget
widget_msg = {
    "message_id": "widget-001",
    "timestamp": time.time(),
  "message_type": "REQUEST",
    "command": "create_widget",
    "payload": {
        "widget_id": "control_panel_001",
        "widget_type": "control_panel",
        "robot_id": "ur5e_001"  # Must have spawned robot first
    }
}
sock.send(json.dumps(widget_msg).encode())
response = sock.recv(4096)
print(response.decode())
```

---

## ?? Completion Tracker

```
Widget Creation Progress:

[ ] WBP_RobotControlPanel
    [ ] Blueprint created
    [ ] Parent class set
    [ ] 6 variables bound
    [ ] Layout complete
    [ ] Compiled successfully
 [ ] Tested in viewport

[ ] WBP_RobotStatusMonitor
    [ ] Blueprint created
    [ ] Parent class set
    [ ] 13 variables bound
    [ ] Layout complete
    [ ] Compiled successfully
    [ ] Tested in viewport

[ ] WBP_MainDashboard
    [ ] Blueprint created
    [ ] Full-screen layout
    [ ] 5 sections created
    [ ] Dynamic content setup
    [ ] Compiled successfully
    [ ] Tested in viewport

[ ] WBP_RobotSpawnDialog
  [ ] Blueprint created
    [ ] Modal dialog setup
    [ ] Form validation
    [ ] Network integration
    [ ] Compiled successfully
    [ ] Tested in viewport

Overall Progress: 0/4 widgets complete
```

---

## ?? Next Steps After Creation

### **Once All Widgets Created:**

1. **Test with Python:**
   ```powershell
   python test_roa_connection.py
   python test_robot_spawn.py
   ```

2. **Create Test Level:**
   - Add WBP_MainDashboard to viewport
   - Test spawning robot via WBP_RobotSpawnDialog
   - Verify control panel controls robot
   - Check status monitor updates

3. **Polish:**
   - Add animations
   - Fine-tune colors
   - Test responsiveness
   - Optimize performance

---

## ?? Pro Tips

1. **Save Often** - Compile and save after each section
2. **Test Incrementally** - Don't wait until end to test
3. **Use Guides** - Detailed guides in `Guides/BP_*.md`
4. **Check Variables** - Most issues are wrong variable names
5. **Parent Class Matters** - Must be set correctly

---

## ?? Need Help?

**If stuck:**
1. Check Output Log for errors
2. Verify parent class is correct
3. Check all variable names match
4. Ensure "Is Variable" is checked
5. Review detailed guide for that widget

**Detailed Guides:**
- `Guides/BP_RobotControlPanel_Guide.md`
- `Guides/BP_RobotStatusMonitor_Guide.md`
- `Guides/BP_MainDashboard_Guide.md`
- `Guides/BP_RobotSpawnDialog_Guide.md`

---

**Ready to Create? Start with WBP_RobotControlPanel!** ??

**Estimated Time:**
- Widget 1: 1-2 hours
- Widget 2: 1-2 hours
- Widget 3: 3-4 hours
- Widget 4: 2-3 hours
- **Total: 8-12 hours**

**You can do this!** ??

---

**Guide Version:** 1.0  
**Last Updated:** January 2025  
**Status:** Ready for Blueprint Creation

