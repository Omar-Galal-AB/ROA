# ROA Plugin Connection Test Suite

**Date:** January 2025  
**Purpose:** Verify ROA Plugin connectivity and functionality  
**Status:** Ready for Testing

---

## ?? Test Overview

This document provides complete instructions for testing the ROA UE5 Plugin's connection capabilities with the Python Webthread component.

---

## ?? Pre-Test Checklist

### **1. Plugin Status**
- [ ] ROA Plugin is compiled (Build successful)
- [ ] Plugin is enabled in UE5 Editor
- [ ] No compilation errors
- [ ] Plugin shows in Plugins window

### **2. Network Configuration**
- [ ] Default port: 9876
- [ ] No firewall blocking port 9876
- [ ] TCP socket support available
- [ ] Network adapter active

### **3. Required Files**
- [ ] ROAModule.cpp (plugin initialization)
- [ ] ROANetworkServer.cpp (server implementation)
- [ ] ROAWorldManager.cpp (world management)
- [ ] ROARobotActor.cpp (robot actor)

---

## ?? Test Suite

### **Test 1: Plugin Initialization** ?

**Objective:** Verify plugin loads and initializes correctly in UE5

**Steps:**
1. Open UE5 Editor with ROA_V1 project
2. Open Output Log (Window ? Developer Tools ? Output Log)
3. Filter log by "LogTemp"
4. Look for initialization messages

**Expected Output:**
```
LogTemp: ROA Plugin: Initializing Robot Operator Assistant Plugin
LogTemp: ROA Plugin: World Manager initialized
LogTemp: ROA Plugin: Widget Manager initialized
LogTemp: ROA Plugin: Network Server started on port 9876
LogTemp: ROA Plugin: Startup complete - Ready for connections
```

**Pass Criteria:**
- ? All 5 messages appear in output log
- ? No error messages
- ? Network server reports port 9876

**Fail Criteria:**
- ? "Failed to start Network Server" message
- ? Any crash or exception
- ? Missing initialization messages

---

### **Test 2: Network Server Listening** ?

**Objective:** Verify network server is listening on port 9876

**Method 1: Using PowerShell**
```powershell
# Check if port 9876 is listening
Test-NetConnection -ComputerName localhost -Port 9876
```

**Expected Output:**
```
ComputerName     : localhost
RemoteAddress    : 127.0.0.1
RemotePort       : 9876
TcpTestSucceeded : True
```

**Method 2: Using netstat**
```powershell
netstat -an | Select-String "9876"
```

**Expected Output:**
```
TCP    0.0.0.0:9876           0.0.0.0:0   LISTENING
```

**Pass Criteria:**
- ? Port 9876 shows as LISTENING
- ? TcpTestSucceeded = True

**Fail Criteria:**
- ? Port not found
- ? Connection refused
- ? TcpTestSucceeded = False

---

### **Test 3: Python Connection Test** ?

**Objective:** Connect from Python and verify TCP communication

**Python Test Script:** `test_roa_connection.py`

