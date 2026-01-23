#!/bin/bash
# =============================================================================
# ROA Observability Stack Startup Script
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OBSERVABILITY_DIR="$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Functions
# =============================================================================

show_help() {
    cat << EOF
ROA Observability Stack Manager

Usage: $0 <command> [options]

Commands:
    start       Start the observability stack
    stop        Stop the observability stack
    restart     Restart the observability stack
    status      Show status of all services
    logs        Show logs (optionally for specific service)
    urls        Show URLs for all services
    clean       Remove all data volumes
    help        Show this help message

Options:
    --profile <name>    Enable profile (beyla, mimir)
    --all               Enable all profiles
    --detach, -d        Run in detached mode (default)
    --follow, -f        Follow logs

Examples:
    $0 start                    # Start core stack
    $0 start --profile beyla    # Start with Beyla eBPF instrumentation
    $0 start --all              # Start with all components
    $0 logs fluent-bit          # Show Fluent Bit logs
    $0 status                   # Show service status

EOF
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
}

check_compose() {
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "Docker Compose is not installed."
        exit 1
    fi
}

create_log_dir() {
    ROA_LOG_DIR="${ROA_LOG_DIR:-$HOME/.roa/logs}"
    if [ ! -d "$ROA_LOG_DIR" ]; then
        log_info "Creating ROA log directory: $ROA_LOG_DIR"
        mkdir -p "$ROA_LOG_DIR"
    fi
    export ROA_LOG_DIR
}

start_stack() {
    local profiles=""
    local detach="-d"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --profile)
                profiles="$profiles --profile $2"
                shift 2
                ;;
            --all)
                profiles="--profile beyla --profile mimir"
                shift
                ;;
            --no-detach)
                detach=""
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    log_info "Starting ROA Observability Stack..."
    create_log_dir
    
    cd "$OBSERVABILITY_DIR"
    $COMPOSE_CMD $profiles up $detach --build
    
    if [ -n "$detach" ]; then
        log_success "Stack started successfully!"
        show_urls
    fi
}

stop_stack() {
    log_info "Stopping ROA Observability Stack..."
    cd "$OBSERVABILITY_DIR"
    $COMPOSE_CMD --profile beyla --profile mimir down
    log_success "Stack stopped."
}

restart_stack() {
    stop_stack
    start_stack "$@"
}

show_status() {
    log_info "ROA Observability Stack Status:"
    echo ""
    cd "$OBSERVABILITY_DIR"
    $COMPOSE_CMD --profile beyla --profile mimir ps
}

show_logs() {
    local service="$1"
    local follow=""
    
    if [ "$2" == "-f" ] || [ "$2" == "--follow" ]; then
        follow="-f"
    fi
    
    cd "$OBSERVABILITY_DIR"
    if [ -n "$service" ] && [ "$service" != "-f" ] && [ "$service" != "--follow" ]; then
        $COMPOSE_CMD logs $follow "$service"
    else
        if [ "$service" == "-f" ] || [ "$service" == "--follow" ]; then
            follow="-f"
        fi
        $COMPOSE_CMD logs $follow
    fi
}

show_urls() {
    echo ""
    log_info "Service URLs:"
    echo "  ┌─────────────────────────────────────────────────────────────┐"
    echo "  │  Foxglove Studio    │  http://localhost:8080                │"
    echo "  │  Grafana            │  http://localhost:3000 (admin/roa_admin)"
    echo "  │  Prometheus         │  http://localhost:9090                │"
    echo "  │  Loki               │  http://localhost:3100                │"
    echo "  │  Tempo              │  http://localhost:3200                │"
    echo "  │  Pyroscope          │  http://localhost:4040                │"
    echo "  │  Alloy UI           │  http://localhost:12345               │"
    echo "  │  Fluent Bit Metrics │  http://localhost:2020                │"
    echo "  └─────────────────────────────────────────────────────────────┘"
    echo ""
    log_info "ROS2 Commands:"
    echo "  # Start Foxglove Bridge for live visualization"
    echo "  ros2 launch foxglove_bridge foxglove_bridge_launch.xml"
    echo ""
    echo "  # Start recording to MCAP"
    echo "  ros2 bag record -s mcap -o ~/.roa/recordings/session_\$(date +%Y%m%d_%H%M%S) -a"
    echo ""
}

clean_volumes() {
    log_warn "This will remove all observability data!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleaning volumes..."
        cd "$OBSERVABILITY_DIR"
        $COMPOSE_CMD --profile beyla --profile mimir down -v
        log_success "Volumes removed."
    else
        log_info "Cancelled."
    fi
}

# =============================================================================
# Main
# =============================================================================

check_docker
check_compose

case "${1:-help}" in
    start)
        shift
        start_stack "$@"
        ;;
    stop)
        stop_stack
        ;;
    restart)
        shift
        restart_stack "$@"
        ;;
    status)
        show_status
        ;;
    logs)
        shift
        show_logs "$@"
        ;;
    urls)
        show_urls
        ;;
    clean)
        clean_volumes
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
