#!/bin/bash
# Stop ROA Dual Bridge Servers

echo "🛑 Stopping ROA bridge servers..."

# Stop rosbridge server (port 9090)
if pgrep -f "roa_bridge_server.py" > /dev/null; then
    pkill -f "roa_bridge_server.py"
    echo "✅ Stopped rosbridge (port 9090)"
else
    echo "⚪ rosbridge was not running"
fi

# Stop command server (port 9876)
if pgrep -f "roa_command_server.py" > /dev/null; then
    pkill -f "roa_command_server.py"
    echo "✅ Stopped command server (port 9876)"
else
    echo "⚪ command server was not running"
fi

# Stop FTI bridge
if pgrep -f "fti_webthread_bridge.py" > /dev/null; then
    pkill -f "fti_webthread_bridge.py"
    echo "✅ Stopped FTI bridge"
else
    echo "⚪ FTI bridge was not running"
fi

sleep 1
echo "✅ All servers stopped"