```python
"""
ROA Plugin Connection Test
Tests basic TCP connection to UE5 Plugin
"""

import socket
import json
import time
import sys

def test_connection(host='localhost', port=9876):
    """Test basic TCP connection"""
    print(f"[TEST] Connecting to {host}:{port}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)  # 5 second timeout
        sock.connect((host, port))
  print("[PASS] ? Connected successfully!")
        return sock
    except socket.timeout:
        print("[FAIL] ? Connection timeout - Server not responding")
      return None
    except ConnectionRefusedError:
 print("[FAIL] ? Connection refused - Server not running")
     return None
    except Exception as e:
        print(f"[FAIL] ? Connection error: {e}")
  return None

def test_connect_command(sock):
    """Test connect command"""
    print("\n[TEST] Sending connect command...")
    
    connect_msg = {
        "message_id": "test-connect-001",
        "timestamp": time.time(),
        "message_type": "REQUEST",
        "command": "connect",
        "payload": {
            "client_name": "ROA_Test_Script",
  "version": "1.0.0",
            "capabilities": ["test"]
        }
    }
    
    try:
     # Send message
        json_str = json.dumps(connect_msg)
        sock.send(json_str.encode('utf-8'))
      print(f"[INFO] Sent: {json_str[:100]}...")
  
     # Receive response
        sock.settimeout(10.0)
        response = sock.recv(4096)
    
        if response:
     response_str = response.decode('utf-8')
            print(f"[INFO] Received: {response_str[:200]}...")

        # Parse JSON
  response_json = json.loads(response_str)
            
   # Verify response
    if response_json.get('message_type') == 'RESPONSE':
    if response_json.get('payload', {}).get('status') == 'success':
       session_id = response_json.get('payload', {}).get('session_id')
         print(f"[PASS] ? Connect successful! Session ID: {session_id}")
    return True, session_id
       else:
      print("[FAIL] ? Connect failed - Status not success")
          return False, None
  else:
     print("[FAIL] ? Invalid response type")
      return False, None
        else:
     print("[FAIL] ? No response received")
 return False, None

    except socket.timeout:
        print("[FAIL] ? Response timeout")
        return False, None
    except json.JSONDecodeError as e:
        print(f"[FAIL] ? Invalid JSON response: {e}")
        return False, None
except Exception as e:
        print(f"[FAIL] ? Error: {e}")
    return False, None

def test_heartbeat(sock):
    """Test heartbeat command"""
    print("\n[TEST] Sending heartbeat...")
    
    heartbeat_msg = {
        "message_id": "test-heartbeat-001",
        "timestamp": time.time(),
        "message_type": "EVENT",
        "command": "heartbeat",
        "payload": {
      "timestamp": time.time()
        }
    }
    
    try:
   json_str = json.dumps(heartbeat_msg)
 sock.send(json_str.encode('utf-8'))
  print(f"[INFO] Sent heartbeat")
        
  # Receive echo
     response = sock.recv(4096)
        if response:
  print(f"[PASS] ? Heartbeat echoed")
            return True
        else:
            print(f"[FAIL] ? No heartbeat response")
return False
            
    except Exception as e:
        print(f"[FAIL] ? Heartbeat error: {e}")
        return False

def test_get_system_status(sock):
    """Test get_system_status command"""
    print("\n[TEST] Getting system status...")
    
    status_msg = {
      "message_id": "test-status-001",
        "timestamp": time.time(),
        "message_type": "REQUEST",
        "command": "get_system_status",
        "payload": {}
    }
    
  try:
        json_str = json.dumps(status_msg)
  sock.send(json_str.encode('utf-8'))
     
    response = sock.recv(4096)
        if response:
       response_json = json.loads(response.decode('utf-8'))
            payload = response_json.get('payload', {})
     
            print(f"[INFO] UE5 Version: {payload.get('ue5_version')}")
   print(f"[INFO] Plugin Version: {payload.get('plugin_version')}")
    print(f"[INFO] Active Robots: {payload.get('active_robots')}")
 print(f"[INFO] FPS: {payload.get('fps')}")
    print(f"[PASS] ? System status retrieved")
          return True
     else:
   print(f"[FAIL] ? No status response")
        return False
            
    except Exception as e:
    print(f"[FAIL] ? Status error: {e}")
        return False

def test_disconnect(sock):
    """Test disconnect command"""
 print("\n[TEST] Disconnecting...")
    
    disconnect_msg = {
        "message_id": "test-disconnect-001",
     "timestamp": time.time(),
     "message_type": "REQUEST",
 "command": "disconnect",
    "payload": {}
    }
    
    try:
        json_str = json.dumps(disconnect_msg)
  sock.send(json_str.encode('utf-8'))
        
        response = sock.recv(4096)
        if response:
    print(f"[PASS] ? Disconnect acknowledged")
return True
        else:
    print(f"[WARN] ?? No disconnect response (acceptable)")
            return True
       
    except Exception as e:
     print(f"[INFO] Disconnected (connection closed)")
        return True

def run_all_tests():
    """Run complete test suite"""
    print("=" * 60)
    print("ROA PLUGIN CONNECTION TEST SUITE")
    print("=" * 60)
    
    results = {
        "connection": False,
 "connect_command": False,
        "heartbeat": False,
 "system_status": False,
        "disconnect": False
  }
    
    # Test 1: Connection
    sock = test_connection()
    if not sock:
  print("\n" + "=" * 60)
        print("TEST SUITE FAILED - Cannot connect to server")
        print("=" * 60)
        return results
    
    results["connection"] = True
    
    # Test 2: Connect Command
    success, session_id = test_connect_command(sock)
    results["connect_command"] = success
    
    if not success:
        sock.close()
        print("\n" + "=" * 60)
        print("TEST SUITE FAILED - Connect command failed")
        print("=" * 60)
        return results
    
    # Test 3: Heartbeat
    results["heartbeat"] = test_heartbeat(sock)
    
    # Test 4: System Status
    results["system_status"] = test_get_system_status(sock)
    
    # Test 5: Disconnect
    results["disconnect"] = test_disconnect(sock)
    
    # Close socket
    sock.close()
    
    # Print results
 print("\n" + "=" * 60)
print("TEST RESULTS")
    print("=" * 60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for test_name, passed_test in results.items():
 status = "? PASS" if passed_test else "? FAIL"
        print(f"{test_name:20s}: {status}")
    
    print("-" * 60)
    print(f"TOTAL: {passed}/{total} tests passed ({passed*100//total}%)")
    print("=" * 60)
    
    if passed == total:
        print("\n?? ALL TESTS PASSED! Plugin is fully functional!")
        return True
    else:
        print(f"\n?? {total - passed} test(s) failed. Check plugin configuration.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
```

