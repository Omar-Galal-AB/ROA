#!/bin/bash
###############################################
# ROA - UE5 Integration Test
# Tests complete WSL -> socat -> UE5 flow
###############################################

echo "========================================="
echo "  ROA UE5 Integration Test"
echo "========================================="
echo ""

# Get Windows IP
WINDOWS_IP=$(ip route show | grep -i default | awk '{ print $3}')
echo "[INFO] Windows IP: $WINDOWS_IP"
echo ""

# Step 1: Check if socat is running
echo "[1] Checking socat relay..."
if ps aux | grep -v grep | grep "socat.*9876" > /dev/null; then
    echo "    ✓ socat relay is running"
else
    echo "    ✗ socat relay NOT running"
    echo "    Starting socat relay..."
    socat -d -d TCP-LISTEN:9876,fork,reuseaddr TCP:$WINDOWS_IP:9876 &
    SOCAT_PID=$!
    sleep 2
    echo "    ✓ socat started (PID: $SOCAT_PID)"
fi
echo ""

# Step 2: Check if UE5 is listening on Windows
echo "[2] Checking UE5 on Windows..."
UE5_LISTENING=$(powershell.exe -Command "netstat -ano | Select-String ':9876.*LISTENING'" 2>/dev/null | head -1)
if [ -n "$UE5_LISTENING" ]; then
    echo "    ✓ UE5 is listening on port 9876"
    UE5_PID=$(echo "$UE5_LISTENING" | awk '{print $NF}')
    echo "    PID: $UE5_PID"
else
    echo "    ✗ UE5 NOT listening on port 9876"
    echo "    Make sure UE5 is running with ROA plugin"
fi
echo ""

# Step 3: Test connection with Python
echo "[3] Testing ROA -> UE5 connection..."
cd "$(dirname "$0")"
python3 -m src.python.UE5Bridge.connection_monitor

TEST_RESULT=$?
echo ""

# Summary
echo "========================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo "  ✓✓✓ INTEGRATION TEST PASSED ✓✓✓"
    echo "========================================="
    echo ""
    echo "ROA can communicate with UE5!"
    echo "Ready to run webthread."
else
    echo "  ✗ INTEGRATION TEST FAILED"
    echo "========================================="
    echo ""
    echo "Troubleshooting:"
    echo "  1. Ensure UE5 is running"
    echo "  2. Open ROA_V1 project in UE5"
    echo "  3. Click Play button"
    echo "  4. Check Output Log for ROA plugin messages"
    echo "  5. Verify ROA plugin is enabled (Edit > Plugins)"
fi
echo ""

exit $TEST_RESULT
