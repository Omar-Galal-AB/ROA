# Blueprint Creation Guide - WBP_RobotSpawnDialog

**Parent Class:** `UserWidget`  
**Size:** 500x700 pixels (Modal Dialog)  
**Purpose:** Interactive robot spawning interface

---

## Step-by-Step Creation

### 1. Create Widget Blueprint
1. Open UE5 Editor
2. Content Browser ? Right-click ? User Interface ? Widget Blueprint
3. Name: `WBP_RobotSpawnDialog`
4. Open the blueprint

### 2. Configure as Modal Dialog
- Root: Canvas Panel
- Size: 500 x 700
- ZOrder: 100 (appears on top)
- Add background overlay to block interaction with main UI

---

## UI Hierarchy

```
Canvas Panel (Root)
??? Image (OverlayBackground - Full Screen)
?   ??? Color: #000000, Opacity: 0.7
?
??? Border (DialogContainer - Centered)
    ??? Vertical Box (DialogContent)
        ?
        ??? Border (DialogHeader)
        ?   ??? Horizontal Box
        ?       ??? Text Block ("Spawn Robot")
      ?       ??? Spacer (Fill)
    ?    ??? Button (CloseButton)
        ?     ??? Text Block ("?")
        ?
        ??? Scroll Box (FormScrollBox)
        ?   ??? Vertical Box (FormContainer)
        ?       ?
        ?       ??? Text Block (Section: "Robot Configuration")
        ?       ?
        ?       ??? Horizontal Box (RobotIDRow)
        ?       ?   ??? Text Block ("Robot ID *")
        ?       ?   ??? Editable Text Box (RobotIDInput)
        ?  ?
        ?       ??? Horizontal Box (RobotTypeRow)
        ?  ?   ??? Text Block ("Robot Type *")
    ?       ?   ??? Combo Box (String) (RobotTypeDropdown)
 ?       ?
        ? ??? Spacer (Height: 16)
        ?       ??? Text Block (Section: "Spawn Location (cm)")
        ?       ?
        ? ??? Horizontal Box (PositionXRow)
        ?     ?   ??? Text Block ("X:")
?       ?   ??? Spin Box (PositionXInput)
        ??
        ?       ??? Horizontal Box (PositionYRow)
        ?       ???? Text Block ("Y:")
    ?       ?   ??? Spin Box (PositionYInput)
        ?       ?
        ?       ??? Horizontal Box (PositionZRow)
   ?       ?   ??? Text Block ("Z:")
        ?       ?   ??? Spin Box (PositionZInput)
        ?       ?
        ?       ??? Spacer (Height: 16)
        ?       ??? Text Block (Section: "Spawn Rotation (°)")
?       ?
        ?       ??? Horizontal Box (RotationRollRow)
    ?     ?   ??? Text Block ("Roll:")
        ?       ?   ??? Spin Box (RotationRollInput)
     ?       ?
        ?    ??? Horizontal Box (RotationPitchRow)
        ?       ?   ??? Text Block ("Pitch:")
    ?       ?   ??? Spin Box (RotationPitchInput)
     ?       ?
        ?       ??? Horizontal Box (RotationYawRow)
    ?       ?   ??? Text Block ("Yaw:")
 ?       ?   ??? Spin Box (RotationYawInput)
     ?       ?
        ?       ??? Spacer (Height: 16)
        ?       ??? Text Block (Section: "Initial Joint Positions (°)")
   ?       ?
        ?       ??? Horizontal Box (Joint0Row)
        ?       ?   ??? Text Block ("Joint 0:")
      ?     ?   ??? Spin Box (Joint0Input)
        ?       ?
 ?       ??? Horizontal Box (Joint1Row)
        ?    ?   ??? Text Block ("Joint 1:")
        ?   ?   ??? Spin Box (Joint1Input)
        ?       ?
        ?       ??? Horizontal Box (Joint2Row)
   ?       ?   ??? Text Block ("Joint 2:")
        ?       ?   ??? Spin Box (Joint2Input)
        ?       ?
        ?       ??? Horizontal Box (Joint3Row)
        ?       ?   ??? Text Block ("Joint 3:")
        ?  ?   ??? Spin Box (Joint3Input)
        ?       ?
        ?       ??? Horizontal Box (Joint4Row)
        ?       ?   ??? Text Block ("Joint 4:")
        ?       ?   ??? Spin Box (Joint4Input)
 ?  ?
        ?       ??? Horizontal Box (Joint5Row)
        ?       ? ??? Text Block ("Joint 5:")
        ??   ??? Spin Box (Joint5Input)
    ?   ?
    ?       ??? Spacer (Height: 16)
      ?       ??? Check Box (LoadFromURDFCheckbox)
        ?         ??? Text Block ("Load from URDF file (advanced)")
        ?
        ??? Border (ValidationMessageBorder)
 ?   ??? Text Block (ValidationMessageText)
     ?
        ??? Horizontal Box (DialogFooter)
     ??? Button (SpawnButton)
            ?   ??? Text Block ("? Spawn Robot")
    ??? Spacer (Width: 8)
    ??? Button (CancelButton)
  ??? Text Block ("Cancel")
```

