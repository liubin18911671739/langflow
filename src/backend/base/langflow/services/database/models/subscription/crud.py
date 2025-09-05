"""CRUD operations for subscription models"""
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, and_, desc, func
from sqlmodel.ext.asyncio import AsyncSession

from .model import (
    Organization, OrganizationMember, OrganizationRole,
    SubscriptionPlan, Subscription, SubscriptionStatus, 
    UsageMetric, MetricType, Invoice, UsageSummary
)


class OrganizationCRUD:
    """组织相关的CRUD操作"""
    
    @staticmethod
    async def create_organization(
        session: AsyncSession,
        name: str,
        slug: str,
        owner_id: str,
        description: Optional[str] = None,
        logo_url: Optional[str] = None,
        website: Optional[str] = None,
        industry: Optional[str] = None
    ) -> Organization:
        """创建新组织"""
        org = Organization(
            name=name,
            slug=slug,
            owner_id=owner_id,
            description=description,
            logo_url=logo_url,
            website=website,
            industry=industry
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)
        
        # 自动添加所有者为管理员
        member = OrganizationMember(
            organization_id=org.id,
            user_id=owner_id,
            role=OrganizationRole.OWNER
        )
        session.add(member)
        await session.commit()
        
        return org
    
    @staticmethod
    async def get_organization_by_id(session: AsyncSession, org_id: str) -> Optional[Organization]:
        """根据ID获取组织"""
        stmt = select(Organization).where(Organization.id == org_id)
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_organization_by_slug(session: AsyncSession, slug: str) -> Optional[Organization]:
        """根据slug获取组织"""
        stmt = select(Organization).where(Organization.slug == slug)
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_user_organizations(session: AsyncSession, user_id: str) -> List[Organization]:
        """获取用户所属的所有组织"""
        stmt = select(Organization).join(OrganizationMember).where(
            OrganizationMember.user_id == user_id
        )
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def add_member(
        session: AsyncSession,
        org_id: str,
        user_id: str,
        role: OrganizationRole = OrganizationRole.MEMBER
    ) -> OrganizationMember:
        """添加组织成员"""
        member = OrganizationMember(
            organization_id=org_id,
            user_id=user_id,
            role=role
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)
        return member


class SubscriptionCRUD:
    """订阅相关的CRUD操作"""
    
    @staticmethod
    async def get_plans(session: AsyncSession, active_only: bool = True) -> List[SubscriptionPlan]:
        """获取订阅计划列表"""
        stmt = select(SubscriptionPlan)
        if active_only:
            stmt = stmt.where(SubscriptionPlan.is_active == True)
        stmt = stmt.order_by(SubscriptionPlan.price)
        result = await session.exec(stmt)
        return list(result.fetchall())
    
    @staticmethod
    async def get_plan_by_id(session: AsyncSession, plan_id: str) -> Optional[SubscriptionPlan]:
        """根据ID获取订阅计划"""
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def get_plan_by_stripe_price_id(
        session: AsyncSession, 
        stripe_price_id: str
    ) -> Optional[SubscriptionPlan]:
        """根据Stripe Price ID获取订阅计划"""
        stmt = select(SubscriptionPlan).where(
            (SubscriptionPlan.stripe_price_id == stripe_price_id) |
            (SubscriptionPlan.stripe_yearly_price_id == stripe_price_id)
        )
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def create_subscription(
        session: AsyncSession,
        organization_id: str,
        plan_id: str,
        stripe_customer_id: Optional[str] = None,
        stripe_subscription_id: Optional[str] = None,
        status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
        is_yearly: bool = False,
        trial_end: Optional[datetime] = None
    ) -> Subscription:
        """创建新订阅"""
        now = datetime.now(timezone.utc)
        subscription = Subscription(
            organization_id=organization_id,
            plan_id=plan_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            status=status,
            is_yearly=is_yearly,
            current_period_start=now,
            current_period_end=now,  # 稍后更新
            trial_end=trial_end
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        return subscription
    
    @staticmethod
    async def get_organization_subscription(
        session: AsyncSession, 
        org_id: str
    ) -> Optional[Subscription]:
        """获取组织的当前订阅"""
        stmt = select(Subscription).where(
            and_(
                Subscription.organization_id == org_id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING])
            )
        ).order_by(desc(Subscription.created_at))
        result = await session.exec(stmt)
        return result.first()
    
    @staticmethod
    async def update_subscription_from_stripe(
        session: AsyncSession,
        subscription_id: str,
        **updates
    ) -> Optional[Subscription]:
        """从Stripe webhook更新订阅信息"""
        stmt = select(Subscription).where(Subscription.id == subscription_id)
        result = await session.exec(stmt)
        subscription = result.first()
        
        if subscription:
            for key, value in updates.items():
                setattr(subscription, key, value)
            subscription.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(subscription)
        
        return subscription


