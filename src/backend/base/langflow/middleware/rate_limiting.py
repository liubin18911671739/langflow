"""Rate limiting middleware for API endpoints"""
import time
import asyncio
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from langflow.services.deps import get_settings_service


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware to prevent API abuse"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings_service().settings
        
        # Rate limiting rules (endpoint: (requests, window_seconds))
        self.rate_limits = {
            # Default limits
            "default": (100, 60),  # 100 requests per minute
            
            # Authentication endpoints
            "/api/v1/login": (5, 60),  # 5 login attempts per minute
            "/api/v1/register": (3, 3600),  # 3 registrations per hour
            
            # API endpoints
            "/api/v1/chat": (60, 60),  # 60 chat requests per minute
            "/api/v1/flows": (30, 60),  # 30 flow operations per minute
            "/api/v1/endpoints": (20, 60),  # 20 endpoint operations per minute
            
            # File operations
            "/api/v1/files/upload": (10, 60),  # 10 file uploads per minute
            "/api/v1/files/download": (20, 60),  # 20 file downloads per minute
            
            # Admin endpoints
            "/api/v1/admin": (5, 60),  # 5 admin operations per minute
        }
        
        # In-memory storage for rate limiting
        # In production, this should be replaced with Redis
        self.request_records: Dict[str, deque] = defaultdict(deque)
        self.cleanup_task: Optional[asyncio.Task] = None
        
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with rate limiting"""
        
        # Skip rate limiting for health checks and static files
        if self._should_skip_rate_limit(request.url.path):
            return await call_next(request)
        
        # Get client identifier
        client_id = await self._get_client_id(request)
        
        # Check rate limit
        if not await self._check_rate_limit(client_id, request.url.path, request.method):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": self._get_retry_after(client_id, request.url.path)
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        self._add_rate_limit_headers(response, client_id, request.url.path)
        
        return response
    
    def _should_skip_rate_limit(self, path: str) -> bool:
        """Check if path should be skipped from rate limiting"""
        skip_paths = [
            "/health",
            "/health_check",
            "/api/v1/health",
            "/api/v1/health_check",
            "/static/",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
        
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    async def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier for rate limiting"""
        # Try to get user ID from authenticated user
        if hasattr(request.state, 'user') and request.state.user:
            return f"user:{request.state.user.id}"
        
        # Use API key if present
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        if api_key:
            return f"api_key:{api_key[:16]}"  # Use first 16 chars for privacy
        
        # Use IP address as fallback
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return f"ip:{forwarded_for.split(',')[0].strip()}"
        
        # Use remote address
        return f"ip:{request.client.host if request.client else 'unknown'}"
    
    async def _check_rate_limit(self, client_id: str, path: str, method: str) -> bool:
        """Check if request is within rate limit"""
        # Find applicable rate limit
        limit_key, (max_requests, window_seconds) = self._get_rate_limit(path, method)
        
        # Create key for this client and endpoint
        key = f"{client_id}:{limit_key}"
        
        # Get current timestamp
        current_time = time.time()
        
        # Clean old requests
        while self.request_records[key] and self.request_records[key][0] < current_time - window_seconds:
            self.request_records[key].popleft()
        
        # Check if limit exceeded
        if len(self.request_records[key]) >= max_requests:
            return False
        
        # Record this request
        self.request_records[key].append(current_time)
        
        # Start cleanup task if not running
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_old_records())
        
        return True
    
    def _get_rate_limit(self, path: str, method: str) -> Tuple[str, Tuple[int, int]]:
        """Get rate limit for the given path"""
        # Check exact matches first
        for endpoint, limit in self.rate_limits.items():
            if path.startswith(endpoint):
                return endpoint, limit
        
        # Use default limit
        return "default", self.rate_limits["default"]
    
    def _get_retry_after(self, client_id: str, path: str) -> int:
        """Get retry after seconds for rate limited client"""
        limit_key, (_, window_seconds) = self._get_rate_limit(path, "GET")
        key = f"{client_id}:{limit_key}"
        
        if not self.request_records[key]:
            return 60
        
        # Calculate when oldest request will expire
        oldest_request = self.request_records[key][0]
        retry_after = int(oldest_request + window_seconds - time.time())
        
        return max(1, retry_after)
    
    def _add_rate_limit_headers(self, response: Response, client_id: str, path: str):
        """Add rate limiting headers to response"""
        limit_key, (max_requests, window_seconds) = self._get_rate_limit(path, "GET")
        key = f"{client_id}:{limit_key}"
        
        current_time = time.time()
        
        # Clean old requests
        while self.request_records[key] and self.request_records[key][0] < current_time - window_seconds:
            self.request_records[key].popleft()
        
        remaining_requests = max(0, max_requests - len(self.request_records[key]))
        
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining_requests)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + window_seconds))
    
    async def _cleanup_old_records(self):
        """Cleanup old request records periodically"""
        while True:
            try:
                await asyncio.sleep(60)  # Cleanup every minute
                current_time = time.time()
                
                # Remove old records
                keys_to_remove = []
                for key, records in self.request_records.items():
                    while records and records[0] < current_time - 3600:  # Remove records older than 1 hour
                        records.popleft()
                    
                    # Remove empty records
                    if not records:
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self.request_records[key]
                
                logger.debug(f"Rate limit cleanup completed. Active records: {len(self.request_records)}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Rate limit cleanup error: {e}")


async def add_rate_limiting_middleware(app):
    """Add rate limiting middleware to application"""
    app.add_middleware(RateLimitMiddleware)
    logger.info("Rate limiting middleware added")