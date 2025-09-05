"""Quota checking decorators for API endpoints"""
import functools
import logging
from typing import Callable, Optional

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.billing.usage_service import UsageService
from langflow.services.database.models.subscription.model import MetricType

logger = logging.getLogger(__name__)


def check_quota(
    metric_type: MetricType,
    amount: int = 1,
    error_message: Optional[str] = None,
    usage_service: Optional[UsageService] = None
):
    """
    装饰器：检查API调用配额
    
    Args:
        metric_type: 使用量类型
        amount: 使用量增量
        error_message: 自定义错误消息
        usage_service: 使用量服务实例
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取参数中的session和org_id
            session = None
            org_id = None
            
            # 从kwargs中查找
            for key, value in kwargs.items():
                if isinstance(value, AsyncSession):
                    session = value
                elif key in ['org_id', 'organization_id'] and isinstance(value, str):
                    org_id = value
            
            # 如果找不到org_id，尝试从其他参数推断
            if not org_id and 'current_user' in kwargs:
                # 这里需要实现从用户获取组织ID的逻辑
                pass
            
            # 如果无法获取必要参数，跳过配额检查
            if not session or not org_id:
                logger.warning("Cannot perform quota check: missing session or org_id")
                return await func(*args, **kwargs)
            
            # 执行配额检查
            service = usage_service or UsageService()
            try:
                can_use, quota_info = await service.check_quota(
                    session, org_id, metric_type, amount
                )
                
                if not can_use:
                    message = error_message or f"Usage quota exceeded for {metric_type.value}"
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "message": message,
                            "quota_info": quota_info
                        }
                    )
                
                # 配额检查通过，执行原函数
                result = await func(*args, **kwargs)
                
                # 成功执行后记录使用量
                await service._track_usage(session, org_id, metric_type, amount)
                
                return result
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Quota check failed: {e}")
                # 如果配额检查失败，仍然允许执行（避免阻塞正常业务）
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def track_usage(
    metric_type: MetricType,
    amount: int = 1,
    usage_service: Optional[UsageService] = None
):
    """
    装饰器：仅追踪使用量，不检查配额
    
    Args:
        metric_type: 使用量类型
        amount: 使用量增量
        usage_service: 使用量服务实例
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # 成功执行后追踪使用量
            session = None
            org_id = None
            
            for key, value in kwargs.items():
                if isinstance(value, AsyncSession):
                    session = value
                elif key in ['org_id', 'organization_id'] and isinstance(value, str):
                    org_id = value
            
            if session and org_id:
                service = usage_service or UsageService()
                try:
                    await service._track_usage(session, org_id, metric_type, amount)
                except Exception as e:
                    logger.error(f"Usage tracking failed: {e}")
            
            return result
        
        return wrapper
    return decorator


def require_subscription(
    min_plan_type: str = "basic",
    error_message: Optional[str] = None
):
    """
    装饰器：要求特定订阅等级
    
    Args:
        min_plan_type: 最低订阅类型要求
        error_message: 自定义错误消息
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取session和org_id
            session = None
            org_id = None
            
            for key, value in kwargs.items():
                if isinstance(value, AsyncSession):
                    session = value
                elif key in ['org_id', 'organization_id'] and isinstance(value, str):
                    org_id = value
            
            if session and org_id:
                from langflow.services.database.models.subscription.crud import SubscriptionCRUD
                
                try:
                    subscription = await SubscriptionCRUD.get_organization_subscription(
                        session, org_id
                    )
                    
                    if not subscription:
                        message = error_message or f"This feature requires a {min_plan_type} subscription"
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail={
                                "message": message,
                                "required_plan": min_plan_type,
                                "current_plan": "free"
                            }
                        )
                    
                    # 检查订阅等级
                    plan_hierarchy = {
                        'free': 0,
                        'basic': 1,
                        'professional': 2,
                        'enterprise': 3
                    }
                    
                    current_level = plan_hierarchy.get(subscription.plan.plan_type.value, 0)
                    required_level = plan_hierarchy.get(min_plan_type, 1)
                    
                    if current_level < required_level:
                        message = error_message or f"This feature requires a {min_plan_type} subscription"
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail={
                                "message": message,
                                "required_plan": min_plan_type,
                                "current_plan": subscription.plan.plan_type.value
                            }
                        )
                    
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Subscription check failed: {e}")
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# 便捷的预定义装饰器
check_api_quota = functools.partial(check_quota, MetricType.API_CALLS)
check_flow_quota = functools.partial(check_quota, MetricType.FLOW_EXECUTIONS)
check_storage_quota = functools.partial(check_quota, MetricType.STORAGE_MB)

track_api_call = functools.partial(track_usage, MetricType.API_CALLS)
track_flow_execution = functools.partial(track_usage, MetricType.FLOW_EXECUTIONS)

require_basic_plan = functools.partial(require_subscription, "basic")
require_professional_plan = functools.partial(require_subscription, "professional")
require_enterprise_plan = functools.partial(require_subscription, "enterprise")