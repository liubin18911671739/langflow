"""Component lazy loading system for performance optimization"""
import asyncio
import importlib
import inspect
import time
from typing import Any, Dict, List, Optional, Set, Type, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from loguru import logger
from pydantic import BaseModel, Field

from langflow.services.cache.services import ComponentCacheService, get_cache_service_factory


class ComponentPriority(str, Enum):
    """Component loading priority"""
    HIGH = "high"      # Critical components, load immediately
    MEDIUM = "medium"  # Common components, load on demand
    LOW = "low"        # Rarely used components, load only when needed


class ComponentStatus(str, Enum):
    """Component loading status"""
    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"


@dataclass
class ComponentMetadata:
    """Metadata for lazy-loaded components"""
    name: str
    module_path: str
    class_name: str
    priority: ComponentPriority
    dependencies: List[str]
    file_size: int
    load_time: Optional[float] = None
    status: ComponentStatus = ComponentStatus.NOT_LOADED
    error_message: Optional[str] = None
    last_used: Optional[float] = None
    usage_count: int = 0


class ComponentLoadConfig(BaseModel):
    """Configuration for component lazy loading"""
    enable_lazy_loading: bool = Field(default=True, description="Enable lazy loading")
    preload_high_priority: bool = Field(default=True, description="Preload high priority components")
    max_concurrent_loads: int = Field(default=3, description="Maximum concurrent component loads")
    component_timeout: float = Field(default=30.0, description="Component loading timeout")
    cache_loaded_components: bool = Field(default=True, description="Cache loaded components")
    memory_threshold: int = Field(default=512 * 1024 * 1024, description="Memory threshold in bytes")
    enable_usage_tracking: bool = Field(default=True, description="Enable usage tracking")
    unload_unused_components: bool = Field(default=True, description="Unload unused components")
    unused_threshold: int = Field(default=3600, description="Unused threshold in seconds")


