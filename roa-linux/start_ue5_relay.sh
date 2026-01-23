#!/bin/bash
# ROA - Start UE5 Connection Relay
# This forwards localhost:9876 in WSL to Windows UE5

echo "Starting UE5 connection relay..."

# Check if socat is already running
if pgrep -f "socat.*9876" > /dev/null; then
    echo "Relay already running"
    exit 0
fi

# Start socat relay in background
socat TCP-LISTEN:9876,fork,reuseaddr TCP:172.27.64.1:9876 &

echo "UE5 relay started (PID: $!)"
echo "ROA can now connect to localhost:9876"