class UsageMetricCRUD:
    """使用量追踪相关的CRUD操作"""
    
    @staticmethod
    async def record_usage(
        session: AsyncSession,
        organization_id: str,
        metric_type: MetricType,
        value: int = 1,
        metadata: Optional[dict] = None
    ) -> UsageMetric:
        """记录使用量"""
        now = datetime.now(timezone.utc)
        
        # 获取当前计费周期
        period_start, period_end = await UsageMetricCRUD._get_current_billing_period(
            session, organization_id
        )
        
        metric = UsageMetric(
            organization_id=organization_id,
            metric_type=metric_type,
            value=value,
            recorded_at=now,
            period_start=period_start,
            period_end=period_end,
            metadata=metadata or {}
        )
        session.add(metric)
        await session.commit()
        await session.refresh(metric)
        return metric
    
    @staticmethod
    async def get_usage_summary(
        session: AsyncSession,
        organization_id: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> UsageSummary:
        """获取使用量汇总"""
        if not period_start or not period_end:
            period_start, period_end = await UsageMetricCRUD._get_current_billing_period(
                session, organization_id
            )
        
        # 查询使用量数据
        stmt = select(
            UsageMetric.metric_type,
            func.sum(UsageMetric.value).label('total_value')
        ).where(
            and_(
                UsageMetric.organization_id == organization_id,
                UsageMetric.period_start >= period_start,
                UsageMetric.period_end <= period_end
            )
        ).group_by(UsageMetric.metric_type)
        
        result = await session.exec(stmt)
        usage_data = {metric_type: total for metric_type, total in result.fetchall()}
        
        # 获取订阅限制
        subscription = await SubscriptionCRUD.get_organization_subscription(session, organization_id)
        limits = subscription.plan.limits if subscription else {}
        
        # 计算使用率
        usage_percentage = {}
        for metric_type in MetricType:
            used = usage_data.get(metric_type, 0)
            limit = limits.get(metric_type.value, 0)
            if limit > 0:
                usage_percentage[metric_type] = (used / limit) * 100
            else:
                usage_percentage[metric_type] = 0
        
        return UsageSummary(
            period_start=period_start,
            period_end=period_end,
            metrics=usage_data,
            limits=limits,
            usage_percentage=usage_percentage
        )
    
    @staticmethod
    async def check_usage_limit(
        session: AsyncSession,
        organization_id: str,
        metric_type: MetricType,
        increment: int = 1
    ) -> tuple[bool, int, int]:
        """检查使用量是否超限
        
        Returns:
            tuple[bool, int, int]: (是否可以使用, 当前使用量, 限制量)
        """
        # 获取当前使用量
        summary = await UsageMetricCRUD.get_usage_summary(session, organization_id)
        current_usage = summary.metrics.get(metric_type, 0)
        limit = summary.limits.get(metric_type.value, 0)
        
        # -1 表示无限制
        if limit == -1:
            return True, current_usage, limit
        
        # 检查是否会超限
        can_use = (current_usage + increment) <= limit
        return can_use, current_usage, limit
    
    @staticmethod
    async def _get_current_billing_period(
        session: AsyncSession,
        organization_id: str
    ) -> tuple[datetime, datetime]:
        """获取当前计费周期"""
        subscription = await SubscriptionCRUD.get_organization_subscription(session, organization_id)
        if subscription:
            return subscription.current_period_start, subscription.current_period_end
        
        # 如果没有订阅，使用当月作为计费周期
        now = datetime.now(timezone.utc)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)
        
        return period_start, period_end


class InvoiceCRUD:
    """发票相关的CRUD操作"""
    
    @staticmethod
    async def create_invoice_from_stripe(
        session: AsyncSession,
        subscription_id: str,
        stripe_invoice_data: dict
    ) -> Invoice:
        """从Stripe数据创建发票"""
        invoice = Invoice(
            subscription_id=subscription_id,
            stripe_invoice_id=stripe_invoice_data['id'],
            stripe_payment_intent_id=stripe_invoice_data.get('payment_intent'),
            invoice_number=stripe_invoice_data['number'],
            amount=stripe_invoice_data['amount_paid'] / 100,  # Stripe金额是分
            currency=stripe_invoice_data['currency'].upper(),
            period_start=datetime.fromtimestamp(
                stripe_invoice_data['lines']['data'][0]['period']['start'], 
                tz=timezone.utc
            ),
            period_end=datetime.fromtimestamp(
                stripe_invoice_data['lines']['data'][0]['period']['end'], 
                tz=timezone.utc
            ),
            due_date=datetime.fromtimestamp(
                stripe_invoice_data['due_date'], tz=timezone.utc
            ) if stripe_invoice_data.get('due_date') else None,
            paid_at=datetime.fromtimestamp(
                stripe_invoice_data['status_transitions']['paid_at'], 
                tz=timezone.utc
            ) if stripe_invoice_data['status_transitions'].get('paid_at') else None,
            status=stripe_invoice_data['status'],
            hosted_invoice_url=stripe_invoice_data.get('hosted_invoice_url'),
            invoice_pdf=stripe_invoice_data.get('invoice_pdf')
        )
        
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)
        return invoice
    
    @staticmethod
    async def get_organization_invoices(
        session: AsyncSession,
        organization_id: str,
        limit: int = 50
    ) -> List[Invoice]:
        """获取组织的发票列表"""
        stmt = select(Invoice).join(Subscription).where(
            Subscription.organization_id == organization_id
        ).order_by(desc(Invoice.created_at)).limit(limit)
        
        result = await session.exec(stmt)
        return list(result.fetchall())