"""Enhanced Redis caching strategy for Langflow performance optimization"""
import json
import pickle
import hashlib
import asyncio
from typing import Any, Optional, Dict, List, Union, Callable
from datetime import datetime, timedelta
from functools import wraps
from enum import Enum
import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError
from loguru import logger
from pydantic import BaseModel, Field

from langflow.services.deps import get_settings_service


class CacheKeyPrefix(str, Enum):
    """Cache key prefixes for different data types"""
    FLOW = "flow"
    COMPONENT = "component"
    USER = "user"
    PROJECT = "project"
    SESSION = "session"
    API_KEY = "api_key"
    QUERY = "query"
    TEMPLATE = "template"
    SETTINGS = "settings"
    METADATA = "metadata"


class CacheStrategy(str, Enum):
    """Caching strategies"""
    SIMPLE = "simple"           # Simple key-value caching
    TTL = "ttl"                 # Time-based expiration
    LRU = "lru"                 # Least recently used
    LFU = "lfu"                 # Least frequently used
    WRITE_THROUGH = "write_through"  # Write through cache
    WRITE_BACK = "write_back"       # Write back cache
    CACHE_ASIDE = "cache_aside"     # Cache aside pattern


class CacheConfig(BaseModel):
    """Configuration for cache behavior"""
    default_ttl: int = Field(default=3600, ge=1, description="Default TTL in seconds")
    max_memory: str = Field(default="512mb", description="Maximum memory usage")
    eviction_policy: str = Field(default="allkeys-lru", description="Redis eviction policy")
    connection_pool_size: int = Field(default=10, ge=1, description="Connection pool size")
    retry_attempts: int = Field(default=3, ge=0, description="Retry attempts for failed operations")
    retry_delay: float = Field(default=0.1, ge=0.01, description="Delay between retries")
    compression_enabled: bool = Field(default=True, description="Enable value compression")
    serialization_method: str = Field(default="pickle", description="Serialization method")


class CacheStats(BaseModel):
    """Cache performance statistics"""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    hit_rate: float = 0.0
    memory_usage: int = 0
    keys_count: int = 0
    avg_response_time: float = 0.0


