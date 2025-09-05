"""Multi-tenant context middleware for Row Level Security"""
import logging
from typing import Callable, Optional

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.database.models.subscription.crud import OrganizationCRUD
from langflow.services.deps import get_session

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    中间件：为每个请求设置租户上下文，启用PostgreSQL RLS
    
    工作原理：
    1. 从请求中提取组织ID（请求头、路径参数、用户会话等）
    2. 验证用户对该组织的访问权限
    3. 设置数据库会话变量 app.current_organization_id
    4. PostgreSQL RLS策略会自动过滤数据
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.excluded_paths = {
            '/api/v1/login',
            '/api/v1/users',
            '/api/v1/billing/organizations',  # 创建组织时不需要组织上下文
            '/api/v1/billing/plans',         # 公共计划信息
            '/docs',
            '/openapi.json',
            '/health',
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并设置租户上下文"""
        path = request.url.path
        
        # 跳过不需要租户上下文的路径
        if self._should_skip_path(path):
            return await call_next(request)
        
        try:
            # 获取组织ID
            org_id = await self._extract_organization_id(request)
            
            if org_id:
                # 验证用户访问权限
                if await self._validate_organization_access(request, org_id):
                    # 设置数据库会话中的租户上下文
                    await self._set_tenant_context(request, org_id)
                    
                    # 将组织ID添加到请求状态，供后续使用
                    request.state.current_organization_id = org_id
                else:
                    return Response(
                        content='{"error": "Access denied to organization"}',
                        status_code=status.HTTP_403_FORBIDDEN,
                        headers={"Content-Type": "application/json"}
                    )
            
            # 处理请求
            response = await call_next(request)
            
            return response
            
        except Exception as e:
            logger.error(f"Tenant context middleware error: {e}")
            # 如果设置租户上下文失败，不阻塞请求，但记录错误
            return await call_next(request)
    
    def _should_skip_path(self, path: str) -> bool:
        """判断路径是否需要跳过租户上下文设置"""
        # 完全匹配
        if path in self.excluded_paths:
            return True
        
        # 前缀匹配
        skip_prefixes = ['/docs', '/static', '/_internal', '/health']
        for prefix in skip_prefixes:
            if path.startswith(prefix):
                return True
                
        return False
    
    async def _extract_organization_id(self, request: Request) -> Optional[str]:
        """从请求中提取组织ID"""
        
        # 1. 从请求头中获取（优先级最高）
        org_id = request.headers.get('X-Organization-ID')
        if org_id:
            return org_id
        
        # 2. 从路径参数中获取
        if 'org_id' in request.path_params:
            return request.path_params['org_id']
        
        # 3. 从查询参数中获取
        org_id = request.query_params.get('org_id')
        if org_id:
            return org_id
        
        # 4. 从用户会话中推断默认组织
        user_id = getattr(request.state, 'user_id', None)
        if user_id:
            return await self._get_user_default_organization(user_id)
        
        return None
    
    async def _get_user_default_organization(self, user_id: str) -> Optional[str]:
        """获取用户的默认组织"""
        try:
            # 这里需要一个不依赖RLS的查询来获取用户组织
            # 可以直接查询organizationmember表
            async with get_session() as session:
                # 禁用RLS进行这个查询
                await session.exec(text("SET row_security = off"))
                
                user_orgs = await OrganizationCRUD.get_user_organizations(session, user_id)
                
                # 重新启用RLS
                await session.exec(text("SET row_security = on"))
                
                if user_orgs:
                    # 返回用户的第一个组织作为默认组织
                    return user_orgs[0].id
                    
        except Exception as e:
            logger.error(f"Failed to get user default organization: {e}")
        
        return None
    
    async def _validate_organization_access(self, request: Request, org_id: str) -> bool:
        """验证用户对组织的访问权限"""
        try:
            user_id = getattr(request.state, 'user_id', None)
            if not user_id:
                # 如果没有用户ID，可能是公开端点，允许访问
                return True
            
            async with get_session() as session:
                # 禁用RLS进行权限检查
                await session.exec(text("SET row_security = off"))
                
                user_orgs = await OrganizationCRUD.get_user_organizations(session, user_id)
                
                # 重新启用RLS
                await session.exec(text("SET row_security = on"))
                
                # 检查用户是否属于该组织
                return any(org.id == org_id for org in user_orgs)
                
        except Exception as e:
            logger.error(f"Failed to validate organization access: {e}")
            return False
    
    async def _set_tenant_context(self, request: Request, org_id: str):
        """设置数据库会话中的租户上下文"""
        try:
            # 获取当前请求的数据库会话
            session = getattr(request.state, 'db_session', None)
            
            if session and isinstance(session, AsyncSession):
                # 设置PostgreSQL会话变量，RLS策略会使用这个变量
                await session.exec(text(f"SELECT set_current_tenant('{org_id}')"))
                logger.debug(f"Set tenant context to organization: {org_id}")
            else:
                logger.warning("No database session found in request state")
                
        except Exception as e:
            logger.error(f"Failed to set tenant context: {e}")
            raise


async def add_tenant_context_middleware(app):
    """添加租户上下文中间件到应用"""
    app.add_middleware(TenantContextMiddleware)
    logger.info("Tenant context middleware added")


class TenantContextManager:
    """租户上下文管理工具类"""
    
    @staticmethod
    async def set_organization_context(session: AsyncSession, org_id: str):
        """手动设置组织上下文（用于后台任务等场景）"""
        try:
            await session.exec(text(f"SELECT set_current_tenant('{org_id}')"))
            logger.debug(f"Manually set tenant context to: {org_id}")
        except Exception as e:
            logger.error(f"Failed to manually set tenant context: {e}")
            raise
    
    @staticmethod
    async def clear_organization_context(session: AsyncSession):
        """清除组织上下文"""
        try:
            await session.exec(text("SELECT set_current_tenant('')"))
            logger.debug("Cleared tenant context")
        except Exception as e:
            logger.error(f"Failed to clear tenant context: {e}")
    
    @staticmethod
    async def get_current_organization(session: AsyncSession) -> Optional[str]:
        """获取当前组织上下文"""
        try:
            result = await session.exec(text("SELECT get_current_tenant()"))
            org_id = result.scalar()
            return org_id if org_id else None
        except Exception as e:
            logger.error(f"Failed to get current tenant context: {e}")
            return None
    
    @staticmethod
    async def bypass_rls(session: AsyncSession):
        """临时禁用RLS（谨慎使用，仅用于管理操作）"""
        try:
            await session.exec(text("SET row_security = off"))
            logger.warning("RLS has been disabled for this session")
        except Exception as e:
            logger.error(f"Failed to disable RLS: {e}")
    
    @staticmethod 
    async def enable_rls(session: AsyncSession):
        """重新启用RLS"""
        try:
            await session.exec(text("SET row_security = on"))
            logger.debug("RLS has been enabled for this session")
        except Exception as e:
            logger.error(f"Failed to enable RLS: {e}")


# 依赖注入函数：获取当前组织ID
async def get_current_organization_id(request: Request) -> Optional[str]:
    """依赖注入：获取当前请求的组织ID"""
    return getattr(request.state, 'current_organization_id', None)


# 依赖注入函数：要求必须有组织上下文
async def require_organization_context(request: Request) -> str:
    """依赖注入：要求必须有组织上下文，否则抛出异常"""
    org_id = getattr(request.state, 'current_organization_id', None)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context is required for this operation"
        )
    return org_id