---

## Detailed Component Setup

### **Overlay Background**
- Type: Image
- Anchors: Fill Screen
- Color: #000000
- Opacity: 0.7 (70% transparent)
- ZOrder: 99
- **Purpose:** Blocks interaction with background, modal effect

### **Dialog Container**
- Type: Border
- Position: Center of screen
- Size: 500 x 700
- Background Color: #2D2D2D
- Border: 2px, #404040
- Border Radius: 8px
- Shadow: Yes (4px offset, 0.5 opacity)
- Padding: 0 (padding in child elements)

---

### **Dialog Header**

#### Border (DialogHeader)
- Background Color: #1976D2 (Primary Blue)
- Padding: 16, 16, 16, 16
- Height: 56px

#### Title Text
- Text: "Spawn Robot"
- Font: Roboto Bold, 18
- Color: #FFFFFF

#### CloseButton
- Size: 32 x 32
- Style:
  - Normal: Transparent
  - Hovered: #1565C0
  - Pressed: #0D47A1
- Text: "?"
- Font: 20px
- Color: #FFFFFF
- **Event:** OnClicked ? Close Dialog

---

### **Form Container**

#### Section Headers
- Text: Section name
- Font: Roboto Bold, 14
- Color: #00BCD4
- Padding Bottom: 8px

#### Label Text Blocks
- Font: Roboto Regular, 12
- Color: #B0B0B0
- Width: 120px (fixed)
- Alignment: Right
- Padding Right: 8px

---

### **Input Fields**

#### RobotIDInput (Editable Text Box)
- Width: Fill
- Height: 32px
- Font: Roboto Regular, 14
- Text Color: #FFFFFF
- Background: #3D3D3D
- Border: 1px, #404040
- Hint Text: "e.g., ur5e_001"
- **Validation:** Required, alphanumeric + underscore only

#### RobotTypeDropdown (Combo Box String)
- Width: Fill
- Height: 32px
- Background: #3D3D3D
- Options: 
  - "ur3"
  - "ur3e"
- "ur5"
  - "ur5e"
  - "ur10"
  - "ur10e"
  - "ur15"
  - "ur15e"
  - "ur20"
  - "ur30"
  - "ur3_cb3"
  - "ur5_cb3"
  - "ur10_cb3"
- Default: "ur5e"

#### Position Spin Boxes (X, Y, Z)
- Width: Fill
- Height: 32px
- Min Value: -10000.0
- Max Value: 10000.0
- Value: 0.0
- Delta: 10.0 (increment)
- Decimal Places: 2
- Background: #3D3D3D

**Default Values:**
- PositionXInput: 0.0
- PositionYInput: 0.0
- PositionZInput: 100.0 (spawn 1 meter above ground)

#### Rotation Spin Boxes (Roll, Pitch, Yaw)
- Width: Fill
- Height: 32px
- Min Value: -180.0
- Max Value: 180.0
- Value: 0.0
- Delta: 5.0 (increment)
- Decimal Places: 1
- Background: #3D3D3D

**Default Values:** All 0.0

#### Joint Position Spin Boxes (0-5)
- Width: Fill
- Height: 32px
- Min Value: -180.0
- Max Value: 180.0
- Value: 0.0
- Delta: 5.0 (increment)
- Decimal Places: 1
- Background: #3D3D3D

**Default Values:** 
- Joint0: 0.0
- Joint1: -90.0 (common rest position)
- Joint2: 90.0 (common rest position)
- Joint3: 0.0
- Joint4: 90.0 (common rest position)
- Joint5: 0.0

#### LoadFromURDFCheckbox
- Size: 20 x 20
- Style: Modern checkbox
- Default: Unchecked
- **Future Feature:** Enable URDF file loading

---

### **Validation Message**

#### ValidationMessageBorder
- Background Color: #F44336 (Red - error)
- Padding: 8, 8, 8, 8
- Visibility: Collapsed (by default)
- Border Radius: 4px

