#!/bin/bash
# ROA Linux Uninstallation Script
# Robot Operator Application - Linux Uninstaller
# Version: 0.1.0-alpha

set -e

PRODUCT_NAME="ROA"
INSTALL_DIR="/opt/roa"
BIN_LINK="/usr/local/bin/roa"

echo "========================================"
echo "ROA Linux Uninstaller"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Confirm uninstallation
read -p "Are you sure you want to uninstall ROA? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled"
    exit 0
fi

# Remove installation directory
echo "Removing ROA files..."
if [ -d "${INSTALL_DIR}" ]; then
    rm -rf ${INSTALL_DIR}
    echo "  ✓ Removed ${INSTALL_DIR}"
fi

# Remove symlink
echo "Removing symbolic link..."
if [ -L "${BIN_LINK}" ]; then
    rm ${BIN_LINK}
    echo "  ✓ Removed ${BIN_LINK}"
fi

# Remove desktop entry
echo "Removing desktop entry..."
if [ -f "/usr/share/applications/roa.desktop" ]; then
    rm /usr/share/applications/roa.desktop
    echo "  ✓ Removed desktop entry"
fi

echo ""
echo "========================================"
echo "ROA has been uninstalled"
echo "========================================"
echo ""
echo "User data in ~/.roa has been preserved"
echo "To remove user data, run: rm -rf ~/.roa"
echo ""
