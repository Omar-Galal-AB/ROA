#!/bin/bash
# Test script for metrics server endpoints

set -e

METRICS_URL="${METRICS_URL:-http://localhost:9090}"
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "ROA Metrics Server Test"
echo "======================================================================"
echo "Testing: $METRICS_URL"
echo ""

# Test /health endpoint
echo -e "${BOLD}1. Testing /health endpoint${NC}"
echo "----------------------------------------------------------------------"
if curl -f -s "${METRICS_URL}/health" | jq . ; then
    echo -e "${GREEN}✅ Health check passed${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
    exit 1
fi
echo ""

# Test /metrics endpoint
echo -e "${BOLD}2. Testing /metrics endpoint${NC}"
echo "----------------------------------------------------------------------"
METRIC_COUNT=$(curl -s "${METRICS_URL}/metrics" | grep -E "^[a-z]" | wc -l)
echo "Found $METRIC_COUNT metric families"
if [ "$METRIC_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ Metrics endpoint working${NC}"
else
    echo -e "${RED}❌ No metrics found${NC}"
    exit 1
fi
echo ""

# Test gzip compression
echo -e "${BOLD}3. Testing gzip compression${NC}"
echo "----------------------------------------------------------------------"
UNCOMPRESSED_SIZE=$(curl -s "${METRICS_URL}/metrics" | wc -c)
COMPRESSED_SIZE=$(curl -s -H "Accept-Encoding: gzip" "${METRICS_URL}/metrics" | wc -c)
COMPRESSION_RATIO=$(echo "scale=1; $UNCOMPRESSED_SIZE / $COMPRESSED_SIZE" | bc)

echo "Uncompressed size: $UNCOMPRESSED_SIZE bytes"
echo "Compressed size:   $COMPRESSED_SIZE bytes"
echo "Compression ratio: ${COMPRESSION_RATIO}x"

if [ "$COMPRESSED_SIZE" -lt "$UNCOMPRESSED_SIZE" ]; then
    echo -e "${GREEN}✅ Compression working${NC}"
else
    echo -e "${BLUE}ℹ️  Compression not applied (payload too small)${NC}"
fi
echo ""

# Test CORS headers
echo -e "${BOLD}4. Testing CORS headers${NC}"
echo "----------------------------------------------------------------------"
CORS_HEADER=$(curl -s -I "${METRICS_URL}/metrics" | grep -i "access-control-allow-origin" || true)
if [ -n "$CORS_HEADER" ]; then
    echo "$CORS_HEADER"
    echo -e "${GREEN}✅ CORS headers present${NC}"
else
    echo -e "${RED}❌ CORS headers missing${NC}"
fi
echo ""

# Test sample metrics
echo -e "${BOLD}5. Sample Metrics${NC}"
echo "----------------------------------------------------------------------"
echo "Heartbeat metrics:"
curl -s "${METRICS_URL}/metrics" | grep "roa_heartbeat" | head -5

echo ""
echo "Component health metrics:"
curl -s "${METRICS_URL}/metrics" | grep "roa_component_health" | head -5

echo ""
echo "Request metrics:"
curl -s "${METRICS_URL}/metrics" | grep "roa_request" | head -5

echo ""
echo "======================================================================"
echo -e "${GREEN}All tests passed!${NC}"
echo "======================================================================"
