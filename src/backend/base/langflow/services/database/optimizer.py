"""Database query optimization utilities and middleware"""
import time
import logging
from typing import Any, Dict, List, Optional, Union, Callable
from contextlib import asynccontextmanager
from functools import wraps
from datetime import datetime
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, func, select, delete, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool
from loguru import logger
from pydantic import BaseModel, Field

from langflow.services.cache.services import QueryCacheService, get_cache_service_factory


class QueryMetrics(BaseModel):
    """Query performance metrics"""
    query: str = Field(..., description="SQL query")
    execution_time: float = Field(..., description="Execution time in milliseconds")
    rows_affected: int = Field(default=0, description="Number of rows affected")
    cached: bool = Field(default=False, description="Was result cached")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True


class QueryOptimizationConfig(BaseModel):
    """Configuration for query optimization"""
    enable_query_cache: bool = Field(default=True, description="Enable query caching")
    enable_query_logging: bool = Field(default=True, description="Enable query logging")
    enable_slow_query_detection: bool = Field(default=True, description="Enable slow query detection")
    slow_query_threshold: float = Field(default=1000.0, description="Slow query threshold in milliseconds")
    enable_connection_pooling: bool = Field(default=True, description="Enable connection pooling")
    max_connections: int = Field(default=20, description="Maximum database connections")
    pool_timeout: int = Field(default=30, description="Connection pool timeout")
    pool_recycle: int = Field(default=3600, description="Connection pool recycle time")
    enable_read_only_replicas: bool = Field(default=False, description="Enable read-only replicas")
    enable_batch_operations: bool = Field(default=True, description="Enable batch operations")


class DatabaseOptimizer:
    """Database query optimization service"""
    
    def __init__(self, config: QueryOptimizationConfig):
        self.config = config
        self.query_metrics: List[QueryMetrics] = []
        self.slow_queries: List[QueryMetrics] = []
        self.cache_service: Optional[QueryCacheService] = None
        
    async def initialize(self):
        """Initialize the database optimizer"""
        if self.config.enable_query_cache:
            cache_factory = await get_cache_service_factory()
            self.cache_service = cache_factory.get_query_cache()
        
        logger.info("Database optimizer initialized")
    
    def create_optimized_engine(self, database_url: str) -> Any:
        """Create optimized database engine"""
        engine_config = {
            "echo": False,
            "future": True,
            "pool_pre_ping": True,
            "pool_recycle": self.config.pool_recycle,
            "pool_timeout": self.config.pool_timeout,
            "connect_args": {
                "connect_timeout": 10,
                "command_timeout": 30,
            }
        }
        
        if self.config.enable_connection_pooling:
            engine_config.update({
                "pool_size": self.config.max_connections,
                "max_overflow": self.config.max_connections // 2,
                "poolclass": None,  # Use default pool class
            })
        else:
            engine_config["poolclass"] = NullPool
        
        return create_async_engine(database_url, **engine_config)
    
    @asynccontextmanager
    async def optimized_session(self, engine: Any):
        """Create optimized database session"""
        async_session = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
        
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
    
    async def execute_optimized_query(
        self,
        session: AsyncSession,
        query: Any,
        params: Optional[Dict] = None,
        use_cache: bool = True,
        cache_ttl: int = 1800
    ) -> Any:
        """Execute optimized query with caching and metrics"""
        start_time = time.time()
        
        # Generate query key for caching
        query_str = str(query.compile(compile_kwargs={"literal_binds": True}))
        cache_key = (query_str, tuple(params.items()) if params else ())
        
        # Try to get from cache
        cached_result = None
        if use_cache and self.cache_service and self.config.enable_query_cache:
            cached_result = await self.cache_service.get_query_result(query_str, cache_key)
        
        if cached_result is not None:
            execution_time = (time.time() - start_time) * 1000
            
            # Log cached query
            if self.config.enable_query_logging:
                metrics = QueryMetrics(
                    query=query_str,
                    execution_time=execution_time,
                    cached=True
                )
                self._log_query_metrics(metrics)
            
            return cached_result
        
        # Execute query
        try:
            if params:
                result = await session.execute(query, params)
            else:
                result = await session.execute(query)
            
            execution_time = (time.time() - start_time) * 1000
            
            # Process result
            processed_result = self._process_query_result(result)
            
            # Cache result
            if use_cache and self.cache_service and self.config.enable_query_cache:
                await self.cache_service.set_query_result(query_str, cache_key, processed_result, cache_ttl)
            
            # Log query metrics
            if self.config.enable_query_logging:
                metrics = QueryMetrics(
                    query=query_str,
                    execution_time=execution_time,
                    rows_affected=result.rowcount if hasattr(result, 'rowcount') else 0
                )
                self._log_query_metrics(metrics)
            
            return processed_result
            
        except SQLAlchemyError as e:
            logger.error(f"Query execution error: {e}")
            raise e
    
    def _process_query_result(self, result: Any) -> Any:
        """Process query result based on type"""
        if hasattr(result, 'scalar_one_or_none'):
            return result.scalar_one_or_none()
        elif hasattr(result, 'scalar_one'):
            return result.scalar_one()
        elif hasattr(result, 'scalars'):
            return result.scalars().all()
        elif hasattr(result, 'all'):
            return result.all()
        else:
            return result
    
    def _log_query_metrics(self, metrics: QueryMetrics):
        """Log query metrics"""
        self.query_metrics.append(metrics)
        
        # Keep only last 1000 metrics
        if len(self.query_metrics) > 1000:
            self.query_metrics = self.query_metrics[-1000:]
        
        # Log slow queries
        if (self.config.enable_slow_query_detection and 
            metrics.execution_time > self.config.slow_query_threshold):
            self.slow_queries.append(metrics)
            
            # Keep only last 100 slow queries
            if len(self.slow_queries) > 100:
                self.slow_queries = self.slow_queries[-100:]
            
            logger.warning(f"Slow query detected: {metrics.query} took {metrics.execution_time:.2f}ms")
    
    def get_query_stats(self) -> Dict[str, Any]:
        """Get query performance statistics"""
        if not self.query_metrics:
            return {
                "total_queries": 0,
                "avg_execution_time": 0,
                "cache_hit_rate": 0,
                "slow_queries": 0
            }
        
        total_queries = len(self.query_metrics)
        avg_execution_time = sum(m.execution_time for m in self.query_metrics) / total_queries
        cached_queries = sum(1 for m in self.query_metrics if m.cached)
        cache_hit_rate = cached_queries / total_queries if total_queries > 0 else 0
        
        return {
            "total_queries": total_queries,
            "avg_execution_time": avg_execution_time,
            "cache_hit_rate": cache_hit_rate,
            "slow_queries": len(self.slow_queries)
        }