class ComponentLoader:
    """Component loader with lazy loading capabilities"""
    
    def __init__(self, config: ComponentLoadConfig):
        self.config = config
        self.loaded_components: Dict[str, Any] = {}
        self.component_metadata: Dict[str, ComponentMetadata] = {}
        self.loading_queue: asyncio.Queue = asyncio.Queue()
        self.loading_tasks: Dict[str, asyncio.Task] = {}
        self.cache_service: Optional[ComponentCacheService] = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._loading_lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize the component loader"""
        if self.config.cache_loaded_components:
            cache_factory = await get_cache_service_factory()
            self.cache_service = cache_factory.get_component_cache()
        
        # Start background loading tasks
        if self.config.preload_high_priority:
            asyncio.create_task(self._preload_high_priority_components())
        
        # Start component management task
        asyncio.create_task(self._manage_components())
        
        logger.info("Component loader initialized")
    
    def register_component(
        self,
        name: str,
        module_path: str,
        class_name: str,
        priority: ComponentPriority = ComponentPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ):
        """Register a component for lazy loading"""
        metadata = ComponentMetadata(
            name=name,
            module_path=module_path,
            class_name=class_name,
            priority=priority,
            dependencies=dependencies or [],
            file_size=0  # Will be calculated later
        )
        
        self.component_metadata[name] = metadata
        logger.debug(f"Registered component: {name}")
    
    async def get_component(self, name: str) -> Optional[Any]:
        """Get a component, loading it if necessary"""
        if name not in self.component_metadata:
            logger.error(f"Component not registered: {name}")
            return None
        
        metadata = self.component_metadata[name]
        
        # Update usage statistics
        if self.config.enable_usage_tracking:
            metadata.usage_count += 1
            metadata.last_used = time.time()
        
        # Return if already loaded
        if name in self.loaded_components:
            return self.loaded_components[name]
        
        # Load component
        return await self._load_component(name)
    
    async def _load_component(self, name: str) -> Optional[Any]:
        """Load a single component"""
        if name not in self.component_metadata:
            return None
        
        metadata = self.component_metadata[name]
        
        # Check if already loading
        if name in self.loading_tasks:
            try:
                return await asyncio.wait_for(
                    self.loading_tasks[name], 
                    timeout=self.config.component_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Component loading timeout: {name}")
                metadata.status = ComponentStatus.ERROR
                metadata.error_message = "Loading timeout"
                return None
        
        # Start loading
        async with self._loading_lock:
            if name in self.loaded_components:
                return self.loaded_components[name]
            
            metadata.status = ComponentStatus.LOADING
            
            # Create loading task
            task = asyncio.create_task(self._load_component_task(name))
            self.loading_tasks[name] = task
        
        try:
            # Wait for loading to complete
            component = await asyncio.wait_for(
                task,
                timeout=self.config.component_timeout
            )
            
            return component
            
        except asyncio.TimeoutError:
            logger.error(f"Component loading timeout: {name}")
            metadata.status = ComponentStatus.ERROR
            metadata.error_message = "Loading timeout"
            return None
        except Exception as e:
            logger.error(f"Component loading error: {name}: {e}")
            metadata.status = ComponentStatus.ERROR
            metadata.error_message = str(e)
            return None
        finally:
            # Clean up loading task
            if name in self.loading_tasks:
                del self.loading_tasks[name]
    
    async def _load_component_task(self, name: str) -> Optional[Any]:
        """Task to load a component"""
        metadata = self.component_metadata[name]
        start_time = time.time()
        
        try:
            # Try to get from cache first
            if self.cache_service:
                cached_component = await self.cache_service.get_component_template(name)
                if cached_component:
                    self.loaded_components[name] = cached_component
                    metadata.status = ComponentStatus.LOADED
                    metadata.load_time = time.time() - start_time
                    logger.debug(f"Component loaded from cache: {name}")
                    return cached_component
            
            # Load dependencies first
            for dep_name in metadata.dependencies:
                await self.get_component(dep_name)
            
            # Load the component
            component = await self._load_component_from_module(metadata)
            
            if component:
                self.loaded_components[name] = component
                metadata.status = ComponentStatus.LOADED
                metadata.load_time = time.time() - start_time
                
                # Cache the component
                if self.cache_service:
                    component_data = {
                        "class": component,
                        "module": metadata.module_path,
                        "load_time": metadata.load_time
                    }
                    await self.cache_service.set_component_template(name, component_data)
                
                logger.debug(f"Component loaded: {name} in {metadata.load_time:.2f}s")
                return component
            
            return None
            
        except Exception as e:
            metadata.status = ComponentStatus.ERROR
            metadata.error_message = str(e)
            logger.error(f"Failed to load component {name}: {e}")
            return None
    
    async def _load_component_from_module(self, metadata: ComponentMetadata) -> Optional[Any]:
        """Load component from module"""
        try:
            # Import module
            module = importlib.import_module(metadata.module_path)
            
            # Get component class
            component_class = getattr(module, metadata.class_name)
            
            # Validate component
            if not inspect.isclass(component_class):
                raise ValueError(f"Component {metadata.name} is not a class")
            
            # Create component instance
            component = component_class()
            
            return component
            
        except ImportError as e:
            logger.error(f"Failed to import module {metadata.module_path}: {e}")
            raise e
        except AttributeError as e:
            logger.error(f"Component class {metadata.class_name} not found in {metadata.module_path}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Failed to instantiate component {metadata.name}: {e}")
            raise e
    
    async def _preload_high_priority_components(self):
        """Preload high priority components"""
        high_priority_components = [
            name for name, metadata in self.component_metadata.items()
            if metadata.priority == ComponentPriority.HIGH
        ]
        
        if not high_priority_components:
            return
        
        logger.info(f"Preloading {len(high_priority_components)} high priority components")
        
        # Load components in batches
        batch_size = self.config.max_concurrent_loads
        
        for i in range(0, len(high_priority_components), batch_size):
            batch = high_priority_components[i:i + batch_size]
            
            tasks = [
                self.get_component(name) 
                for name in batch
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Small delay between batches
            await asyncio.sleep(0.1)
        
        logger.info("High priority components preloaded")
    
    async def _manage_components(self):
        """Background task to manage loaded components"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                if self.config.unload_unused_components:
                    await self._unload_unused_components()
                
                # Log memory usage
                await self._log_memory_usage()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Component management error: {e}")
    
    async def _unload_unused_components(self):
        """Unload unused components to free memory"""
        current_time = time.time()
        components_to_unload = []
        
        for name, metadata in self.component_metadata.items():
            if (metadata.status == ComponentStatus.LOADED and
                metadata.last_used and
                current_time - metadata.last_used > self.config.unused_threshold and
                metadata.priority == ComponentPriority.LOW):
                
                components_to_unload.append(name)
        
        for name in components_to_unload:
            await self._unload_component(name)
    
    async def _unload_component(self, name: str):
        """Unload a component"""
        if name in self.loaded_components:
            del self.loaded_components[name]
            
            if name in self.component_metadata:
                metadata = self.component_metadata[name]
                metadata.status = ComponentStatus.NOT_LOADED
                logger.debug(f"Component unloaded: {name}")
    
    async def _log_memory_usage(self):
        """Log memory usage statistics"""
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            loaded_count = len(self.loaded_components)
            total_count = len(self.component_metadata)
            
            logger.info(
                f"Memory usage: {memory_info.rss / 1024 / 1024:.1f}MB, "
                f"Components loaded: {loaded_count}/{total_count}"
            )
            
        except ImportError:
            pass  # psutil not available
    
    def get_component_stats(self) -> Dict[str, Any]:
        """Get component loading statistics"""
        stats = {
            "total_components": len(self.component_metadata),
            "loaded_components": len(self.loaded_components),
            "loading_components": len(self.loading_tasks),
            "error_components": sum(
                1 for m in self.component_metadata.values()
                if m.status == ComponentStatus.ERROR
            ),
            "high_priority_count": sum(
                1 for m in self.component_metadata.values()
                if m.priority == ComponentPriority.HIGH
            ),
            "medium_priority_count": sum(
                1 for m in self.component_metadata.values()
                if m.priority == ComponentPriority.MEDIUM
            ),
            "low_priority_count": sum(
                1 for m in self.component_metadata.values()
                if m.priority == ComponentPriority.LOW
            )
        }
        
        # Calculate average load time
        loaded_metadata = [
            m for m in self.component_metadata.values()
            if m.load_time is not None
        ]
        
        if loaded_metadata:
            stats["average_load_time"] = sum(m.load_time for m in loaded_metadata) / len(loaded_metadata)
        
        return stats
    
    async def shutdown(self):
        """Shutdown the component loader"""
        # Cancel all loading tasks
        for task in self.loading_tasks.values():
            task.cancel()
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("Component loader shutdown complete")


# Global component loader instance
_component_loader: Optional[ComponentLoader] = None


async def get_component_loader() -> ComponentLoader:
    """Get global component loader instance"""
    global _component_loader
    if _component_loader is None:
        config = ComponentLoadConfig()
        _component_loader = ComponentLoader(config)
        await _component_loader.initialize()
    return _component_loader


# Decorator for lazy loading
def lazy_component(name: str, priority: ComponentPriority = ComponentPriority.MEDIUM):
    """Decorator to register a component for lazy loading"""
    def decorator(cls):
        async def register():
            loader = await get_component_loader()
            loader.register_component(
                name=name,
                module_path=cls.__module__,
                class_name=cls.__name__,
                priority=priority
            )
        
        # Schedule registration
        asyncio.create_task(register())
        return cls
    return decorator


# Utility function to get component with lazy loading
async def get_lazy_component(name: str) -> Optional[Any]:
    """Get a component with lazy loading"""
    loader = await get_component_loader()
    return await loader.get_component(name)