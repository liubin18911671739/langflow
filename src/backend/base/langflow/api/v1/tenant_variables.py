"""Multi-tenant aware Variables API endpoints"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.middleware.tenant_context import require_organization_context
from langflow.services.database.models.variable.model import (
    Variable,
    VariableCreate,
    VariableRead,
    VariableUpdate,
)
from langflow.services.database.models.variable.crud import VariableCRUD

router = APIRouter(prefix="/tenant/variables", tags=["Tenant Variables"])


@router.post("/", response_model=VariableRead, status_code=201)
async def create_variable(
    *,
    session: DbSession,
    variable: VariableCreate,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
):
    """Create a new variable in the current organization."""
    try:
        if not variable.name or not variable.value:
            raise HTTPException(
                status_code=400,
                detail="Variable name and value cannot be empty"
            )
        
        # Check if variable name already exists for this user in organization
        if await VariableCRUD.check_variable_name_exists(
            session=session,
            name=variable.name,
            organization_id=organization_id,
            user_id=str(current_user.id)
        ):
            raise HTTPException(
                status_code=400,
                detail="Variable name already exists for this user in the organization"
            )
        
        db_variable = await VariableCRUD.create_variable(
            session=session,
            variable_data=variable,
            organization_id=organization_id,
            user_id=str(current_user.id)
        )
        return VariableRead.model_validate(db_variable, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=List[VariableRead], status_code=200)
async def read_variables(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
    limit: int = 50,
    offset: int = 0,
):
    """Get all variables for the current user in the organization."""
    try:
        variables = await VariableCRUD.get_variables_by_user(
            session=session,
            user_id=str(current_user.id),
            organization_id=organization_id,
            limit=limit,
            offset=offset
        )
        return [VariableRead.model_validate(variable, from_attributes=True) for variable in variables]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/organization", response_model=List[VariableRead], status_code=200)
async def read_organization_variables(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    variable_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    search_query: Optional[str] = None,
):
    """Get all variables in the organization (admin view)."""
    try:
        variables = await VariableCRUD.get_organization_variables(
            session=session,
            organization_id=organization_id,
            variable_type=variable_type,
            limit=limit,
            offset=offset,
            search_query=search_query
        )
        return [VariableRead.model_validate(variable, from_attributes=True) for variable in variables]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/by-type/{variable_type}", response_model=List[VariableRead], status_code=200)
async def get_variables_by_type(
    *,
    session: DbSession,
    variable_type: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    user_id: Optional[str] = None,
    limit: int = 50,
):
    """Get variables by type."""
    try:
        variables = await VariableCRUD.get_variables_by_type(
            session=session,
            variable_type=variable_type,
            organization_id=organization_id,
            user_id=user_id or str(current_user.id),
            limit=limit
        )
        return [VariableRead.model_validate(variable, from_attributes=True) for variable in variables]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/statistics", response_model=dict, status_code=200)
async def get_variable_statistics(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
):
    """Get organization variable statistics."""
    try:
        stats = await VariableCRUD.get_variable_statistics(
            session=session,
            organization_id=organization_id
        )
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search", response_model=List[VariableRead], status_code=200)
async def search_variables(
    *,
    session: DbSession,
    query: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    variable_type: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 20,
):
    """Search variables in the organization."""
    try:
        variables = await VariableCRUD.search_variables(
            session=session,
            organization_id=organization_id,
            query=query,
            variable_type=variable_type,
            user_id=user_id or str(current_user.id),
            limit=limit
        )
        return [VariableRead.model_validate(variable, from_attributes=True) for variable in variables]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{variable_id}", response_model=VariableRead, status_code=200)
async def read_variable(
    *,
    session: DbSession,
    variable_id: UUID,
    organization_id: str = Depends(require_organization_context),
):
    """Read a specific variable."""
    try:
        variable = await VariableCRUD.get_variable_by_id(
            session=session,
            variable_id=variable_id,
            organization_id=organization_id
        )
        if not variable:
            raise HTTPException(status_code=404, detail="Variable not found")
        return VariableRead.model_validate(variable, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/by-name/{variable_name}", response_model=VariableRead, status_code=200)
async def get_variable_by_name(
    *,
    session: DbSession,
    variable_name: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    user_id: Optional[str] = None,
):
    """Get variable by name."""
    try:
        variable = await VariableCRUD.get_variable_by_name(
            session=session,
            name=variable_name,
            organization_id=organization_id,
            user_id=user_id or str(current_user.id)
        )
        if not variable:
            raise HTTPException(status_code=404, detail="Variable not found")
        return VariableRead.model_validate(variable, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{variable_id}", response_model=VariableRead, status_code=200)
async def update_variable(
    *,
    session: DbSession,
    variable_id: UUID,
    variable_update: VariableUpdate,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
):
    """Update a variable."""
    try:
        # If name is being changed, check uniqueness
        if variable_update.name:
            if await VariableCRUD.check_variable_name_exists(
                session=session,
                name=variable_update.name,
                organization_id=organization_id,
                user_id=str(current_user.id),
                exclude_id=variable_id
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Variable name already exists for this user in the organization"
                )
        
        updated_variable = await VariableCRUD.update_variable(
            session=session,
            variable_id=variable_id,
            variable_update=variable_update,
            organization_id=organization_id
        )
        if not updated_variable:
            raise HTTPException(status_code=404, detail="Variable not found")
        return VariableRead.model_validate(updated_variable, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{variable_id}", status_code=200)
async def delete_variable(
    *,
    session: DbSession,
    variable_id: UUID,
    organization_id: str = Depends(require_organization_context),
):
    """Delete a variable."""
    try:
        success = await VariableCRUD.delete_variable(
            session=session,
            variable_id=variable_id,
            organization_id=organization_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Variable not found")
        return {"message": "Variable deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{variable_id}/duplicate", response_model=VariableRead, status_code=201)
async def duplicate_variable(
    *,
    session: DbSession,
    variable_id: UUID,
    new_name: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
):
    """Duplicate a variable within the current organization."""
    try:
        duplicated_variable = await VariableCRUD.duplicate_variable(
            session=session,
            variable_id=variable_id,
            new_name=new_name,
            organization_id=organization_id,
            user_id=str(current_user.id)
        )
        if not duplicated_variable:
            raise HTTPException(
                status_code=400,
                detail="Variable not found or name already exists"
            )
        return VariableRead.model_validate(duplicated_variable, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e