#### ValidationMessageText
- Text: "" (empty by default)
- Font: Roboto Medium, 12
- Color: #FFFFFF
- Auto Wrap: Yes

---

### **Dialog Footer**

#### Border (DialogFooter)
- Background Color: #3D3D3D
- Padding: 16, 16, 16, 16
- Height: 72px
- Border Top: 1px, #404040

#### SpawnButton
- Size: Fill x 40px
- Weight: 1.0
- Style:
  - Normal: #4CAF50 (Success Green)
  - Hovered: #66BB6A
  - Pressed: #388E3C
  - Disabled: #606060
- Border Radius: 4px
- **Event:** OnClicked ? Validate and Spawn

#### CancelButton
- Size: Fill x 40px
- Weight: 1.0
- Style:
  - Normal: #606060
  - Hovered: #757575
  - Pressed: #424242
- Border Radius: 4px
- **Event:** OnClicked ? Close Dialog

---

## Blueprint Graph - Core Functions

### Event Construct
```
Event Construct
? Initialize Default Values
? Populate Robot Type Dropdown
? Set Focus (RobotIDInput)
? Hide Validation Message
```

### Function: Initialize Default Values
```
Custom Event: InitializeDefaults
? Set RobotIDInput Text: ""
? Set RobotTypeDropdown: "ur5e"
? Set Position X: 0.0
? Set Position Y: 0.0
? Set Position Z: 100.0
? Set Rotations: 0.0
? Set Joints: [0, -90, 90, 0, 90, 0]
```

### Function: Populate Robot Type Dropdown
```
Custom Event: PopulateRobotTypes
? Clear Options
? Add Option: "ur3"
? Add Option: "ur3e"
? Add Option: "ur5"
? Add Option: "ur5e" (set as selected)
? Add Option: "ur10"
? ... (all 13 robot types)
```

### Function: Validate Inputs
```
Function: ValidateInputs ? Returns Boolean
? Get Robot ID Text
? Is Empty?
  ? True: Show Error "Robot ID is required"
  ? Return False
? Contains Invalid Characters?
  ? True: Show Error "Robot ID can only contain letters, numbers, and underscores"
  ? Return False
? Get Robot Type
? Is Valid Option?
  ? False: Show Error "Please select a robot type"
  ? Return False
? All Valid:
  ? Hide Validation Message
  ? Return True
```

### Function: Show Validation Error
```
Function: ShowValidationError (String ErrorMessage)
? Set ValidationMessageText: ErrorMessage
? Set Visibility: Visible
? Play Animation: Shake
```

### Function: Hide Validation Message
```
Function: HideValidationMessage
? Set Visibility: Collapsed
```

### Event: On Spawn Button Clicked
```
Event: SpawnButton OnClicked
? Call ValidateInputs
? Branch
  ? True (Valid):
    ? Collect Form Data
    ? Create Spawn Request JSON
    ? Send to Network Server
    ? Show Success Notification
    ? Close Dialog
  ? False (Invalid):
    ? [Validation error already shown]
```

### Function: Collect Form Data
```
Function: CollectFormData ? Returns Struct
? Create FROASpawnRobotRequest struct
? RobotId = RobotIDInput.Text
? RobotType = RobotTypeDropdown.SelectedOption
? SpawnLocation.X = PositionXInput.Value
? SpawnLocation.Y = PositionYInput.Value
? SpawnLocation.Z = PositionZInput.Value
? SpawnRotation.Roll = RotationRollInput.Value
? SpawnRotation.Pitch = RotationPitchInput.Value
? SpawnRotation.Yaw = RotationYawInput.Value
? InitialJointStates = [Joint0-5 values in radians]
? Return struct
```

### Function: Degrees to Radians
```
Function: DegreesToRadians (Float Degrees) ? Returns Float
? Return: Degrees * PI / 180.0
```

### Function: Send Spawn Request
```
Function: SendSpawnRequest (FROASpawnRobotRequest Request)
? Get ROA Module
? Get Network Server
? Create spawn_robot message
? Send Message
? Wait for Response (async)
```

### Event: On Cancel Button Clicked
```
Event: CancelButton OnClicked
? Play Close Animation
? Remove from Parent
```

### Event: On Close Button Clicked
```
Event: CloseButton OnClicked
? Play Close Animation
? Remove from Parent
```

---

## Validation Rules

