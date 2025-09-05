"""Specialized cache services for different data types"""
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
import json
from loguru import logger

from .redis_cache import RedisCacheManager, CacheKeyPrefix, cache_result


class FlowCacheService:
    """Cache service for flow-related data"""
    
    def __init__(self, cache_manager: RedisCacheManager):
        self.cache_manager = cache_manager
    
    async def get_flow(self, flow_id: str) -> Optional[Dict]:
        """Get flow from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.FLOW, [flow_id])
    
    async def set_flow(self, flow_id: str, flow_data: Dict, ttl: int = 3600) -> bool:
        """Set flow in cache"""
        return await self.cache_manager.set(CacheKeyPrefix.FLOW, [flow_id], flow_data, ttl)
    
    async def delete_flow(self, flow_id: str) -> bool:
        """Delete flow from cache"""
        return await self.cache_manager.delete(CacheKeyPrefix.FLOW, [flow_id])
    
    async def get_user_flows(self, user_id: str) -> Optional[List[Dict]]:
        """Get user's flows from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.FLOW, [f"user_{user_id}"])
    
    async def set_user_flows(self, user_id: str, flows: List[Dict], ttl: int = 1800) -> bool:
        """Set user's flows in cache"""
        return await self.cache_manager.set(CacheKeyPrefix.FLOW, [f"user_{user_id}"], flows, ttl)
    
    async def get_flow_execution_result(self, flow_id: str, execution_id: str) -> Optional[Dict]:
        """Get flow execution result from cache"""
        key = f"execution_{flow_id}_{execution_id}"
        return await self.cache_manager.get(CacheKeyPrefix.FLOW, [key])
    
    async def set_flow_execution_result(
        self, 
        flow_id: str, 
        execution_id: str, 
        result: Dict, 
        ttl: int = 7200
    ) -> bool:
        """Set flow execution result in cache"""
        key = f"execution_{flow_id}_{execution_id}"
        return await self.cache_manager.set(CacheKeyPrefix.FLOW, [key], result, ttl)