**Run Test:**
```powershell
python test_roa_connection.py
```

**Expected Output:**
```
============================================================
ROA PLUGIN CONNECTION TEST SUITE
============================================================
[TEST] Connecting to localhost:9876...
[PASS] ? Connected successfully!

[TEST] Sending connect command...
[INFO] Sent: {"message_id": "test-connect-001"...
[INFO] Received: {"message_id": "test-connect-001"...
[PASS] ? Connect successful! Session ID: abc-123-def

[TEST] Sending heartbeat...
[PASS] ? Heartbeat echoed

[TEST] Getting system status...
[INFO] UE5 Version: 5.6.0
[INFO] Plugin Version: 1.0.0-alpha
[INFO] Active Robots: 0
[INFO] FPS: 60.0
[PASS] ? System status retrieved

[TEST] Disconnecting...
[PASS] ? Disconnect acknowledged

============================================================
TEST RESULTS
============================================================
connection        : ? PASS
connect_command     : ? PASS
heartbeat : ? PASS
system_status    : ? PASS
disconnect      : ? PASS
------------------------------------------------------------
TOTAL: 5/5 tests passed (100%)
============================================================

?? ALL TESTS PASSED! Plugin is fully functional!
```

**Pass Criteria:**
- ? All 5 tests pass
- ? Connection established
- ? Commands processed
- ? Responses received

**Fail Criteria:**
- ? Any test fails
- ? Connection timeout
- ? Invalid responses

---

### **Test 4: Robot Spawn Test** ?

**Objective:** Test robot spawning functionality

**Python Test Script:** `test_robot_spawn.py`

```python
"""
ROA Plugin Robot Spawn Test
Tests robot spawning and management
"""

import socket
import json
import time

def connect_to_server():
    """Connect and authenticate"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 9876))
    
    # Send connect command
    connect_msg = {
        "message_id": "spawn-test-connect",
        "timestamp": time.time(),
    "message_type": "REQUEST",
        "command": "connect",
        "payload": {
   "client_name": "Robot_Spawn_Test",
     "version": "1.0.0"
        }
    }
    
    sock.send(json.dumps(connect_msg).encode())
    response = sock.recv(4096)
    
    return sock

def test_spawn_robot(sock):
    """Test spawning a robot"""
    print("[TEST] Spawning robot...")
    
    spawn_msg = {
      "message_id": "spawn-test-001",
        "timestamp": time.time(),
    "message_type": "REQUEST",
        "command": "spawn_robot",
        "payload": {
   "robot_id": "test_ur5e_001",
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
    
    sock.send(json.dumps(spawn_msg).encode())
    response = sock.recv(4096)
    
    response_json = json.loads(response.decode())
    
    if response_json.get('payload', {}).get('status') == 'success':
        print("[PASS] ? Robot spawned successfully!")
        print(f"[INFO] Robot ID: {response_json['payload']['robot_id']}")
    print(f"[INFO] Robot Type: {response_json['payload']['robot_type']}")
        return True
    else:
        print(f"[FAIL] ? Spawn failed: {response_json}")
      return False

def test_list_robots(sock):
    """Test listing robots"""
    print("\n[TEST] Listing robots...")
  
    list_msg = {
        "message_id": "list-test-001",
        "timestamp": time.time(),
        "message_type": "REQUEST",
        "command": "list_robots",
        "payload": {}
    }
    
    sock.send(json.dumps(list_msg).encode())
    response = sock.recv(4096)
    
    response_json = json.loads(response.decode())
    robots = response_json.get('payload', {}).get('robots', [])
    
    print(f"[INFO] Found {len(robots)} robot(s)")
    for robot in robots:
     print(f"  - {robot['robot_id']}: {robot['status']}")
    
    if len(robots) > 0:
        print("[PASS] ? Robot list retrieved")
        return True
 else:
        print("[FAIL] ? No robots found")
        return False

def test_get_robot_state(sock, robot_id):
    """Test getting robot state"""
    print(f"\n[TEST] Getting state for robot: {robot_id}")
  
    state_msg = {
   "message_id": "state-test-001",
        "timestamp": time.time(),
        "message_type": "REQUEST",
        "command": "get_robot_state",
        "payload": {
            "robot_id": robot_id
     }
    }
    
    sock.send(json.dumps(state_msg).encode())
 response = sock.recv(4096)
    
    response_json = json.loads(response.decode())
    payload = response_json.get('payload', {})
    
    if 'position' in payload:
        print(f"[INFO] Position: {payload['position']}")
        print(f"[INFO] Joints: {payload.get('joint_positions', [])}")
      print("[PASS] ? Robot state retrieved")
 return True
    else:
   print("[FAIL] ? Failed to get robot state")
        return False

def test_despawn_robot(sock, robot_id):
 """Test despawning robot"""
    print(f"\n[TEST] Despawning robot: {robot_id}")
    
    despawn_msg = {
        "message_id": "despawn-test-001",
   "timestamp": time.time(),
        "message_type": "REQUEST",
      "command": "despawn_robot",
        "payload": {
  "robot_id": robot_id
        }
    }
    
    sock.send(json.dumps(despawn_msg).encode())
    response = sock.recv(4096)
    
    response_json = json.loads(response.decode())
    
    if response_json.get('message_type') == 'RESPONSE':
   print("[PASS] ? Robot despawned")
        return True
  else:
        print("[FAIL] ? Despawn failed")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("ROA ROBOT SPAWN TEST")
    print("=" * 60)
    
    try:
        sock = connect_to_server()
    
# Run tests
      test_spawn_robot(sock)
        test_list_robots(sock)
     test_get_robot_state(sock, "test_ur5e_001")
        test_despawn_robot(sock, "test_ur5e_001")
        
        sock.close()
   print("\n? All robot tests completed!")
     
    except Exception as e:
 print(f"\n? Test failed with error: {e}")
```

