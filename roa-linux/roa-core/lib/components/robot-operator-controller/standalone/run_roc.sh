#!/bin/bash
# Launcher script for ROC Standalone Desktop App
# ROA - Robot Operations & Automation

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "================================"
echo "ROC Standalone Desktop Application"
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

echo "Starting ROC Desktop Application..."
python3 roc_desktop.py