### Robot ID
- **Required:** Yes
- **Min Length:** 3
- **Max Length:** 32
- **Pattern:** `^[a-zA-Z0-9_]+$`
- **Examples:** 
  - ? "ur5e_001"
  - ? "robot_1"
  - ? "robot-1" (hyphen not allowed)
  - ? "ur" (too short)

### Position Values
- **Range:** -10000 to +10000 cm
- **Default:** (0, 0, 100)
- **Validation:** Numeric only

### Rotation Values
- **Range:** -180 to +180 degrees
- **Default:** (0, 0, 0)
- **Conversion:** Degrees ? Radians before sending

### Joint Values
- **Range:** -180 to +180 degrees
- **Default:** [0, -90, 90, 0, 90, 0]
- **Conversion:** Degrees ? Radians before sending

---

## Animations

### Dialog Open Animation
```
Animation: DialogOpen (0.3s)
? Scale: 0.8 ? 1.0 (EaseOut)
? Opacity: 0.0 ? 1.0 (Linear)
```

### Dialog Close Animation
```
Animation: DialogClose (0.2s)
? Scale: 1.0 ? 0.9 (EaseIn)
? Opacity: 1.0 ? 0.0 (Linear)
```

### Shake Animation (Error)
```
Animation: Shake (0.3s)
? Position X: 0 ? 10 ? -10 ? 5 ? -5 ? 0 (EaseInOut)
```

---

## Network Integration

### Spawn Request Message
```json
{
    "message_id": "spawn-{GUID}",
    "timestamp": 1234567890.123,
  "message_type": "REQUEST",
    "command": "spawn_robot",
    "payload": {
        "robot_id": "ur5e_001",
        "robot_type": "ur5e",
        "spawn_location": {
   "x": 0.0,
            "y": 0.0,
  "z": 100.0
     },
        "spawn_rotation": {
            "roll": 0.0,
   "pitch": 0.0,
     "yaw": 0.0
        },
        "initial_joint_states": [0.0, -1.57, 1.57, 0.0, 1.57, 0.0]
    }
}
```

### Response Handling
```
On Response Received:
? If Success:
  ? Show Success Toast "Robot spawned successfully"
  ? Close Dialog
  ? Refresh Robot List in Main Dashboard
? If Error:
  ? Show Validation Error with server message
  ? Keep Dialog Open
```

---

## Testing Checklist

### Visual Testing
- [ ] Dialog centers on screen
- [ ] Overlay blocks background interaction
- [ ] All input fields visible and styled
- [ ] Buttons styled correctly
- [ ] Scrolling works for long content
- [ ] Validation messages appear/disappear correctly

### Functional Testing
- [ ] Robot ID validation works
- [ ] Robot type dropdown populates
- [ ] Position inputs accept numeric values
- [ ] Rotation inputs accept numeric values
- [ ] Joint inputs accept numeric values
- [ ] Spawn button validates before sending
- [ ] Cancel button closes dialog
- [ ] Close button (X) closes dialog
- [ ] Data converts degrees?radians correctly

### Integration Testing
- [ ] Dialog opens from main dashboard
- [ ] Spawn request sent to network server
- [ ] Success response closes dialog
- [ ] Error response shows message
- [ ] Dashboard updates after spawn
- [ ] Can spawn multiple robots sequentially

---

## Common Issues & Solutions

### Issue: Dialog doesn't center
**Solution:** Set anchors to center (0.5, 0.5), alignment to center (0.5, 0.5)

### Issue: Overlay doesn't block clicks
**Solution:** Ensure Image component has "Is Enabled" checked

### Issue: Validation doesn't work
**Solution:** Check ValidateInputs function is called before sending

### Issue: Degrees not converting to radians
**Solution:** Multiply by PI/180 before sending: `Degrees * 3.14159 / 180`

---

## Final Checklist

- [ ] Blueprint created with name `WBP_RobotSpawnDialog`
- [ ] Parent class is `UserWidget`
- [ ] Overlay background configured
- [ ] Dialog container centered and styled
- [ ] All 13 robot types in dropdown
- [ ] All input fields have proper ranges
- [ ] Validation function implemented
- [ ] Spawn button sends network command
- [ ] Cancel button closes dialog
- [ ] Animations for open/close
- [ ] Degrees to radians conversion
- [ ] Network integration complete
- [ ] Error handling implemented
- [ ] Blueprint compiles without errors
- [ ] Tested with various inputs

---

**Estimated Creation Time:** 2-3 hours  
**Complexity:** Medium  
**Dependencies:** ROA Network Server  
**Priority:** High (Required for robot spawning)

**This dialog provides the primary interface for spawning robots in the simulation!**

