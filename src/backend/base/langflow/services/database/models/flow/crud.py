"""Multi-tenant CRUD operations for Flow model"""
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.database.models.flow.model import Flow, FlowCreate, FlowUpdate
from langflow.services.database.models.folder.model import Folder
from langflow.middleware.tenant_context import TenantContextManager


class FlowCRUD:
    """Multi-tenant CRUD operations for Flow model"""
    
    @staticmethod
    async def create_flow(
        session: AsyncSession,
        flow_data: FlowCreate,
        organization_id: str,
        user_id: str
    ) -> Flow:
        """创建新的流程"""
        # 确保在正确的租户上下文中
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 创建流程，自动包含organization_id
        flow = Flow(
            **flow_data.model_dump(exclude_unset=True),
            organization_id=organization_id,
            user_id=user_id
        )
        
        session.add(flow)
        await session.commit()
        await session.refresh(flow)
        
        return flow
    
    @staticmethod
    async def get_flow_by_id(
        session: AsyncSession,
        flow_id: str,
        organization_id: str
    ) -> Optional[Flow]:
        """根据ID获取流程（自动应用RLS）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Flow).where(Flow.id == flow_id)
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_flows_by_user(
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        folder_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Flow]:
        """获取用户在指定组织中的流程"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Flow).where(Flow.user_id == user_id)
        
        if folder_id:
            stmt = stmt.where(Flow.folder_id == folder_id)
        
        stmt = stmt.offset(offset).limit(limit).order_by(Flow.updated_at.desc())
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def get_organization_flows(
        session: AsyncSession,
        organization_id: str,
        limit: int = 50,
        offset: int = 0,
        search_query: Optional[str] = None
    ) -> List[Flow]:
        """获取组织中的所有流程（管理员视图）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Flow)
        
        if search_query:
            search_filter = or_(
                Flow.name.ilike(f"%{search_query}%"),
                Flow.description.ilike(f"%{search_query}%")
            )
            stmt = stmt.where(search_filter)
        
        stmt = stmt.offset(offset).limit(limit).order_by(Flow.updated_at.desc())
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def update_flow(
        session: AsyncSession,
        flow_id: str,
        flow_update: FlowUpdate,
        organization_id: str
    ) -> Optional[Flow]:
        """更新流程"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 由于RLS，这个查询只会返回属于当前组织的流程
        stmt = select(Flow).where(Flow.id == flow_id)
        result = await session.exec(stmt)
        flow = result.first()
        
        if not flow:
            return None
        
        # 更新字段
        for key, value in flow_update.model_dump(exclude_unset=True).items():
            setattr(flow, key, value)
        
        await session.commit()
        await session.refresh(flow)
        
        return flow
    
    @staticmethod
    async def delete_flow(
        session: AsyncSession,
        flow_id: str,
        organization_id: str
    ) -> bool:
        """删除流程"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Flow).where(Flow.id == flow_id)
        result = await session.exec(stmt)
        flow = result.first()
        
        if not flow:
            return False
        
        await session.delete(flow)
        await session.commit()
        
        return True
    
    @staticmethod
    async def get_public_flows(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0
    ) -> List[Flow]:
        """获取公共流程（跨组织）"""
        # 临时禁用RLS以获取公共流程
        await TenantContextManager.bypass_rls(session)
        
        try:
            stmt = select(Flow).where(
                Flow.access_type == 'PUBLIC'
            ).offset(offset).limit(limit).order_by(Flow.updated_at.desc())
            
            result = await session.exec(stmt)
            return list(result.fetchall())
        finally:
            # 重新启用RLS
            await TenantContextManager.enable_rls(session)
    
    @staticmethod
    async def duplicate_flow(
        session: AsyncSession,
        flow_id: str,
        new_name: str,
        organization_id: str,
        user_id: str,
        target_folder_id: Optional[str] = None
    ) -> Optional[Flow]:
        """复制流程到当前组织"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 获取原始流程
        stmt = select(Flow).where(Flow.id == flow_id)
        result = await session.exec(stmt)
        original_flow = result.first()
        
        if not original_flow:
            return None
        
        # 创建副本
        flow_copy = Flow(
            name=new_name,
            description=original_flow.description,
            data=original_flow.data,
            icon=original_flow.icon,
            icon_bg_color=original_flow.icon_bg_color,
            gradient=original_flow.gradient,
            tags=original_flow.tags,
            is_component=original_flow.is_component,
            organization_id=organization_id,
            user_id=user_id,
            folder_id=target_folder_id or original_flow.folder_id
        )
        
        session.add(flow_copy)
        await session.commit()
        await session.refresh(flow_copy)
        
        return flow_copy
    
    @staticmethod
    async def move_flow_to_folder(
        session: AsyncSession,
        flow_id: str,
        target_folder_id: Optional[str],
        organization_id: str
    ) -> Optional[Flow]:
        """移动流程到指定文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 获取流程
        stmt = select(Flow).where(Flow.id == flow_id)
        result = await session.exec(stmt)
        flow = result.first()
        
        if not flow:
            return None
        
        # 如果指定了目标文件夹，验证文件夹是否属于同一组织
        if target_folder_id:
            folder_stmt = select(Folder).where(Folder.id == target_folder_id)
            folder_result = await session.exec(folder_stmt)
            target_folder = folder_result.first()
            
            if not target_folder:
                return None  # 文件夹不存在或不属于当前组织
        
        # 更新流程的文件夹
        flow.folder_id = target_folder_id
        await session.commit()
        await session.refresh(flow)
        
        return flow
    
    @staticmethod
    async def get_flow_statistics(
        session: AsyncSession,
        organization_id: str
    ) -> dict:
        """获取组织的流程统计信息"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 总流程数
        total_stmt = select(func.count(Flow.id))
        total_result = await session.exec(total_stmt)
        total_flows = total_result.scalar() or 0
        
        # 组件数
        components_stmt = select(func.count(Flow.id)).where(Flow.is_component == True)
        components_result = await session.exec(components_stmt)
        total_components = components_result.scalar() or 0
        
        # 公共流程数
        public_stmt = select(func.count(Flow.id)).where(Flow.access_type == 'PUBLIC')
        public_result = await session.exec(public_stmt)
        public_flows = public_result.scalar() or 0
        
        # 最近创建的流程（按用户分组）
        recent_stmt = select(
            func.count(Flow.id).label('count'),
            Flow.user_id
        ).group_by(Flow.user_id).order_by(func.count(Flow.id).desc()).limit(5)
        
        recent_result = await session.exec(recent_stmt)
        top_creators = [
            {"user_id": str(user_id), "flow_count": count}
            for count, user_id in recent_result.fetchall()
        ]
        
        return {
            "total_flows": total_flows,
            "total_components": total_components,
            "public_flows": public_flows,
            "top_creators": top_creators
        }
    
    @staticmethod
    async def search_flows(
        session: AsyncSession,
        organization_id: str,
        query: str,
        user_id: Optional[str] = None,
        include_public: bool = True,
        limit: int = 20
    ) -> List[Flow]:
        """搜索流程（支持跨组织的公共流程）"""
        flows = []
        
        # 搜索当前组织的流程
        await TenantContextManager.set_organization_context(session, organization_id)
        
        org_stmt = select(Flow).where(
            or_(
                Flow.name.ilike(f"%{query}%"),
                Flow.description.ilike(f"%{query}%")
            )
        )
        
        if user_id:
            org_stmt = org_stmt.where(Flow.user_id == user_id)
        
        org_stmt = org_stmt.limit(limit)
        org_result = await session.exec(org_stmt)
        flows.extend(org_result.fetchall())
        
        # 如果启用了公共流程搜索且结果不足，搜索公共流程
        if include_public and len(flows) < limit:
            remaining_limit = limit - len(flows)
            
            # 临时禁用RLS搜索公共流程
            await TenantContextManager.bypass_rls(session)
            
            try:
                public_stmt = select(Flow).where(
                    and_(
                        Flow.access_type == 'PUBLIC',
                        or_(
                            Flow.name.ilike(f"%{query}%"),
                            Flow.description.ilike(f"%{query}%")
                        )
                    )
                ).limit(remaining_limit)
                
                public_result = await session.exec(public_stmt)
                flows.extend(public_result.fetchall())
            finally:
                await TenantContextManager.enable_rls(session)
        
        return flows[:limit]