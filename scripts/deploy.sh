#!/bin/bash

# Langflow Production Deployment Script
# This script helps deploy Langflow in production environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="langflow"
COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE=".env.production"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    log_success "Docker is installed"
}

# Check if Docker Compose is installed
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    log_success "Docker Compose is installed"
}

# Create environment file if it doesn't exist
setup_environment() {
    if [ ! -f "$ENV_FILE" ]; then
        log_info "Creating environment file from template..."
        cp .env.production.example "$ENV_FILE"
        log_warning "Please update $ENV_FILE with your configuration before continuing"
        log_warning "At minimum, update:"
        log_warning "  - LANGFLOW_SECRET_KEY (generate with: openssl rand -hex 32)"
        log_warning "  - LANGFLOW_DB_PASSWORD"
        log_warning "  - LANGFLOW_REDIS_PASSWORD"
        log_warning "  - GRAFANA_PASSWORD"
        log_warning "  - LANGFLOW_SUPERUSER_PASSWORD"
        read -p "Press Enter after you've updated the environment file..."
    else
        log_success "Environment file exists"
    fi
}

# Generate strong secrets if not set
generate_secrets() {
    if grep -q "your-super-secret-key-change-this-in-production" "$ENV_FILE"; then
        log_info "Generating strong secrets..."
        
        # Generate secret key
        SECRET_KEY=$(openssl rand -hex 32)
        sed -i "s/your-super-secret-key-change-this-in-production/$SECRET_KEY/" "$ENV_FILE"
        
        # Generate database password
        DB_PASSWORD=$(openssl rand -hex 16)
        sed -i "s/your-secure-database-password/$DB_PASSWORD/" "$ENV_FILE"
        
        # Generate redis password
        REDIS_PASSWORD=$(openssl rand -hex 16)
        sed -i "s/your-secure-redis-password/$REDIS_PASSWORD/" "$ENV_FILE"
        
        # Generate grafana password
        GRAFANA_PASSWORD=$(openssl rand -hex 12)
        sed -i "s/your-secure-grafana-password/$GRAFANA_PASSWORD/" "$ENV_FILE"
        
        # Generate superuser password
        SUPERUSER_PASSWORD=$(openssl rand -hex 12)
        sed -i "s/your-super-secure-password/$SUPERUSER_PASSWORD/" "$ENV_FILE"
        
        log_success "Strong secrets generated and saved to $ENV_FILE"
    fi
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    mkdir -p docker/nginx/ssl
    mkdir -p docker/prometheus
    mkdir -p docker/grafana/provisioning/dashboards
    mkdir -p docker/grafana/provisioning/datasources
    log_success "Directories created"
}

# Set proper permissions
set_permissions() {
    log_info "Setting proper permissions..."
    chmod 600 "$ENV_FILE"
    chmod 700 docker/entrypoint.sh
    log_success "Permissions set"
}

# Deploy the application
deploy() {
    log_info "Starting deployment..."
    
    # Pull latest images
    log_info "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" pull
    
    # Build custom images
    log_info "Building custom images..."
    docker-compose -f "$COMPOSE_FILE" build --no-cache
    
    # Start services
    log_info "Starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d
    
    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    sleep 30
    
    # Check service health
    check_health
}

# Check service health
check_health() {
    log_info "Checking service health..."
    
    # Check Langflow
    if curl -f http://localhost:7860/api/v1/health_check > /dev/null 2>&1; then
        log_success "Langflow is healthy"
    else
        log_error "Langflow is not responding"
        return 1
    fi
    
    # Check database
    if docker-compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U langflow -d langflow > /dev/null 2>&1; then
        log_success "PostgreSQL is healthy"
    else
        log_error "PostgreSQL is not responding"
        return 1
    fi
    
    # Check Redis
    if docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis is healthy"
    else
        log_error "Redis is not responding"
        return 1
    fi
    
    log_success "All services are healthy"
}

# Show status
show_status() {
    log_info "Service status:"
    docker-compose -f "$COMPOSE_FILE" ps
}

# Show logs
show_logs() {
    service=${1:-}
    if [ -z "$service" ]; then
        log_info "Showing all logs (press Ctrl+C to exit)..."
        docker-compose -f "$COMPOSE_FILE" logs -f
    else
        log_info "Showing logs for $service (press Ctrl+C to exit)..."
        docker-compose -f "$COMPOSE_FILE" logs -f "$service"
    fi
}

# Stop services
stop() {
    log_info "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" down
    log_success "Services stopped"
}

# Restart services
restart() {
    log_info "Restarting services..."
    docker-compose -f "$COMPOSE_FILE" restart
    log_success "Services restarted"
}

# Update deployment
update() {
    log_info "Updating deployment..."
    
    # Pull latest images
    docker-compose -f "$COMPOSE_FILE" pull
    
    # Rebuild and restart
    docker-compose -f "$COMPOSE_FILE" up -d --force-recreate
    
    log_success "Deployment updated"
}

# Backup
backup() {
    log_info "Creating backup..."
    
    # Create backup directory
    BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup database
    docker-compose -f "$COMPOSE_FILE" exec -T postgres pg_dump -U langflow -d langflow > "$BACKUP_DIR/database.sql"
    
    # Backup uploads
    docker-compose -f "$COMPOSE_FILE" cp langflow:/app/uploads "$BACKUP_DIR/"
    
    # Backup config files
    cp "$ENV_FILE" "$BACKUP_DIR/"
    
    log_success "Backup created in $BACKUP_DIR"
}

# Restore
restore() {
    if [ -z "$1" ]; then
        log_error "Please specify backup directory"
        exit 1
    fi
    
    BACKUP_DIR="$1"
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        exit 1
    fi
    
    log_warning "This will restore from backup: $BACKUP_DIR"
    log_warning "All current data will be lost!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Restore cancelled"
        exit 0
    fi
    
    # Stop services
    stop
    
    # Restore database
    docker-compose -f "$COMPOSE_FILE" up -d postgres
    sleep 10
    docker-compose -f "$COMPOSE_FILE" exec -T postgres psql -U langflow -d langflow < "$BACKUP_DIR/database.sql"
    
    # Restore uploads
    docker-compose -f "$COMPOSE_FILE" cp "$BACKUP_DIR/uploads/" langflow:/app/
    
    # Start all services
    deploy
    
    log_success "Restore completed"
}

# Show help
show_help() {
    echo "Langflow Production Deployment Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  deploy      - Deploy Langflow in production"
    echo "  status      - Show service status"
    echo "  logs [svc]  - Show logs (optional: specify service)"
    echo "  stop        - Stop all services"
    echo "  restart     - Restart all services"
    echo "  update      - Update deployment"
    echo "  backup      - Create backup"
    echo "  restore     - Restore from backup"
    echo "  health      - Check service health"
    echo "  help        - Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  COMPOSE_FILE    - Docker Compose file (default: docker-compose.production.yml)"
    echo "  ENV_FILE        - Environment file (default: .env.production)"
}

# Main script logic
main() {
    case "${1:-}" in
        "deploy")
            check_docker
            check_docker_compose
            setup_environment
            generate_secrets
            create_directories
            set_permissions
            deploy
            show_status
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "$2"
            ;;
        "stop")
            stop
            ;;
        "restart")
            restart
            ;;
        "update")
            update
            ;;
        "backup")
            backup
            ;;
        "restore")
            restore "$2"
            ;;
        "health")
            check_health
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"