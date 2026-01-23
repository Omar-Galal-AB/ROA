# Webthread Standalone Monitor

A standalone desktop application for monitoring the ROA Webthread system.

## Features

- **Real-time Component Monitoring**: Track health status of all 5 ROA components (FTI, DIMC, ROC, COMC, ROS2Bridge, UE5Bridge)
- **System Statistics**: View uptime, error counts, and performance metrics
- **Live Logs**: Monitor system events and errors in real-time
- **Connection Status**: Check ROS2, UE5, and Gazebo connections
- **Independent Operation**: Can run alongside UE5 or completely standalone

## Requirements

- Python 3.10+
- PyQt6
- pyyaml

## Installation

```bash
# Install dependencies
pip install -r ../requirements.txt
```

## Usage

### Linux/Mac:
```bash
./run_monitor.sh
```

### Windows:
```bash
python webthread_monitor.py
```

### Manual:
```bash
cd components/webthread/standalone
python3 webthread_monitor.py
```

## Features in Detail

### Component Health Monitoring
- Real-time status updates (500ms refresh)
- Color-coded status indicators (green/orange/red)
- Response time tracking
- Error counting per component

### System Logs
- Timestamped log entries
- Filterable by level (INFO, WARNING, ERROR)
- Clear and export functionality

### Statistics Panel
- Total component count
- Healthy/Degraded/Failed breakdowns
- Error and warning totals
- System uptime

### Connections Monitor
- ROS2 connection status
- UE5 connection status
- Gazebo connection status (optional)

## Dual-Mode Operation

The Webthread Monitor is designed to work in two modes:

1. **Standalone**: Monitor ROA system from outside UE5
2. **Integrated**: Run alongside UE5 for enhanced monitoring

Both modes can run **simultaneously** for maximum visibility.

## Controls

- **Start/Stop**: Control Webthread monitoring
- **Clear Logs**: Reset log display
- **Window Close**: Gracefully shutdown monitoring

## Status Indicators

- 🟢 **Green**: Component healthy
- 🟠 **Orange**: Component degraded
- 🔴 **Red**: Component failed
- ⚪ **White**: Component unknown/not responding

## Architecture

```
┌─────────────────────────────┐
│  Webthread Monitor (Qt)     │
│  ┌───────────────────────┐  │
│  │ MonitorThread         │  │
│  │ (Background updates)  │  │
│  └───────────────────────┘  │
│          ↓                   │
│  ┌───────────────────────┐  │
│  │ WebthreadCore         │  │
│  │ (ROA Core Component)  │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
         ↓
    ROS2 Topics
```

## Troubleshooting

**App won't start:**
- Ensure PyQt6 is installed: `pip install PyQt6`
- Check Python version: `python3 --version` (should be 3.10+)

**No component data:**
- Ensure Webthread core is started
- Check ROS2 is installed and sourced
- Verify other ROA components are running

**UI freezing:**
- Check if monitoring thread is running
- Reduce update frequency if needed (edit code)

## Development

The monitor is built with PyQt6 and follows the MVC pattern:

- `webthread_monitor.py`: Main application and UI
- `MonitorThread`: Background worker for status updates
- Integration with existing Webthread Python modules

## License

Part of the ROA project.
