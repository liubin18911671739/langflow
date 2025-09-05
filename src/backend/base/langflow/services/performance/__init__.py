"""Performance optimization services initialization"""
from loguru import logger

from langflow.services.cache.redis_cache import initialize_cache, close_cache
from langflow.services.database.optimizer import initialize_database_optimizer
from langflow.services.components.lazy_loader import get_component_loader


async def initialize_performance_services():
    """Initialize all performance optimization services"""
    
    logger.info("Initializing performance optimization services...")
    
    try:
        # Initialize cache service
        await initialize_cache()
        logger.info("✓ Cache service initialized")
        
        # Initialize database optimizer
        await initialize_database_optimizer()
        logger.info("✓ Database optimizer initialized")
        
        # Initialize component loader
        component_loader = await get_component_loader()
        logger.info("✓ Component loader initialized")
        
        logger.info("All performance optimization services initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize performance services: {e}")
        raise e


async def shutdown_performance_services():
    """Shutdown all performance optimization services"""
    
    logger.info("Shutting down performance optimization services...")
    
    try:
        # Close cache service
        await close_cache()
        logger.info("✓ Cache service shutdown")
        
        # Shutdown component loader
        from langflow.services.components.lazy_loader import _component_loader
        if _component_loader:
            await _component_loader.shutdown()
            logger.info("✓ Component loader shutdown")
        
        logger.info("All performance optimization services shutdown successfully")
        
    except Exception as e:
        logger.error(f"Failed to shutdown performance services: {e}")
        raise e


# Performance monitoring and metrics
class PerformanceMonitor:
    """Performance monitoring and metrics collection"""
    
    def __init__(self):
        self.metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "db_queries": 0,
            "slow_queries": 0,
            "compressed_responses": 0,
            "component_loads": 0,
            "component_load_time": 0.0
        }
    
    def increment_cache_hits(self):
        """Increment cache hit counter"""
        self.metrics["cache_hits"] += 1
    
    def increment_cache_misses(self):
        """Increment cache miss counter"""
        self.metrics["cache_misses"] += 1
    
    def increment_db_queries(self):
        """Increment database query counter"""
        self.metrics["db_queries"] += 1
    
    def increment_slow_queries(self):
        """Increment slow query counter"""
        self.metrics["slow_queries"] += 1
    
    def increment_compressed_responses(self):
        """Increment compressed response counter"""
        self.metrics["compressed_responses"] += 1
    
    def add_component_load_time(self, load_time: float):
        """Add component load time"""
        self.metrics["component_loads"] += 1
        self.metrics["component_load_time"] += load_time
    
    def get_metrics(self) -> dict:
        """Get current metrics"""
        metrics = self.metrics.copy()
        
        # Calculate derived metrics
        total_cache_requests = metrics["cache_hits"] + metrics["cache_misses"]
        if total_cache_requests > 0:
            metrics["cache_hit_rate"] = metrics["cache_hits"] / total_cache_requests
        else:
            metrics["cache_hit_rate"] = 0.0
        
        if metrics["db_queries"] > 0:
            metrics["slow_query_rate"] = metrics["slow_queries"] / metrics["db_queries"]
        else:
            metrics["slow_query_rate"] = 0.0
        
        if metrics["component_loads"] > 0:
            metrics["avg_component_load_time"] = metrics["component_load_time"] / metrics["component_loads"]
        else:
            metrics["avg_component_load_time"] = 0.0
        
        return metrics
    
    def reset_metrics(self):
        """Reset all metrics"""
        for key in self.metrics:
            self.metrics[key] = 0 if not isinstance(self.metrics[key], float) else 0.0


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


# Performance optimization utilities
class PerformanceUtils:
    """Utility functions for performance optimization"""
    
    @staticmethod
    async def measure_execution_time(func, *args, **kwargs):
        """Measure execution time of a function"""
        import time
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            return result, execution_time
        except Exception as e:
            execution_time = time.time() - start_time
            raise e
    
    @staticmethod
    def format_execution_time(seconds: float) -> str:
        """Format execution time for display"""
        if seconds < 0.001:
            return f"{seconds * 1000000:.0f}μs"
        elif seconds < 1:
            return f"{seconds * 1000:.1f}ms"
        else:
            return f"{seconds:.2f}s"
    
    @staticmethod
    def calculate_performance_score(metrics: dict) -> float:
        """Calculate overall performance score (0-100)"""
        score = 100.0
        
        # Cache hit rate impact (30% weight)
        cache_hit_rate = metrics.get("cache_hit_rate", 0)
        score += cache_hit_rate * 30
        
        # Slow query rate impact (-25% weight)
        slow_query_rate = metrics.get("slow_query_rate", 0)
        score -= slow_query_rate * 25
        
        # Compression impact (15% weight)
        compression_ratio = metrics.get("compression_ratio", 0)
        score += compression_ratio * 15
        
        # Component load time impact (-30% weight)
        avg_load_time = metrics.get("avg_component_load_time", 0)
        if avg_load_time > 1.0:  # More than 1 second
            score -= min(30, (avg_load_time - 1.0) * 10)
        
        return max(0, min(100, score))


# Export for external use
__all__ = [
    "initialize_performance_services",
    "shutdown_performance_services",
    "get_performance_monitor",
    "PerformanceUtils"
]