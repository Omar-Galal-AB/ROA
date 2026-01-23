# Blueprint Creation Guide - WBP_RobotControlPanel

**Parent Class:** `ROARobotControlPanel`  
**Size:** 400x600 pixels  
**Purpose:** Control robot joints with sliders and buttons

---

## Step-by-Step Creation

### 1. Create Widget Blueprint
1. Open UE5 Editor
2. Content Browser ? Right-click ? User Interface ? Widget Blueprint
3. Name: `WBP_RobotControlPanel`
4. Open the blueprint

### 2. Set Parent Class
1. In Class Settings (top-right)
2. Parent Class ? Search for `ROARobotControlPanel`
3. Select `ROARobotControlPanel`

### 3. Root Canvas Setup
- Root: Canvas Panel (already exists)
- Set Size: 400 x 600

---

## UI Hierarchy

```
Canvas Panel (Root)
??? Vertical Box (MainContainer)
    ??? Border (HeaderBorder)
    ?   ??? Horizontal Box
    ?       ??? Text Block (RobotNameText) **BIND**
 ?       ??? Text Block (RobotTypeText) **BIND**
    ?
    ??? Spacer (Height: 16)
    ?
  ??? Scroll Box (JointSlidersContainer) **BIND**
    ?   ??? [Dynamic joint sliders created by C++]
    ?
    ??? Spacer (Height: 16)
    ?
    ??? Horizontal Box (MotionDurationRow)
    ?   ??? Text Block ("Motion Duration:")
    ?   ??? Slider (DurationSlider)
    ?   ??? Text Block (DurationValueText)
    ?
    ??? Spacer (Height: 16)
    ?
 ??? Horizontal Box (ButtonRow)
        ??? Button (ApplyButton) **BIND**
 ?   ??? Text Block ("Apply")
        ??? Button (ResetButton) **BIND**
        ?   ??? Text Block ("Reset")
        ??? Button (EmergencyStopButton) **BIND**
   ??? Text Block ("E-STOP")
```

---

## Detailed Component Setup

### **HeaderBorder**
- Type: Border
- Padding: 8, 8, 8, 8
- Background Color: #2D2D2D
- Border Color: #404040
- Brush: Rounded Box

### **RobotNameText** ? MUST BIND
- Type: Text Block
- Variable Name: `RobotNameText`
- Is Variable: ? **Checked**
- Text: "Robot Name"
- Font: Roboto Bold, 18
- Color: #FFFFFF
- Horizontal Alignment: Left

### **RobotTypeText** ? MUST BIND
- Type: Text Block
- Variable Name: `RobotTypeText`
- Is Variable: ? **Checked**
- Text: "ur5e"
- Font: Roboto Regular, 14
- Color: #B0B0B0
- Horizontal Alignment: Right

### **JointSlidersContainer** ? MUST BIND
- Type: Scroll Box (not Vertical Box!)
- Variable Name: `JointSlidersContainer`
- Is Variable: ? **Checked**
- Orientation: Vertical
- Scroll Bar Visibility: Visible When Needed
- Always Show Scrollbar: No
- Height: Fill (weight: 1.0)

**Note:** Joint sliders are created dynamically by C++ code. This container will be populated automatically when InitializeWithRobot() is called.

### **Motion Duration Row**

#### DurationSlider
- Type: Slider
- Min Value: 0.1
- Max Value: 10.0
- Value: 2.0
- Step Size: 0.1

#### DurationValueText
- Type: Text Block
- Text: "2.0s"
- Font: Roboto Mono, 12
- Color: #00BCD4
- Width: 60px

### **ApplyButton** ? MUST BIND
- Type: Button
- Variable Name: `ApplyButton`
- Is Variable: ? **Checked**
- Size: Fill width, 36px height
- Style:
  - Normal Color: #2196F3
  - Hovered Color: #42A5F5
  - Pressed Color: #1976D2
- Padding: 8, 8, 8, 8

**Child Text:**
- Text: "Apply Joint Positions"
- Font: Roboto Medium, 14
- Color: #FFFFFF
- Alignment: Center

### **ResetButton** ? MUST BIND
- Type: Button
- Variable Name: `ResetButton`
- Is Variable: ? **Checked**
- Size: Fill width, 36px height
- Style:
  - Normal Color: #FFC107
  - Hovered Color: #FFD54F
  - Pressed Color: #FFA000
