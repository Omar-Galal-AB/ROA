# ROA - UE5 Connection Setup Guide (WSL)

## Problem: Connection Refused

You're running ROA on **Linux (WSL)** and UE5 on **Windows**. They need to communicate across the WSL-Windows network boundary, but Windows Firewall blocks the connection by default.

## Solution: Configure Windows Firewall

### Step 1: Configure Firewall (ONE TIME SETUP)

**On Windows**, run PowerShell **AS ADMINISTRATOR**:

1. Right-click Start Menu → **Windows PowerShell (Admin)**
2. Navigate to the project:
   ```powershell
   cd D:\ROA\UE5_Projects\ROA_V1
   ```
3. Run the firewall configuration script:
   ```powershell
   .\configure_firewall.ps1
   ```

This script will:
- ✅ Open port 9876 for incoming connections
- ✅ Allow WSL to connect to UE5
- ✅ Test if UE5 is listening

### Step 2: Test Connection

**On Linux (WSL)**, test if UE5 is reachable:

```bash
cd /home/myws/roa/roa_linux
./test_ue5_connection.sh
```

Expected output if successful:
```
✓ SUCCESS: Port 9876 is ACCESSIBLE!
```

If it fails:
```
✗ FAILED: Port 9876 is NOT accessible
```
→ Make sure UE5 is running and firewall script was run as Administrator

### Step 3: Launch ROA

Once the test succeeds:

```bash
roa
```

The **Webthread Monitor** should show:
- Header: **"UE5: Connected"** in green ✅
- Connections tab: UE5 with green ● indicator

## Technical Details

### Network Configuration

- **UE5 Server**: Windows (localhost:9876)
- **ROA Client**: WSL (connects to 172.27.64.1:9876)
- **Auto-detection**: ROA automatically detects WSL and uses Windows host IP

### Port Information

- **Port**: 9876 (TCP)
- **Protocol**: JSON over TCP with 4-byte length prefix
- **Direction**: WSL → Windows (Inbound to Windows)

### Troubleshooting

#### "Connection Refused"
1. Ensure UE5 is running with ROA_V1 project open
2. Check UE5 Output Log for: `"ROA Network Server: Started successfully on port 9876"`
3. Run firewall script as Administrator
4. Test connection with `./test_ue5_connection.sh`

#### "Timeout"
1. Windows Firewall may still be blocking
2. Try disabling Windows Defender Firewall temporarily for testing
3. Check if antivirus is blocking the connection

#### UE5 Not Starting Server
1. Check UE5 Output Log for plugin initialization
2. Ensure ROA plugin is enabled in UE5
3. Restart UE5 editor

### Manual Firewall Configuration

If the script doesn't work, configure manually:

1. Open **Windows Defender Firewall with Advanced Security**
2. Click **Inbound Rules** → **New Rule**
3. Select **Port** → Click Next
4. Select **TCP** → Specific local ports: **9876** → Next
5. Select **Allow the connection** → Next
6. Check all profiles (Domain, Private, Public) → Next
7. Name: "ROA UE5 Network Server" → Finish

## Quick Reference

| Item | Value |
|------|-------|
| Windows Firewall Script | `D:\ROA\UE5_Projects\ROA_V1\configure_firewall.ps1` |
| WSL Connection Test | `/home/myws/roa/roa_linux/test_ue5_connection.sh` |
| UE5 Port | 9876 (TCP) |
| Windows Host IP | Auto-detected (typically 172.27.x.1) |
| Launch Command | `roa` |

## Verification

After setup, you should see:

**UE5 Output Log:**
```
LogTemp: ROA Network Server: Started successfully on port 9876
LogTemp: ROA Network Server: Accepted connection from 172.27.x.x:xxxxx
```

**ROA Webthread Monitor:**
```
Header: UE5: Connected ✓ (green)
Connections Tab: UE5 • Connected - 172.27.64.1:9876
```

---

**Next Steps After Connection:**
1. ✅ Import URDF files via FTI
2. ✅ Spawn robots in UE5
3. ✅ Control joints from ROC
