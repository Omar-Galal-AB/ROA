#!/bin/bash
# ROA Debian Package Builder
# Builds a .deb package for Debian/Ubuntu systems

set -e

PRODUCT_NAME="roa"
PRODUCT_VERSION="0.1.0"
ARCH="amd64"
BUILD_DIR="build/${PRODUCT_NAME}_${PRODUCT_VERSION}_${ARCH}"

echo "========================================"
echo "ROA Debian Package Builder"
echo "========================================"
echo ""

# Clean previous build
echo "Cleaning previous build..."
rm -rf build
mkdir -p ${BUILD_DIR}/DEBIAN
mkdir -p ${BUILD_DIR}/opt/roa
mkdir -p ${BUILD_DIR}/usr/share/applications
mkdir -p ${BUILD_DIR}/usr/share/icons/hicolor/256x256/apps

# Copy files
echo "Copying files..."
cp -r roa-core/* ${BUILD_DIR}/opt/roa/

# Fix permissions for WSL compatibility
echo "Setting correct permissions..."
chmod -R 755 ${BUILD_DIR}
chmod 755 ${BUILD_DIR}/DEBIAN

# Create control file
echo "Creating control file..."
cat > ${BUILD_DIR}/DEBIAN/control << EOF
Package: ${PRODUCT_NAME}
Version: ${PRODUCT_VERSION}
Section: science
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.8), python3-pip
Maintainer: ROA Development Team <dev@roa.example.com>
Description: Robot Operator Application
 ROA is a comprehensive robot control and simulation platform
 that integrates with ROS2 and Unreal Engine 5 for realistic
 robot operation and testing.
EOF

# Create postinst script
echo "Creating postinst script..."
cat > ${BUILD_DIR}/DEBIAN/postinst << 'EOF'
#!/bin/bash
set -e

# Install Python dependencies
pip3 install -r /opt/roa/requirements.txt

# Create user data directory
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    mkdir -p ${USER_HOME}/.roa
    chown -R ${SUDO_USER}:${SUDO_USER} ${USER_HOME}/.roa
fi

# Create symlink
ln -sf /opt/roa/bin/roa /usr/local/bin/roa

echo "ROA installation completed successfully!"
EOF

chmod 755 ${BUILD_DIR}/DEBIAN/postinst

# Create prerm script
echo "Creating prerm script..."
cat > ${BUILD_DIR}/DEBIAN/prerm << 'EOF'
#!/bin/bash
set -e

# Remove symlink
if [ -L "/usr/local/bin/roa" ]; then
    rm /usr/local/bin/roa
fi
EOF

chmod 755 ${BUILD_DIR}/DEBIAN/prerm

# Build package
echo "Building Debian package..."
dpkg-deb --build ${BUILD_DIR}

# Move to current directory
mv build/${PRODUCT_NAME}_${PRODUCT_VERSION}_${ARCH}.deb ./

echo ""
echo "========================================"
echo "Package built successfully!"
echo "Output: ${PRODUCT_NAME}_${PRODUCT_VERSION}_${ARCH}.deb"
echo "========================================"
echo ""
echo "To install: sudo dpkg -i ${PRODUCT_NAME}_${PRODUCT_VERSION}_${ARCH}.deb"
echo ""
