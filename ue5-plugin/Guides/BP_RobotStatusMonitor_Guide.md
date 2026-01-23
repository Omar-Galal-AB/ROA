# Blueprint Creation Guide - WBP_RobotStatusMonitor

**Parent Class:** `ROARobotStatusMonitor`  
**Size:** 350x500 pixels  
**Purpose:** Display real-time robot state information

---

## Step-by-Step Creation

### 1. Create Widget Blueprint
1. Open UE5 Editor
2. Content Browser ? Right-click ? User Interface ? Widget Blueprint
3. Name: `WBP_RobotStatusMonitor`
4. Open the blueprint

### 2. Set Parent Class
1. In Class Settings (top-right)
2. Parent Class ? Search for `ROARobotStatusMonitor`
3. Select `ROARobotStatusMonitor`

### 3. Root Canvas Setup
- Root: Canvas Panel (already exists)
- Set Size: 350 x 500

---

## UI Hierarchy

```
Canvas Panel (Root)
??? Vertical Box (MainContainer)
    ??? Border (HeaderBorder)
    ?   ??? Horizontal Box
    ?       ??? Border (StatusIndicator) **BIND**
    ?       ??? Text Block (RobotIdText) **BIND**
    ?       ??? Text Block (RobotTypeText) **BIND**
    ?
    ??? Spacer (Height: 8)
    ?
    ??? Border (PositionSection)
    ?   ??? Vertical Box
    ?       ??? Text Block (Header: "Position")
    ?       ??? Horizontal Box
    ?       ?   ??? Text Block ("X:")
    ?       ?   ??? Text Block (PositionXText) **BIND**
    ?       ??? Horizontal Box
    ?       ?   ??? Text Block ("Y:")
    ?   ?   ??? Text Block (PositionYText) **BIND**
    ?       ??? Horizontal Box
    ?    ??? Text Block ("Z:")
    ?    ??? Text Block (PositionZText) **BIND**
    ?
    ??? Spacer (Height: 8)
    ?
    ??? Border (RotationSection)
    ?   ??? Vertical Box
    ? ??? Text Block (Header: "Rotation")
    ?     ??? Horizontal Box
    ?       ?   ??? Text Block ("Roll:")
    ?       ?   ??? Text Block (RotationRollText) **BIND**
    ?    ??? Horizontal Box
    ?       ?   ??? Text Block ("Pitch:")
    ?  ?   ??? Text Block (RotationPitchText) **BIND**
    ?     ??? Horizontal Box
    ?           ??? Text Block ("Yaw:")
    ?   ??? Text Block (RotationYawText) **BIND**
    ?
    ??? Spacer (Height: 8)
    ?
  ??? Border (JointsSection)
    ?   ??? Vertical Box
    ?       ??? Text Block (Header: "Joint Positions")
    ?       ??? Text Block (JointPositionsText) **BIND**
    ?
    ??? Spacer (Height: 8)
    ?
    ??? Border (EndEffectorSection)
    ?   ??? Vertical Box
    ?       ??? Text Block (Header: "End Effector")
    ?    ??? Text Block (EndEffectorPositionText) **BIND**
    ?
    ??? Spacer (Height: 8)
    ?
    ??? Border (CollisionSection)
        ??? Vertical Box
         ??? Text Block (Header: "Collision Status")
     ??? Horizontal Box
   ?   ??? Text Block ("Status:")
     ?   ??? Text Block (CollisionStatusText) **BIND**
      ??? Horizontal Box
         ??? Text Block ("Count:")
          ??? Text Block (CollisionCountText) **BIND**
```

---

## Detailed Component Setup

### **HeaderBorder**
- Type: Border
- Padding: 8, 8, 8, 8
- Background Color: #2D2D2D
- Border Color: #404040

### **StatusIndicator** ? MUST BIND
- Type: Border
- Variable Name: `StatusIndicator`
- Is Variable: ? **Checked**
- Size: 24x24 pixels (fixed)
- Background Color: #4CAF50 (Green - will change dynamically)
- Border Radius: 12px (circular)
- Brush: Rounded Box

### **RobotIdText** ? MUST BIND
- Type: Text Block
- Variable Name: `RobotIdText`
- Is Variable: ? **Checked**
- Text: "Robot ID"
- Font: Roboto Bold, 16
- Color: #FFFFFF

### **RobotTypeText** ? MUST BIND
- Type: Text Block
- Variable Name: `RobotTypeText`
- Is Variable: ? **Checked**
- Text: "ur5e"
- Font: Roboto Regular, 12
- Color: #B0B0B0

