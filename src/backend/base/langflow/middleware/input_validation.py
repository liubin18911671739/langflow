"""Input validation middleware for security hardening"""
import json
import re
from typing import Dict, List, Optional, Set
from urllib.parse import unquote
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Input validation middleware to prevent injection attacks"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # SQL injection patterns
        self.sql_injection_patterns = [
            r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|UNION|EXEC|EXECUTE)\b",
            r"(?i)\b(OR\s+\d+\s*=\s*\d+|AND\s+\d+\s*=\s*\d+)\b",
            r"(?i)\b(WAITFOR\s+DELAY|SLEEP\()\b",
            r"(?i)\b(XP_|SP_)\w+\b",
            r"(?i);.*--",
            r"(?i)/\*.*\*/",
        ]
        
        # XSS patterns
        self.xss_patterns = [
            r"<script.*?>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",
            r"<iframe.*?>",
            r"<object.*?>",
            r"<embed.*?>",
            r"<applet.*?>",
            r"<meta.*?>",
            r"expression\(",
            r"vbscript:",
            r"onload\s*=",
            r"onerror\s*=",
        ]
        
        # Command injection patterns
        self.command_injection_patterns = [
            r"(?i)\b(system|exec|eval|shell_exec|passthru|proc_open|popen)\b\s*\(",
            r"(?i)[;&|`$(){}[\]]",
            r"(?i)\b(rm|ls|cat|pwd|whoami|id|ps|kill)\b",
            r"(?i)\b(nc|netcat|curl|wget|telnet)\b",
            r"(?i)\b(>|>>|<|<<)\s+\w+",
        ]
        
        # Path traversal patterns
        self.path_traversal_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"/etc/",
            r"/proc/",
            r"/sys/",
            r"/dev/",
            r"~/",
            r"%2e%2e%2f",
            r"%2e%2e\\",
        ]
        
        # File inclusion patterns
        self.file_inclusion_patterns = [
            r"(?i)\b(include|require|include_once|require_once)\b\s*\(",
            r"(?i)\b(file_get_contents|file_put_contents|fopen|readfile)\b\s*\(",
            r"(?i)\b(php://|filter://|expect://|data://)\w+",
        ]
        
        # Size limits
        self.max_query_string_length = 2048
        self.max_header_length = 8192
        self.max_body_size = 10 * 1024 * 1024  # 10MB
        
        # Paths that require stricter validation
        self.strict_validation_paths = {
            "/api/v1/login",
            "/api/v1/register",
            "/api/v1/users",
            "/api/v1/api_key",
        }
        
        # Sensitive fields that should never contain certain patterns
        self.sensitive_fields = {
            "password", "api_key", "token", "secret", "credential", "auth"
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with input validation"""
        
        # Validate request basics
        await self._validate_request_basics(request)
        
        # Validate query parameters
        await self._validate_query_params(request)
        
        # Validate headers
        await self._validate_headers(request)
        
        # Validate request body for POST/PUT/PATCH
        if request.method in ("POST", "PUT", "PATCH"):
            await self._validate_request_body(request)
        
        # Process request
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(f"Request processing error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    
    async def _validate_request_basics(self, request: Request):
        """Validate basic request properties"""
        # Check HTTP method
        if request.method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="Method not allowed"
            )
        
        # Check URL length
        if len(str(request.url)) > 2048:
            raise HTTPException(
                status_code=status.HTTP_414_REQUEST_URI_TOO_LONG,
                detail="Request URI too long"
            )
    
    async def _validate_query_params(self, request: Request):
        """Validate query parameters"""
        query_string = str(request.query_params)
        
        # Check query string length
        if len(query_string) > self.max_query_string_length:
            raise HTTPException(
                status_code=status.HTTP_414_REQUEST_URI_TOO_LONG,
                detail="Query string too long"
            )
        
        # Validate each parameter
        for key, value in request.query_params.multi_items():
            # Decode URL-encoded values
            decoded_key = unquote(key)
            decoded_value = unquote(value)
            
            # Check for injection patterns
            if self._contains_injection_patterns(decoded_key) or self._contains_injection_patterns(decoded_value):
                logger.warning(f"Potential injection attempt in query parameter: {key}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid input detected"
                )
            
            # Additional validation for sensitive fields
            if decoded_key.lower() in self.sensitive_fields:
                await self._validate_sensitive_field(decoded_key, decoded_value, request.url.path)
    
    async def _validate_headers(self, request: Request):
        """Validate request headers"""
        for name, value in request.headers.items():
            # Check header length
            if len(name) > 1024 or len(value) > self.max_header_length:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Header too long"
                )
            
            # Skip validation for certain headers
            if name.lower() in ("authorization", "cookie", "user-agent"):
                continue
            
            # Check for injection patterns
            if self._contains_injection_patterns(name) or self._contains_injection_patterns(value):
                logger.warning(f"Potential injection attempt in header: {name}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid input detected"
                )
    
    async def _validate_request_body(self, request: Request):
        """Validate request body"""
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request entity too large"
            )
        
        # Read and validate body
        try:
            body = await request.body()
            
            # Skip empty body
            if not body:
                return
            
            # Parse as JSON if content type indicates
            content_type = request.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                await self._validate_json_body(body, request.url.path)
            elif "application/x-www-form-urlencoded" in content_type:
                await self._validate_form_data(body.decode("utf-8", errors="ignore"), request.url.path)
            
        except Exception as e:
            logger.error(f"Body validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request body"
            )
    
    async def _validate_json_body(self, body: bytes, path: str):
        """Validate JSON request body"""
        try:
            data = json.loads(body.decode("utf-8", errors="ignore"))
            
            # Recursively validate JSON structure
            await self._validate_json_structure(data, path)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in request body: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON format"
            )
    
    async def _validate_json_structure(self, data, path: str, parent_key: str = ""):
        """Recursively validate JSON structure"""
        if isinstance(data, dict):
            for key, value in data.items():
                current_key = f"{parent_key}.{key}" if parent_key else key
                
                # Validate key
                if self._contains_injection_patterns(key):
                    logger.warning(f"Potential injection attempt in JSON key: {current_key}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid input detected"
                    )
                
                # Validate value
                if isinstance(value, (str, int, float, bool)):
                    if isinstance(value, str) and self._contains_injection_patterns(value):
                        logger.warning(f"Potential injection attempt in JSON value: {current_key}")
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid input detected"
                        )
                    
                    # Additional validation for sensitive fields
                    if key.lower() in self.sensitive_fields:
                        await self._validate_sensitive_field(current_key, str(value), path)
                
                # Recursively validate nested structures
                elif isinstance(value, (dict, list)):
                    await self._validate_json_structure(value, path, current_key)
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_key = f"{parent_key}[{i}]"
                await self._validate_json_structure(item, path, current_key)
    
    async def _validate_form_data(self, form_data: str, path: str):
        """Validate form data"""
        try:
            # Parse form data
            pairs = form_data.split("&")
            for pair in pairs:
                if "=" not in pair:
                    continue
                
                key, value = pair.split("=", 1)
                decoded_key = unquote(key)
                decoded_value = unquote(value)
                
                # Check for injection patterns
                if self._contains_injection_patterns(decoded_key) or self._contains_injection_patterns(decoded_value):
                    logger.warning(f"Potential injection attempt in form data: {decoded_key}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid input detected"
                    )
                
                # Additional validation for sensitive fields
                if decoded_key.lower() in self.sensitive_fields:
                    await self._validate_sensitive_field(decoded_key, decoded_value, path)
        
        except Exception as e:
            logger.error(f"Form data validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid form data"
            )
    
    async def _validate_sensitive_field(self, field_name: str, field_value: str, path: str):
        """Validate sensitive fields with stricter rules"""
        # Stricter validation for sensitive paths
        if path in self.strict_validation_paths:
            # Password strength validation
            if "password" in field_name.lower():
                if len(field_value) < 8:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Password must be at least 8 characters long"
                    )
                
                # Check for common weak passwords
                weak_passwords = ["password", "123456", "qwerty", "admin", "letmein"]
                if field_value.lower() in weak_passwords:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Password is too weak"
                    )
            
            # API key format validation
            if "api_key" in field_name.lower() or "token" in field_name.lower():
                if not re.match(r'^[a-zA-Z0-9\-_]{16,}$', field_value):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid API key format"
                    )
    
    def _contains_injection_patterns(self, input_str: str) -> bool:
        """Check if input contains injection patterns"""
        if not isinstance(input_str, str):
            return False
        
        # Check all pattern types
        all_patterns = (
            self.sql_injection_patterns +
            self.xss_patterns +
            self.command_injection_patterns +
            self.path_traversal_patterns +
            self.file_inclusion_patterns
        )
        
        for pattern in all_patterns:
            if re.search(pattern, input_str):
                return True
        
        return False


async def add_input_validation_middleware(app):
    """Add input validation middleware to application"""
    app.add_middleware(InputValidationMiddleware)
    logger.info("Input validation middleware added")