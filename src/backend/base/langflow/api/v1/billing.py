"""Billing and subscription management API endpoints"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, validator
from sqlmodel.ext.asyncio import AsyncSession

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.billing.stripe_service import StripeService
from langflow.services.billing.usage_service import UsageService
from langflow.services.database.models.subscription.crud import (
    OrganizationCRUD, SubscriptionCRUD, InvoiceCRUD, UsageMetricCRUD
)
from langflow.services.database.models.subscription.model import (
    OrganizationCreate, OrganizationRead, SubscriptionPlanRead, 
    SubscriptionRead, UsageMetricRead, UsageSummary, MetricType
)
from langflow.services.deps import get_settings_service

router = APIRouter(tags=["Billing"], prefix="/billing")
security = HTTPBearer()


# Pydantic模型用于API请求
class CreateSubscriptionRequest(BaseModel):
    plan_id: str
    payment_method_id: Optional[str] = None
    is_yearly: bool = False
    trial_days: Optional[int] = None


class UpdateSubscriptionRequest(BaseModel):
    plan_id: str
    proration_behavior: str = "create_prorations"


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


class UsageTrackingRequest(BaseModel):
    metric_type: MetricType
    value: int = 1
    metadata: Optional[dict] = None


class BillingPortalRequest(BaseModel):
    return_url: str


# 组织管理端点
@router.post("/organizations", response_model=OrganizationRead, status_code=201)
async def create_organization(
    request: CreateOrganizationRequest,
    current_user: CurrentActiveUser,
    session: DbSession
) -> OrganizationRead:
    """创建新组织"""
    try:
        # 检查slug是否已存在
        existing_org = await OrganizationCRUD.get_organization_by_slug(session, request.slug)
        if existing_org:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization slug already exists"
            )
        
        org = await OrganizationCRUD.create_organization(
            session=session,
            name=request.name,
            slug=request.slug,
            owner_id=str(current_user.id),
            description=request.description
        )
        
        return OrganizationRead.model_validate(org)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create organization: {str(e)}"
        )


@router.get("/organizations", response_model=List[OrganizationRead])
async def list_user_organizations(
    current_user: CurrentActiveUser,
    session: DbSession
) -> List[OrganizationRead]:
    """获取用户所属的组织列表"""
    try:
        organizations = await OrganizationCRUD.get_user_organizations(session, str(current_user.id))
        return [OrganizationRead.model_validate(org) for org in organizations]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch organizations: {str(e)}"
        )


@router.get("/organizations/{org_id}", response_model=OrganizationRead)
async def get_organization(
    org_id: str,
    current_user: CurrentActiveUser,
    session: DbSession
) -> OrganizationRead:
    """获取组织详情"""
    try:
        org = await OrganizationCRUD.get_organization_by_id(session, org_id)
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found"
            )
        
        # 检查用户是否有权限访问该组织
        user_orgs = await OrganizationCRUD.get_user_organizations(session, str(current_user.id))
        if org.id not in [user_org.id for user_org in user_orgs]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return OrganizationRead.model_validate(org)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch organization: {str(e)}"
        )


# 订阅计划端点
@router.get("/plans", response_model=List[SubscriptionPlanRead])
async def list_subscription_plans(session: DbSession) -> List[SubscriptionPlanRead]:
    """获取可用的订阅计划列表"""
    try:
        plans = await SubscriptionCRUD.get_plans(session)
        return [SubscriptionPlanRead.model_validate(plan) for plan in plans]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch plans: {str(e)}"
        )


# 订阅管理端点
@router.post("/organizations/{org_id}/subscription", status_code=201)
async def create_subscription(
    org_id: str,
    request: CreateSubscriptionRequest,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """为组织创建订阅"""
    try:
        # 验证组织权限
        org = await OrganizationCRUD.get_organization_by_id(session, org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        # 检查是否已有激活订阅
        existing_sub = await SubscriptionCRUD.get_organization_subscription(session, org_id)
        if existing_sub:
            raise HTTPException(
                status_code=400, 
                detail="Organization already has an active subscription"
            )
        
        # 创建Stripe服务实例
        stripe_service = StripeService(get_settings_service())
        
        # 创建订阅
        result = await stripe_service.create_subscription(
            session=session,
            organization_id=org_id,
            plan_id=request.plan_id,
            payment_method_id=request.payment_method_id,
            trial_days=request.trial_days,
            is_yearly=request.is_yearly
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.get("/organizations/{org_id}/subscription", response_model=SubscriptionRead)
async def get_organization_subscription(
    org_id: str,
    current_user: CurrentActiveUser,
    session: DbSession
) -> SubscriptionRead:
    """获取组织的当前订阅"""
    try:
        subscription = await SubscriptionCRUD.get_organization_subscription(session, org_id)
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )
        
        return SubscriptionRead.model_validate(subscription)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch subscription: {str(e)}"
        )


@router.put("/organizations/{org_id}/subscription")
async def update_subscription(
    org_id: str,
    request: UpdateSubscriptionRequest,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """更新组织订阅"""
    try:
        stripe_service = StripeService(get_settings_service())
        
        updated_subscription = await stripe_service.update_subscription(
            session=session,
            subscription_id=org_id,  # 这里需要调整逻辑
            new_plan_id=request.plan_id,
            proration_behavior=request.proration_behavior
        )
        
        return {
            "message": "Subscription updated successfully",
            "subscription_id": updated_subscription.id
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update subscription: {str(e)}"
        )


@router.delete("/organizations/{org_id}/subscription")
async def cancel_subscription(
    org_id: str,
    cancel_immediately: bool = False,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """取消组织订阅"""
    try:
        stripe_service = StripeService(get_settings_service())
        
        updated_subscription = await stripe_service.cancel_subscription(
            session=session,
            subscription_id=org_id,  # 这里需要调整逻辑
            cancel_immediately=cancel_immediately
        )
        
        return {
            "message": "Subscription canceled successfully",
            "cancel_at_period_end": updated_subscription.cancel_at_period_end
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel subscription: {str(e)}"
        )


# 使用量追踪端点
@router.get("/organizations/{org_id}/usage", response_model=UsageSummary)
async def get_usage_summary(
    org_id: str,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    current_user: CurrentActiveUser,
    session: DbSession
) -> UsageSummary:
    """获取组织使用量汇总"""
    try:
        usage_service = UsageService()
        summary = await usage_service.get_usage_summary(
            session, org_id, period_start, period_end
        )
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch usage summary: {str(e)}"
        )


@router.post("/organizations/{org_id}/usage/track")
async def track_usage(
    org_id: str,
    request: UsageTrackingRequest,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """手动追踪使用量（主要用于测试）"""
    try:
        usage_service = UsageService()
        success = await usage_service._track_usage(
            session, org_id, request.metric_type, request.value, request.metadata
        )
        
        return {
            "success": success,
            "metric_type": request.metric_type.value,
            "value": request.value
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to track usage: {str(e)}"
        )


@router.get("/organizations/{org_id}/usage/quota")
async def check_quota(
    org_id: str,
    metric_type: MetricType,
    requested_amount: int = 1,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """检查组织配额"""
    try:
        usage_service = UsageService()
        can_use, quota_info = await usage_service.check_quota(
            session, org_id, metric_type, requested_amount
        )
        
        return {
            "can_use": can_use,
            "quota_info": quota_info
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check quota: {str(e)}"
        )


@router.get("/organizations/{org_id}/usage/alerts")
async def get_quota_alerts(
    org_id: str,
    warning_threshold: float = 0.8,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """获取配额告警"""
    try:
        usage_service = UsageService()
        alerts = await usage_service.get_quota_alerts(
            session, org_id, warning_threshold
        )
        
        return {
            "alerts": alerts,
            "alert_count": len(alerts),
            "has_critical": any(alert['severity'] == 'critical' for alert in alerts)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch quota alerts: {str(e)}"
        )


# 发票和计费端点
@router.get("/organizations/{org_id}/invoices")
async def list_invoices(
    org_id: str,
    limit: int = 50,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """获取组织发票列表"""
    try:
        invoices = await InvoiceCRUD.get_organization_invoices(session, org_id, limit)
        
        return {
            "invoices": [
                {
                    "id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "amount": float(invoice.amount),
                    "currency": invoice.currency,
                    "status": invoice.status,
                    "period_start": invoice.period_start,
                    "period_end": invoice.period_end,
                    "created_at": invoice.created_at,
                    "hosted_invoice_url": invoice.hosted_invoice_url
                }
                for invoice in invoices
            ],
            "total": len(invoices)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch invoices: {str(e)}"
        )


@router.post("/organizations/{org_id}/billing-portal")
async def create_billing_portal_session(
    org_id: str,
    request: BillingPortalRequest,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    """创建Stripe客户门户会话"""
    try:
        # 获取组织的Stripe客户ID
        subscription = await SubscriptionCRUD.get_organization_subscription(session, org_id)
        if not subscription or not subscription.stripe_customer_id:
            raise HTTPException(
                status_code=400,
                detail="No billing customer found"
            )
        
        stripe_service = StripeService(get_settings_service())
        portal_session = await stripe_service.create_billing_portal_session(
            subscription.stripe_customer_id,
            request.return_url
        )
        
        return {"url": portal_session.url}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create billing portal session: {str(e)}"
        )


# Stripe Webhook端点
@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    session: DbSession,
    stripe_signature: str = Depends(lambda request: request.headers.get("stripe-signature"))
) -> Dict:
    """处理Stripe webhook事件"""
    try:
        if not stripe_signature:
            raise HTTPException(
                status_code=400,
                detail="Missing stripe-signature header"
            )
        
        # 读取请求体
        payload = await request.body()
        
        # 处理webhook
        stripe_service = StripeService(get_settings_service())
        result = await stripe_service.handle_webhook(
            payload, stripe_signature, session
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Webhook processing failed: {str(e)}"
        )