- Padding: 8, 8, 8, 8

**Child Text:**
- Text: "Reset to Zero"
- Font: Roboto Medium, 14
- Color: #000000
- Alignment: Center

### **EmergencyStopButton** ? MUST BIND
- Type: Button
- Variable Name: `EmergencyStopButton`
- Is Variable: ? **Checked**
- Size: Fill width, 48px height (taller for safety)
- Style:
  - Normal Color: #F44336
  - Hovered Color: #E57373
  - Pressed Color: #D32F2F
- Padding: 8, 8, 8, 8

**Child Text:**
- Text: "?? EMERGENCY STOP"
- Font: Roboto Bold, 16
- Color: #FFFFFF
- Alignment: Center

---

## Variable Bindings Checklist

**Critical Variables (MUST be marked as "Is Variable" and named exactly):**

- [ ] `RobotNameText` - Text Block for robot ID
- [ ] `RobotTypeText` - Text Block for robot type
- [ ] `JointSlidersContainer` - Scroll Box for joint sliders
- [ ] `ApplyButton` - Button to apply joint positions
- [ ] `ResetButton` - Button to reset joints
- [ ] `EmergencyStopButton` - Button for emergency stop

**Event Bindings (Handled by C++ automatically via AddDynamic):**
- ApplyButton::OnClicked ? Handled in NativeConstruct()
- ResetButton::OnClicked ? Handled in NativeConstruct()
- EmergencyStopButton::OnClicked ? Handled in NativeConstruct()

---

## Style Guide

### Colors
```
Background: #2D2D2D
Border: #404040
Primary Button: #2196F3
Reset Button: #FFC107
Emergency: #F44336
Text White: #FFFFFF
Text Gray: #B0B0B0
```

### Fonts
```
Headers: Roboto Bold
Body: Roboto Regular
Values: Roboto Mono
```

### Spacing
```
Padding: 8px
Margin: 16px between sections
Button Height: 36px (48px for E-Stop)
```

---

## Testing

### In Editor:
1. Compile blueprint
2. Add to viewport in a test level
3. Create a test robot actor
4. Call InitializeWithRobot() from blueprint

### Test Cases:
- [ ] Widget displays robot name correctly
- [ ] Widget displays robot type correctly
- [ ] Joint sliders are created dynamically
- [ ] Apply button is clickable
- [ ] Reset button is clickable
- [ ] Emergency stop button is clickable (red, prominent)
- [ ] Slider values update from robot state

---

## Common Issues & Solutions

### Issue: Variables not binding
**Solution:** Ensure "Is Variable" is checked and name matches exactly (case-sensitive)

### Issue: Buttons don't work
**Solution:** Event bindings are automatic in C++, just ensure button variables are named correctly

### Issue: Joint sliders don't appear
**Solution:** Joint sliders are created dynamically by C++. Container must be a VerticalBox (or ScrollBox)

### Issue: Parent class not found
**Solution:** Rebuild project to generate C++ classes, then refresh editor

---

## Blueprint Graph (Optional Events)

You can add these custom events in the Event Graph if needed:

### On Joint Slider Changed (Custom Event)
```
Event OnSliderValueChanged (float NewValue, int32 JointIndex)
? Format String "Joint {JointIndex}: {NewValue}°"
? Print String
```

### On Apply Clicked (Custom Event)
```
Event OnApplyClicked
? Play Sound (optional)
? Show notification (optional)
```

---

## Final Checklist

- [ ] Blueprint created with name `WBP_RobotControlPanel`
- [ ] Parent class set to `ROARobotControlPanel`
- [ ] All 6 required variables created and bound
- [ ] Variable names match exactly (case-sensitive)
- [ ] All variables marked as "Is Variable"
- [ ] UI layout matches specification
- [ ] Buttons styled with correct colors
- [ ] Emergency stop button is prominent and red
- [ ] Blueprint compiles without errors
- [ ] Widget tested in editor

---

**Estimated Creation Time:** 1-2 hours  
**Complexity:** Medium  
**Dependencies:** ROARobotControlPanel C++ class (already implemented)

**Once complete, this widget can be instantiated from Python via the `create_widget` command!**

