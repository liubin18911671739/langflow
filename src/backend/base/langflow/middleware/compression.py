"""Request compression middleware for performance optimization"""
import gzip
import zlib
import io
from typing import Optional, Dict, Any, List
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import MutableHeaders
from loguru import logger
from pydantic import BaseModel, Field
import time


class CompressionConfig(BaseModel):
    """Configuration for request compression"""
    enable_compression: bool = Field(default=True, description="Enable compression")
    min_size_to_compress: int = Field(default=1024, description="Minimum size to compress in bytes")
    compression_level: int = Field(default=6, ge=1, le=9, description="Compression level")
    enable_decompression: bool = Field(default=True, description="Enable request decompression")
    supported_algorithms: List[str] = Field(
        default=["gzip", "deflate"], 
        description="Supported compression algorithms"
    )
    compressible_content_types: List[str] = Field(
        default=[
            "application/json",
            "application/xml",
            "text/xml",
            "text/html",
            "text/plain",
            "text/css",
            "text/javascript",
            "application/javascript"
        ],
        description="Content types to compress"
    )
    excluded_paths: List[str] = Field(
        default=[
            "/health",
            "/metrics",
            "/static/",
            "/docs",
            "/redoc"
        ],
        description="Paths to exclude from compression"
    )


class CompressionMetrics(BaseModel):
    """Compression performance metrics"""
    total_requests: int = 0
    compressed_responses: int = 0
    compressed_requests: int = 0
    total_original_size: int = 0
    total_compressed_size: int = 0
    compression_ratio: float = 0.0
    average_compression_time: float = 0.0


class CompressionMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response compression"""
    
    def __init__(self, app, config: CompressionConfig):
        super().__init__(app)
        self.config = config
        self.metrics = CompressionMetrics()
    
    async def dispatch(self, request: Request, call_next):
        """Process request with compression"""
        start_time = time.time()
        
        # Skip compression for excluded paths
        if self._should_skip_compression(request.url.path):
            return await call_next(request)
        
        # Decompress request body if needed
        decompressed_request = await self._decompress_request(request)
        
        # Process request
        response = await call_next(decompressed_request)
        
        # Compress response if needed
        compressed_response = await self._compress_response(response)
        
        # Update metrics
        self._update_metrics(start_time)
        
        return compressed_response
    
    def _should_skip_compression(self, path: str) -> bool:
        """Check if path should be skipped from compression"""
        return any(path.startswith(excluded_path) for excluded_path in self.config.excluded_paths)
    
    async def _decompress_request(self, request: Request) -> Request:
        """Decompress request body if compressed"""
        if not self.config.enable_decompression:
            return request
        
        # Check content encoding
        content_encoding = request.headers.get("content-encoding", "").lower()
        
        if content_encoding not in self.config.supported_algorithms:
            return request
        
        # Read and decompress body
        try:
            body = await request.body()
            
            if content_encoding == "gzip":
                decompressed = gzip.decompress(body)
            elif content_encoding == "deflate":
                decompressed = zlib.decompress(body)
            else:
                return request
            
            # Create new request with decompressed body
            scope = request.scope.copy()
            scope["body"] = decompressed
            
            # Remove content-encoding header
            headers = MutableHeaders(request.headers)
            if "content-encoding" in headers:
                del headers["content-encoding"]
            
            # Update content-length
            if "content-length" in headers:
                headers["content-length"] = str(len(decompressed))
            
            scope["headers"] = list(headers.items())
            
            # Update metrics
            self.metrics.compressed_requests += 1
            self.metrics.total_original_size += len(body)
            self.metrics.total_compressed_size += len(decompressed)
            
            return Request(scope, receive=request.receive)
            
        except Exception as e:
            logger.error(f"Request decompression error: {e}")
            return request
    
    async def _compress_response(self, response: Response) -> Response:
        """Compress response if needed"""
        if not self.config.enable_compression:
            return response
        
        # Check if response should be compressed
        if not self._should_compress_response(response):
            return response
        
        # Get response body
        try:
            if hasattr(response, 'body'):
                body = response.body
            elif hasattr(response, 'render'):
                body = await response.render()
            else:
                return response
            
            # Check size
            if len(body) < self.config.min_size_to_compress:
                return response
            
            # Compress body
            compressed_body = await self._compress_body(body)
            
            # Only use compressed version if it's smaller
            if len(compressed_body) >= len(body):
                return response
            
            # Create new response with compressed body
            if isinstance(response, JSONResponse):
                compressed_response = JSONResponse(
                    content=response.body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    background=response.background
                )
            else:
                compressed_response = Response(
                    content=compressed_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                    background=response.background
                )
            
            # Add compression headers
            compressed_response.headers["content-encoding"] = "gzip"
            compressed_response.headers["content-length"] = str(len(compressed_body))
            
            # Remove existing content-length
            if "content-length" in compressed_response.headers:
                del compressed_response.headers["content-length"]
            
            # Update metrics
            self.metrics.compressed_responses += 1
            self.metrics.total_original_size += len(body)
            self.metrics.total_compressed_size += len(compressed_body)
            
            return compressed_response
            
        except Exception as e:
            logger.error(f"Response compression error: {e}")
            return response
    
    def _should_compress_response(self, response: Response) -> bool:
        """Check if response should be compressed"""
        # Check content type
        content_type = response.headers.get("content-type", "").lower()
        
        if not any(
            content_type.startswith(compressible_type) 
            for compressible_type in self.config.compressible_content_types
        ):
            return False
        
        # Check if already compressed
        if "content-encoding" in response.headers:
            return False
        
        # Check status code
        if response.status_code not in [200, 201, 202]:
            return False
        
        return True
    
    async def _compress_body(self, body: bytes) -> bytes:
        """Compress response body"""
        start_time = time.time()
        
        try:
            # Use gzip compression
            compressed = gzip.compress(body, compresslevel=self.config.compression_level)
            
            # Update compression time metrics
            compression_time = (time.time() - start_time) * 1000
            
            if self.metrics.total_requests == 0:
                self.metrics.average_compression_time = compression_time
            else:
                self.metrics.average_compression_time = (
                    (self.metrics.average_compression_time * self.metrics.total_requests + compression_time) 
                    / (self.metrics.total_requests + 1)
                )
            
            return compressed
            
        except Exception as e:
            logger.error(f"Body compression error: {e}")
            return body
    
    def _update_metrics(self, start_time: float):
        """Update compression metrics"""
        self.metrics.total_requests += 1
        
        # Calculate compression ratio
        if self.metrics.total_original_size > 0:
            self.metrics.compression_ratio = (
                1 - (self.metrics.total_compressed_size / self.metrics.total_original_size)
            )
    
    def get_metrics(self) -> CompressionMetrics:
        """Get compression metrics"""
        return self.metrics


class AdaptiveCompressionMiddleware(BaseHTTPMiddleware):
    """Adaptive compression middleware based on network conditions"""
    
    def __init__(self, app, config: CompressionConfig):
        super().__init__(app)
        self.config = config
        self.client_compression_stats: Dict[str, Dict] = {}
    
    async def dispatch(self, request: Request, call_next):
        """Process request with adaptive compression"""
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Get client compression stats
        client_stats = self._get_client_stats(client_id)
        
        # Decide whether to compress based on client stats
        should_compress = self._should_compress_for_client(client_stats, request)
        
        if should_compress:
            # Use standard compression middleware
            compression_middleware = CompressionMiddleware(self.app, self.config)
            return await compression_middleware.dispatch(request, call_next)
        else:
            # Skip compression
            return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier"""
        # Use IP address as client identifier
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        return request.client.host if request.client else "unknown"
    
    def _get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get or create client compression stats"""
        if client_id not in self.client_compression_stats:
            self.client_compression_stats[client_id] = {
                "requests_count": 0,
                "compression_ratio": 0.0,
                "avg_compression_time": 0.0,
                "network_speed": "unknown",  # Could be detected
                "last_seen": None
            }
        
        return self.client_compression_stats[client_id]
    
    def _should_compress_for_client(self, client_stats: Dict[str, Any], request: Request) -> bool:
        """Decide whether to compress for this client"""
        # Check client's network speed (simplified)
        user_agent = request.headers.get("user-agent", "").lower()
        
        # Mobile clients might benefit more from compression
        is_mobile = any(
            mobile in user_agent 
            for mobile in ["mobile", "android", "iphone", "ipad"]
        )
        
        # Check if client has slow network
        has_slow_network = (
            client_stats.get("network_speed") == "slow" or
            client_stats.get("compression_ratio", 0) > 0.3  # Good compression ratio
        )
        
        # Always compress for mobile or slow networks
        if is_mobile or has_slow_network:
            return True
        
        # For fast networks, only compress large responses
        if client_stats.get("network_speed") == "fast":
            # Check accept-encoding header
            accept_encoding = request.headers.get("accept-encoding", "")
            return "gzip" in accept_encoding.lower()
        
        # Default to compress
        return True


class CompressionMiddlewareFactory:
    """Factory for creating compression middleware"""
    
    @staticmethod
    def create_standard_compression(config: CompressionConfig) -> CompressionMiddleware:
        """Create standard compression middleware"""
        return CompressionMiddleware(None, config)
    
    @staticmethod
    def create_adaptive_compression(config: CompressionConfig) -> AdaptiveCompressionMiddleware:
        """Create adaptive compression middleware"""
        return AdaptiveCompressionMiddleware(None, config)
    
    @staticmethod
    def create_optimal_compression(config: CompressionConfig) -> BaseHTTPMiddleware:
        """Create optimal compression middleware based on configuration"""
        if config.enable_compression:
            # Use adaptive compression for better performance
            return AdaptiveCompressionMiddleware(None, config)
        else:
            # Return no-op middleware
            class NoOpMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    return await call_next(request)
            
            return NoOpMiddleware(None)


# Global compression middleware instance
_compression_middleware: Optional[BaseHTTPMiddleware] = None


def get_compression_middleware(config: Optional[CompressionConfig] = None) -> BaseHTTPMiddleware:
    """Get global compression middleware instance"""
    global _compression_middleware
    if _compression_middleware is None:
        config = config or CompressionConfig()
        _compression_middleware = CompressionMiddlewareFactory.create_optimal_compression(config)
    return _compression_middleware


# Decorator for compressing function responses
def compress_response(min_size: int = 1024):
    """Decorator to compress function responses"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Compress if result is large enough
            if isinstance(result, (str, bytes, dict)) and len(str(result)) > min_size:
                config = CompressionConfig()
                middleware = CompressionMiddlewareFactory.create_standard_compression(config)
                
                # Create a mock response
                from fastapi import Response
                response = Response(content=result)
                
                # Compress the response
                compressed_response = await middleware._compress_response(response)
                
                # Return compressed content
                return compressed_response.body
            
            return result
        return wrapper
    return decorator