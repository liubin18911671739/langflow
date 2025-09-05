"""Security headers middleware for enhanced security"""
from typing import Dict, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Security headers middleware to add security-related HTTP headers"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Security headers configuration
        self.security_headers = {
            # Content Security Policy
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' wss: https:; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self'; "
                "object-src 'none'; "
                "plugin-types 'none';"
            ),
            
            # Prevent MIME type sniffing
            "X-Content-Type-Options": "nosniff",
            
            # Prevent clickjacking
            "X-Frame-Options": "DENY",
            
            # Enable XSS protection
            "X-XSS-Protection": "1; mode=block",
            
            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            
            # HSTS (HTTPS enforcement)
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
            
            # Permissions policy
            "Permissions-Policy": (
                "accelerometer=(), "
                "ambient-light-sensor=(), "
                "battery=(), "
                "bluetooth=(), "
                "camera=(), "
                "cross-origin-isolated=(), "
                "display-capture=(), "
                "document-domain=(), "
                "encrypted-media=(), "
                "execution-while-not-rendered=(), "
                "execution-while-out-of-viewport=(), "
                "fullscreen=(), "
                "geolocation=(), "
                "gyroscope=(), "
                "hid=(), "
                "identity-credentials-get=(), "
                "idle-detection=(), "
                "local-fonts=(), "
                "magnetometer=(), "
                "microphone=(), "
                "midi=(), "
                "otp-credentials=(), "
                "payment=(), "
                "picture-in-picture=(), "
                "publickey-credentials-get=(), "
                "screen-wake-lock=(), "
                "serial=(), "
                "storage-access=(), "
                "usb=(), "
                "web-share=(), "
                "window-management=(), "
                "xr-spatial-tracking=()"
            ),
            
            # Remove server information
            "Server": "Langflow",
            
            # Prevent caching of sensitive data
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        
        # Paths that can have relaxed security headers
        self.relaxed_paths = [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static",
        ]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and add security headers"""
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        await self._add_security_headers(response, request.url.path)
        
        # Remove potentially sensitive headers
        await self._remove_sensitive_headers(response)
        
        return response
    
    async def _add_security_headers(self, response: Response, path: str):
        """Add security headers to response"""
        # Check if path should have relaxed security
        use_relaxed_security = any(path.startswith(relaxed_path) for relaxed_path in self.relaxed_paths)
        
        if use_relaxed_security:
            # Relaxed security for documentation and static files
            headers = self._get_relaxed_security_headers()
        else:
            # Full security for all other paths
            headers = self.security_headers
        
        # Add headers to response
        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value
    
    async def _remove_sensitive_headers(self, response: Response):
        """Remove potentially sensitive headers"""
        sensitive_headers = [
            "X-Powered-By",
            "X-AspNet-Version",
            "X-AspNetMvc-Version",
            "X-Generator",
            "X-Drupal-Cache",
            "X-Varnish",
            "X-Runtime",
            "X-Version",
            "Server-Timing",
        ]
        
        for header in sensitive_headers:
            if header in response.headers:
                del response.headers[header]
    
    def _get_relaxed_security_headers(self) -> Dict[str, str]:
        """Get relaxed security headers for documentation and static files"""
        relaxed_headers = self.security_headers.copy()
        
        # Relax CSP for documentation
        relaxed_headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self' wss: https:; "
            "frame-ancestors 'self'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "object-src 'none';"
        )
        
        # Allow caching for static files
        relaxed_headers["Cache-Control"] = "public, max-age=3600"
        del relaxed_headers["Pragma"]
        del relaxed_headers["Expires"]
        
        return relaxed_headers


class CORSConfigurationMiddleware(BaseHTTPMiddleware):
    """Enhanced CORS configuration middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # CORS configuration
        self.allowed_origins = [
            "http://localhost:3000",
            "http://localhost:7860",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:7860",
        ]
        
        self.allowed_methods = [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "OPTIONS",
            "HEAD",
        ]
        
        self.allowed_headers = [
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-API-Key",
            "X-Requested-With",
            "X-CSRF-Token",
            "X-Organization-ID",
            "X-Tenant-ID",
        ]
        
        self.exposed_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Request-ID",
        ]
        
        self.max_age = 86400  # 24 hours
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with CORS handling"""
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            return await self._handle_preflight(request)
        
        # Process request
        response = await call_next(request)
        
        # Add CORS headers to actual response
        await self._add_cors_headers(response, request.headers.get("origin"))
        
        return response
    
    async def _handle_preflight(self, request: Request) -> Response:
        """Handle CORS preflight requests"""
        origin = request.headers.get("origin")
        
        if not self._is_origin_allowed(origin):
            return JSONResponse(
                {"error": "Origin not allowed"},
                status_code=403
            )
        
        response = JSONResponse({"status": "ok"})
        await self._add_cors_headers(response, origin, is_preflight=True)
        
        return response
    
    async def _add_cors_headers(self, response: Response, origin: Optional[str], is_preflight: bool = False):
        """Add CORS headers to response"""
        if origin and self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
        
        if is_preflight:
            response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allowed_methods)
            response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allowed_headers)
            response.headers["Access-Control-Max-Age"] = str(self.max_age)
        
        if self.exposed_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(self.exposed_headers)
        
        # Additional security headers
        response.headers["Access-Control-Allow-Credentials"] = "true"
    
    def _is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if origin is allowed"""
        if not origin:
            return False
        
        return origin in self.allowed_origins


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # CSRF protection configuration
        self.protected_methods = ["POST", "PUT", "DELETE", "PATCH"]
        self.exempt_paths = [
            "/api/v1/login",
            "/api/v1/register",
            "/api/v1/health",
            "/api/v1/health_check",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        
        # CSRF token header name
        self.csrf_header = "X-CSRF-Token"
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with CSRF protection"""
        
        # Skip CSRF protection for exempt methods and paths
        if (request.method not in self.protected_methods or 
            any(request.url.path.startswith(path) for path in self.exempt_paths)):
            return await call_next(request)
        
        # Validate CSRF token
        if not await self._validate_csrf_token(request):
            return JSONResponse(
                {"error": "CSRF token validation failed"},
                status_code=403
            )
        
        # Process request
        response = await call_next(request)
        
        # Add CSRF token to response if needed
        await self._add_csrf_token(response)
        
        return response
    
    async def _validate_csrf_token(self, request: Request) -> bool:
        """Validate CSRF token"""
        # Get token from header
        header_token = request.headers.get(self.csrf_header)
        
        # Get token from cookie
        cookie_token = request.cookies.get("csrf_token")
        
        # For now, we'll use a simple validation
        # In production, this should use proper CSRF token validation
        return header_token and cookie_token and header_token == cookie_token
    
    async def _add_csrf_token(self, response: Response):
        """Add CSRF token to response"""
        # This is a simplified version
        # In production, generate proper CSRF tokens
        csrf_token = "temp_csrf_token"  # Replace with proper token generation
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,
            secure=True,
            samesite="strict"
        )


async def add_security_headers_middleware(app):
    """Add security headers middleware to application"""
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CORSConfigurationMiddleware)
    app.add_middleware(CSRFProtectionMiddleware)
    logger.info("Security headers middleware added")