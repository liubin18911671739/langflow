"""Enhanced error handling middleware with circuit breaker, retry, and recovery mechanisms"""
import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import traceback
import uuid

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from langflow.services.cache.redis_cache import RedisCacheManager, CacheKeyPrefix, get_cache_manager
from langflow.services.deps import get_settings_service


class ErrorType(str, Enum):
    """Error types for classification"""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    SERVICE_UNAVAILABLE = "service_unavailable"
    DATABASE = "database"
    EXTERNAL_API = "external_api"
    INTERNAL_SERVER = "internal_server"
    TIMEOUT = "timeout"
    NETWORK = "network"


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service is back


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5      # Number of failures to open circuit
    recovery_timeout: int = 60      # Seconds before attempting recovery
    success_threshold: int = 3      # Successful requests to close circuit
    monitoring_window: int = 300    # Time window for failure counting


@dataclass
class RetryConfig:
    """Retry configuration"""
    max_attempts: int = 3
    initial_delay: float = 0.5      # Initial delay in seconds
    max_delay: float = 30.0         # Maximum delay between retries
    exponential_base: float = 2.0   # Base for exponential backoff
    jitter: bool = True             # Add random jitter to delays


class ErrorResponse(BaseModel):
    """Standardized error response model"""
    error: bool = True
    error_type: str
    message: str
    detail: Optional[str] = None
    code: Optional[str] = None
    timestamp: str
    request_id: str
    retry_after: Optional[int] = None
    help_url: Optional[str] = None


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Enhanced error handling middleware with circuit breaker and retry mechanisms"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings_service().settings
        self.cache_manager: Optional[RedisCacheManager] = None
        
        # Circuit breaker configurations per endpoint pattern
        self.circuit_configs = {
            "/api/v1/chat": CircuitBreakerConfig(failure_threshold=10, recovery_timeout=30),
            "/api/v1/flows": CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60),
            "/api/v1/billing": CircuitBreakerConfig(failure_threshold=3, recovery_timeout=120),
            "/api/v1/admin": CircuitBreakerConfig(failure_threshold=2, recovery_timeout=300),
            "default": CircuitBreakerConfig()
        }
        
        # Retry configurations per endpoint pattern
        self.retry_configs = {
            "/api/v1/chat": RetryConfig(max_attempts=2, initial_delay=0.1),
            "/api/v1/flows": RetryConfig(max_attempts=3, initial_delay=0.5),
            "/api/v1/billing": RetryConfig(max_attempts=3, initial_delay=1.0),
            "default": RetryConfig()
        }
        
        # Error message templates
        self.error_messages = {
            ErrorType.VALIDATION: "Invalid input data. Please check your request and try again.",
            ErrorType.AUTHENTICATION: "Authentication failed. Please check your credentials.",
            ErrorType.AUTHORIZATION: "Access denied. You don't have permission to perform this action.",
            ErrorType.NOT_FOUND: "The requested resource was not found.",
            ErrorType.RATE_LIMIT: "Too many requests. Please slow down and try again later.",
            ErrorType.SERVICE_UNAVAILABLE: "Service is temporarily unavailable. Please try again later.",
            ErrorType.DATABASE: "Database error occurred. Please try again later.",
            ErrorType.EXTERNAL_API: "External service error. Please try again later.",
            ErrorType.INTERNAL_SERVER: "An internal error occurred. Our team has been notified.",
            ErrorType.TIMEOUT: "Request timed out. Please try again.",
            ErrorType.NETWORK: "Network error occurred. Please check your connection.",
        }
        
        # Skip error handling for these paths
        self.skip_paths = [
            "/health",
            "/health_check", 
            "/api/v1/health",
            "/static/",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
        
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with comprehensive error handling"""
        # Skip error handling for certain paths
        if self._should_skip_error_handling(request.url.path):
            return await call_next(request)
        
        # Initialize cache manager if needed
        if not self.cache_manager:
            try:
                self.cache_manager = await get_cache_manager()
            except Exception as e:
                logger.error(f"Failed to initialize cache manager: {e}")
        
        # Generate request ID for tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Get endpoint configuration
        endpoint_pattern = self._get_endpoint_pattern(request.url.path)
        circuit_config = self._get_circuit_config(endpoint_pattern)
        retry_config = self._get_retry_config(endpoint_pattern)
        
        try:
            # Check circuit breaker state
            if not await self._check_circuit_breaker(endpoint_pattern, circuit_config):
                return self._create_error_response(
                    ErrorType.SERVICE_UNAVAILABLE,
                    "Service is temporarily unavailable due to high error rate",
                    request_id,
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    retry_after=circuit_config.recovery_timeout
                )
            
            # Execute request with retry mechanism
            response = await self._execute_with_retry(
                request, call_next, endpoint_pattern, retry_config, circuit_config, request_id
            )
            
            return response
            
        except Exception as e:
            # Record failure in circuit breaker
            await self._record_circuit_failure(endpoint_pattern, circuit_config)
            
            # Handle the error
            return await self._handle_error(e, request, request_id)
    
    async def _execute_with_retry(
        self, 
        request: Request, 
        call_next: Callable, 
        endpoint_pattern: str,
        retry_config: RetryConfig,
        circuit_config: CircuitBreakerConfig,
        request_id: str
    ) -> Response:
        """Execute request with retry logic"""
        last_exception = None
        
        for attempt in range(retry_config.max_attempts):
            try:
                # Execute the request
                start_time = time.time()
                response = await call_next(request)
                execution_time = time.time() - start_time
                
                # Check if response indicates success
                if response.status_code < 500:
                    # Record success for circuit breaker
                    await self._record_circuit_success(endpoint_pattern, circuit_config)
                    
                    # Add monitoring headers
                    response.headers["X-Request-ID"] = request_id
                    response.headers["X-Execution-Time"] = f"{execution_time:.3f}s"
                    response.headers["X-Retry-Attempt"] = str(attempt + 1)
                    
                    return response
                else:
                    # Server error, prepare for retry
                    last_exception = HTTPException(
                        status_code=response.status_code,
                        detail=f"Server error: {response.status_code}"
                    )
                    
            except Exception as e:
                last_exception = e
                logger.warning(f"Request attempt {attempt + 1} failed: {str(e)}")
            
            # Don't retry on the last attempt
            if attempt < retry_config.max_attempts - 1:
                delay = self._calculate_retry_delay(attempt, retry_config)
                logger.info(f"Retrying request after {delay:.2f}s delay (attempt {attempt + 1}/{retry_config.max_attempts})")
                await asyncio.sleep(delay)
        
        # All retries exhausted, record failure
        await self._record_circuit_failure(endpoint_pattern, circuit_config)
        
        # Raise the last exception
        if last_exception:
            raise last_exception
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Request failed after all retry attempts"
            )
    
    def _calculate_retry_delay(self, attempt: int, config: RetryConfig) -> float:
        """Calculate delay for retry with exponential backoff and jitter"""
        delay = config.initial_delay * (config.exponential_base ** attempt)
        delay = min(delay, config.max_delay)
        
        if config.jitter:
            import random
            # Add jitter (±25% of the delay)
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.1, delay)  # Minimum delay of 0.1 seconds
    
    async def _check_circuit_breaker(self, endpoint_pattern: str, config: CircuitBreakerConfig) -> bool:
        """Check circuit breaker state and decide whether to allow request"""
        if not self.cache_manager:
            return True  # Allow request if cache is not available
        
        try:
            # Get circuit state
            circuit_key = f"circuit:{endpoint_pattern}"
            circuit_data = await self.cache_manager.get(CacheKeyPrefix.METADATA, [circuit_key])
            
            if not circuit_data:
                # No circuit data, assume closed state
                return True
            
            state = circuit_data.get("state", CircuitState.CLOSED)
            failure_count = circuit_data.get("failure_count", 0)
            last_failure_time = circuit_data.get("last_failure_time", 0)
            success_count = circuit_data.get("success_count", 0)
            
            current_time = time.time()
            
            if state == CircuitState.CLOSED:
                # Normal operation
                return True
                
            elif state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if current_time - last_failure_time >= config.recovery_timeout:
                    # Transition to half-open state
                    circuit_data.update({
                        "state": CircuitState.HALF_OPEN,
                        "success_count": 0
                    })
                    await self.cache_manager.set(
                        CacheKeyPrefix.METADATA, 
                        [circuit_key], 
                        circuit_data, 
                        ttl=config.monitoring_window
                    )
                    return True
                else:
                    return False
                    
            elif state == CircuitState.HALF_OPEN:
                # Allow limited requests to test service health
                return True
                
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            return True  # Allow request on error
    
    async def _record_circuit_success(self, endpoint_pattern: str, config: CircuitBreakerConfig):
        """Record successful request for circuit breaker"""
        if not self.cache_manager:
            return
        
        try:
            circuit_key = f"circuit:{endpoint_pattern}"
            circuit_data = await self.cache_manager.get(CacheKeyPrefix.METADATA, [circuit_key])
            
            if not circuit_data:
                circuit_data = {
                    "state": CircuitState.CLOSED,
                    "failure_count": 0,
                    "success_count": 0,
                    "last_failure_time": 0
                }
            
            state = circuit_data.get("state", CircuitState.CLOSED)
            success_count = circuit_data.get("success_count", 0) + 1
            
            if state == CircuitState.HALF_OPEN:
                if success_count >= config.success_threshold:
                    # Close the circuit
                    circuit_data.update({
                        "state": CircuitState.CLOSED,
                        "failure_count": 0,
                        "success_count": 0,
                        "last_failure_time": 0
                    })
                    logger.info(f"Circuit breaker closed for {endpoint_pattern}")
                else:
                    circuit_data["success_count"] = success_count
            
            await self.cache_manager.set(
                CacheKeyPrefix.METADATA,
                [circuit_key],
                circuit_data,
                ttl=config.monitoring_window
            )
            
        except Exception as e:
            logger.error(f"Failed to record circuit success: {e}")
    
    async def _record_circuit_failure(self, endpoint_pattern: str, config: CircuitBreakerConfig):
        """Record failed request for circuit breaker"""
        if not self.cache_manager:
            return
        
        try:
            circuit_key = f"circuit:{endpoint_pattern}"
            circuit_data = await self.cache_manager.get(CacheKeyPrefix.METADATA, [circuit_key])
            
            if not circuit_data:
                circuit_data = {
                    "state": CircuitState.CLOSED,
                    "failure_count": 0,
                    "success_count": 0,
                    "last_failure_time": 0
                }
            
            current_time = time.time()
            state = circuit_data.get("state", CircuitState.CLOSED)
            failure_count = circuit_data.get("failure_count", 0) + 1
            
            circuit_data.update({
                "failure_count": failure_count,
                "last_failure_time": current_time,
                "success_count": 0
            })
            
            # Check if we should open the circuit
            if state != CircuitState.OPEN and failure_count >= config.failure_threshold:
                circuit_data["state"] = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened for {endpoint_pattern} after {failure_count} failures")
            elif state == CircuitState.HALF_OPEN:
                # Go back to open state
                circuit_data["state"] = CircuitState.OPEN
                logger.warning(f"Circuit breaker reopened for {endpoint_pattern}")
            
            await self.cache_manager.set(
                CacheKeyPrefix.METADATA,
                [circuit_key],
                circuit_data,
                ttl=config.monitoring_window
            )
            
        except Exception as e:
            logger.error(f"Failed to record circuit failure: {e}")
    
    async def _handle_error(self, error: Exception, request: Request, request_id: str) -> JSONResponse:
        """Handle and classify errors, returning user-friendly responses"""
        error_type, status_code, user_message, detail = self._classify_error(error)
        
        # Log the error with context
        logger.error(
            f"Request error: {str(error)} | "
            f"Type: {error_type} | "
            f"Path: {request.url.path} | "
            f"Method: {request.method} | "
            f"Request ID: {request_id} | "
            f"User Agent: {request.headers.get('user-agent', 'Unknown')} | "
            f"Traceback: {traceback.format_exc()}"
        )
        
        return self._create_error_response(
            error_type, user_message, request_id, status_code, detail
        )
    
    def _classify_error(self, error: Exception) -> tuple[ErrorType, int, str, Optional[str]]:
        """Classify error and return appropriate response information"""
        if isinstance(error, HTTPException):
            if error.status_code == 400:
                return ErrorType.VALIDATION, error.status_code, self.error_messages[ErrorType.VALIDATION], str(error.detail)
            elif error.status_code == 401:
                return ErrorType.AUTHENTICATION, error.status_code, self.error_messages[ErrorType.AUTHENTICATION], None
            elif error.status_code == 403:
                return ErrorType.AUTHORIZATION, error.status_code, self.error_messages[ErrorType.AUTHORIZATION], None
            elif error.status_code == 404:
                return ErrorType.NOT_FOUND, error.status_code, self.error_messages[ErrorType.NOT_FOUND], None
            elif error.status_code == 429:
                return ErrorType.RATE_LIMIT, error.status_code, self.error_messages[ErrorType.RATE_LIMIT], None
            elif error.status_code >= 500:
                return ErrorType.INTERNAL_SERVER, error.status_code, self.error_messages[ErrorType.INTERNAL_SERVER], None
        
        # Check for specific exception types
        error_str = str(error).lower()
        
        if "timeout" in error_str or "timed out" in error_str:
            return ErrorType.TIMEOUT, 408, self.error_messages[ErrorType.TIMEOUT], str(error)
        elif "connection" in error_str or "network" in error_str:
            return ErrorType.NETWORK, 503, self.error_messages[ErrorType.NETWORK], str(error)
        elif "database" in error_str or "sql" in error_str:
            return ErrorType.DATABASE, 503, self.error_messages[ErrorType.DATABASE], None
        elif "api" in error_str and ("external" in error_str or "third" in error_str):
            return ErrorType.EXTERNAL_API, 503, self.error_messages[ErrorType.EXTERNAL_API], None
        
        # Default to internal server error
        return ErrorType.INTERNAL_SERVER, 500, self.error_messages[ErrorType.INTERNAL_SERVER], None
    
    def _create_error_response(
        self, 
        error_type: ErrorType, 
        message: str, 
        request_id: str,
        status_code: int,
        detail: Optional[str] = None,
        retry_after: Optional[int] = None
    ) -> JSONResponse:
        """Create standardized error response"""
        
        error_response = ErrorResponse(
            error_type=error_type.value,
            message=message,
            detail=detail,
            code=f"E{status_code}_{error_type.value.upper()}",
            timestamp=datetime.utcnow().isoformat(),
            request_id=request_id,
            retry_after=retry_after,
            help_url=f"https://docs.langflow.org/errors#{error_type.value.replace('_', '-')}"
        )
        
        headers = {"X-Request-ID": request_id}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        
        return JSONResponse(
            status_code=status_code,
            content=error_response.dict(),
            headers=headers
        )
    
    def _should_skip_error_handling(self, path: str) -> bool:
        """Check if path should skip error handling"""
        return any(path.startswith(skip_path) for skip_path in self.skip_paths)
    
    def _get_endpoint_pattern(self, path: str) -> str:
        """Get endpoint pattern for configuration lookup"""
        for pattern in self.circuit_configs.keys():
            if pattern != "default" and path.startswith(pattern):
                return pattern
        return "default"
    
    def _get_circuit_config(self, pattern: str) -> CircuitBreakerConfig:
        """Get circuit breaker configuration for endpoint pattern"""
        return self.circuit_configs.get(pattern, self.circuit_configs["default"])
    
    def _get_retry_config(self, pattern: str) -> RetryConfig:
        """Get retry configuration for endpoint pattern"""
        return self.retry_configs.get(pattern, self.retry_configs["default"])


async def add_error_handling_middleware(app):
    """Add error handling middleware to the application"""
    app.add_middleware(ErrorHandlingMiddleware)
    logger.info("Error handling middleware added with circuit breaker and retry capabilities")