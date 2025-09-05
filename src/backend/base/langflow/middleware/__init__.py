"""Middleware initialization for security and performance features"""
from loguru import logger

from langflow.middleware.rate_limiting import add_rate_limiting_middleware
from langflow.middleware.input_validation import add_input_validation_middleware
from langflow.middleware.security_headers import add_security_headers_middleware
from langflow.middleware.api_key_auth import add_api_key_auth_middleware
from langflow.middleware.compression import get_compression_middleware, CompressionConfig
from langflow.middleware.error_handling import add_error_handling_middleware


async def add_security_middleware(app):
    """Add all security middleware to the application"""
    
    logger.info("Adding security middleware...")
    
    # Add input validation middleware (first in chain)
    await add_input_validation_middleware(app)
    logger.info("✓ Input validation middleware added")
    
    # Add rate limiting middleware
    await add_rate_limiting_middleware(app)
    logger.info("✓ Rate limiting middleware added")
    
    # Add security headers middleware
    await add_security_headers_middleware(app)
    logger.info("✓ Security headers middleware added")
    
    # Add API key authentication middleware
    await add_api_key_auth_middleware(app)
    logger.info("✓ API key authentication middleware added")
    
    logger.info("All security middleware added successfully")


async def add_performance_middleware(app):
    """Add all performance optimization middleware to the application"""
    
    logger.info("Adding performance middleware...")
    
    # Add compression middleware
    compression_config = CompressionConfig()
    compression_middleware = get_compression_middleware(compression_config)
    
    # Add middleware to application
    app.add_middleware(type(compression_middleware))
    logger.info("✓ Compression middleware added")
    
    logger.info("All performance middleware added successfully")


async def add_all_middleware(app):
    """Add all security and performance middleware to the application"""
    
    logger.info("Adding all middleware...")
    
    # Add error handling middleware first (before all other middleware)
    await add_error_handling_middleware(app)
    logger.info("✓ Error handling middleware added")
    
    # Add performance middleware
    await add_performance_middleware(app)
    
    # Add security middleware
    await add_security_middleware(app)
    
    logger.info("All middleware added successfully")


# Export individual middleware adders for flexibility
__all__ = [
    "add_security_middleware",
    "add_performance_middleware",
    "add_all_middleware",
    "add_rate_limiting_middleware", 
    "add_input_validation_middleware",
    "add_security_headers_middleware",
    "add_api_key_auth_middleware",
    "add_error_handling_middleware"
]