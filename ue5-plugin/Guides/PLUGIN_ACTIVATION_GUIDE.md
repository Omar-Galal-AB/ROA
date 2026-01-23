# ?? ROA Plugin Activation Guide

**How to Enable the ROA Plugin in Your UE5 Project**

---

## Method 1: Through UE5 Editor (Recommended)

### **Step 1: Open UE5 Editor**
```
1. Launch ROA_V1.uproject
2. Wait for the editor to fully load
```

### **Step 2: Open Plugins Window**
```
1. Menu Bar ? Edit ? Plugins
   OR
2. Press: Ctrl + Shift + P (quick shortcut)
```

### **Step 3: Find ROA Plugin**
```
1. In the Plugins window, use the search box
2. Type: "ROA"
3. You should see: "ROA - Robot Operator Assistant"
```

### **Step 4: Enable the Plugin**
```
1. Check the checkbox next to "ROA"
2. Status should change to: ? Enabled
3. A popup will appear asking to restart editor
4. Click: "Restart Now"
```

### **Step 5: Verify Activation**
```
After restart, check:
1. Edit ? Plugins ? Search "ROA" ? Should show ? Enabled
2. Window ? Developer Tools ? Output Log
3. Search for: "ROA Plugin"
4. Should see: "ROA Plugin: Startup complete - Ready for connections"
```

---

## Method 2: Through .uproject File (Manual)

### **Edit ROA_V1.uproject**
```json
{
    "FileVersion": 3,
    "EngineAssociation": "5.6",
    "Category": "",
    "Description": "",
    "Modules": [
{
            "Name": "ROA_V1",
            "Type": "Runtime",
        "LoadingPhase": "Default"
    }
    ],
    "Plugins": [
     {
       "Name": "ROA",
            "Enabled": true
   }
    ]
}
```

**Steps:**
1. Close UE5 Editor
2. Open `ROA_V1.uproject` in text editor
3. Add the "Plugins" section as shown above
4. Save file
5. Reopen project
6. Plugin should auto-enable

---

## Method 3: Verify Plugin is Detected

### **Check Plugin Folder Structure**
```
Plugins/
??? ROA_PlugIn/
    ??? ROA.uplugin ? (Plugin descriptor)
    ??? Source/
    ?   ??? ROA/
    ?       ??? Public/ (12 headers)
    ?       ??? Private/ (12 implementations)
    ??? Resources/
  ??? Icon128.png (optional)
```

### **Check ROA.uplugin File**
```json
{
    "FileVersion": 3,
 "Version": 1,
    "VersionName": "1.0.0-alpha",
    "FriendlyName": "ROA - Robot Operator Assistant",
    "Description": "Universal Robot control and simulation plugin for UE5",
    "Category": "Robotics",
    "CreatedBy": "ROA Development Team",
    "CreatedByURL": "",
    "DocsURL": "",
    "MarketplaceURL": "",
    "SupportURL": "",
    "CanContainContent": true,
    "IsBetaVersion": true,
    "IsExperimentalVersion": false,
    "Installed": false,
    "Modules": [
        {
          "Name": "ROA",
            "Type": "Runtime",
            "LoadingPhase": "Default"
     }
    ]
}
```

---

## Verification Checklist

### **? Plugin Activated Successfully When:**
- [ ] Plugin shows in Edit ? Plugins with ? Enabled
- [ ] Output Log shows "ROA Plugin: Startup complete"
- [ ] Output Log shows "Network Server started on port 9876"
- [ ] No red error messages in Output Log
- [ ] Can see ROA classes in Content Browser ? C++ Classes
- [ ] ROARobotActor appears in Place Actors panel

### **? Common Issues:**

#### **Issue: Plugin doesn't appear in list**
**Solution:**
1. Check Plugins/ROA_PlugIn folder exists
2. Verify ROA.uplugin file exists
3. Right-click ROA_V1.uproject ? "Generate Visual Studio project files"
4. Rebuild project

#### **Issue: Plugin shows but won't enable**
**Solution:**
1. Check Output Log for error messages
2. Verify plugin compiled successfully (Build ? Build Solution)
3. Check all dependencies are met
4. Restart Visual Studio and UE5

