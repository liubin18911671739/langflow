"""API key authentication middleware"""
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

from langflow.services.api_key_manager import ApiKeyManager, get_api_key_manager
from langflow.services.database.models.api_key.model import ApiKey


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """API key authentication middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        self.api_key_manager = get_api_key_manager()
        
        # Paths that require API key authentication
        self.protected_paths = [
            "/api/v1/chat",
            "/api/v1/flows",
            "/api/v1/endpoints",
            "/api/v1/validate",
            "/api/v1/files",
            "/api/v1/variables",
            "/api/v1/projects",
            "/api/v1/store",
        ]
        
        # Paths that are exempt from API key authentication
        self.exempt_paths = [
            "/api/v1/health",
            "/api/v1/health_check",
            "/api/v1/login",
            "/api/v1/register",
            "/api/v1/docs",
            "/api/v1/redoc",
            "/api/v1/openapi.json",
            "/static",
            "/docs",
            "/redoc",
        ]
        
        # API key header names
        self.api_key_header = "X-API-Key"
        self.api_secret_header = "X-API-Secret"
        
        # Bearer token for alternative authentication
        self.bearer_scheme = APIKeyHeader(name="Authorization", auto_error=False)
    
    async def dispatch(self, request: Request, call_next):
        """Process request with API key authentication"""
        
        # Skip authentication for exempt paths
        if self._should_skip_auth(request.url.path):
            return await call_next(request)
        
        # Authenticate request
        api_key_record = await self._authenticate_request(request)
        
        if not api_key_record:
            return JSONResponse(
                {"error": "Invalid or missing API credentials"},
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "APIKey"}
            )
        
        # Add API key info to request state
        request.state.api_key = api_key_record
        request.state.user_id = api_key_record.user_id
        
        # Process request
        response = await call_next(request)
        
        # Add API key usage headers
        response.headers["X-API-Key-ID"] = str(api_key_record.id)
        response.headers["X-API-Key-Name"] = api_key_record.name
        
        return response
    
    def _should_skip_auth(self, path: str) -> bool:
        """Check if path should skip authentication"""
        return any(path.startswith(exempt_path) for exempt_path in self.exempt_paths)
    
    async def _authenticate_request(self, request: Request) -> Optional[ApiKey]:
        """Authenticate request using API key"""
        
        # Try API key headers first
        api_key = request.headers.get(self.api_key_header)
        api_secret = request.headers.get(self.api_secret_header)
        
        if api_key and api_secret:
            return await self._validate_api_key_credentials(
                api_key, api_secret, request
            )
        
        # Try Bearer token (alternative authentication method)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            return await self._validate_bearer_token(token, request)
        
        # Try query parameters (less secure, but supported)
        api_key_param = request.query_params.get("api_key")
        api_secret_param = request.query_params.get("api_secret")
        
        if api_key_param and api_secret_param:
            logger.warning("API key authentication via query parameters - less secure")
            return await self._validate_api_key_credentials(
                api_key_param, api_secret_param, request
            )
        
        return None
    
    async def _validate_api_key_credentials(
        self,
        api_key: str,
        api_secret: str,
        request: Request
    ) -> Optional[ApiKey]:
        """Validate API key credentials"""
        
        try:
            # Get client information for security checks
            client_ip = self._get_client_ip(request)
            client_referer = request.headers.get("referer")
            
            # Validate with API key manager
            api_key_record = await self.api_key_manager.validate_api_key(
                api_key=api_key,
                api_key_secret=api_secret,
                request_ip=client_ip,
                request_referer=client_referer
            )
            
            if api_key_record:
                logger.debug(f"API key authenticated: {api_key_record.name} ({api_key_record.id})")
            
            return api_key_record
            
        except Exception as e:
            logger.error(f"API key validation error: {e}")
            return None
    
    async def _validate_bearer_token(self, token: str, request: Request) -> Optional[ApiKey]:
        """Validate Bearer token (alternative authentication)"""
        
        # For now, we'll treat bearer tokens as API keys
        # In production, this could validate JWT tokens or other token formats
        try:
            # Try to decode as JWT if it's a JWT token
            if '.' in token:
                return await self._validate_jwt_token(token, request)
            else:
                # Treat as API key
                return await self._validate_api_key_credentials(
                    token, "", request  # No secret for bearer tokens
                )
                
        except Exception as e:
            logger.error(f"Bearer token validation error: {e}")
            return None
    
    async def _validate_jwt_token(self, token: str, request: Request) -> Optional[ApiKey]:
        """Validate JWT token"""
        
        # This is a placeholder for JWT validation
        # In production, implement proper JWT validation with proper libraries
        try:
            import jwt
            from langflow.services.deps import get_settings_service
            
            settings = get_settings_service().settings
            
            # Decode JWT token
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=["HS256"]
            )
            
            # Extract API key ID from payload
            api_key_id = payload.get("api_key_id")
            if not api_key_id:
                return None
            
            # Get API key from database
            from langflow.services.database.models.api_key.crud import get_api_key_by_id
            api_key_record = await get_api_key_by_id(None, api_key_id)
            
            if api_key_record and api_key_record.status == "active":
                return api_key_record
                
        except Exception as e:
            logger.error(f"JWT validation error: {e}")
        
        return None
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        
        # Check for forwarded IP (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Use direct connection IP
        return request.client.host if request.client else "unknown"


class APIKeyPermissionMiddleware(BaseHTTPMiddleware):
    """API key permission validation middleware"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Permission requirements for different endpoints
        self.endpoint_permissions = {
            # Read operations
            "GET": {
                "/api/v1/flows": ["read"],
                "/api/v1/projects": ["read"],
                "/api/v1/variables": ["read"],
                "/api/v1/files": ["read"],
            },
            
            # Write operations
            "POST": {
                "/api/v1/flows": ["write"],
                "/api/v1/projects": ["write"],
                "/api/v1/variables": ["write"],
                "/api/v1/files": ["write"],
                "/api/v1/chat": ["write"],
            },
            
            # Update operations
            "PUT": {
                "/api/v1/flows": ["write"],
                "/api/v1/projects": ["write"],
                "/api/v1/variables": ["write"],
            },
            
            # Delete operations
            "DELETE": {
                "/api/v1/flows": ["write"],
                "/api/v1/projects": ["write"],
                "/api/v1/variables": ["write"],
                "/api/v1/files": ["write"],
            },
            
            # Admin operations
            "POST": {
                "/api/v1/users": ["admin"],
                "/api/v1/admin": ["admin"],
            }
        }
    
    async def dispatch(self, request: Request, call_next):
        """Process request with permission validation"""
        
        # Skip permission check if no API key in request
        if not hasattr(request.state, 'api_key'):
            return await call_next(request)
        
        # Check permissions
        if not await self._check_permissions(request):
            return JSONResponse(
                {"error": "Insufficient permissions"},
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        # Process request
        return await call_next(request)
    
    async def _check_permissions(self, request: Request) -> bool:
        """Check if API key has required permissions"""
        
        api_key = request.state.api_key
        method = request.method
        path = request.url.path
        
        # Get required permissions for this endpoint
        required_permissions = self._get_required_permissions(method, path)
        
        if not required_permissions:
            return True  # No specific permissions required
        
        # Check if API key has required permissions
        api_key_permissions = api_key.permissions or []
        
        return any(
            perm in api_key_permissions 
            for perm in required_permissions
        )
    
    def _get_required_permissions(self, method: str, path: str) -> list[str]:
        """Get required permissions for endpoint"""
        
        # Check method-specific permissions
        method_perms = self.endpoint_permissions.get(method, {})
        
        # Find matching path
        for endpoint_path, permissions in method_perms.items():
            if path.startswith(endpoint_path):
                return permissions
        
        # Default to read permission for GET requests
        if method == "GET":
            return ["read"]
        
        # Default to write permission for other methods
        return ["write"]


async def add_api_key_auth_middleware(app):
    """Add API key authentication middleware to application"""
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(APIKeyPermissionMiddleware)
    logger.info("API key authentication middleware added")