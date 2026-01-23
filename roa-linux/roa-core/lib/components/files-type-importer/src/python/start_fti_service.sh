#!/bin/bash
# FTI IPC Service Startup Script
# This script is called by UE5 to start the IPC service
# It handles proper working directory, environment setup, and logging

SCRIPT_DIR="/home/myws/roa/roa_linux/roa-core/lib/components/files-type-importer/src/python"
SERVICE_SCRIPT="roa_ipc_service.py"
LOG_FILE="/tmp/fti_ipc.log"
PID_FILE="/tmp/fti_ipc.pid"
AUTO_SHUTDOWN_DELAY="${1:-300}"  # Default 5 minutes

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Service already running with PID $OLD_PID"
        exit 0
    else
        echo "Stale PID file found, removing..."
        rm -f "$PID_FILE"
    fi
fi

# Change to script directory
cd "$SCRIPT_DIR" || {
    echo "ERROR: Cannot change to $SCRIPT_DIR"
    exit 1
}

# Start the service
echo "Starting FTI IPC Service..."
echo "  Script: $SCRIPT_DIR/$SERVICE_SCRIPT"
echo "  Log: $LOG_FILE"
echo "  Auto-shutdown: ${AUTO_SHUTDOWN_DELAY}s"

nohup python3 "$SERVICE_SCRIPT" --debug --auto-shutdown-delay "$AUTO_SHUTDOWN_DELAY" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!

# Save PID
echo "$NEW_PID" > "$PID_FILE"

# Wait a moment and verify it started
sleep 2

if ps -p "$NEW_PID" > /dev/null 2>&1; then
    echo "Service started successfully with PID $NEW_PID"
    exit 0
else
    echo "ERROR: Service failed to start"
    echo "Check log: $LOG_FILE"
    cat "$LOG_FILE" | tail -20
    exit 1
fi