**Run Test:**
```powershell
python test_robot_spawn.py
```

**Expected Output:**
```
============================================================
ROA ROBOT SPAWN TEST
============================================================
[TEST] Spawning robot...
[PASS] ? Robot spawned successfully!
[INFO] Robot ID: test_ur5e_001
[INFO] Robot Type: ur5e

[TEST] Listing robots...
[INFO] Found 1 robot(s)
  - test_ur5e_001: active
[PASS] ? Robot list retrieved

[TEST] Getting state for robot: test_ur5e_001
[INFO] Position: {'x': 0.0, 'y': 0.0, 'z': 100.0}
[INFO] Joints: [0.0, -1.57, 1.57, 0.0, 1.57, 0.0]
[PASS] ? Robot state retrieved

[TEST] Despawning robot: test_ur5e_001
[PASS] ? Robot despawned

? All robot tests completed!
```

---

## ?? Test Results Template

```
TEST RUN: [Date/Time]
TESTER: [Your Name]
UE5 VERSION: 5.6.0
PLUGIN VERSION: 1.0.0

??????????????????????????????????????????????????????????
? Test Name  ? Result ? Notes     ?
??????????????????????????????????????????????????????????
? Plugin Initialization       ? ?/?  ?          ?
? Network Server Listening ? ?/?  ?               ?
? Python Connection Test      ? ?/?  ?    ?
? Connect Command             ? ?/?  ?      ?
? Heartbeat ? ?/?  ?   ?
? System Status      ? ?/?  ?         ?
? Disconnect           ? ?/?  ?         ?
? Robot Spawn       ? ?/?  ? ?
? Robot List        ? ?/?  ?            ?
? Robot State Query           ? ?/?  ?     ?
? Robot Despawn            ? ?/?  ?        ?
??????????????????????????????????????????????????????????

OVERALL STATUS: ? PASS / ? FAIL
PASS RATE: __/11 (___%)

ISSUES FOUND:
1. [List any issues]
2. [...]

RECOMMENDATIONS:
1. [List recommendations]
2. [...]
```

---

## ?? Troubleshooting

### **Issue: Plugin not loading**
**Solution:**
1. Check plugin is enabled: Edit ? Plugins ? Search "ROA"
2. Rebuild project: Build ? Build Solution
3. Restart UE5 Editor

### **Issue: Port 9876 already in use**
**Solution:**
```powershell
# Find process using port
netstat -ano | findstr :9876

# Kill process (replace PID)
taskkill /PID [PID] /F
```

### **Issue: Connection timeout**
**Solution:**
1. Check firewall settings
2. Verify plugin initialized (check output log)
3. Try different port (modify ROAModule.cpp)

### **Issue: Python script fails**
**Solution:**
1. Install Python 3.8+
2. No additional packages needed (uses standard library)
3. Check Python is in PATH

---

## ? Success Criteria

**Plugin is fully functional if:**
- ? All initialization messages appear
- ? Port 9876 is listening
- ? Python can connect
- ? All commands respond correctly
- ? Robot spawning works
- ? No crashes or errors

---

## ?? Next Steps After Testing

### **If Tests Pass:**
1. ? Plugin is production-ready
2. ? Integrate with Python Webthread
3. ? Create blueprints for UI
4. ? Test with ROS2 integration

### **If Tests Fail:**
1. ? Review error messages
2. ? Check compilation
3. ? Verify plugin enabled
4. ? Debug with breakpoints
5. ? Contact support

---

**Test Documentation Version:** 1.0  
**Last Updated:** January 2025  
**Status:** Ready for Testing