#### **Issue: "Module 'ROA' could not be loaded"**
**Solution:**
1. Close UE5 Editor
2. Delete Binaries/ folder in plugin
3. Delete Intermediate/ folder in plugin
4. Rebuild project in Visual Studio
5. Reopen UE5 Editor

---

## Test Plugin is Working

### **Quick Test:**
```powershell
# In PowerShell (while UE5 Editor is running)
cd D:\ROA\UE5_Projects\ROA_V1
python test_roa_connection.py
```

**Expected Output:**
```
[PASS] ? Connected successfully!
[PASS] ? Connect successful!
TOTAL: 5/5 tests passed (100%)
?? ALL TESTS PASSED! Plugin is fully functional!
```

---

## Advanced: Enable for All Projects

If you want ROA available globally:

### **Option 1: Engine Plugin**
```
1. Copy Plugins/ROA_PlugIn/ to:
   D:\Games\EPIC\UE_5.6\Engine\Plugins\ROA_PlugIn\
2. Restart UE5
3. Plugin available in all projects
```

### **Option 2: Marketplace-Style Install**
```
1. Package plugin as .uplugin
2. Install via Epic Games Launcher
3. Available in all projects
```

---

## Plugin Capabilities After Activation

### **What You Get:**

? **C++ Classes Available:**
- ROARobotActor (Robot spawning)
- ROAWidgetBase (Widget base class)
- ROARobotControlPanel (Control panel widget)
- ROARobotStatusMonitor (Status monitor widget)
- All in Content Browser ? C++ Classes ? ROA

? **Network Server:**
- TCP socket on port 9876
- JSON protocol
- Python integration ready

? **Blueprint Support:**
- Can create Blueprint child classes
- Widget blueprints can inherit from ROA widgets
- Full Blueprint API exposure

? **Editor Integration:**
- Place robot actors in viewport
- Widget creation tools
- Real-time debugging

---

## Next Steps After Activation

1. ? **Test Connection:**
   ```powershell
   python test_roa_connection.py
   ```

2. ? **Create Blueprints:**
   - Follow guides in `Guides/BP_*.md`
   - Start with WBP_RobotControlPanel

3. ? **Spawn Test Robot:**
   ```powershell
   python test_robot_spawn.py
```

4. ? **Build UI:**
   - Create all 4 priority widgets
 - Test with Python integration

---

## Troubleshooting

### **Plugin Not Loading**
```
1. Check: Output Log ? Filter "LogPluginManager"
2. Look for: "Plugin 'ROA' failed to load"
3. Check: Compilation errors in Output Log
4. Solution: Rebuild plugin in Visual Studio
```

### **Network Server Not Starting**
```
1. Check: Output Log ? Filter "LogTemp"
2. Look for: "Failed to start Network Server"
3. Check: Port 9876 not in use (netstat -an | findstr 9876)
4. Check: Windows Firewall settings
```

### **Classes Not Visible**
```
1. Check: View Options in Content Browser
2. Enable: "Show C++ Classes"
3. Enable: "Show Plugin Content"
4. Refresh: Right-click ? "Show in Explorer" ? Back to editor
```

---

## Status Indicators

### **Plugin Enabled Successfully:**
```
?? Edit ? Plugins ? ROA ? ? Enabled
?? Output Log: "ROA Plugin: Startup complete"
?? Output Log: "Network Server started on port 9876"
?? C++ Classes ? ROA folder visible
?? test_roa_connection.py ? All tests pass
```

### **Plugin Not Working:**
```
?? Edit ? Plugins ? ROA ? ? Disabled
?? Output Log: Red error messages
?? Output Log: "Module could not be loaded"
?? C++ Classes ? ROA folder missing
?? test_roa_connection.py ? Connection refused
```

---

**Activation Complete!** ??

**Next:** Create Blueprints (see `Guides/GUI_BLUEPRINTS_SUMMARY.md`)

---

**Guide Version:** 1.0  
**Last Updated:** January 2025  
**Plugin Version:** 1.0.0-alpha

