#!/bin/bash
# ROA Linux Installation Script
# Robot Operator Application - Linux Installation
# Version: 0.1.0-alpha

set -e

PRODUCT_NAME="ROA"
PRODUCT_VERSION="0.1.0"
INSTALL_DIR="/opt/roa"
BIN_LINK="/usr/local/bin/roa"

echo "========================================"
echo "ROA Linux Installer v${PRODUCT_VERSION}"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed!"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Found Python ${PYTHON_VERSION}"

# Create installation directory
echo "Creating installation directory..."
mkdir -p ${INSTALL_DIR}

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Copy files
echo "Installing ROA files..."
cp -r ${SCRIPT_DIR}/roa-core/* ${INSTALL_DIR}/

# Install Python dependencies
echo "Installing Python dependencies..."
if [ -f ${INSTALL_DIR}/requirements.txt ]; then
    pip3 install -r ${INSTALL_DIR}/requirements.txt
fi

# Create symlink
echo "Creating symbolic link..."
ln -sf ${INSTALL_DIR}/bin/roa ${BIN_LINK}

# Make executables executable
chmod +x ${INSTALL_DIR}/bin/*

# Create desktop entry
echo "Creating desktop entry..."
cat > /usr/share/applications/roa.desktop << EOF
[Desktop Entry]
Name=ROA - Robot Operator Application
Comment=Robot control and simulation platform
Exec=${INSTALL_DIR}/bin/roa
Icon=${INSTALL_DIR}/share/icons/roa.png
Terminal=false
Type=Application
Categories=Development;Science;
EOF

# Create user data directory
echo "Creating user data directory..."
mkdir -p ~/.roa/config
mkdir -p ~/.roa/logs
mkdir -p ~/.roa/snapshots
mkdir -p ~/.roa/backups
mkdir -p ~/.roa/archives

# Set permissions
echo "Setting permissions..."
chown -R ${SUDO_USER}:${SUDO_USER} ~/.roa
chmod -R 755 ${INSTALL_DIR}

echo ""
echo "========================================"
echo "Installation completed successfully!"
echo "========================================"
echo ""
echo "You can now run ROA by typing: roa"
echo "Or find it in your application menu"
echo ""
echo "Installation directory: ${INSTALL_DIR}"
echo "User data directory: ~/.roa"
echo ""