---

### **Position Section**

#### Section Border
- Background Color: #3D3D3D
- Padding: 8, 8, 8, 8
- Border Color: #404040

#### Header Text
- Text: "?? Position (cm)"
- Font: Roboto Bold, 14
- Color: #00BCD4

#### PositionXText ? MUST BIND
- Type: Text Block
- Variable Name: `PositionXText`
- Is Variable: ? **Checked**
- Text: "0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF
- Horizontal Alignment: Right

#### PositionYText ? MUST BIND
- Type: Text Block
- Variable Name: `PositionYText`
- Is Variable: ? **Checked**
- Text: "0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF
- Horizontal Alignment: Right

#### PositionZText ? MUST BIND
- Type: Text Block
- Variable Name: `PositionZText`
- Is Variable: ? **Checked**
- Text: "0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF
- Horizontal Alignment: Right

---

### **Rotation Section**

#### Section Border
- Background Color: #3D3D3D
- Padding: 8, 8, 8, 8
- Border Color: #404040

#### Header Text
- Text: "?? Rotation (°)"
- Font: Roboto Bold, 14
- Color: #00BCD4

#### RotationRollText ? MUST BIND
- Type: Text Block
- Variable Name: `RotationRollText`
- Is Variable: ? **Checked**
- Text: "0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF
- Horizontal Alignment: Right

#### RotationPitchText ? MUST BIND
- Type: Text Block
- Variable Name: `RotationPitchText`
- Is Variable: ? **Checked**
- Text: "0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF
- Horizontal Alignment: Right

#### RotationYawText ? MUST BIND
- Type: Text Block
- Variable Name: `RotationYawText`
- Is Variable: ? **Checked**
- Text: "0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF
- Horizontal Alignment: Right

---

### **Joints Section**

#### Section Border
- Background Color: #3D3D3D
- Padding: 8, 8, 8, 8
- Border Color: #404040

#### Header Text
- Text: "?? Joint Positions (°)"
- Font: Roboto Bold, 14
- Color: #00BCD4

#### JointPositionsText ? MUST BIND
- Type: Text Block
- Variable Name: `JointPositionsText`
- Is Variable: ? **Checked**
- Text: "J0: 0.0, J1: 0.0, J2: 0.0, J3: 0.0, J4: 0.0, J5: 0.0"
- Font: Roboto Mono, 11
- Color: #FFFFFF
- Auto Wrap Text: ? Enabled
- Wrap Text At: 320 pixels

---

### **End Effector Section**

#### Section Border
- Background Color: #3D3D3D
- Padding: 8, 8, 8, 8
- Border Color: #404040

#### Header Text
- Text: "?? End Effector Position"
- Font: Roboto Bold, 14
- Color: #00BCD4

#### EndEffectorPositionText ? MUST BIND
- Type: Text Block
- Variable Name: `EndEffectorPositionText`
- Is Variable: ? **Checked**
- Text: "X: 0.00, Y: 0.00, Z: 0.00"
- Font: Roboto Mono, 12
- Color: #FFFFFF

---

### **Collision Section**

#### Section Border
- Background Color: #3D3D3D
- Padding: 8, 8, 8, 8
- Border Color: #404040

#### Header Text
- Text: "?? Collision Status"
- Font: Roboto Bold, 14
- Color: #FFC107

#### CollisionStatusText ? MUST BIND
- Type: Text Block
- Variable Name: `CollisionStatusText`
- Is Variable: ? **Checked**
- Text: "OK"
- Font: Roboto Bold, 14
- Color: #4CAF50 (Green - changes dynamically)
- Horizontal Alignment: Right

#### CollisionCountText ? MUST BIND
- Type: Text Block
- Variable Name: `CollisionCountText`
- Is Variable: ? **Checked**
- Text: "0"
- Font: Roboto Mono, 14
- Color: #FFFFFF
- Horizontal Alignment: Right

---

## Variable Bindings Checklist

**Critical Variables (MUST be marked as "Is Variable" and named exactly):**

