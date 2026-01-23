#!/bin/bash
# ROA - Test UE5 connectivity from WSL

echo "========================================"
echo "ROA - UE5 Connection Test (WSL)"
echo "========================================"
echo ""

# Detect Windows host IP
WINDOWS_IP=$(ip route show | grep -i default | awk '{print $3}')

if [ -z "$WINDOWS_IP" ]; then
    echo "ERROR: Could not detect Windows host IP"
    exit 1
fi

echo "Windows Host IP: $WINDOWS_IP"
echo "Target Port: 9876"
echo ""

# Test connection
echo "Testing connection..."
timeout 3 bash -c "cat < /dev/null > /dev/tcp/$WINDOWS_IP/9876" 2>/dev/null

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ SUCCESS: Port 9876 is ACCESSIBLE!" 
    echo ""
    echo "UE5 Network Server is reachable from WSL."
    echo "You can now launch ROA: roa"
    echo ""
else
    echo ""
    echo "✗ FAILED: Port 9876 is NOT accessible"
    echo ""
    echo "Possible causes:"
    echo "  1. UE5 is not running"
    echo "  2. Windows Firewall is blocking the port"
    echo ""
    echo "Solutions:"
    echo "  1. Make sure UE5 is open with ROA_V1 project"
    echo "  2. Run this PowerShell script AS ADMINISTRATOR on Windows:"
    echo "     D:\\ROA\\UE5_Projects\\ROA_V1\\configure_firewall.ps1"
    echo ""
    echo "After running the script, test again with:"
    echo "  ./test_ue5_connection.sh"
    echo ""
fi
