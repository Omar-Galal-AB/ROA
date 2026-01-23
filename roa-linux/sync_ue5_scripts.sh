#!/bin/bash
# ROA - Sync UE5 Python scripts between production FTI and UE5 project
# This ensures both locations stay in sync

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FTI_UE5_DIR="$SCRIPT_DIR/roa-core/lib/components/files-type-importer/src/python/UE5"
UE5_PROJECT_DIR="/mnt/d/ROA/UE5_Projects/ROA_V1/Content/Python/ROA"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          ROA UE5 Scripts Sync                               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if directories exist
if [ ! -d "$FTI_UE5_DIR" ]; then
    echo "❌ FTI UE5 directory not found: $FTI_UE5_DIR"
    exit 1
fi

if [ ! -d "$UE5_PROJECT_DIR" ]; then
    echo "❌ UE5 project directory not found: $UE5_PROJECT_DIR"
    exit 1
fi

echo "Source (Production FTI): $FTI_UE5_DIR"
echo "Target (UE5 Project):    $UE5_PROJECT_DIR"
echo ""

# Sync FTI -> UE5 Project (production is source of truth)
echo "📦 Syncing scripts from FTI to UE5 project..."

for file in "$FTI_UE5_DIR"/*.py; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        echo "  → $filename"
        cp "$file" "$UE5_PROJECT_DIR/"
    fi
done

echo ""
echo "✅ Sync complete!"
echo ""
echo "Files in UE5 project:"
ls -la "$UE5_PROJECT_DIR"/*.py 2>/dev/null | awk '{print "  " $NF}'
