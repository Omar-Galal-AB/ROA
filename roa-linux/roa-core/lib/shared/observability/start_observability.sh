#!/bin/bash
# =============================================================================
# ROA Observability Stack Startup Script
# =============================================================================
# This script starts the complete observability infrastructure and
# optionally starts the ROA components with instrumentation.
#
# Usage:
#   ./start_observability.sh [options]
#
# Options:
#   --infra-only    Start only infrastructure (Docker containers)
#   --components    Start ROA components with observability
#   --all           Start everything (default)
#   --stop          Stop all services
#   --status        Show status of all services
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROA_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CONFIG_DIR="$ROA_ROOT/config/observability"
SHARED_OBS_DIR="$ROA_ROOT/roa-core/lib/shared/observability"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Check dependencies
check_dependencies() {
    log_section "Checking Dependencies"
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    log_info "Docker: $(docker --version)"
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    log_info "Docker Compose: $(docker compose version 2>/dev/null || docker-compose --version)"
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 is not installed"
        exit 1
    fi
    log_info "Python3: $(python3 --version)"
    
    log_info "All dependencies satisfied"
}

# Install Python packages
install_python_deps() {
    log_section "Installing Python Dependencies"
    
    if [ -f "$SHARED_OBS_DIR/requirements.txt" ]; then
        log_info "Installing from requirements.txt..."
        pip3 install -r "$SHARED_OBS_DIR/requirements.txt" --quiet || {
            log_warn "Some packages may not have installed correctly"
        }
    else
        log_warn "requirements.txt not found, installing core packages..."
        pip3 install prometheus-client opentelemetry-api opentelemetry-sdk --quiet || true
    fi
    
    log_info "Python dependencies installed"
}

# Start infrastructure
start_infrastructure() {
    log_section "Starting Observability Infrastructure"
    
    if [ ! -f "$CONFIG_DIR/docker-compose.yml" ]; then
        log_error "docker-compose.yml not found at $CONFIG_DIR"
        exit 1
    fi
    
    cd "$CONFIG_DIR"
    
    log_info "Starting Docker containers..."
    docker compose up -d
    
    log_info "Waiting for services to be ready..."
    sleep 10
    
    # Check service health
    log_info "Checking service status..."
    docker compose ps
    
    log_section "Service Endpoints"
    echo ""
    echo "  📊 Grafana:         http://localhost:3000   (admin/admin)"
    echo "  🦊 Foxglove Studio: http://localhost:8765"
    echo "  📈 Prometheus:      http://localhost:9090"
    echo "  📝 Loki:            http://localhost:3100"
    echo "  🔍 Tempo:           http://localhost:3200"
    echo "  🔥 Pyroscope:       http://localhost:4040"
    echo ""
}

# Stop infrastructure
stop_infrastructure() {
    log_section "Stopping Observability Infrastructure"
    
    cd "$CONFIG_DIR"
    docker compose down
    
    log_info "Infrastructure stopped"
}

# Run tests
run_tests() {
    log_section "Running Observability Tests"
    
    cd "$SHARED_OBS_DIR"
    python3 -m pytest tests.py -v || python3 tests.py
}

# Show status
show_status() {
    log_section "Observability Stack Status"
    
    echo ""
    log_info "Docker Containers:"
    cd "$CONFIG_DIR" 2>/dev/null && docker compose ps 2>/dev/null || echo "  No containers running"
    
    echo ""
    log_info "Component Metrics Endpoints:"
    
    for port in 9091 9092 9093 9094 9095; do
        component=""
        case $port in
            9091) component="webthread" ;;
            9092) component="fti" ;;
            9093) component="dimc" ;;
            9094) component="roc" ;;
            9095) component="comc" ;;
        esac
        
        if curl -s "http://localhost:$port/metrics" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $component (port $port)"
        else
            echo -e "  ${RED}✗${NC} $component (port $port)"
        fi
    done
    
    echo ""
    log_info "Health Endpoints:"
    
    for port in 8081 8082 8083 8084 8085; do
        component=""
        case $port in
            8081) component="webthread" ;;
            8082) component="fti" ;;
            8083) component="dimc" ;;
            8084) component="roc" ;;
            8085) component="comc" ;;
        esac
        
        if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $component (port $port)"
        else
            echo -e "  ${RED}✗${NC} $component (port $port)"
        fi
    done
}

# Print usage
print_usage() {
    echo "ROA Observability Stack Startup Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start       Start the complete observability stack"
    echo "  infra       Start only infrastructure (Docker containers)"
    echo "  stop        Stop all services"
    echo "  status      Show status of all services"
    echo "  test        Run observability tests"
    echo "  install     Install Python dependencies"
    echo "  help        Show this help message"
    echo ""
}

# Main
main() {
    case "${1:-start}" in
        start|all)
            check_dependencies
            install_python_deps
            start_infrastructure
            show_status
            ;;
        infra|infrastructure)
            check_dependencies
            start_infrastructure
            ;;
        stop)
            stop_infrastructure
            ;;
        status)
            show_status
            ;;
        test)
            run_tests
            ;;
        install)
            install_python_deps
            ;;
        help|--help|-h)
            print_usage
            ;;
        *)
            log_error "Unknown command: $1"
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
