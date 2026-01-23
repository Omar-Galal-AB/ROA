# ?? ROA Plugin Test - Quick Start Guide

**Ready to test your ROA Plugin? Follow these simple steps!**

---

## ? Quick Test (5 minutes)

### **Step 1: Start UE5 Editor**
```
1. Open ROA_V1.uproject
2. Wait for editor to load
3. Check Output Log for these messages:
   ? "ROA Plugin: Startup complete - Ready for connections"
   ? "Network Server started on port 9876"
```

### **Step 2: Run Basic Connection Test**
```powershell
# In PowerShell, navigate to project folder
cd D:\ROA\UE5_Projects\ROA_V1

# Run connection test
python test_roa_connection.py
```

**Expected Output:**
```
============================================================
ROA PLUGIN CONNECTION TEST SUITE
============================================================
[TEST] Connecting to localhost:9876...
[PASS] ? Connected successfully!
...
TOTAL: 5/5 tests passed (100%)
?? ALL TESTS PASSED! Plugin is fully functional!
```

### **Step 3: Test Robot Spawning**
```powershell
# Run robot spawn test
python test_robot_spawn.py
```

**Expected Output:**
```
============================================================
ROA ROBOT SPAWN & CONTROL TEST
============================================================
[TEST] Spawning robot...
[PASS] ? Robot spawned successfully!
...
TOTAL: 7/7 tests passed (100%)
?? ALL ROBOT TESTS PASSED!
```

---

## ? Success Indicators

**You're good to go if you see:**
- ? Green checkmarks (?) for all tests
- ? "ALL TESTS PASSED" message
- ? No error messages or ? symbols
- ? Robot appears in UE5 viewport (for spawn test)

---

## ? Common Issues & Fixes

### **Issue: "Connection refused"**
**Fix:**
1. Make sure UE5 Editor is running
2. Check Output Log for "Network Server started"
3. Try restarting editor

### **Issue: "Port already in use"**
**Fix:**
```powershell
# Find and kill process using port 9876
netstat -ano | findstr :9876
taskkill /PID [PID_NUMBER] /F
```

### **Issue: "Python not found"**
**Fix:**
1. Install Python 3.8+: https://www.python.org/downloads/
2. Make sure Python is in PATH
3. Test: `python --version`

### **Issue: Test timeout**
**Fix:**
1. Check Windows Firewall isn't blocking port 9876
2. Verify plugin is enabled: Edit ? Plugins ? ROA
3. Rebuild plugin: Build ? Build Solution

---

## ?? What Each Test Does

### **test_roa_connection.py**
Tests basic plugin functionality:
- ? TCP connection
- ? Connect command
- ? Heartbeat
- ? System status query
- ? Disconnect

**Run Time:** ~5 seconds

### **test_robot_spawn.py**
Tests robot operations:
- ? Robot spawning
- ? Robot listing
- ? State queries
- ? Joint control
- ? Emergency stop
- ? Robot despawn

**Run Time:** ~10 seconds

---

## ?? Next Steps After Successful Tests

1. **? Tests Pass?** ? Plugin is fully functional!
2. **Create blueprints** ? Follow guides in `Guides/` folder
3. **Integrate with ROS2** ? Connect Python Webthread
4. **Build your application** ? Use Main Dashboard

---

## ?? Need Help?

**Check these files:**
- `Guides/PLUGIN_CONNECTION_TEST.md` - Detailed test documentation
- `Guides/README.md` - Plugin documentation
- `Guides/COMMUNICATION_PROTOCOL.md` - Protocol specification

**Output Log Location:**
- Window ? Developer Tools ? Output Log
- Filter by "LogTemp" to see plugin messages

---

## ?? Verify Plugin Loaded

**Quick Visual Check:**
1. Edit ? Plugins
2. Search "ROA"
3. Should show: "ROA - Robot Operator Assistant" ? Enabled

**Quick Log Check:**
```powershell
# In UE5 Output Log, search for:
"ROA Plugin"

# Should show:
LogTemp: ROA Plugin: Initializing Robot Operator Assistant Plugin
LogTemp: ROA Plugin: Startup complete - Ready for connections
```

---

## ?? Test Schedule

**Initial Testing:**
- Connection Test: 5 minutes
- Robot Spawn Test: 5 minutes
- **Total:** 10 minutes

**Recommended Testing:**
- After plugin changes: Run both tests
- Before committing code: Run both tests
- Before release: Full test suite

---

## ?? Pro Tips

1. **Keep UE5 Output Log visible** during tests
2. **Run tests with editor focused** to see robots spawn
3. **Use "Show All Logs"** in Output Log for full details
4. **Take screenshots** of successful tests for documentation

---

**Ready? Let's test! ??**

```powershell
# Test 1: Connection (5 min)
python test_roa_connection.py

# Test 2: Robot Spawn (5 min)
python test_robot_spawn.py

# Success? You're done! ??
```

---

**Quick Start Version:** 1.0  
**Last Updated:** January 2025  
**Estimated Time:** 10 minutes total

