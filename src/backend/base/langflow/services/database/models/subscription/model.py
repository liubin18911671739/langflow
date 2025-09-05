from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from pydantic import BaseModel, validator
from sqlalchemy import JSON, Column, Decimal
from sqlmodel import Field, Relationship, SQLModel

from langflow.schema.serialize import UUIDstr

if TYPE_CHECKING:
    from langflow.services.database.models.user.model import User


class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"


class MetricType(str, Enum):
    API_CALLS = "api_calls"
    FLOW_EXECUTIONS = "flow_executions"
    STORAGE_MB = "storage_mb"
    COMPUTE_MINUTES = "compute_minutes"
    TEAM_MEMBERS = "team_members"


class Organization(SQLModel, table=True):  # type: ignore[call-arg]
    """组织/团队模型 - 支持多租户架构"""
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    name: str = Field(max_length=255, index=True)
    slug: str = Field(max_length=100, unique=True, index=True)  # URL友好的标识符
    description: Optional[str] = Field(default=None, max_length=500)
    
    # 组织设置
    logo_url: Optional[str] = Field(default=None)
    website: Optional[str] = Field(default=None)
    industry: Optional[str] = Field(default=None)
    
    # 时间戳
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 关系
    owner_id: UUIDstr = Field(foreign_key="user.id")
    owner: "User" = Relationship(back_populates="owned_organizations")
    
    members: list["OrganizationMember"] = Relationship(back_populates="organization")
    subscriptions: list["Subscription"] = Relationship(back_populates="organization")
    usage_metrics: list["UsageMetric"] = Relationship(back_populates="organization")


class OrganizationRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class OrganizationMember(SQLModel, table=True):  # type: ignore[call-arg]
    """组织成员模型"""
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    organization_id: UUIDstr = Field(foreign_key="organization.id")
    user_id: UUIDstr = Field(foreign_key="user.id")
    role: OrganizationRole = Field(default=OrganizationRole.MEMBER)
    
    # 权限
    permissions: dict = Field(sa_column=Column(JSON), default={})
    
    # 时间戳
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 关系
    organization: Organization = Relationship(back_populates="members")
    user: "User" = Relationship(back_populates="organization_memberships")


class SubscriptionPlan(SQLModel, table=True):  # type: ignore[call-arg]
    """订阅计划模型 - 定义不同的定价层次"""
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    name: str = Field(max_length=100, unique=True, index=True)
    plan_type: PlanType = Field(index=True)
    description: Optional[str] = Field(default=None, max_length=500)
    
    # 定价信息
    price: Decimal = Field(decimal_places=2, max_digits=10)  # 月费价格
    yearly_price: Optional[Decimal] = Field(default=None, decimal_places=2, max_digits=10)  # 年费价格
    currency: str = Field(default="USD", max_length=3)
    
    # Stripe集成
    stripe_price_id: Optional[str] = Field(default=None, unique=True)  # 月费Price ID
    stripe_yearly_price_id: Optional[str] = Field(default=None, unique=True)  # 年费Price ID
    stripe_product_id: Optional[str] = Field(default=None)
    
    # 功能限制
    limits: dict = Field(sa_column=Column(JSON), default={})  # 例如: {"api_calls": 10000, "storage_mb": 1000}
    features: list = Field(sa_column=Column(JSON), default=[])  # 例如: ["advanced_analytics", "sso", "priority_support"]
    
    # 状态
    is_active: bool = Field(default=True)
    is_popular: bool = Field(default=False)  # 标记为推荐计划
    
    # 时间戳
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 关系
    subscriptions: list["Subscription"] = Relationship(back_populates="plan")