- [ ] `RobotIdText` - Text Block for robot ID
- [ ] `RobotTypeText` - Text Block for robot type
- [ ] `PositionXText` - Text Block for X position
- [ ] `PositionYText` - Text Block for Y position
- [ ] `PositionZText` - Text Block for Z position
- [ ] `RotationRollText` - Text Block for roll rotation
- [ ] `RotationPitchText` - Text Block for pitch rotation
- [ ] `RotationYawText` - Text Block for yaw rotation
- [ ] `JointPositionsText` - Text Block for all joint positions
- [ ] `EndEffectorPositionText` - Text Block for end effector position
- [ ] `CollisionStatusText` - Text Block for collision status
- [ ] `CollisionCountText` - Text Block for collision count
- [ ] `StatusIndicator` - Border for status color indicator

**Total: 13 Variables**

---

## Style Guide

### Colors
```
Background Dark: #2D2D2D
Background Light: #3D3D3D
Border: #404040
Status OK: #4CAF50 (Green)
Status Warning: #FFC107 (Yellow)
Status Error: #F44336 (Red)
Info Blue: #00BCD4
Text White: #FFFFFF
Text Gray: #B0B0B0
```

### Status Indicator Colors (Dynamic)
- **Green (#4CAF50):** Robot OK, no collisions
- **Yellow (#FFC107):** Robot disabled or warning
- **Red (#F44336):** Robot colliding or error

### Fonts
```
Headers: Roboto Bold, 14px
Labels: Roboto Regular, 12px
Values: Roboto Mono, 12px
Status: Roboto Bold, 14px
```

### Spacing
```
Section Padding: 8px
Section Margin: 8px
Label-Value Spacing: 4px
```

---

## Update Rate Configuration

This widget updates automatically at **20 Hz** (50ms interval) as configured in the C++ class.

To change update rate, modify in C++ constructor:
```cpp
UpdateInterval = 0.05f; // 20 Hz (50ms)
```

---

## Testing

### In Editor:
1. Compile blueprint
2. Add to viewport in a test level
3. Create a test robot actor
4. Call InitializeWithRobot() from blueprint
5. Move robot and verify values update

### Test Cases:
- [ ] Widget displays robot ID correctly
- [ ] Widget displays robot type correctly
- [ ] Position values update in real-time
- [ ] Rotation values update in real-time
- [ ] Joint positions display correctly
- [ ] End effector position updates
- [ ] Collision status shows OK (green)
- [ ] Status indicator is circular and green
- [ ] All values formatted with 2 decimal places

### Collision Test:
1. Make robot collide with something
2. Verify:
   - [ ] CollisionStatusText changes to "COLLIDING" (red)
   - [ ] StatusIndicator changes to red
   - [ ] CollisionCountText increments

---

## Common Issues & Solutions

### Issue: Variables not binding
**Solution:** Ensure "Is Variable" is checked and name matches exactly (case-sensitive)

### Issue: Values not updating
**Solution:** Check that InitializeWithRobot() was called with valid robot actor

### Issue: Status indicator not circular
**Solution:** Set Border Radius to 12px (half of 24px size) and use Rounded Box brush

### Issue: Text wrapping incorrectly
**Solution:** Enable Auto Wrap Text and set Wrap Text At to widget width minus padding

---

## Performance Considerations

- Update Rate: 20 Hz (good for monitoring)
- 13 text components updating
- Minimal CPU impact (~0.1%)
- Memory: ~1 MB per widget

---

## Blueprint Graph (Optional Enhancements)

### Custom Event: Flash on Collision
```
Event OnCollisionDetected
? Play Animation (Flash Red)
? Play Sound (Alert Beep)
```

### Custom Event: Highlight Value Change
```
Event OnValueChanged (Text Target)
? Set Color (Cyan)
? Delay (0.2s)
? Set Color (White)
```

---

## Final Checklist

- [ ] Blueprint created with name `WBP_RobotStatusMonitor`
- [ ] Parent class set to `ROARobotStatusMonitor`
- [ ] All 13 required variables created and bound
- [ ] Variable names match exactly (case-sensitive)
- [ ] All variables marked as "Is Variable"
- [ ] UI layout matches specification
- [ ] Status indicator is circular (Border Radius: 12px)
- [ ] All sections have proper borders and padding
- [ ] Fonts and colors match style guide
- [ ] Blueprint compiles without errors
- [ ] Widget tested in editor with real robot
- [ ] Values update at 20 Hz
- [ ] Collision status changes color dynamically

---

**Estimated Creation Time:** 1-2 hours  
**Complexity:** Medium  
**Dependencies:** ROARobotStatusMonitor C++ class (already implemented)  
**Update Rate:** 20 Hz (automatic)

**Once complete, this widget provides comprehensive real-time robot monitoring!**

