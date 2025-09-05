"""Multi-tenant CRUD operations for Variable model"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.database.models.variable.model import Variable, VariableCreate, VariableUpdate
from langflow.middleware.tenant_context import TenantContextManager


class VariableCRUD:
    """Multi-tenant CRUD operations for Variable model"""
    
    @staticmethod
    async def create_variable(
        session: AsyncSession,
        variable_data: VariableCreate,
        organization_id: str,
        user_id: str
    ) -> Variable:
        """创建新的变量"""
        # 确保在正确的租户上下文中
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 创建变量，自动包含organization_id
        variable = Variable(
            **variable_data.model_dump(exclude_unset=True),
            organization_id=organization_id,
            user_id=UUID(user_id)
        )
        
        session.add(variable)
        await session.commit()
        await session.refresh(variable)
        
        return variable
    
    @staticmethod
    async def get_variable_by_id(
        session: AsyncSession,
        variable_id: UUID,
        organization_id: str
    ) -> Optional[Variable]:
        """根据ID获取变量（自动应用RLS）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(Variable.id == variable_id)
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_variable_by_name(
        session: AsyncSession,
        name: str,
        organization_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Variable]:
        """根据名称获取变量（支持用户级别过滤）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(Variable.name == name)
        
        if user_id:
            stmt = stmt.where(Variable.user_id == UUID(user_id))
        
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_variables_by_user(
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Variable]:
        """获取用户在指定组织中的变量"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(
            Variable.user_id == UUID(user_id)
        ).offset(offset).limit(limit).order_by(Variable.updated_at.desc())
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def get_organization_variables(
        session: AsyncSession,
        organization_id: str,
        variable_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        search_query: Optional[str] = None
    ) -> List[Variable]:
        """获取组织中的所有变量（管理员视图）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable)
        
        # 按类型过滤
        if variable_type:
            stmt = stmt.where(Variable.type == variable_type)
        
        # 搜索过滤
        if search_query:
            search_filter = or_(
                Variable.name.ilike(f"%{search_query}%")
            )
            stmt = stmt.where(search_filter)
        
        stmt = stmt.offset(offset).limit(limit).order_by(Variable.updated_at.desc())
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def update_variable(
        session: AsyncSession,
        variable_id: UUID,
        variable_update: VariableUpdate,
        organization_id: str
    ) -> Optional[Variable]:
        """更新变量"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 由于RLS，这个查询只会返回属于当前组织的变量
        stmt = select(Variable).where(Variable.id == variable_id)
        result = await session.exec(stmt)
        variable = result.first()
        
        if not variable:
            return None
        
        # 更新字段
        update_data = variable_update.model_dump(exclude_unset=True, exclude={"id"})
        for key, value in update_data.items():
            setattr(variable, key, value)
        
        await session.commit()
        await session.refresh(variable)
        
        return variable
    
    @staticmethod
    async def delete_variable(
        session: AsyncSession,
        variable_id: UUID,
        organization_id: str
    ) -> bool:
        """删除变量"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(Variable.id == variable_id)
        result = await session.exec(stmt)
        variable = result.first()
        
        if not variable:
            return False
        
        await session.delete(variable)
        await session.commit()
        
        return True
    
    @staticmethod
    async def check_variable_name_exists(
        session: AsyncSession,
        name: str,
        organization_id: str,
        user_id: str,
        exclude_id: Optional[UUID] = None
    ) -> bool:
        """检查变量名称是否已存在（同一用户和组织内唯一）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(
            and_(
                Variable.name == name,
                Variable.user_id == UUID(user_id)
            )
        )
        
        # 排除指定ID（用于更新时的检查）
        if exclude_id:
            stmt = stmt.where(Variable.id != exclude_id)
        
        result = await session.exec(stmt)
        return result.first() is not None
    
    @staticmethod
    async def get_variables_by_type(
        session: AsyncSession,
        variable_type: str,
        organization_id: str,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Variable]:
        """根据类型获取变量"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(Variable.type == variable_type)
        
        if user_id:
            stmt = stmt.where(Variable.user_id == UUID(user_id))
        
        stmt = stmt.limit(limit).order_by(Variable.name)
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def get_variable_statistics(
        session: AsyncSession,
        organization_id: str
    ) -> dict:
        """获取组织的变量统计信息"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 总变量数
        total_stmt = select(func.count(Variable.id))
        total_result = await session.exec(total_stmt)
        total_variables = total_result.scalar() or 0
        
        # 按类型统计
        type_stats_stmt = select(
            Variable.type,
            func.count(Variable.id).label('count')
        ).group_by(Variable.type)
        
        type_stats_result = await session.exec(type_stats_stmt)
        type_stats = {
            var_type: count for var_type, count in type_stats_result.fetchall()
        }
        
        # 按用户统计（前5名）
        user_stats_stmt = select(
            Variable.user_id,
            func.count(Variable.id).label('count')
        ).group_by(Variable.user_id).order_by(func.count(Variable.id).desc()).limit(5)
        
        user_stats_result = await session.exec(user_stats_stmt)
        top_users = [
            {"user_id": str(user_id), "variable_count": count}
            for user_id, count in user_stats_result.fetchall()
        ]
        
        return {
            "total_variables": total_variables,
            "type_statistics": type_stats,
            "top_users": top_users
        }
    
    @staticmethod
    async def duplicate_variable(
        session: AsyncSession,
        variable_id: UUID,
        new_name: str,
        organization_id: str,
        user_id: str
    ) -> Optional[Variable]:
        """复制变量"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 获取原始变量
        stmt = select(Variable).where(Variable.id == variable_id)
        result = await session.exec(stmt)
        original_variable = result.first()
        
        if not original_variable:
            return None
        
        # 检查新名称是否已存在
        if await VariableCRUD.check_variable_name_exists(session, new_name, organization_id, user_id):
            return None
        
        # 创建副本
        variable_copy = Variable(
            name=new_name,
            value=original_variable.value,
            default_fields=original_variable.default_fields,
            type=original_variable.type,
            organization_id=organization_id,
            user_id=UUID(user_id)
        )
        
        session.add(variable_copy)
        await session.commit()
        await session.refresh(variable_copy)
        
        return variable_copy
    
    @staticmethod
    async def search_variables(
        session: AsyncSession,
        organization_id: str,
        query: str,
        variable_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Variable]:
        """搜索变量"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Variable).where(
            Variable.name.ilike(f"%{query}%")
        )
        
        # 按类型过滤
        if variable_type:
            stmt = stmt.where(Variable.type == variable_type)
        
        # 按用户过滤
        if user_id:
            stmt = stmt.where(Variable.user_id == UUID(user_id))
        
        stmt = stmt.limit(limit).order_by(Variable.name)
        
        result = await session.exec(stmt)
        return list(result.fetchall())