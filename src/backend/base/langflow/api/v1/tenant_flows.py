"""Multi-tenant aware Flow API endpoints"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlmodel import apaginate
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.api.utils import CurrentActiveUser, DbSession, remove_api_keys
from langflow.api.v1.schemas import FlowListCreate
from langflow.middleware.tenant_context import get_current_organization_id, require_organization_context
from langflow.services.database.models.flow.model import (
    Flow,
    FlowCreate,
    FlowRead,
    FlowUpdate,
)
from langflow.services.database.models.flow.crud import FlowCRUD
from langflow.utils.compression import compress_response

# build router
router = APIRouter(prefix="/tenant/flows", tags=["Tenant Flows"])


@router.post("/", response_model=FlowRead, status_code=201)
async def create_flow(
    *,
    session: DbSession,
    flow: FlowCreate,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
):
    """Create a new flow in the current organization context."""
    try:
        db_flow = await FlowCRUD.create_flow(
            session=session,
            flow_data=flow,
            organization_id=organization_id,
            user_id=str(current_user.id)
        )
        return db_flow
    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Flow name must be unique within the organization"
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/", response_model=list[FlowRead] | Page[FlowRead], status_code=200)
async def read_flows(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
    folder_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    params: Annotated[Params, Depends()] = None,
):
    """Retrieve flows in the current organization."""
    try:
        if folder_id:
            # Get flows in specific folder
            flows = await FlowCRUD.get_flows_by_user(
                session=session,
                user_id=str(current_user.id),
                organization_id=organization_id,
                folder_id=str(folder_id),
                limit=limit,
                offset=offset
            )
        else:
            # Get all user flows in organization
            flows = await FlowCRUD.get_flows_by_user(
                session=session,
                user_id=str(current_user.id),
                organization_id=organization_id,
                limit=limit,
                offset=offset
            )
        
        return compress_response([FlowRead.model_validate(flow, from_attributes=True) for flow in flows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/organization", response_model=list[FlowRead], status_code=200)
async def read_organization_flows(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    limit: int = 50,
    offset: int = 0,
    search_query: Optional[str] = None,
):
    """Retrieve all flows in the organization (admin view)."""
    try:
        flows = await FlowCRUD.get_organization_flows(
            session=session,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
            search_query=search_query
        )
        return compress_response([FlowRead.model_validate(flow, from_attributes=True) for flow in flows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/public", response_model=list[FlowRead], status_code=200)
async def read_public_flows(
    *,
    session: DbSession,
    limit: int = 50,
    offset: int = 0,
):
    """Retrieve public flows (cross-organization)."""
    try:
        flows = await FlowCRUD.get_public_flows(
            session=session,
            limit=limit,
            offset=offset
        )
        return compress_response([FlowRead.model_validate(flow, from_attributes=True) for flow in flows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/search", response_model=list[FlowRead], status_code=200)
async def search_flows(
    *,
    session: DbSession,
    query: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    user_id: Optional[str] = None,
    include_public: bool = True,
    limit: int = 20,
):
    """Search flows within organization and optionally include public flows."""
    try:
        flows = await FlowCRUD.search_flows(
            session=session,
            organization_id=organization_id,
            query=query,
            user_id=user_id or str(current_user.id),
            include_public=include_public,
            limit=limit
        )
        return compress_response([FlowRead.model_validate(flow, from_attributes=True) for flow in flows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/statistics", response_model=dict, status_code=200)
async def get_flow_statistics(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
):
    """Get organization flow statistics."""
    try:
        stats = await FlowCRUD.get_flow_statistics(
            session=session,
            organization_id=organization_id
        )
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{flow_id}", response_model=FlowRead, status_code=200)
async def read_flow(
    *,
    session: DbSession,
    flow_id: str,
    organization_id: str = Depends(require_organization_context),
):
    """Read a specific flow."""
    try:
        flow = await FlowCRUD.get_flow_by_id(
            session=session,
            flow_id=flow_id,
            organization_id=organization_id
        )
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return FlowRead.model_validate(flow, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{flow_id}", response_model=FlowRead, status_code=200)
async def update_flow(
    *,
    session: DbSession,
    flow_id: str,
    flow_update: FlowUpdate,
    organization_id: str = Depends(require_organization_context),
):
    """Update a flow."""
    try:
        updated_flow = await FlowCRUD.update_flow(
            session=session,
            flow_id=flow_id,
            flow_update=flow_update,
            organization_id=organization_id
        )
        if not updated_flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return FlowRead.model_validate(updated_flow, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Flow name or endpoint name must be unique within the organization"
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{flow_id}", status_code=200)
async def delete_flow(
    *,
    session: DbSession,
    flow_id: str,
    organization_id: str = Depends(require_organization_context),
):
    """Delete a flow."""
    try:
        success = await FlowCRUD.delete_flow(
            session=session,
            flow_id=flow_id,
            organization_id=organization_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Flow not found")
        return {"message": "Flow deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{flow_id}/duplicate", response_model=FlowRead, status_code=201)
async def duplicate_flow(
    *,
    session: DbSession,
    flow_id: str,
    new_name: str,
    organization_id: str = Depends(require_organization_context),
    current_user: CurrentActiveUser,
    target_folder_id: Optional[str] = None,
):
    """Duplicate a flow within the current organization."""
    try:
        duplicated_flow = await FlowCRUD.duplicate_flow(
            session=session,
            flow_id=flow_id,
            new_name=new_name,
            organization_id=organization_id,
            user_id=str(current_user.id),
            target_folder_id=target_folder_id
        )
        if not duplicated_flow:
            raise HTTPException(status_code=404, detail="Flow not found or duplication failed")
        return FlowRead.model_validate(duplicated_flow, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/{flow_id}/move", response_model=FlowRead, status_code=200)
async def move_flow_to_folder(
    *,
    session: DbSession,
    flow_id: str,
    target_folder_id: Optional[str],
    organization_id: str = Depends(require_organization_context),
):
    """Move a flow to a different folder."""
    try:
        moved_flow = await FlowCRUD.move_flow_to_folder(
            session=session,
            flow_id=flow_id,
            target_folder_id=target_folder_id,
            organization_id=organization_id
        )
        if not moved_flow:
            raise HTTPException(status_code=404, detail="Flow not found or move operation failed")
        return FlowRead.model_validate(moved_flow, from_attributes=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/batch/", response_model=list[FlowRead], status_code=201)
async def create_flows(
    *,
    session: DbSession,
    flow_list: FlowListCreate,
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
):
    """Create multiple flows."""
    try:
        created_flows = []
        for flow_data in flow_list.flows:
            flow = await FlowCRUD.create_flow(
                session=session,
                flow_data=flow_data,
                organization_id=organization_id,
                user_id=str(current_user.id)
            )
            created_flows.append(flow)
        
        return [FlowRead.model_validate(flow, from_attributes=True) for flow in created_flows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/upload/", response_model=list[FlowRead], status_code=201)
async def upload_file(
    *,
    session: DbSession,
    file: Annotated[UploadFile, File(...)],
    current_user: CurrentActiveUser,
    organization_id: str = Depends(require_organization_context),
    folder_id: Optional[str] = None,
):
    """Upload flows from a file."""
    try:
        contents = await file.read()
        data = orjson.loads(contents)
        
        flow_list = FlowListCreate(**data) if "flows" in data else FlowListCreate(flows=[FlowCreate(**data)])
        created_flows = []
        
        for flow_data in flow_list.flows:
            if folder_id:
                flow_data.folder_id = UUID(folder_id)
            
            flow = await FlowCRUD.create_flow(
                session=session,
                flow_data=flow_data,
                organization_id=organization_id,
                user_id=str(current_user.id)
            )
            created_flows.append(flow)
        
        return [FlowRead.model_validate(flow, from_attributes=True) for flow in created_flows]
    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="One or more flow names already exist in the organization"
            ) from e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download/", status_code=200)
async def download_flows(
    flow_ids: list[str],
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
):
    """Download flows as ZIP file."""
    try:
        flows = []
        for flow_id in flow_ids:
            flow = await FlowCRUD.get_flow_by_id(
                session=session,
                flow_id=flow_id,
                organization_id=organization_id
            )
            if flow:
                flows.append(flow)
        
        if not flows:
            raise HTTPException(status_code=404, detail="No flows found.")
        
        flows_without_api_keys = [remove_api_keys(flow.model_dump()) for flow in flows]
        
        if len(flows_without_api_keys) > 1:
            # Create ZIP file
            zip_stream = io.BytesIO()
            
            with zipfile.ZipFile(zip_stream, "w") as zip_file:
                for flow in flows_without_api_keys:
                    flow_json = json.dumps(jsonable_encoder(flow))
                    zip_file.writestr(f"{flow['name']}.json", flow_json)
            
            zip_stream.seek(0)
            
            current_time = datetime.now(tz=timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
            filename = f"{current_time}_langflow_flows.zip"
            
            return StreamingResponse(
                zip_stream,
                media_type="application/x-zip-compressed",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        
        return flows_without_api_keys[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e