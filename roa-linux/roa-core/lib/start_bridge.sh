#!/bin/bash
# Start ROA Dual Bridge Servers for UE5 communication
# Port 9090: rosbridge (WSL → UE5 ROS2 publishing)
# Port 9876: command server (UE5 → WSL commands)

source /opt/ros/humble/setup.bash

cd /home/myws/roa/roa_linux/roa-core/lib

# Check if rosbridge already running
BRIDGE_RUNNING=false
COMMAND_RUNNING=false

if pgrep -f "roa_bridge_server.py" > /dev/null; then
    echo "⚠️  rosbridge (port 9090) already running"
    BRIDGE_RUNNING=true
fi

if pgrep -f "roa_command_server.py" > /dev/null; then
    echo "⚠️  command server (port 9876) already running"
    COMMAND_RUNNING=true
fi

if [ "$BRIDGE_RUNNING" = true ] && [ "$COMMAND_RUNNING" = true ]; then
    echo "✅ Both servers already running"
    exit 0
fi

# Start rosbridge server (port 9090)
if [ "$BRIDGE_RUNNING" = false ]; then
    setsid python3 roa_bridge_server.py --port 9090 > /tmp/roa_bridge.log 2>&1 &
    echo "🚀 Starting rosbridge on port 9090..."
fi

# Start command server (port 9876)
if [ "$COMMAND_RUNNING" = false ]; then
    setsid python3 roa_command_server.py --port 9876 > /tmp/roa_command.log 2>&1 &
    echo "🚀 Starting command server on port 9876..."
fi

# Give them a moment to start
sleep 2

# Verify both started
BRIDGE_OK=false
COMMAND_OK=false

if pgrep -f "roa_bridge_server.py" > /dev/null; then
    BRIDGE_OK=true
    echo "✅ rosbridge server running (port 9090)"
else
    echo "❌ rosbridge server failed to start"
    cat /tmp/roa_bridge.log
fi

if pgrep -f "roa_command_server.py" > /dev/null; then
    COMMAND_OK=true
    echo "✅ command server running (port 9876)"
else
    echo "❌ command server failed to start"
    cat /tmp/roa_command.log
fi

# Start FTI bridge for heartbeats (connects to command server)
FTI_BRIDGE_PATH="/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python/fti_webthread_bridge.py"
if [ -f "$FTI_BRIDGE_PATH" ]; then
    if ! pgrep -f "fti_webthread_bridge.py" > /dev/null; then
        setsid python3 "$FTI_BRIDGE_PATH" --host localhost --port 9876 > /tmp/fti_bridge.log 2>&1 &
        echo "🚀 Starting FTI heartbeat bridge..."
        sleep 1
        if pgrep -f "fti_webthread_bridge.py" > /dev/null; then
            echo "✅ FTI bridge running"
        else
            echo "⚠️  FTI bridge failed to start (optional)"
        fi
    else
        echo "✅ FTI bridge already running"
    fi
fi

if [ "$BRIDGE_OK" = true ] && [ "$COMMAND_OK" = true ]; then
    echo "🎉 Both servers started successfully"
    exit 0
else
    echo "⚠️  Some servers failed to start"
    exit 1
fi