class RedisCacheManager:
    """Enhanced Redis cache manager with multiple strategies"""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.redis_client: Optional[redis.Redis] = None
        self.is_connected = False
        self.stats = CacheStats()
        self._local_cache: Dict[str, Any] = {}  # Fallback local cache
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            settings = get_settings_service().settings
            
            # Parse Redis URL
            redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379/0')
            
            # Create Redis client with optimized settings
            self.redis_client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False,
                max_connections=self.config.connection_pool_size,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
            )
            
            # Test connection
            await self.redis_client.ping()
            self.is_connected = True
            
            # Configure Redis settings
            await self._configure_redis()
            
            logger.info("Redis cache manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            self.is_connected = False
            # Fall back to local cache
            logger.warning("Using local cache as fallback")
    
    async def _configure_redis(self):
        """Configure Redis settings"""
        if not self.is_connected or not self.redis_client:
            return
            
        try:
            # Set memory policy
            await self.redis_client.config_set("maxmemory-policy", self.config.eviction_policy)
            
            # Set memory limit
            await self.redis_client.config_set("maxmemory", self.config.max_memory)
            
            # Enable compression for large values
            await self.redis_client.config_set("hash-max-ziplist-entries", 512)
            await self.redis_client.config_set("hash-max-ziplist-value", 64)
            
            logger.info("Redis configured for optimal performance")
            
        except Exception as e:
            logger.error(f"Failed to configure Redis: {e}")
    
    def _generate_key(self, prefix: CacheKeyPrefix, key_parts: List[Any]) -> str:
        """Generate consistent cache key"""
        key_string = ":".join(str(part) for part in key_parts)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"{prefix.value}:{key_hash}"
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for storage"""
        try:
            if self.config.serialization_method == "pickle":
                serialized = pickle.dumps(value)
            elif self.config.serialization_method == "json":
                serialized = json.dumps(value, default=str).encode()
            else:
                serialized = str(value).encode()
            
            # Compress if enabled and value is large
            if self.config.compression_enabled and len(serialized) > 1024:
                import zlib
                serialized = zlib.compress(serialized)
            
            return serialized
            
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            return str(value).encode()
    
    def _deserialize_value(self, serialized: bytes) -> Any:
        """Deserialize value from storage"""
        try:
            # Decompress if needed
            if self.config.compression_enabled and len(serialized) > 1024:
                try:
                    import zlib
                    serialized = zlib.decompress(serialized)
                except:
                    pass  # Not compressed
            
            if self.config.serialization_method == "pickle":
                return pickle.loads(serialized)
            elif self.config.serialization_method == "json":
                return json.loads(serialized.decode())
            else:
                return serialized.decode()
                
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            return serialized.decode()
    
    async def get(self, prefix: CacheKeyPrefix, key_parts: List[Any]) -> Optional[Any]:
        """Get value from cache"""
        key = self._generate_key(prefix, key_parts)
        
        async with self._lock:
            start_time = asyncio.get_event_loop().time()
            
            try:
                # Try Redis first
                if self.is_connected and self.redis_client:
                    value = await self.redis_client.get(key)
                    if value is not None:
                        deserialized = self._deserialize_value(value)
                        self.stats.hits += 1
                        self._update_stats(start_time)
                        return deserialized
                
                # Fallback to local cache
                if key in self._local_cache:
                    value, expiry = self._local_cache[key]
                    if expiry > datetime.utcnow():
                        self.stats.hits += 1
                        self._update_stats(start_time)
                        return value
                    else:
                        del self._local_cache[key]
                
                self.stats.misses += 1
                self._update_stats(start_time)
                return None
                
            except Exception as e:
                logger.error(f"Cache get error: {e}")
                self.stats.misses += 1
                self._update_stats(start_time)
                return None
    
    async def set(
        self, 
        prefix: CacheKeyPrefix, 
        key_parts: List[Any], 
        value: Any, 
        ttl: Optional[int] = None,
        strategy: CacheStrategy = CacheStrategy.TTL
    ) -> bool:
        """Set value in cache"""
        key = self._generate_key(prefix, key_parts)
        serialized = self._serialize_value(value)
        
        if ttl is None:
            ttl = self.config.default_ttl
        
        async with self._lock:
            try:
                # Try Redis first
                if self.is_connected and self.redis_client:
                    if strategy == CacheStrategy.TTL:
                        await self.redis_client.setex(key, ttl, serialized)
                    else:
                        await self.redis_client.set(key, serialized)
                    
                    # Update local cache as backup
                    expiry = datetime.utcnow() + timedelta(seconds=ttl)
                    self._local_cache[key] = (value, expiry)
                    
                    # Clean up local cache if too large
                    if len(self._local_cache) > 1000:
                        self._cleanup_local_cache()
                    
                    return True
                
                # Fallback to local cache only
                expiry = datetime.utcnow() + timedelta(seconds=ttl)
                self._local_cache[key] = (value, expiry)
                
                # Clean up local cache if too large
                if len(self._local_cache) > 1000:
                    self._cleanup_local_cache()
                
                return True
                
            except Exception as e:
                logger.error(f"Cache set error: {e}")
                # Still try to set in local cache
                expiry = datetime.utcnow() + timedelta(seconds=ttl)
                self._local_cache[key] = (value, expiry)
                return False
    
    async def delete(self, prefix: CacheKeyPrefix, key_parts: List[Any]) -> bool:
        """Delete value from cache"""
        key = self._generate_key(prefix, key_parts)
        
        async with self._lock:
            try:
                # Try Redis first
                if self.is_connected and self.redis_client:
                    await self.redis_client.delete(key)
                
                # Remove from local cache
                if key in self._local_cache:
                    del self._local_cache[key]
                
                return True
                
            except Exception as e:
                logger.error(f"Cache delete error: {e}")
                # Still try to remove from local cache
                if key in self._local_cache:
                    del self._local_cache[key]
                return False
    
    async def clear_pattern(self, prefix: CacheKeyPrefix, pattern: str = "*") -> int:
        """Clear all keys matching pattern"""
        try:
            if self.is_connected and self.redis_client:
                # Find matching keys
                keys = []
                async for key in self.redis_client.scan_iter(match=f"{prefix.value}:{pattern}"):
                    keys.append(key)
                
                if keys:
                    await self.redis_client.delete(*keys)
                
                # Clear from local cache
                local_pattern = f"{prefix.value}:*"
                keys_to_remove = [k for k in self._local_cache.keys() if k.startswith(local_pattern)]
                for key in keys_to_remove:
                    del self._local_cache[key]
                
                return len(keys)
            
            return 0
            
        except Exception as e:
            logger.error(f"Cache clear pattern error: {e}")
            return 0
    
    async def get_stats(self) -> CacheStats:
        """Get cache statistics"""
        try:
            if self.is_connected and self.redis_client:
                info = await self.redis_client.info()
                self.stats.memory_usage = info.get('used_memory', 0)
                self.stats.keys_count = info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0)
            
            # Calculate hit rate
            if self.stats.total_requests > 0:
                self.stats.hit_rate = self.stats.hits / self.stats.total_requests
            
            return self.stats
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return self.stats
    
    def _update_stats(self, start_time: float):
        """Update cache statistics"""
        self.stats.total_requests += 1
        response_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        # Update average response time
        if self.stats.total_requests == 1:
            self.stats.avg_response_time = response_time
        else:
            self.stats.avg_response_time = (
                (self.stats.avg_response_time * (self.stats.total_requests - 1) + response_time) 
                / self.stats.total_requests
            )
    
    def _cleanup_local_cache(self):
        """Clean up expired entries from local cache"""
        current_time = datetime.utcnow()
        expired_keys = [
            key for key, (_, expiry) in self._local_cache.items() 
            if expiry <= current_time
        ]
        
        for key in expired_keys:
            del self._local_cache[key]
        
        # Keep only the most recent 500 entries
        if len(self._local_cache) > 500:
            sorted_items = sorted(
                self._local_cache.items(), 
                key=lambda x: x[1][1],  # Sort by expiry time
                reverse=True
            )
            self._local_cache = dict(sorted_items[:500])
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False


# Cache decorator
def cache_result(
    prefix: CacheKeyPrefix,
    ttl: Optional[int] = None,
    key_func: Optional[Callable] = None,
    strategy: CacheStrategy = CacheStrategy.TTL
):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                key_parts = key_func(*args, **kwargs)
            else:
                key_parts = [func.__name__, str(args), str(sorted(kwargs.items()))]
            
            # Try to get from cache
            cache_manager = get_cache_manager()
            cached_result = await cache_manager.get(prefix, key_parts)
            
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set(prefix, key_parts, result, ttl, strategy)
            
            return result
        
        return wrapper
    return decorator


# Global cache manager instance
_cache_manager: Optional[RedisCacheManager] = None


async def get_cache_manager() -> RedisCacheManager:
    """Get global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = RedisCacheManager()
        await _cache_manager.initialize()
    return _cache_manager


async def initialize_cache():
    """Initialize cache manager"""
    await get_cache_manager()


async def close_cache():
    """Close cache manager"""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.close()
        _cache_manager = None