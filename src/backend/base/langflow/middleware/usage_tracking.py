"""Usage tracking middleware for monitoring API usage and enforcing quotas"""
import logging
import time
from typing import Callable, Optional

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.billing.usage_service import UsageService
from langflow.services.database.models.subscription.crud import OrganizationCRUD
from langflow.services.database.models.subscription.model import MetricType

logger = logging.getLogger(__name__)


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """中间件：追踪API使用量并执行配额限制"""
    
    def __init__(self, app, usage_service: UsageService):
        super().__init__(app)
        self.usage_service = usage_service
        
        # 需要追踪的API端点模式
        self.tracked_endpoints = {
            '/api/v1/chat': MetricType.API_CALLS,
            '/api/v1/flows': MetricType.API_CALLS,
            '/api/v1/endpoints': MetricType.API_CALLS,
            '/api/v1/validate': MetricType.API_CALLS,
        }
        
        # 需要限制配额的端点（高消耗操作）
        self.quota_enforced_endpoints = {
            '/api/v1/chat',
            '/api/v1/flows/run',
            '/api/v1/endpoints/run'
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并追踪使用量"""
        start_time = time.time()
        
        # 检查是否为需要追踪的端点
        if not self._should_track_endpoint(request.url.path):
            return await call_next(request)
        
        # 获取组织ID（从用户信息或请求头中）
        org_id = await self._get_organization_id(request)
        if not org_id:
            # 如果无法获取组织ID，继续处理但不追踪
            return await call_next(request)
        
        try:
            # 检查配额（对于高消耗端点）
            if self._should_enforce_quota(request.url.path):
                session = await self._get_database_session(request)
                can_use, quota_info = await self.usage_service.check_quota(
                    session, org_id, MetricType.API_CALLS
                )
                
                if not can_use:
                    # 返回配额超限错误
                    return Response(
                        content='{"error": "Usage quota exceeded", "quota_info": ' + str(quota_info) + '}',
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        headers={"Content-Type": "application/json"}
                    )
            
            # 处理请求
            response = await call_next(request)
            
            # 成功处理后追踪使用量
            if 200 <= response.status_code < 300:
                await self._track_request_usage(request, response, org_id, start_time)
            
            return response
            
        except Exception as e:
            logger.error(f"Usage tracking middleware error: {e}")
            # 如果追踪失败，不阻塞请求
            return await call_next(request)
    
    def _should_track_endpoint(self, path: str) -> bool:
        """判断端点是否需要追踪"""
        for tracked_path in self.tracked_endpoints.keys():
            if path.startswith(tracked_path):
                return True
        return False
    
    def _should_enforce_quota(self, path: str) -> bool:
        """判断端点是否需要强制配额检查"""
        for enforced_path in self.quota_enforced_endpoints:
            if path.startswith(enforced_path):
                return True
        return False
    
    async def _get_organization_id(self, request: Request) -> Optional[str]:
        """从请求中获取组织ID"""
        try:
            # 从请求头中获取
            org_id = request.headers.get('X-Organization-ID')
            if org_id:
                return org_id
            
            # 从查询参数中获取
            org_id = request.query_params.get('org_id')
            if org_id:
                return org_id
            
            # 从用户信息中推断（需要实现用户到组织的映射）
            user_id = getattr(request.state, 'user_id', None)
            if user_id:
                session = await self._get_database_session(request)
                if session:
                    user_orgs = await OrganizationCRUD.get_user_organizations(session, user_id)
                    if user_orgs:
                        # 返回用户的第一个组织ID
                        return user_orgs[0].id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get organization ID: {e}")
            return None
    
    async def _get_database_session(self, request: Request) -> Optional[AsyncSession]:
        """获取数据库会话"""
        try:
            # 这里需要根据实际的依赖注入实现来获取会话
            # 可能需要从request.state中获取或者通过其他方式
            return getattr(request.state, 'db_session', None)
        except Exception as e:
            logger.error(f"Failed to get database session: {e}")
            return None
    
    async def _track_request_usage(
        self, 
        request: Request, 
        response: Response, 
        org_id: str, 
        start_time: float
    ):
        """追踪请求的使用量"""
        try:
            session = await self._get_database_session(request)
            if not session:
                return
            
            path = request.url.path
            method = request.method
            user_id = getattr(request.state, 'user_id', None)
            
            # 追踪API调用
            await self.usage_service.track_api_call(
                session, org_id, f"{method} {path}", user_id
            )
            
            # 如果是流程执行，追踪执行时间
            if 'run' in path or 'execute' in path:
                execution_time_ms = int((time.time() - start_time) * 1000)
                flow_id = request.query_params.get('flow_id') or request.path_params.get('flow_id')
                
                await self.usage_service.track_flow_execution(
                    session, org_id, flow_id or 'unknown', execution_time_ms, user_id
                )
            
            logger.debug(f"Tracked usage for org {org_id}: {method} {path}")
            
        except Exception as e:
            logger.error(f"Failed to track request usage: {e}")


async def add_usage_tracking_middleware(app, usage_service: UsageService = None):
    """添加使用量追踪中间件到应用"""
    if usage_service is None:
        usage_service = UsageService()
    
    app.add_middleware(UsageTrackingMiddleware, usage_service=usage_service)
    logger.info("Usage tracking middleware added")