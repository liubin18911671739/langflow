"""Multi-tenant CRUD operations for Folder model"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.database.models.folder.model import Folder, FolderCreate, FolderUpdate
from langflow.services.database.models.flow.model import Flow
from langflow.middleware.tenant_context import TenantContextManager


class FolderCRUD:
    """Multi-tenant CRUD operations for Folder model"""
    
    @staticmethod
    async def create_folder(
        session: AsyncSession,
        folder_data: FolderCreate,
        organization_id: str,
        user_id: str
    ) -> Folder:
        """创建新的文件夹"""
        # 确保在正确的租户上下文中
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 创建文件夹，自动包含organization_id
        folder = Folder(
            name=folder_data.name,
            description=folder_data.description,
            organization_id=organization_id,
            user_id=UUID(user_id)
        )
        
        session.add(folder)
        await session.commit()
        await session.refresh(folder)
        
        return folder
    
    @staticmethod
    async def get_folder_by_id(
        session: AsyncSession,
        folder_id: UUID,
        organization_id: str
    ) -> Optional[Folder]:
        """根据ID获取文件夹（自动应用RLS）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder).where(Folder.id == folder_id)
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_folder_by_name(
        session: AsyncSession,
        name: str,
        organization_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Folder]:
        """根据名称获取文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder).where(Folder.name == name)
        
        if user_id:
            stmt = stmt.where(Folder.user_id == UUID(user_id))
        
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_folders_by_user(
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        parent_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Folder]:
        """获取用户在指定组织中的文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder).where(Folder.user_id == UUID(user_id))
        
        # 根目录或子目录过滤
        if parent_id:
            stmt = stmt.where(Folder.parent_id == parent_id)
        else:
            stmt = stmt.where(Folder.parent_id.is_(None))
        
        stmt = stmt.offset(offset).limit(limit).order_by(Folder.name)
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def get_organization_folders(
        session: AsyncSession,
        organization_id: str,
        parent_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
        search_query: Optional[str] = None
    ) -> List[Folder]:
        """获取组织中的所有文件夹（管理员视图）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder)
        
        # 父文件夹过滤
        if parent_id:
            stmt = stmt.where(Folder.parent_id == parent_id)
        else:
            stmt = stmt.where(Folder.parent_id.is_(None))
        
        # 搜索过滤
        if search_query:
            search_filter = or_(
                Folder.name.ilike(f"%{search_query}%"),
                Folder.description.ilike(f"%{search_query}%")
            )
            stmt = stmt.where(search_filter)
        
        stmt = stmt.offset(offset).limit(limit).order_by(Folder.name)
        
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def get_folder_tree(
        session: AsyncSession,
        organization_id: str,
        user_id: Optional[str] = None,
        root_folder_id: Optional[UUID] = None
    ) -> List[dict]:
        """获取文件夹树形结构"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 构建基础查询
        stmt = select(Folder)
        
        if user_id:
            stmt = stmt.where(Folder.user_id == UUID(user_id))
        
        stmt = stmt.order_by(Folder.name)
        result = await session.exec(stmt)
        all_folders = list(result.fetchall())
        
        # 构建树形结构
        folder_map = {folder.id: folder for folder in all_folders}
        
        def build_tree(parent_id: Optional[UUID]) -> List[dict]:
            children = []
            for folder in all_folders:
                if folder.parent_id == parent_id:
                    folder_dict = {
                        "id": str(folder.id),
                        "name": folder.name,
                        "description": folder.description,
                        "user_id": str(folder.user_id),
                        "parent_id": str(folder.parent_id) if folder.parent_id else None,
                        "children": build_tree(folder.id)
                    }
                    children.append(folder_dict)
            return children
        
        return build_tree(root_folder_id)
    
    @staticmethod
    async def update_folder(
        session: AsyncSession,
        folder_id: UUID,
        folder_update: FolderUpdate,
        organization_id: str
    ) -> Optional[Folder]:
        """更新文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 由于RLS，这个查询只会返回属于当前组织的文件夹
        stmt = select(Folder).where(Folder.id == folder_id)
        result = await session.exec(stmt)
        folder = result.first()
        
        if not folder:
            return None
        
        # 检查父文件夹循环引用
        if folder_update.parent_id and folder_update.parent_id == folder.id:
            return None
        
        # 更新字段
        update_data = folder_update.model_dump(exclude_unset=True, exclude={"components", "flows"})
        for key, value in update_data.items():
            setattr(folder, key, value)
        
        await session.commit()
        await session.refresh(folder)
        
        return folder
    
    @staticmethod
    async def delete_folder(
        session: AsyncSession,
        folder_id: UUID,
        organization_id: str,
        force: bool = False
    ) -> bool:
        """删除文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder).where(Folder.id == folder_id)
        result = await session.exec(stmt)
        folder = result.first()
        
        if not folder:
            return False
        
        # 检查是否有子文件夹
        child_stmt = select(Folder).where(Folder.parent_id == folder_id)
        child_result = await session.exec(child_stmt)
        has_children = child_result.first() is not None
        
        # 检查是否有关联的流程
        flow_stmt = select(Flow).where(Flow.folder_id == folder_id)
        flow_result = await session.exec(flow_stmt)
        has_flows = flow_result.first() is not None
        
        # 如果有子项且不是强制删除，则不允许删除
        if (has_children or has_flows) and not force:
            return False
        
        # 如果强制删除，先处理子项
        if force:
            if has_children:
                # 删除所有子文件夹（递归）
                child_folders = await session.exec(child_stmt)
                for child_folder in child_folders:
                    await FolderCRUD.delete_folder(session, child_folder.id, organization_id, force=True)
            
            if has_flows:
                # 将流程移到根目录
                flows = await session.exec(flow_stmt)
                for flow in flows:
                    flow.folder_id = None
                    session.add(flow)
        
        await session.delete(folder)
        await session.commit()
        
        return True
    
    @staticmethod
    async def check_folder_name_exists(
        session: AsyncSession,
        name: str,
        organization_id: str,
        parent_id: Optional[UUID] = None,
        exclude_id: Optional[UUID] = None
    ) -> bool:
        """检查文件夹名称是否已存在（同一父文件夹下唯一）"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder).where(Folder.name == name)
        
        if parent_id:
            stmt = stmt.where(Folder.parent_id == parent_id)
        else:
            stmt = stmt.where(Folder.parent_id.is_(None))
        
        # 排除指定ID（用于更新时的检查）
        if exclude_id:
            stmt = stmt.where(Folder.id != exclude_id)
        
        result = await session.exec(stmt)
        return result.first() is not None
    
    @staticmethod
    async def move_folder(
        session: AsyncSession,
        folder_id: UUID,
        target_parent_id: Optional[UUID],
        organization_id: str
    ) -> Optional[Folder]:
        """移动文件夹到指定父文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 获取文件夹
        stmt = select(Folder).where(Folder.id == folder_id)
        result = await session.exec(stmt)
        folder = result.first()
        
        if not folder:
            return None
        
        # 检查目标父文件夹是否存在（如果不为None）
        if target_parent_id:
            parent_stmt = select(Folder).where(Folder.id == target_parent_id)
            parent_result = await session.exec(parent_stmt)
            target_parent = parent_result.first()
            
            if not target_parent:
                return None
            
            # 防止循环引用
            if await FolderCRUD._would_create_cycle(session, folder_id, target_parent_id):
                return None
        
        # 检查目标位置是否已有同名文件夹
        if await FolderCRUD.check_folder_name_exists(
            session, folder.name, organization_id, target_parent_id, folder_id
        ):
            return None
        
        # 更新文件夹的父ID
        folder.parent_id = target_parent_id
        await session.commit()
        await session.refresh(folder)
        
        return folder
    
    @staticmethod
    async def _would_create_cycle(
        session: AsyncSession,
        folder_id: UUID,
        target_parent_id: UUID
    ) -> bool:
        """检查移动操作是否会创建循环引用"""
        current_id = target_parent_id
        
        while current_id:
            if current_id == folder_id:
                return True
            
            stmt = select(Folder.parent_id).where(Folder.id == current_id)
            result = await session.exec(stmt)
            parent_id = result.first()
            current_id = parent_id
        
        return False
    
    @staticmethod
    async def get_folder_statistics(
        session: AsyncSession,
        organization_id: str
    ) -> dict:
        """获取组织的文件夹统计信息"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        # 总文件夹数
        total_stmt = select(func.count(Folder.id))
        total_result = await session.exec(total_stmt)
        total_folders = total_result.scalar() or 0
        
        # 根文件夹数
        root_stmt = select(func.count(Folder.id)).where(Folder.parent_id.is_(None))
        root_result = await session.exec(root_stmt)
        root_folders = root_result.scalar() or 0
        
        # 按用户统计（前5名）
        user_stats_stmt = select(
            Folder.user_id,
            func.count(Folder.id).label('count')
        ).group_by(Folder.user_id).order_by(func.count(Folder.id).desc()).limit(5)
        
        user_stats_result = await session.exec(user_stats_stmt)
        top_users = [
            {"user_id": str(user_id), "folder_count": count}
            for user_id, count in user_stats_result.fetchall()
        ]
        
        # 文件夹深度统计
        depth_stats = await FolderCRUD._calculate_folder_depths(session, organization_id)
        
        return {
            "total_folders": total_folders,
            "root_folders": root_folders,
            "max_depth": depth_stats.get("max_depth", 0),
            "average_depth": depth_stats.get("average_depth", 0),
            "top_users": top_users
        }
    
    @staticmethod
    async def _calculate_folder_depths(
        session: AsyncSession,
        organization_id: str
    ) -> dict:
        """计算文件夹深度统计"""
        # 获取所有文件夹
        stmt = select(Folder)
        result = await session.exec(stmt)
        folders = list(result.fetchall())
        
        folder_map = {folder.id: folder for folder in folders}
        depths = []
        
        def calculate_depth(folder_id: UUID, visited: set = None) -> int:
            if visited is None:
                visited = set()
            
            if folder_id in visited:
                return 0  # 防止循环引用
            
            visited.add(folder_id)
            folder = folder_map.get(folder_id)
            
            if not folder or not folder.parent_id:
                return 1
            
            return 1 + calculate_depth(folder.parent_id, visited)
        
        for folder in folders:
            depth = calculate_depth(folder.id)
            depths.append(depth)
        
        if not depths:
            return {"max_depth": 0, "average_depth": 0}
        
        return {
            "max_depth": max(depths),
            "average_depth": round(sum(depths) / len(depths), 2)
        }
    
    @staticmethod
    async def search_folders(
        session: AsyncSession,
        organization_id: str,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Folder]:
        """搜索文件夹"""
        await TenantContextManager.set_organization_context(session, organization_id)
        
        stmt = select(Folder).where(
            or_(
                Folder.name.ilike(f"%{query}%"),
                Folder.description.ilike(f"%{query}%")
            )
        )
        
        # 按用户过滤
        if user_id:
            stmt = stmt.where(Folder.user_id == UUID(user_id))
        
        stmt = stmt.limit(limit).order_by(Folder.name)
        
        result = await session.exec(stmt)
        return list(result.fetchall())