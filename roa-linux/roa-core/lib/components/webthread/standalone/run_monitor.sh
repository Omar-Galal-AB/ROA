#!/bin/bash
# Launcher script for Webthread Standalone Monitor
# ROA - Robot Operations & Automation

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "================================"
echo "Webthread Standalone Monitor"
echo "ROA - Robot Operations & Automation"
echo "================================"
echo ""

# Check if PyQt6 is installed
python3 -c "import PyQt6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "PyQt6 not found. Installing dependencies..."
    pip install -r ../requirements.txt
    echo ""
fi

echo "Starting Webthread Monitor..."
python3 webthread_monitor.py