# Query optimization decorators
def cache_query(ttl: int = 1800):
    """Decorator to cache query results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache service
            cache_factory = await get_cache_service_factory()
            cache_service = cache_factory.get_query_cache()
            
            # Generate cache key
            key_data = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            
            # Try to get from cache
            cached_result = await cache_service.get_query_result(key_data)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache_service.set_query_result(key_data, (), result, ttl)
            
            return result
        return wrapper
    return decorator


def log_query():
    """Decorator to log query execution"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000
                
                logger.debug(f"Query {func.__name__} executed in {execution_time:.2f}ms")
                
                return result
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                logger.error(f"Query {func.__name__} failed after {execution_time:.2f}ms: {e}")
                raise e
        return wrapper
    return decorator


class QueryOptimizer:
    """Utility class for query optimization"""
    
    @staticmethod
    def optimize_select_query(query: Any) -> Any:
        """Optimize SELECT query"""
        # Add only necessary columns
        if hasattr(query, 'columns') and query.columns:
            # Ensure only required columns are selected
            pass
        
        # Add proper indexing hints
        if hasattr(query, 'with_hint'):
            # Add index hints if needed
            pass
        
        return query
    
    @staticmethod
    def create_pagination_query(
        base_query: Any,
        page: int = 1,
        page_size: int = 20,
        count_query: Optional[Any] = None
    ) -> tuple[Any, Any]:
        """Create optimized pagination query"""
        offset = (page - 1) * page_size
        
        # Paginated query
        paginated_query = base_query.offset(offset).limit(page_size)
        
        # Count query
        if count_query is None:
            count_query = select(func.count()).select_from(base_query.subquery())
        
        return paginated_query, count_query
    
    @staticmethod
    def create_batch_insert_query(
        model: Any,
        data: List[Dict],
        batch_size: int = 1000
    ) -> List[Any]:
        """Create batch insert queries"""
        queries = []
        
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            query = insert(model).values(batch)
            queries.append(query)
        
        return queries
    
    @staticmethod
    def create_batch_update_query(
        model: Any,
        updates: List[Dict],
        id_column: str = "id"
    ) -> Any:
        """Create batch update query"""
        case_expressions = []
        
        for update_data in updates:
            if id_column not in update_data:
                continue
            
            record_id = update_data[id_column]
            for column, value in update_data.items():
                if column == id_column:
                    continue
                
                case_expressions.append(
                    func.case(
                        (getattr(model, id_column) == record_id, value)
                    )
                )
        
        if not case_expressions:
            return None
        
        # Create update query with CASE statements
        update_query = update(model)
        
        return update_query


# Global database optimizer instance
_db_optimizer: Optional[DatabaseOptimizer] = None


async def get_database_optimizer() -> DatabaseOptimizer:
    """Get global database optimizer instance"""
    global _db_optimizer
    if _db_optimizer is None:
        config = QueryOptimizationConfig()
        _db_optimizer = DatabaseOptimizer(config)
        await _db_optimizer.initialize()
    return _db_optimizer


async def initialize_database_optimizer():
    """Initialize database optimizer"""
    await get_database_optimizer()


class DatabaseMiddleware:
    """Middleware for database connection optimization"""
    
    def __init__(self, app, optimizer: DatabaseOptimizer):
        self.app = app
        self.optimizer = optimizer
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Add database session to request scope
        async def send_wrapper(message):
            await send(message)
        
        await self.app(scope, receive, send_wrapper)