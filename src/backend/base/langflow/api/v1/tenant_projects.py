"""Multi-tenant aware Projects (Folders) API endpoints"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.middleware.tenant_context import require_organization_context
from langflow.services.database.models.folder.model import (
    Folder,
    FolderCreate,
    FolderRead,
    FolderUpdate,
)
from langflow.services.database.models.folder.crud import FolderCRUD

router = APIRouter(prefix="/tenant/projects", tags=["Tenant Projects"])


@router.post("/", response_model=FolderRead, status_code=201)
async def create_project(
    *,
    session: DbSession,
    project: FolderCreate,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
):
    """Create a new project (folder) in the current organization."""
    try:
        # Check if name already exists in organization
        if await FolderCRUD.check_folder_name_exists(
            session=session,
            name=project.name,
            organization_id=organization_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Project name already exists in organization"
            )
        
        folder = await FolderCRUD.create_folder(
            session=session,
            folder_data=project,
            organization_id=organization_id,
            user_id=str(current_user.id)
        )
        return FolderRead.model_validate(folder, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=List[FolderRead], status_code=200)
async def read_projects(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
    parent_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    search_query: Optional[str] = None,
):
    """Get projects for the current user in the organization."""
    try:
        folders = await FolderCRUD.get_folders_by_user(
            session=session,
            user_id=str(current_user.id),
            organization_id=organization_id,
            parent_id=parent_id,
            limit=limit,
            offset=offset
        )
        return [FolderRead.model_validate(folder, from_attributes=True) for folder in folders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/organization", response_model=List[FolderRead], status_code=200)
async def read_organization_projects(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    parent_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    search_query: Optional[str] = None,
):
    """Get all projects in the organization (admin view)."""
    try:
        folders = await FolderCRUD.get_organization_folders(
            session=session,
            organization_id=organization_id,
            parent_id=parent_id,
            limit=limit,
            offset=offset,
            search_query=search_query
        )
        return [FolderRead.model_validate(folder, from_attributes=True) for folder in folders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tree", response_model=List[dict], status_code=200)
async def get_folder_tree(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    root_folder_id: Optional[UUID] = None,
):
    """Get folder tree structure."""
    try:
        tree = await FolderCRUD.get_folder_tree(
            session=session,
            organization_id=organization_id,
            user_id=str(current_user.id),
            root_folder_id=root_folder_id
        )
        return tree
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/statistics", response_model=dict, status_code=200)
async def get_folder_statistics(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
):
    """Get organization folder statistics."""
    try:
        stats = await FolderCRUD.get_folder_statistics(
            session=session,
            organization_id=organization_id
        )
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search", response_model=List[FolderRead], status_code=200)
async def search_folders(
    *,
    session: DbSession,
    query: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    user_id: Optional[str] = None,
    limit: int = 20,
):
    """Search folders in the organization."""
    try:
        folders = await FolderCRUD.search_folders(
            session=session,
            organization_id=organization_id,
            query=query,
            user_id=user_id or str(current_user.id),
            limit=limit
        )
        return [FolderRead.model_validate(folder, from_attributes=True) for folder in folders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{project_id}", response_model=FolderRead, status_code=200)
async def read_project(
    *,
    session: DbSession,
    project_id: UUID,
    organization_id: str = Depends(require_organization_context),
):
    """Read a specific project."""
    try:
        folder = await FolderCRUD.get_folder_by_id(
            session=session,
            folder_id=project_id,
            organization_id=organization_id
        )
        if not folder:
            raise HTTPException(status_code=404, detail="Project not found")
        return FolderRead.model_validate(folder, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{project_id}", response_model=FolderRead, status_code=200)
async def update_project(
    *,
    session: DbSession,
    project_id: UUID,
    folder_update: FolderUpdate,
    organization_id: str = Depends(require_organization_context),
):
    """Update a project."""
    try:
        # If name is being changed, check uniqueness
        if folder_update.name:
            if await FolderCRUD.check_folder_name_exists(
                session=session,
                name=folder_update.name,
                organization_id=organization_id,
                parent_id=folder_update.parent_id,
                exclude_id=project_id
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Project name already exists in the target location"
                )
        
        updated_folder = await FolderCRUD.update_folder(
            session=session,
            folder_id=project_id,
            folder_update=folder_update,
            organization_id=organization_id
        )
        if not updated_folder:
            raise HTTPException(status_code=404, detail="Project not found")
        return FolderRead.model_validate(updated_folder, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{project_id}", status_code=200)
async def delete_project(
    *,
    session: DbSession,
    project_id: UUID,
    organization_id: str = Depends(require_organization_context),
    force: bool = False,
):
    """Delete a project."""
    try:
        success = await FolderCRUD.delete_folder(
            session=session,
            folder_id=project_id,
            organization_id=organization_id,
            force=force
        )
        if not success:
            if force:
                raise HTTPException(status_code=404, detail="Project not found")
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Project contains subfolders or flows. Use force=true to delete anyway."
                )
        return {"message": "Project deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{project_id}/move", response_model=FolderRead, status_code=200)
async def move_project(
    *,
    session: DbSession,
    project_id: UUID,
    target_parent_id: Optional[UUID],
    organization_id: str = Depends(require_organization_context),
):
    """Move a project to a different parent folder."""
    try:
        moved_folder = await FolderCRUD.move_folder(
            session=session,
            folder_id=project_id,
            target_parent_id=target_parent_id,
            organization_id=organization_id
        )
        if not moved_folder:
            raise HTTPException(
                status_code=400,
                detail="Cannot move folder - would create cycle, target not found, or name conflict"
            )
        return FolderRead.model_validate(moved_folder, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e