class Subscription(SQLModel, table=True):  # type: ignore[call-arg]
    """用户订阅模型"""
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    organization_id: UUIDstr = Field(foreign_key="organization.id")
    plan_id: UUIDstr = Field(foreign_key="subscriptionplan.id")
    
    # Stripe集成
    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    stripe_subscription_id: Optional[str] = Field(default=None, unique=True, index=True)
    stripe_latest_invoice_id: Optional[str] = Field(default=None)
    
    # 订阅状态
    status: SubscriptionStatus = Field(default=SubscriptionStatus.ACTIVE, index=True)
    
    # 计费周期
    is_yearly: bool = Field(default=False)  # 是否年付
    current_period_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_period_end: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 试用期
    trial_start: Optional[datetime] = Field(default=None)
    trial_end: Optional[datetime] = Field(default=None)
    
    # 取消相关
    cancel_at_period_end: bool = Field(default=False)
    canceled_at: Optional[datetime] = Field(default=None)
    ended_at: Optional[datetime] = Field(default=None)
    
    # 时间戳
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 关系
    organization: Organization = Relationship(back_populates="subscriptions")
    plan: SubscriptionPlan = Relationship(back_populates="subscriptions")
    invoices: list["Invoice"] = Relationship(back_populates="subscription")


class Invoice(SQLModel, table=True):  # type: ignore[call-arg]
    """发票模型"""
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    subscription_id: UUIDstr = Field(foreign_key="subscription.id")
    
    # Stripe集成
    stripe_invoice_id: str = Field(unique=True, index=True)
    stripe_payment_intent_id: Optional[str] = Field(default=None)
    
    # 发票信息
    invoice_number: str = Field(unique=True, index=True)
    amount: Decimal = Field(decimal_places=2, max_digits=10)
    currency: str = Field(default="USD", max_length=3)
    
    # 时间信息
    period_start: datetime
    period_end: datetime
    due_date: Optional[datetime] = Field(default=None)
    paid_at: Optional[datetime] = Field(default=None)
    
    # 状态
    status: str = Field(max_length=50, index=True)  # draft, open, paid, uncollectible, void
    
    # PDF下载
    hosted_invoice_url: Optional[str] = Field(default=None)
    invoice_pdf: Optional[str] = Field(default=None)
    
    # 时间戳
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 关系
    subscription: Subscription = Relationship(back_populates="invoices")


class UsageMetric(SQLModel, table=True):  # type: ignore[call-arg]
    """使用量追踪模型"""
    id: UUIDstr = Field(default_factory=uuid4, primary_key=True, unique=True)
    organization_id: UUIDstr = Field(foreign_key="organization.id")
    
    # 指标信息
    metric_type: MetricType = Field(index=True)
    value: int = Field(default=0)
    
    # 时间维度
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    period_start: datetime = Field(index=True)  # 计费周期开始
    period_end: datetime = Field(index=True)    # 计费周期结束
    
    # 额外元数据
    metadata: dict = Field(sa_column=Column(JSON), default={})  # 存储额外信息，如用户ID、流程ID等
    
    # 关系
    organization: Organization = Relationship(back_populates="usage_metrics")


# Pydantic模型用于API响应
class OrganizationRead(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    logo_url: Optional[str]
    website: Optional[str]
    industry: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class OrganizationCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    
    @validator('slug')
    def slug_alphanumeric(cls, v):
        import re
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Slug must contain only lowercase letters, numbers, and hyphens')
        return v


class SubscriptionPlanRead(BaseModel):
    id: str
    name: str
    plan_type: PlanType
    description: Optional[str]
    price: float
    yearly_price: Optional[float]
    currency: str
    limits: dict
    features: list
    is_active: bool
    is_popular: bool
    
    class Config:
        from_attributes = True


class SubscriptionRead(BaseModel):
    id: str
    status: SubscriptionStatus
    is_yearly: bool
    current_period_start: datetime
    current_period_end: datetime
    trial_end: Optional[datetime]
    cancel_at_period_end: bool
    plan: SubscriptionPlanRead
    
    class Config:
        from_attributes = True


class UsageMetricRead(BaseModel):
    metric_type: MetricType
    value: int
    recorded_at: datetime
    period_start: datetime
    period_end: datetime
    
    class Config:
        from_attributes = True


class UsageSummary(BaseModel):
    """使用量汇总模型"""
    period_start: datetime
    period_end: datetime
    metrics: dict[MetricType, int]  # 例如: {MetricType.API_CALLS: 5000, MetricType.STORAGE_MB: 250}
    limits: dict[MetricType, int]   # 来自订阅计划的限制
    usage_percentage: dict[MetricType, float]  # 使用率百分比