class ComponentCacheService:
    """Cache service for component-related data"""
    
    def __init__(self, cache_manager: RedisCacheManager):
        self.cache_manager = cache_manager
    
    async def get_component_types(self) -> Optional[List[Dict]]:
        """Get component types from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.COMPONENT, ["types"])
    
    async def set_component_types(self, types: List[Dict], ttl: int = 7200) -> bool:
        """Set component types in cache"""
        return await self.cache_manager.set(CacheKeyPrefix.COMPONENT, ["types"], types, ttl)
    
    async def get_component_template(self, component_type: str) -> Optional[Dict]:
        """Get component template from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.COMPONENT, ["template", component_type])
    
    async def set_component_template(
        self, 
        component_type: str, 
        template: Dict, 
        ttl: int = 3600
    ) -> bool:
        """Set component template in cache"""
        return await self.cache_manager.set(
            CacheKeyPrefix.COMPONENT, 
            ["template", component_type], 
            template, 
            ttl
        )
    
    async def get_component_schema(self, component_type: str) -> Optional[Dict]:
        """Get component schema from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.COMPONENT, ["schema", component_type])
    
    async def set_component_schema(
        self, 
        component_type: str, 
        schema: Dict, 
        ttl: int = 3600
    ) -> bool:
        """Set component schema in cache"""
        return await self.cache_manager.set(
            CacheKeyPrefix.COMPONENT, 
            ["schema", component_type], 
            schema, 
            ttl
        )


class UserCacheService:
    """Cache service for user-related data"""
    
    def __init__(self, cache_manager: RedisCacheManager):
        self.cache_manager = cache_manager
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """Get user profile from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.USER, [user_id])
    
    async def set_user_profile(self, user_id: str, profile: Dict, ttl: int = 1800) -> bool:
        """Set user profile in cache"""
        return await self.cache_manager.set(CacheKeyPrefix.USER, [user_id], profile, ttl)
    
    async def get_user_permissions(self, user_id: str) -> Optional[List[str]]:
        """Get user permissions from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.USER, [f"permissions_{user_id}"])
    
    async def set_user_permissions(
        self, 
        user_id: str, 
        permissions: List[str], 
        ttl: int = 1800
    ) -> bool:
        """Set user permissions in cache"""
        return await self.cache_manager.set(
            CacheKeyPrefix.USER, 
            [f"permissions_{user_id}"], 
            permissions, 
            ttl
        )
    
    async def get_user_session(self, session_id: str) -> Optional[Dict]:
        """Get user session from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.SESSION, [session_id])
    
    async def set_user_session(
        self, 
        session_id: str, 
        session_data: Dict, 
        ttl: int = 86400
    ) -> bool:
        """Set user session in cache"""
        return await self.cache_manager.set(CacheKeyPrefix.SESSION, [session_id], session_data, ttl)
    
    async def delete_user_session(self, session_id: str) -> bool:
        """Delete user session from cache"""
        return await self.cache_manager.delete(CacheKeyPrefix.SESSION, [session_id])
    
    async def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cache entries for a user"""
        patterns = [
            f"{user_id}",
            f"permissions_{user_id}",
            f"session_{user_id}"
        ]
        
        count = 0
        for pattern in patterns:
            count += await self.cache_manager.clear_pattern(CacheKeyPrefix.USER, pattern)
        
        return count


class QueryCacheService:
    """Cache service for database queries"""
    
    def __init__(self, cache_manager: RedisCacheManager):
        self.cache_manager = cache_manager
    
    def generate_query_key(self, query: str, params: tuple = ()) -> str:
        """Generate cache key for database query"""
        import hashlib
        key_data = f"{query}:{params}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def get_query_result(self, query: str, params: tuple = ()) -> Optional[Any]:
        """Get query result from cache"""
        key = self.generate_query_key(query, params)
        return await self.cache_manager.get(CacheKeyPrefix.QUERY, [key])
    
    async def set_query_result(
        self, 
        query: str, 
        params: tuple, 
        result: Any, 
        ttl: int = 1800
    ) -> bool:
        """Set query result in cache"""
        key = self.generate_query_key(query, params)
        return await self.cache_manager.set(CacheKeyPrefix.QUERY, [key], result, ttl)
    
    async def invalidate_query_cache(self, table_name: str) -> int:
        """Invalidate cache for specific table"""
        return await self.cache_manager.clear_pattern(CacheKeyPrefix.QUERY, f"*{table_name}*")


class SettingsCacheService:
    """Cache service for application settings"""
    
    def __init__(self, cache_manager: RedisCacheManager):
        self.cache_manager = cache_manager
    
    async def get_settings(self, user_id: Optional[str] = None) -> Optional[Dict]:
        """Get settings from cache"""
        key = f"user_{user_id}" if user_id else "global"
        return await self.cache_manager.get(CacheKeyPrefix.SETTINGS, [key])
    
    async def set_settings(
        self, 
        settings: Dict, 
        user_id: Optional[str] = None, 
        ttl: int = 3600
    ) -> bool:
        """Set settings in cache"""
        key = f"user_{user_id}" if user_id else "global"
        return await self.cache_manager.set(CacheKeyPrefix.SETTINGS, [key], settings, ttl)
    
    async def get_feature_flags(self) -> Optional[Dict]:
        """Get feature flags from cache"""
        return await self.cache_manager.get(CacheKeyPrefix.SETTINGS, ["feature_flags"])
    
    async def set_feature_flags(self, flags: Dict, ttl: int = 1800) -> bool:
        """Set feature flags in cache"""
        return await self.cache_manager.set(CacheKeyPrefix.SETTINGS, ["feature_flags"], flags, ttl)


class CacheServiceFactory:
    """Factory for creating cache services"""
    
    def __init__(self, cache_manager: RedisCacheManager):
        self.cache_manager = cache_manager
        self.flow_cache = FlowCacheService(cache_manager)
        self.component_cache = ComponentCacheService(cache_manager)
        self.user_cache = UserCacheService(cache_manager)
        self.query_cache = QueryCacheService(cache_manager)
        self.settings_cache = SettingsCacheService(cache_manager)
    
    def get_flow_cache(self) -> FlowCacheService:
        """Get flow cache service"""
        return self.flow_cache
    
    def get_component_cache(self) -> ComponentCacheService:
        """Get component cache service"""
        return self.component_cache
    
    def get_user_cache(self) -> UserCacheService:
        """Get user cache service"""
        return self.user_cache
    
    def get_query_cache(self) -> QueryCacheService:
        """Get query cache service"""
        return self.query_cache
    
    def get_settings_cache(self) -> SettingsCacheService:
        """Get settings cache service"""
        return self.settings_cache


# Global cache service factory
_cache_factory: Optional[CacheServiceFactory] = None


async def get_cache_service_factory() -> CacheServiceFactory:
    """Get global cache service factory"""
    global _cache_factory
    if _cache_factory is None:
        from .redis_cache import get_cache_manager
        cache_manager = await get_cache_manager()
        _cache_factory = CacheServiceFactory(cache_manager)
    return _cache_factory