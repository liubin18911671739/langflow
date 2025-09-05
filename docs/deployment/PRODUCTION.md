# Langflow Production Deployment Guide

This guide explains how to deploy Langflow in a production environment with all the security and performance enhancements.

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available
- Port 7860 (or custom port) available
- SSL certificate (recommended for production)

### 2. Initial Setup

```bash
# Clone the repository
git clone https://github.com/langflow-ai/langflow.git
cd langflow

# Run the deployment script
./scripts/deploy.sh deploy
```

The script will:
- Check prerequisites
- Create necessary configuration files
- Generate strong security keys
- Set up the directory structure
- Deploy all services

### 3. Access Langflow

- **Application**: http://localhost:7860
- **Grafana Dashboard**: http://localhost:3000 (admin: password from .env)
- **Prometheus Metrics**: http://localhost:9090

## Configuration

### Environment Variables

The main configuration is in `.env.production`. Key settings:

```bash
# Security (generate strong secrets)
LANGFLOW_SECRET_KEY=your-super-secret-key
LANGFLOW_DB_PASSWORD=your-database-password
LANGFLOW_REDIS_PASSWORD=your-redis-password

# Application
LANGFLOW_PUBLIC_URL=https://your-domain.com
LANGFLOW_SUPERUSER_USERNAME=admin
LANGFLOW_SUPERUSER_PASSWORD=your-admin-password

# Database
LANGFLOW_DATABASE_URL=postgresql://langflow:password@postgres:5432/langflow
```

### Security Features

The deployment includes comprehensive security measures:

1. **API Rate Limiting**
   - Configurable per-endpoint limits
   - IP-based throttling
   - Automatic blocking of abuse

2. **Input Validation**
   - SQL injection protection
   - XSS prevention
   - Command injection detection
   - Path traversal protection

3. **Security Headers**
   - Content Security Policy (CSP)
   - XSS Protection
   - Clickjacking protection
   - HSTS enforcement

4. **API Key Management**
   - Secure key generation and rotation
   - Permission-based access control
   - IP and referer restrictions
   - Automatic key expiration

5. **Network Security**
   - Nginx reverse proxy
   - SSL/TLS termination
   - Request filtering
   - DDoS protection

## Deployment Commands

### Common Operations

```bash
# Check service status
./scripts/deploy.sh status

# View logs
./scripts/deploy.sh logs
./scripts/deploy.sh logs langflow

# Restart services
./scripts/deploy.sh restart

# Stop all services
./scripts/deploy.sh stop

# Update deployment
./scripts/deploy.sh update

# Check health
./scripts/deploy.sh health
```

### Backup and Restore

```bash
# Create backup
./scripts/deploy.sh backup

# Restore from backup
./scripts/deploy.sh restore ./backups/20240101_120000
```

## Architecture

### Service Components

1. **Langflow Application**
   - Main application server
   - Includes all security middleware
   - Health check endpoints

2. **PostgreSQL Database**
   - Persistent data storage
   - Automatic backups
   - Health monitoring

3. **Redis Cache**
   - Session storage
   - Rate limiting data
   - Performance caching

4. **Nginx Reverse Proxy**
   - SSL termination
   - Load balancing
   - Static file serving
   - Security headers

5. **Monitoring Stack**
   - Prometheus metrics collection
   - Grafana dashboards
   - Alert management

### Security Middleware Stack

```
Request → Nginx → Input Validation → Rate Limiting → Security Headers → API Key Auth → Application
```

## SSL Configuration

### Using Let's Encrypt (Recommended)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Update nginx configuration to use SSL
```

### Manual SSL Configuration

1. Place your SSL certificates in `docker/nginx/ssl/`
2. Update `docker/nginx/nginx.conf` to enable SSL
3. Uncomment the HTTPS server block

## Scaling and Performance

### Horizontal Scaling

```yaml
# In docker-compose.production.yml
langflow:
  deploy:
    replicas: 3
```

### Database Optimization

- Use connection pooling
- Enable query caching
- Regular maintenance and vacuuming
- Monitor slow queries

### Cache Optimization

- Redis for session storage
- Application-level caching
- CDN for static assets

## Monitoring and Logging

### Key Metrics to Monitor

- Application response time
- Error rates
- Database performance
- Memory usage
- API key usage

### Log Management

- Structured logging in JSON format
- Centralized log aggregation
- Alert thresholds for critical errors
- Regular log rotation

## Security Best Practices

### Production Checklist

- [ ] Change all default passwords
- [ ] Use strong secret keys
- [ ] Enable SSL/TLS
- [ ] Configure firewall rules
- [ ] Set up monitoring alerts
- [ ] Enable automatic backups
- [ ] Review access controls
- [ ] Update dependencies regularly
- [ ] Test disaster recovery

### Regular Maintenance

1. **Daily**
   - Monitor health checks
   - Review error logs
   - Check security alerts

2. **Weekly**
   - Update dependencies
   - Review access logs
   - Test backup restoration

3. **Monthly**
   - Security audit
   - Performance review
   - Capacity planning

## Troubleshooting

### Common Issues

1. **Services not starting**
   ```bash
   ./scripts/deploy.sh logs
   ./scripts/deploy.sh health
   ```

2. **Database connection issues**
   - Check database credentials
   - Verify network connectivity
   - Review database logs

3. **Memory issues**
   - Increase available RAM
   - Optimize database queries
   - Clear cache regularly

4. **SSL certificate issues**
   - Verify certificate validity
   - Check nginx configuration
   - Test SSL connection

### Debug Mode

For debugging, you can temporarily enable debug mode:

```bash
# In .env.production
LANGFLOW_DEBUG=true
LANGFLOW_LOG_LEVEL=DEBUG
```

Remember to disable debug mode in production!

## Support

For issues and questions:
- GitHub Issues: https://github.com/langflow-ai/langflow/issues
- Documentation: https://docs.langflow.org
- Community: https://discord.gg/langflow

## License

This deployment configuration is part of the Langflow project and is licensed under the MIT License.