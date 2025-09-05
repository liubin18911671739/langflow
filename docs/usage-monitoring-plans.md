# 使用量监控实现方案

## 方案一：基于数据库的实时监控

### 架构概述

基于PostgreSQL数据库实现实时使用量监控，利用现有多租户架构，通过数据库触发器和聚合查询实现高效的监控机制。

### 数据库设计

#### 1. 使用量记录表

```sql
-- 使用量记录主表
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR NOT NULL REFERENCES organization(id),
    user_id UUID REFERENCES "user"(id),
    resource_type VARCHAR(50) NOT NULL, -- 'api_call', 'storage', 'execution_time'
    resource_id VARCHAR, -- flow_id, file_id, etc.
    metric_name VARCHAR(50) NOT NULL, -- 'count', 'bytes', 'milliseconds'
    metric_value BIGINT NOT NULL,
    metadata JSONB, -- 额外信息：endpoint, method, status_code等
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    date_bucket DATE GENERATED ALWAYS AS (DATE(created_at)) STORED
);

-- 索引优化
CREATE INDEX idx_usage_org_date ON usage_records(organization_id, date_bucket);
CREATE INDEX idx_usage_resource ON usage_records(resource_type, metric_name);
CREATE INDEX idx_usage_created ON usage_records(created_at);

-- 分区表（按月分区）
CREATE TABLE usage_records_2024_01 PARTITION OF usage_records
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

#### 2. 使用量汇总表

```sql
-- 每日汇总表
CREATE TABLE daily_usage_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR NOT NULL,
    user_id UUID,
    date DATE NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    total_value BIGINT NOT NULL,
    record_count INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(organization_id, user_id, date, resource_type, metric_name)
);

-- 月度汇总表
CREATE TABLE monthly_usage_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR NOT NULL,
    user_id UUID,
    year_month VARCHAR(7) NOT NULL, -- '2024-03'
    resource_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    total_value BIGINT NOT NULL,
    record_count INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(organization_id, user_id, year_month, resource_type, metric_name)
);
```

#### 3. 配额限制表

```sql
-- 组织配额配置
CREATE TABLE organization_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id VARCHAR NOT NULL REFERENCES organization(id),
    resource_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    quota_limit BIGINT NOT NULL, -- 限制值
    quota_period VARCHAR(20) NOT NULL, -- 'daily', 'monthly', 'yearly'
    reset_day INT, -- 月度重置日期
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(organization_id, resource_type, metric_name, quota_period)
);

-- 插入默认配额
INSERT INTO organization_quotas (organization_id, resource_type, metric_name, quota_limit, quota_period) VALUES
('default-org', 'api_call', 'count', 1000, 'daily'),
('default-org', 'storage', 'bytes', 104857600, 'monthly'), -- 100MB
('default-org', 'execution_time', 'milliseconds', 3600000, 'daily'); -- 1小时
```

### 后端实现

#### 1. 使用量追踪服务

```python
# src/backend/base/langflow/services/usage/models.py
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel
from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4

class ResourceType(str, Enum):
    API_CALL = "api_call"
    STORAGE = "storage"
    EXECUTION_TIME = "execution_time"

class MetricName(str, Enum):
    COUNT = "count"
    BYTES = "bytes" 
    MILLISECONDS = "milliseconds"

class QuotaPeriod(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"

class UsageRecord(SQLModel, table=True):
    __tablename__ = "usage_records"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: str = Field(foreign_key="organization.id", index=True)
    user_id: Optional[UUID] = Field(foreign_key="user.id")
    resource_type: ResourceType
    resource_id: Optional[str] = None
    metric_name: MetricName
    metric_value: int
    metadata: Optional[Dict[str, Any]] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    date_bucket: date = Field(index=True)

class OrganizationQuota(SQLModel, table=True):
    __tablename__ = "organization_quotas"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: str = Field(foreign_key="organization.id")
    resource_type: ResourceType
    metric_name: MetricName
    quota_limit: int
    quota_period: QuotaPeriod
    reset_day: Optional[int] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class DailyUsageSummary(SQLModel, table=True):
    __tablename__ = "daily_usage_summary"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: str
    user_id: Optional[UUID]
    date: date
    resource_type: ResourceType
    metric_name: MetricName
    total_value: int
    record_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

#### 2. 使用量服务核心逻辑

```python
# src/backend/base/langflow/services/usage/service.py
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from sqlmodel.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.dialects.postgresql import insert

from .models import (
    UsageRecord, OrganizationQuota, DailyUsageSummary,
    ResourceType, MetricName, QuotaPeriod
)

class UsageTrackingService:
    """使用量追踪服务"""
    
    def __init__(self):
        self._batch_records = []
        self._batch_size = 100
    
    async def record_usage(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        metric_value: int,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UsageRecord:
        """记录使用量"""
        usage_record = UsageRecord(
            organization_id=organization_id,
            user_id=UUID(user_id) if user_id else None,
            resource_type=resource_type,
            resource_id=resource_id,
            metric_name=metric_name,
            metric_value=metric_value,
            metadata=metadata,
            date_bucket=date.today()
        )
        
        session.add(usage_record)
        await session.commit()
        
        # 异步更新汇总数据
        asyncio.create_task(
            self._update_daily_summary(session, usage_record)
        )
        
        return usage_record
    
    async def batch_record_usage(
        self,
        session: AsyncSession,
        records: List[Dict[str, Any]]
    ) -> List[UsageRecord]:
        """批量记录使用量"""
        usage_records = []
        for record_data in records:
            usage_record = UsageRecord(
                organization_id=record_data["organization_id"],
                user_id=UUID(record_data["user_id"]) if record_data.get("user_id") else None,
                resource_type=ResourceType(record_data["resource_type"]),
                resource_id=record_data.get("resource_id"),
                metric_name=MetricName(record_data["metric_name"]),
                metric_value=record_data["metric_value"],
                metadata=record_data.get("metadata"),
                date_bucket=date.today()
            )
            usage_records.append(usage_record)
        
        session.add_all(usage_records)
        await session.commit()
        
        return usage_records
    
    async def check_quota_limit(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        additional_usage: int = 0
    ) -> Dict[str, Any]:
        """检查配额限制"""
        # 获取组织配额配置
        quota_stmt = select(OrganizationQuota).where(
            and_(
                OrganizationQuota.organization_id == organization_id,
                OrganizationQuota.resource_type == resource_type,
                OrganizationQuota.metric_name == metric_name,
                OrganizationQuota.is_active == True
            )
        )
        quota_result = await session.exec(quota_stmt)
        quotas = quota_result.all()
        
        if not quotas:
            return {"allowed": True, "message": "No quota limits configured"}
        
        for quota in quotas:
            current_usage = await self._get_current_period_usage(
                session, organization_id, resource_type, metric_name, quota.quota_period
            )
            
            if current_usage + additional_usage > quota.quota_limit:
                remaining = max(0, quota.quota_limit - current_usage)
                return {
                    "allowed": False,
                    "message": f"Quota limit exceeded for {quota.quota_period} {resource_type.value}",
                    "quota_limit": quota.quota_limit,
                    "current_usage": current_usage,
                    "remaining": remaining,
                    "period": quota.quota_period
                }
        
        return {"allowed": True, "message": "Within quota limits"}
    
    async def get_usage_statistics(
        self,
        session: AsyncSession,
        organization_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        resource_type: Optional[ResourceType] = None
    ) -> Dict[str, Any]:
        """获取使用量统计"""
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()
        
        # 构建查询条件
        conditions = [
            DailyUsageSummary.organization_id == organization_id,
            DailyUsageSummary.date >= start_date,
            DailyUsageSummary.date <= end_date
        ]
        
        if resource_type:
            conditions.append(DailyUsageSummary.resource_type == resource_type)
        
        # 查询汇总数据
        stmt = select(
            DailyUsageSummary.resource_type,
            DailyUsageSummary.metric_name,
            func.sum(DailyUsageSummary.total_value).label("total"),
            func.sum(DailyUsageSummary.record_count).label("count"),
            func.avg(DailyUsageSummary.total_value).label("daily_average")
        ).where(
            and_(*conditions)
        ).group_by(
            DailyUsageSummary.resource_type,
            DailyUsageSummary.metric_name
        )
        
        result = await session.exec(stmt)
        statistics = {}
        
        for row in result:
            resource_key = f"{row.resource_type}_{row.metric_name}"
            statistics[resource_key] = {
                "total": row.total,
                "count": row.count,
                "daily_average": float(row.daily_average) if row.daily_average else 0
            }
        
        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "statistics": statistics
        }
    
    async def _get_current_period_usage(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        period: QuotaPeriod
    ) -> int:
        """获取当前周期的使用量"""
        today = date.today()
        
        if period == QuotaPeriod.DAILY:
            start_date = today
            end_date = today
        elif period == QuotaPeriod.MONTHLY:
            start_date = today.replace(day=1)
            # 下个月第一天
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period == QuotaPeriod.YEARLY:
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
        else:
            return 0
        
        stmt = select(func.coalesce(func.sum(DailyUsageSummary.total_value), 0)).where(
            and_(
                DailyUsageSummary.organization_id == organization_id,
                DailyUsageSummary.resource_type == resource_type,
                DailyUsageSummary.metric_name == metric_name,
                DailyUsageSummary.date >= start_date,
                DailyUsageSummary.date <= end_date
            )
        )
        
        result = await session.exec(stmt)
        return result.scalar() or 0
    
    async def _update_daily_summary(
        self,
        session: AsyncSession,
        usage_record: UsageRecord
    ):
        """更新每日汇总数据"""
        try:
            # 使用 PostgreSQL 的 UPSERT 功能
            stmt = insert(DailyUsageSummary).values(
                organization_id=usage_record.organization_id,
                user_id=usage_record.user_id,
                date=usage_record.date_bucket,
                resource_type=usage_record.resource_type,
                metric_name=usage_record.metric_name,
                total_value=usage_record.metric_value,
                record_count=1
            )
            
            stmt = stmt.on_conflict_do_update(
                constraint='daily_usage_summary_organization_id_user_id_date_resource_type_key',
                set_={
                    'total_value': stmt.excluded.total_value + DailyUsageSummary.total_value,
                    'record_count': stmt.excluded.record_count + DailyUsageSummary.record_count,
                    'updated_at': datetime.utcnow()
                }
            )
            
            await session.exec(stmt)
            await session.commit()
            
        except Exception as e:
            await session.rollback()
            # 记录错误日志，但不阻塞主流程
            print(f"Failed to update daily summary: {e}")


class QuotaEnforcementService:
    """配额执行服务"""
    
    def __init__(self):
        self.usage_service = UsageTrackingService()
    
    async def enforce_quota_check(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        requested_usage: int = 1
    ) -> bool:
        """执行配额检查，返回是否允许继续"""
        quota_check = await self.usage_service.check_quota_limit(
            session, organization_id, resource_type, metric_name, requested_usage
        )
        
        return quota_check["allowed"]
    
    async def get_quota_status(
        self,
        session: AsyncSession,
        organization_id: str
    ) -> Dict[str, Any]:
        """获取组织配额状态"""
        # 获取所有配额配置
        quota_stmt = select(OrganizationQuota).where(
            and_(
                OrganizationQuota.organization_id == organization_id,
                OrganizationQuota.is_active == True
            )
        )
        quota_result = await session.exec(quota_stmt)
        quotas = quota_result.all()
        
        quota_status = {}
        
        for quota in quotas:
            current_usage = await self.usage_service._get_current_period_usage(
                session, organization_id, quota.resource_type, 
                quota.metric_name, quota.quota_period
            )
            
            quota_key = f"{quota.resource_type.value}_{quota.metric_name.value}_{quota.quota_period.value}"
            quota_status[quota_key] = {
                "limit": quota.quota_limit,
                "used": current_usage,
                "remaining": max(0, quota.quota_limit - current_usage),
                "percentage": (current_usage / quota.quota_limit) * 100 if quota.quota_limit > 0 else 0,
                "period": quota.quota_period.value
            }
        
        return quota_status

# 依赖注入
def get_usage_tracking_service() -> UsageTrackingService:
    return UsageTrackingService()

def get_quota_enforcement_service() -> QuotaEnforcementService:
    return QuotaEnforcementService()
```

#### 3. 监控装饰器和中间件

```python
# src/backend/base/langflow/middleware/usage_tracking.py
import time
from functools import wraps
from typing import Callable, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from langflow.services.usage.service import UsageTrackingService
from langflow.services.usage.models import ResourceType, MetricName
from langflow.services.deps import get_session

class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """使用量追踪中间件"""
    
    def __init__(self, app):
        super().__init__(app)
        self.usage_service = UsageTrackingService()
        
        # 需要监控的端点模式
        self.monitored_patterns = [
            '/api/v1/flows',
            '/api/v1/tenant/flows',
            '/api/v1/chat',
            '/api/v1/run'
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 检查是否需要监控此端点
        should_monitor = any(
            request.url.path.startswith(pattern) 
            for pattern in self.monitored_patterns
        )
        
        if not should_monitor:
            return await call_next(request)
        
        # 获取组织上下文
        organization_id = getattr(request.state, 'current_organization_id', None)
        user_id = getattr(request.state, 'user_id', None)
        
        if not organization_id:
            return await call_next(request)
        
        # 执行请求
        response = await call_next(request)
        
        # 计算执行时间
        execution_time = int((time.time() - start_time) * 1000)  # 毫秒
        
        # 记录使用量
        try:
            async with get_session() as session:
                # API调用计数
                await self.usage_service.record_usage(
                    session=session,
                    organization_id=organization_id,
                    resource_type=ResourceType.API_CALL,
                    metric_name=MetricName.COUNT,
                    metric_value=1,
                    user_id=user_id,
                    resource_id=request.url.path,
                    metadata={
                        "method": request.method,
                        "status_code": response.status_code,
                        "endpoint": request.url.path,
                        "user_agent": request.headers.get("user-agent"),
                        "ip_address": request.client.host if request.client else None
                    }
                )
                
                # 执行时间追踪
                await self.usage_service.record_usage(
                    session=session,
                    organization_id=organization_id,
                    resource_type=ResourceType.EXECUTION_TIME,
                    metric_name=MetricName.MILLISECONDS,
                    metric_value=execution_time,
                    user_id=user_id,
                    resource_id=request.url.path,
                    metadata={
                        "method": request.method,
                        "endpoint": request.url.path
                    }
                )
                
        except Exception as e:
            # 记录错误但不影响正常响应
            print(f"Failed to track usage: {e}")
        
        return response


# 装饰器用于特定函数的使用量追踪
def track_usage(
    resource_type: ResourceType,
    metric_name: MetricName,
    get_metric_value: Callable[[Any], int] = lambda x: 1
):
    """使用量追踪装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 执行原函数
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # 尝试从参数中获取组织和用户信息
            organization_id = kwargs.get('organization_id')
            user_id = kwargs.get('user_id')
            session = kwargs.get('session')
            
            if organization_id and session:
                try:
                    usage_service = UsageTrackingService()
                    metric_value = get_metric_value(result)
                    
                    await usage_service.record_usage(
                        session=session,
                        organization_id=organization_id,
                        resource_type=resource_type,
                        metric_name=metric_name,
                        metric_value=metric_value,
                        user_id=user_id,
                        metadata={
                            "function": func.__name__,
                            "module": func.__module__
                        }
                    )
                except Exception as e:
                    print(f"Usage tracking failed in decorator: {e}")
            
            return result
        return wrapper
    return decorator


# 使用示例
@track_usage(ResourceType.STORAGE, MetricName.BYTES, lambda flow: len(str(flow.data)))
async def create_flow_with_tracking(
    session: AsyncSession,
    flow_data: FlowCreate,
    organization_id: str,
    user_id: str
) -> Flow:
    # 创建流程的业务逻辑
    pass
```

### API端点实现

```python
# src/backend/base/langflow/api/v1/usage.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import date, timedelta
from typing import Optional

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.middleware.tenant_context import require_organization_context
from langflow.services.usage.service import (
    UsageTrackingService, QuotaEnforcementService,
    get_usage_tracking_service, get_quota_enforcement_service
)
from langflow.services.usage.models import ResourceType

router = APIRouter(prefix="/usage", tags=["Usage Monitoring"])

@router.get("/statistics")
async def get_usage_statistics(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    resource_type: Optional[ResourceType] = None,
    usage_service: UsageTrackingService = Depends(get_usage_tracking_service)
):
    """获取使用量统计"""
    try:
        statistics = await usage_service.get_usage_statistics(
            session=session,
            organization_id=organization_id,
            start_date=start_date or (date.today() - timedelta(days=30)),
            end_date=end_date or date.today(),
            resource_type=resource_type
        )
        return statistics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quota-status")
async def get_quota_status(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    quota_service: QuotaEnforcementService = Depends(get_quota_enforcement_service)
):
    """获取配额状态"""
    try:
        quota_status = await quota_service.get_quota_status(
            session=session,
            organization_id=organization_id
        )
        return quota_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-quota")
async def check_quota_limit(
    *,
    session: DbSession,
    resource_type: ResourceType,
    metric_value: int = 1,
    organization_id: str = Depends(require_organization_context),
    usage_service: UsageTrackingService = Depends(get_usage_tracking_service)
):
    """检查配额限制"""
    try:
        quota_check = await usage_service.check_quota_limit(
            session=session,
            organization_id=organization_id,
            resource_type=resource_type,
            metric_name=MetricName.COUNT,
            additional_usage=metric_value
        )
        return quota_check
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 优势
- ✅ 简单可靠，易于实现和维护
- ✅ 事务一致性强，数据准确
- ✅ 与现有多租户架构完美集成
- ✅ 支持复杂查询和报表生成

### 劣势
- ❌ 高并发时数据库压力较大
- ❌ 实时性受限于数据库性能
- ❌ 扩展性有限

---

## 方案二：基于Redis的缓存监控

### 架构概述

利用Redis的高性能特性实现高并发场景下的实时使用量监控，通过内存缓存提供毫秒级响应，定期同步到PostgreSQL进行持久化存储。

### 核心设计思路

1. **实时计数**: Redis Hash/Sorted Set存储实时计数
2. **滑动窗口**: 时间窗口内的使用量统计
3. **异步同步**: 定期批量同步到数据库
4. **分布式锁**: 确保并发安全

### Redis数据结构设计

```python
# Redis键命名规范
# 实时计数器
usage:counter:{org_id}:{resource_type}:{metric}:{period}:{date}
# 例: usage:counter:org-123:api_call:count:daily:2024-03-15

# 滑动窗口（按小时）
usage:window:{org_id}:{resource_type}:{metric}:{hour}
# 例: usage:window:org-123:api_call:count:2024031510

# 配额限制
quota:limit:{org_id}:{resource_type}:{metric}:{period}
# 例: quota:limit:org-123:api_call:count:daily

# 详细记录（List，FIFO）
usage:detail:{org_id}:{date}
# 例: usage:detail:org-123:2024-03-15

# 分布式锁
lock:usage:{org_id}:{resource_type}
```

### 实现代码

#### 1. Redis使用量服务

```python
# src/backend/base/langflow/services/usage/redis_service.py
import json
import asyncio
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from contextlib import asynccontextmanager

import redis.asyncio as redis
from pydantic import BaseModel

from .models import ResourceType, MetricName, QuotaPeriod
from .service import UsageTrackingService


class RedisUsageService:
    """基于Redis的高性能使用量监控服务"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_pool = redis.ConnectionPool.from_url(redis_url)
        self.redis = redis.Redis(connection_pool=self.redis_pool)
        self.db_sync_service = UsageTrackingService()
        
        # 配置参数
        self.sync_interval = 60  # 同步间隔（秒）
        self.window_size = 24    # 滑动窗口大小（小时）
        self.max_detail_records = 10000  # 详细记录最大数量
        
    async def record_usage_fast(
        self,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        metric_value: int = 1,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """高速记录使用量（毫秒级响应）"""
        now = datetime.utcnow()
        date_str = now.date().isoformat()
        hour_str = now.strftime("%Y%m%d%H")
        
        async with self.redis.pipeline() as pipe:
            try:
                # 1. 增加实时计数器
                daily_key = f"usage:counter:{organization_id}:{resource_type.value}:{metric_name.value}:daily:{date_str}"
                monthly_key = f"usage:counter:{organization_id}:{resource_type.value}:{metric_name.value}:monthly:{now.strftime('%Y-%m')}"
                
                # 增加计数并设置过期时间
                pipe.hincrby(daily_key, "total", metric_value)
                pipe.hincrby(daily_key, "count", 1)
                pipe.expire(daily_key, 86400 * 7)  # 7天过期
                
                pipe.hincrby(monthly_key, "total", metric_value)
                pipe.hincrby(monthly_key, "count", 1) 
                pipe.expire(monthly_key, 86400 * 32)  # 32天过期
                
                # 2. 更新滑动窗口（按小时）
                window_key = f"usage:window:{organization_id}:{resource_type.value}:{metric_name.value}:{hour_str}"
                pipe.hincrby(window_key, "total", metric_value)
                pipe.hincrby(window_key, "count", 1)
                pipe.expire(window_key, 86400)  # 24小时过期
                
                # 3. 记录详细信息（可选，用于调试和分析）
                if metadata or user_id:
                    detail_key = f"usage:detail:{organization_id}:{date_str}"
                    detail_record = {
                        "timestamp": now.isoformat(),
                        "resource_type": resource_type.value,
                        "metric_name": metric_name.value,
                        "metric_value": metric_value,
                        "user_id": user_id,
                        "resource_id": resource_id,
                        "metadata": metadata
                    }
                    
                    # 使用列表存储，保持FIFO顺序
                    pipe.lpush(detail_key, json.dumps(detail_record))
                    pipe.ltrim(detail_key, 0, self.max_detail_records - 1)  # 限制数量
                    pipe.expire(detail_key, 86400 * 3)  # 3天过期
                
                await pipe.execute()
                return True
                
            except redis.RedisError as e:
                print(f"Redis usage recording failed: {e}")
                return False
    
    async def check_quota_limit_fast(
        self,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        additional_usage: int = 1,
        period: QuotaPeriod = QuotaPeriod.DAILY
    ) -> Dict[str, Any]:
        """快速检查配额限制"""
        try:
            # 获取配额限制
            quota_key = f"quota:limit:{organization_id}:{resource_type.value}:{metric_name.value}:{period.value}"
            quota_limit = await self.redis.get(quota_key)
            
            if not quota_limit:
                # 从数据库加载配额配置到Redis
                await self._load_quota_to_redis(organization_id, resource_type, metric_name, period)
                quota_limit = await self.redis.get(quota_key)
            
            if not quota_limit:
                return {"allowed": True, "message": "No quota limits configured"}
            
            quota_limit = int(quota_limit)
            
            # 获取当前使用量
            current_usage = await self._get_current_usage_from_redis(
                organization_id, resource_type, metric_name, period
            )
            
            if current_usage + additional_usage > quota_limit:
                remaining = max(0, quota_limit - current_usage)
                return {
                    "allowed": False,
                    "message": f"Quota limit exceeded for {period.value} {resource_type.value}",
                    "quota_limit": quota_limit,
                    "current_usage": current_usage,
                    "remaining": remaining,
                    "period": period.value
                }
            
            return {
                "allowed": True,
                "quota_limit": quota_limit,
                "current_usage": current_usage,
                "remaining": quota_limit - current_usage,
                "period": period.value
            }
            
        except redis.RedisError as e:
            print(f"Redis quota check failed: {e}")
            # Redis失败时回退到数据库检查
            return {"allowed": True, "message": "Redis unavailable, defaulting to allow"}
    
    async def get_real_time_stats(
        self,
        organization_id: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """获取实时统计数据（滑动窗口）"""
        now = datetime.utcnow()
        stats = {}
        
        # 获取过去N小时的数据
        for i in range(hours):
            hour_time = now - timedelta(hours=i)
            hour_str = hour_time.strftime("%Y%m%d%H")
            
            # 查询该小时的所有使用量类型
            pattern = f"usage:window:{organization_id}:*:{hour_str}"
            keys = await self.redis.keys(pattern)
            
            for key in keys:
                # 解析键名
                parts = key.decode().split(':')
                if len(parts) >= 6:
                    resource_type = parts[3]
                    metric_name = parts[4]
                    
                    # 获取数据
                    data = await self.redis.hgetall(key)
                    if data:
                        stat_key = f"{resource_type}_{metric_name}"
                        if stat_key not in stats:
                            stats[stat_key] = {
                                "hourly_data": [],
                                "total": 0,
                                "count": 0
                            }
                        
                        total = int(data.get(b'total', b'0'))
                        count = int(data.get(b'count', b'0'))
                        
                        stats[stat_key]["hourly_data"].append({
                            "hour": hour_str,
                            "total": total,
                            "count": count
                        })
                        stats[stat_key]["total"] += total
                        stats[stat_key]["count"] += count
        
        return stats
    
    async def get_quota_status_fast(
        self,
        organization_id: str
    ) -> Dict[str, Any]:
        """快速获取配额状态"""
        quota_status = {}
        
        # 获取所有配额键
        pattern = f"quota:limit:{organization_id}:*"
        quota_keys = await self.redis.keys(pattern)
        
        for key in quota_keys:
            key_str = key.decode()
            parts = key_str.split(':')
            
            if len(parts) >= 6:
                resource_type = parts[3]
                metric_name = parts[4]
                period = parts[5]
                
                quota_limit = int(await self.redis.get(key))
                current_usage = await self._get_current_usage_from_redis(
                    organization_id,
                    ResourceType(resource_type),
                    MetricName(metric_name),
                    QuotaPeriod(period)
                )
                
                quota_key = f"{resource_type}_{metric_name}_{period}"
                quota_status[quota_key] = {
                    "limit": quota_limit,
                    "used": current_usage,
                    "remaining": max(0, quota_limit - current_usage),
                    "percentage": (current_usage / quota_limit) * 100 if quota_limit > 0 else 0,
                    "period": period
                }
        
        return quota_status
    
    async def sync_to_database(self, session) -> Dict[str, int]:
        """将Redis数据同步到数据库"""
        sync_stats = {"records_synced": 0, "errors": 0}
        
        # 获取所有待同步的键
        pattern = "usage:detail:*"
        detail_keys = await self.redis.keys(pattern)
        
        for key in detail_keys:
            try:
                key_str = key.decode()
                parts = key_str.split(':')
                
                if len(parts) >= 4:
                    organization_id = parts[2]
                    date_str = parts[3]
                    
                    # 获取详细记录
                    records = await self.redis.lrange(key, 0, -1)
                    batch_records = []
                    
                    for record_json in records:
                        try:
                            record = json.loads(record_json.decode())
                            batch_records.append({
                                "organization_id": organization_id,
                                "user_id": record.get("user_id"),
                                "resource_type": record["resource_type"],
                                "resource_id": record.get("resource_id"),
                                "metric_name": record["metric_name"],
                                "metric_value": record["metric_value"],
                                "metadata": record.get("metadata")
                            })
                        except json.JSONDecodeError:
                            sync_stats["errors"] += 1
                            continue
                    
                    if batch_records:
                        # 批量插入数据库
                        await self.db_sync_service.batch_record_usage(session, batch_records)
                        sync_stats["records_synced"] += len(batch_records)
                        
                        # 同步成功后删除Redis中的记录
                        await self.redis.delete(key)
                        
            except Exception as e:
                print(f"Failed to sync key {key}: {e}")
                sync_stats["errors"] += 1
        
        return sync_stats
    
    async def _get_current_usage_from_redis(
        self,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        period: QuotaPeriod
    ) -> int:
        """从Redis获取当前周期使用量"""
        now = datetime.utcnow()
        
        if period == QuotaPeriod.DAILY:
            key = f"usage:counter:{organization_id}:{resource_type.value}:{metric_name.value}:daily:{now.date().isoformat()}"
        elif period == QuotaPeriod.MONTHLY:
            key = f"usage:counter:{organization_id}:{resource_type.value}:{metric_name.value}:monthly:{now.strftime('%Y-%m')}"
        else:
            return 0
        
        usage_data = await self.redis.hget(key, "total")
        return int(usage_data) if usage_data else 0
    
    async def _load_quota_to_redis(
        self,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        period: QuotaPeriod
    ):
        """从数据库加载配额配置到Redis"""
        # 这里需要数据库会话，实际实现时需要调整
        quota_key = f"quota:limit:{organization_id}:{resource_type.value}:{metric_name.value}:{period.value}"
        
        # 示例：默认配额
        default_quotas = {
            f"{ResourceType.API_CALL.value}_{MetricName.COUNT.value}_{QuotaPeriod.DAILY.value}": 1000,
            f"{ResourceType.STORAGE.value}_{MetricName.BYTES.value}_{QuotaPeriod.MONTHLY.value}": 104857600,
            f"{ResourceType.EXECUTION_TIME.value}_{MetricName.MILLISECONDS.value}_{QuotaPeriod.DAILY.value}": 3600000,
        }
        
        quota_type = f"{resource_type.value}_{metric_name.value}_{period.value}"
        quota_limit = default_quotas.get(quota_type, 0)
        
        if quota_limit > 0:
            await self.redis.set(quota_key, quota_limit, ex=86400)  # 24小时过期


class RedisUsageMiddleware:
    """Redis使用量追踪中间件"""
    
    def __init__(self, redis_service: RedisUsageService):
        self.redis_service = redis_service
        self.monitored_patterns = [
            '/api/v1/flows',
            '/api/v1/tenant/flows',
            '/api/v1/chat',
            '/api/v1/run'
        ]
    
    async def process_request(self, request, call_next):
        """处理请求并记录使用量"""
        import time
        start_time = time.time()
        
        # 检查是否需要监控
        should_monitor = any(
            request.url.path.startswith(pattern)
            for pattern in self.monitored_patterns
        )
        
        if not should_monitor:
            return await call_next(request)
        
        # 获取组织上下文
        organization_id = getattr(request.state, 'current_organization_id', None)
        user_id = getattr(request.state, 'user_id', None)
        
        if not organization_id:
            return await call_next(request)
        
        # 配额检查（可选，根据需要启用）
        quota_check = await self.redis_service.check_quota_limit_fast(
            organization_id=organization_id,
            resource_type=ResourceType.API_CALL,
            metric_name=MetricName.COUNT,
            additional_usage=1,
            period=QuotaPeriod.DAILY
        )
        
        if not quota_check["allowed"]:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=429,
                detail=quota_check["message"],
                headers={"Retry-After": "86400"}  # 24小时后重试
            )
        
        # 执行请求
        response = await call_next(request)
        
        # 记录使用量（异步，不阻塞响应）
        execution_time = int((time.time() - start_time) * 1000)
        
        # 使用asyncio.create_task异步执行，避免阻塞
        asyncio.create_task(
            self._record_usage_async(
                organization_id, user_id, request, response, execution_time
            )
        )
        
        return response
    
    async def _record_usage_async(
        self,
        organization_id: str,
        user_id: Optional[str],
        request,
        response,
        execution_time: int
    ):
        """异步记录使用量"""
        try:
            # API调用计数
            await self.redis_service.record_usage_fast(
                organization_id=organization_id,
                resource_type=ResourceType.API_CALL,
                metric_name=MetricName.COUNT,
                metric_value=1,
                user_id=user_id,
                resource_id=request.url.path,
                metadata={
                    "method": request.method,
                    "status_code": response.status_code,
                    "endpoint": request.url.path,
                    "user_agent": request.headers.get("user-agent"),
                    "ip_address": request.client.host if request.client else None
                }
            )
            
            # 执行时间追踪
            await self.redis_service.record_usage_fast(
                organization_id=organization_id,
                resource_type=ResourceType.EXECUTION_TIME,
                metric_name=MetricName.MILLISECONDS,
                metric_value=execution_time,
                user_id=user_id,
                resource_id=request.url.path
            )
            
        except Exception as e:
            print(f"Async usage recording failed: {e}")


# 后台同步任务
class RedisToDBSyncTask:
    """Redis到数据库的后台同步任务"""
    
    def __init__(self, redis_service: RedisUsageService, sync_interval: int = 60):
        self.redis_service = redis_service
        self.sync_interval = sync_interval
        self.running = False
    
    async def start_sync_task(self):
        """启动后台同步任务"""
        self.running = True
        while self.running:
            try:
                async with get_session() as session:
                    sync_stats = await self.redis_service.sync_to_database(session)
                    if sync_stats["records_synced"] > 0:
                        print(f"Synced {sync_stats['records_synced']} records to database")
                    
                    if sync_stats["errors"] > 0:
                        print(f"Sync errors: {sync_stats['errors']}")
                        
            except Exception as e:
                print(f"Sync task error: {e}")
            
            await asyncio.sleep(self.sync_interval)
    
    def stop_sync_task(self):
        """停止后台同步任务"""
        self.running = False


# 依赖注入
def get_redis_usage_service() -> RedisUsageService:
    return RedisUsageService()
```

#### 2. API端点扩展

```python
# src/backend/base/langflow/api/v1/usage_redis.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.middleware.tenant_context import require_organization_context
from .redis_service import RedisUsageService, get_redis_usage_service

router = APIRouter(prefix="/usage-realtime", tags=["Real-time Usage Monitoring"])

@router.get("/stats")
async def get_realtime_stats(
    *,
    organization_id: str = Depends(require_organization_context),
    hours: int = 24,
    redis_service: RedisUsageService = Depends(get_redis_usage_service)
):
    """获取实时使用量统计"""
    try:
        stats = await redis_service.get_real_time_stats(
            organization_id=organization_id,
            hours=hours
        )
        return {
            "organization_id": organization_id,
            "time_window_hours": hours,
            "statistics": stats,
            "generated_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quota-status-fast")
async def get_quota_status_fast(
    *,
    organization_id: str = Depends(require_organization_context),
    redis_service: RedisUsageService = Depends(get_redis_usage_service)
):
    """快速获取配额状态"""
    try:
        quota_status = await redis_service.get_quota_status_fast(
            organization_id=organization_id
        )
        return quota_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-to-db")
async def sync_to_database(
    *,
    session: DbSession,
    current_user: CurrentActiveUser,
    redis_service: RedisUsageService = Depends(get_redis_usage_service)
):
    """手动触发同步到数据库（管理员功能）"""
    try:
        sync_stats = await redis_service.sync_to_database(session)
        return {
            "message": "Sync completed",
            "records_synced": sync_stats["records_synced"],
            "errors": sync_stats["errors"],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 方案二优势
- ✅ **高性能**: 毫秒级响应时间
- ✅ **高并发**: 支持万级并发请求
- ✅ **实时性**: 即时的使用量统计
- ✅ **弹性**: Redis故障时可回退到数据库
- ✅ **内存高效**: 自动过期机制控制内存使用

### 方案二劣势
- ❌ **复杂性**: 需要管理Redis集群和同步逻辑
- ❌ **数据一致性**: 可能存在Redis与数据库不一致
- ❌ **内存成本**: 需要额外的Redis资源
- ❌ **运维复杂**: 需要监控Redis和同步任务

---

## 方案三：基于时序数据库的分析监控

### 架构概述

使用专门的时序数据库（如InfluxDB或TimescaleDB）来处理大规模的使用量监控和分析，提供强大的时间序列查询能力和数据分析功能。

### 技术选型：TimescaleDB（基于PostgreSQL）

选择TimescaleDB的原因：
- 与现有PostgreSQL完美兼容
- 提供时序数据的高效压缩和查询
- 支持SQL查询，学习成本低
- 自动分区和数据保留策略

### 数据库设计

#### 1. 时序数据表（Hypertable）

```sql
-- 创建时序数据扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 使用量时序数据表
CREATE TABLE usage_timeseries (
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    organization_id TEXT NOT NULL,
    user_id UUID,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    metric_name TEXT NOT NULL,
    metric_value BIGINT NOT NULL,
    tags JSONB, -- 标签信息：endpoint, method, status_code等
    
    -- 为高基数字段创建索引
    INDEX(organization_id, resource_type, metric_name)
);

-- 转换为hypertable（时序表）
SELECT create_hypertable('usage_timeseries', 'time', chunk_time_interval => INTERVAL '1 day');

-- 创建连续聚合视图（实时聚合）
-- 每小时聚合
CREATE MATERIALIZED VIEW usage_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    organization_id,
    resource_type,
    metric_name,
    SUM(metric_value) as total_value,
    COUNT(*) as record_count,
    AVG(metric_value) as avg_value,
    MIN(metric_value) as min_value,
    MAX(metric_value) as max_value
FROM usage_timeseries
GROUP BY bucket, organization_id, resource_type, metric_name;

-- 每日聚合
CREATE MATERIALIZED VIEW usage_daily  
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS bucket,
    organization_id,
    resource_type, 
    metric_name,
    SUM(metric_value) as total_value,
    COUNT(*) as record_count,
    AVG(metric_value) as avg_value,
    MIN(metric_value) as min_value,
    MAX(metric_value) as max_value
FROM usage_timeseries
GROUP BY bucket, organization_id, resource_type, metric_name;

-- 设置自动刷新策略
SELECT add_continuous_aggregate_policy('usage_hourly',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

SELECT add_continuous_aggregate_policy('usage_daily',
    start_offset => INTERVAL '3 days', 
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

-- 数据保留策略
SELECT add_retention_policy('usage_timeseries', INTERVAL '1 year');
SELECT add_retention_policy('usage_hourly', INTERVAL '2 years');
SELECT add_retention_policy('usage_daily', INTERVAL '5 years');

-- 压缩策略（节省存储空间）
SELECT add_compression_policy('usage_timeseries', INTERVAL '7 days');
SELECT add_compression_policy('usage_hourly', INTERVAL '30 days');
```

#### 2. 配额管理表

```sql
-- 配额配置表（常规表）
CREATE TABLE quota_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    quota_limit BIGINT NOT NULL,
    time_window INTERVAL NOT NULL, -- '1 hour', '1 day', '1 month'
    alert_threshold FLOAT DEFAULT 0.8, -- 80%时告警
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(organization_id, resource_type, metric_name, time_window)
);

-- 插入默认配额
INSERT INTO quota_configurations 
(organization_id, resource_type, metric_name, quota_limit, time_window) VALUES
('default-org', 'api_call', 'count', 1000, '1 day'),
('default-org', 'api_call', 'count', 50, '1 hour'),
('default-org', 'storage', 'bytes', 104857600, '1 month'),
('default-org', 'execution_time', 'milliseconds', 3600000, '1 day');
```

### 实现代码

#### 1. TimescaleDB服务

```python
# src/backend/base/langflow/services/usage/timescale_service.py
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ResourceType, MetricName


class TimescaleUsageService:
    """基于TimescaleDB的时序监控服务"""
    
    async def record_usage_timeseries(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        metric_value: int,
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None
    ):
        """记录时序使用量数据"""
        query = text("""
            INSERT INTO usage_timeseries 
            (organization_id, user_id, resource_type, resource_id, metric_name, metric_value, tags)
            VALUES (:org_id, :user_id, :resource_type, :resource_id, :metric_name, :metric_value, :tags)
        """)
        
        await session.execute(query, {
            "org_id": organization_id,
            "user_id": user_id,
            "resource_type": resource_type.value,
            "resource_id": resource_id,
            "metric_name": metric_name.value,
            "metric_value": metric_value,
            "tags": tags
        })
        await session.commit()
    
    async def batch_record_usage_timeseries(
        self,
        session: AsyncSession,
        records: List[Dict[str, Any]]
    ):
        """批量记录时序数据"""
        if not records:
            return
        
        query = text("""
            INSERT INTO usage_timeseries 
            (organization_id, user_id, resource_type, resource_id, metric_name, metric_value, tags)
            VALUES 
        """ + ",".join([
            f"(:org_id_{i}, :user_id_{i}, :resource_type_{i}, :resource_id_{i}, :metric_name_{i}, :metric_value_{i}, :tags_{i})"
            for i in range(len(records))
        ]))
        
        params = {}
        for i, record in enumerate(records):
            params.update({
                f"org_id_{i}": record["organization_id"],
                f"user_id_{i}": record.get("user_id"),
                f"resource_type_{i}": record["resource_type"],
                f"resource_id_{i}": record.get("resource_id"),
                f"metric_name_{i}": record["metric_name"],
                f"metric_value_{i}": record["metric_value"],
                f"tags_{i}": record.get("tags")
            })
        
        await session.execute(query, params)
        await session.commit()
    
    async def check_quota_with_window(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        time_window: timedelta,
        additional_usage: int = 1
    ) -> Dict[str, Any]:
        """检查时间窗口内的配额限制"""
        
        # 获取配额限制
        quota_query = text("""
            SELECT quota_limit, alert_threshold
            FROM quota_configurations
            WHERE organization_id = :org_id 
                AND resource_type = :resource_type
                AND metric_name = :metric_name
                AND time_window = :time_window
                AND is_active = true
        """)
        
        quota_result = await session.execute(quota_query, {
            "org_id": organization_id,
            "resource_type": resource_type.value,
            "metric_name": metric_name.value,
            "time_window": time_window
        })
        
        quota_row = quota_result.fetchone()
        if not quota_row:
            return {"allowed": True, "message": "No quota configured"}
        
        quota_limit = quota_row[0]
        alert_threshold = quota_row[1]
        
        # 查询当前时间窗口内的使用量
        usage_query = text("""
            SELECT COALESCE(SUM(metric_value), 0) as current_usage
            FROM usage_timeseries
            WHERE organization_id = :org_id
                AND resource_type = :resource_type
                AND metric_name = :metric_name
                AND time >= NOW() - :time_window
        """)
        
        usage_result = await session.execute(usage_query, {
            "org_id": organization_id,
            "resource_type": resource_type.value,
            "metric_name": metric_name.value,
            "time_window": time_window
        })
        
        current_usage = usage_result.scalar() or 0
        
        if current_usage + additional_usage > quota_limit:
            return {
                "allowed": False,
                "message": f"Quota exceeded for {resource_type.value} in {time_window}",
                "quota_limit": quota_limit,
                "current_usage": current_usage,
                "remaining": max(0, quota_limit - current_usage),
                "usage_percentage": (current_usage / quota_limit) * 100
            }
        
        # 检查是否需要告警
        usage_percentage = (current_usage / quota_limit) * 100
        needs_alert = usage_percentage >= (alert_threshold * 100)
        
        return {
            "allowed": True,
            "quota_limit": quota_limit,
            "current_usage": current_usage,
            "remaining": quota_limit - current_usage,
            "usage_percentage": usage_percentage,
            "needs_alert": needs_alert,
            "alert_threshold": alert_threshold * 100
        }
    
    async def get_usage_trends(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: Optional[ResourceType] = None,
        metric_name: Optional[MetricName] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        granularity: str = "1 hour"
    ) -> List[Dict[str, Any]]:
        """获取使用量趋势分析"""
        
        if not start_time:
            start_time = datetime.utcnow() - timedelta(days=7)
        if not end_time:
            end_time = datetime.utcnow()
        
        # 构建查询条件
        conditions = ["organization_id = :org_id", "time BETWEEN :start_time AND :end_time"]
        params = {
            "org_id": organization_id,
            "start_time": start_time,
            "end_time": end_time,
            "granularity": granularity
        }
        
        if resource_type:
            conditions.append("resource_type = :resource_type")
            params["resource_type"] = resource_type.value
        
        if metric_name:
            conditions.append("metric_name = :metric_name")
            params["metric_name"] = metric_name.value
        
        where_clause = " AND ".join(conditions)
        
        query = text(f"""
            SELECT 
                time_bucket(:granularity, time) AS time_bucket,
                resource_type,
                metric_name,
                SUM(metric_value) as total_value,
                COUNT(*) as record_count,
                AVG(metric_value) as avg_value,
                MIN(metric_value) as min_value,
                MAX(metric_value) as max_value
            FROM usage_timeseries
            WHERE {where_clause}
            GROUP BY time_bucket, resource_type, metric_name
            ORDER BY time_bucket DESC
        """)
        
        result = await session.execute(query, params)
        
        trends = []
        for row in result:
            trends.append({
                "timestamp": row[0].isoformat(),
                "resource_type": row[1],
                "metric_name": row[2],
                "total_value": row[3],
                "record_count": row[4],
                "avg_value": float(row[5]) if row[5] else 0,
                "min_value": row[6],
                "max_value": row[7]
            })
        
        return trends
    
    async def get_usage_analytics(
        self,
        session: AsyncSession,
        organization_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """获取使用量分析报告"""
        
        if not start_time:
            start_time = datetime.utcnow() - timedelta(days=30)
        if not end_time:
            end_time = datetime.utcnow()
        
        # 1. 总体统计
        overview_query = text("""
            SELECT 
                resource_type,
                metric_name,
                SUM(metric_value) as total,
                COUNT(*) as count,
                AVG(metric_value) as average,
                MIN(metric_value) as minimum,
                MAX(metric_value) as maximum
            FROM usage_timeseries
            WHERE organization_id = :org_id 
                AND time BETWEEN :start_time AND :end_time
            GROUP BY resource_type, metric_name
        """)
        
        overview_result = await session.execute(overview_query, {
            "org_id": organization_id,
            "start_time": start_time,
            "end_time": end_time
        })
        
        overview = {}
        for row in overview_result:
            key = f"{row[0]}_{row[1]}"
            overview[key] = {
                "total": row[2],
                "count": row[3],
                "average": float(row[4]) if row[4] else 0,
                "minimum": row[5],
                "maximum": row[6]
            }
        
        # 2. 高峰时段分析
        peak_hours_query = text("""
            SELECT 
                EXTRACT(hour from time) as hour,
                SUM(metric_value) as total_usage,
                COUNT(*) as request_count
            FROM usage_timeseries
            WHERE organization_id = :org_id 
                AND time BETWEEN :start_time AND :end_time
                AND resource_type = 'api_call'
                AND metric_name = 'count'
            GROUP BY hour
            ORDER BY total_usage DESC
            LIMIT 5
        """)
        
        peak_result = await session.execute(peak_hours_query, {
            "org_id": organization_id,
            "start_time": start_time,
            "end_time": end_time
        })
        
        peak_hours = []
        for row in peak_result:
            peak_hours.append({
                "hour": int(row[0]),
                "total_usage": row[1],
                "request_count": row[2]
            })
        
        # 3. 用户使用分布
        user_distribution_query = text("""
            SELECT 
                user_id,
                SUM(metric_value) as total_usage,
                COUNT(*) as request_count
            FROM usage_timeseries
            WHERE organization_id = :org_id 
                AND time BETWEEN :start_time AND :end_time
                AND user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY total_usage DESC
            LIMIT 10
        """)
        
        user_result = await session.execute(user_distribution_query, {
            "org_id": organization_id,
            "start_time": start_time,
            "end_time": end_time
        })
        
        user_distribution = []
        for row in user_result:
            user_distribution.append({
                "user_id": str(row[0]),
                "total_usage": row[1],
                "request_count": row[2]
            })
        
        return {
            "period": {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            },
            "overview": overview,
            "peak_hours": peak_hours,
            "user_distribution": user_distribution
        }
    
    async def create_usage_alert(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: ResourceType,
        metric_name: MetricName,
        current_usage: int,
        quota_limit: int,
        threshold_percentage: float
    ):
        """创建使用量告警"""
        # 这里可以集成告警系统，如发送邮件、Slack通知等
        alert_data = {
            "organization_id": organization_id,
            "resource_type": resource_type.value,
            "metric_name": metric_name.value,
            "current_usage": current_usage,
            "quota_limit": quota_limit,
            "usage_percentage": (current_usage / quota_limit) * 100,
            "threshold_percentage": threshold_percentage * 100,
            "timestamp": datetime.utcnow().isoformat(),
            "alert_level": "warning" if (current_usage / quota_limit) < 0.9 else "critical"
        }
        
        # 记录告警到日志或告警系统
        print(f"USAGE ALERT: {alert_data}")
        
        # 可以扩展为发送通知
        # await self.send_alert_notification(alert_data)


# 中间件和装饰器
class TimescaleUsageMiddleware:
    """TimescaleDB使用量追踪中间件"""
    
    def __init__(self, service: TimescaleUsageService):
        self.service = service
        self.monitored_patterns = [
            '/api/v1/flows',
            '/api/v1/tenant/flows', 
            '/api/v1/chat',
            '/api/v1/run'
        ]
    
    async def process_request(self, request, call_next, session):
        """处理请求并记录到时序数据库"""
        import time
        start_time = time.time()
        
        # 检查监控模式
        should_monitor = any(
            request.url.path.startswith(pattern)
            for pattern in self.monitored_patterns
        )
        
        if not should_monitor:
            return await call_next(request)
        
        # 获取组织上下文
        organization_id = getattr(request.state, 'current_organization_id', None)
        user_id = getattr(request.state, 'user_id', None)
        
        if not organization_id:
            return await call_next(request)
        
        # 配额检查
        quota_check = await self.service.check_quota_with_window(
            session=session,
            organization_id=organization_id,
            resource_type=ResourceType.API_CALL,
            metric_name=MetricName.COUNT,
            time_window=timedelta(hours=1),  # 1小时窗口
            additional_usage=1
        )
        
        if not quota_check["allowed"]:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=429,
                detail=quota_check["message"]
            )
        
        # 执行请求
        response = await call_next(request)
        
        # 记录使用量
        execution_time = int((time.time() - start_time) * 1000)
        
        # 异步记录（可选择同步或异步）
        await self._record_timeseries_usage(
            session, organization_id, user_id, request, response, execution_time
        )
        
        # 检查告警
        if quota_check.get("needs_alert"):
            await self.service.create_usage_alert(
                session=session,
                organization_id=organization_id,
                resource_type=ResourceType.API_CALL,
                metric_name=MetricName.COUNT,
                current_usage=quota_check["current_usage"],
                quota_limit=quota_check["quota_limit"],
                threshold_percentage=quota_check.get("alert_threshold", 80) / 100
            )
        
        return response
    
    async def _record_timeseries_usage(
        self,
        session,
        organization_id: str,
        user_id: Optional[str],
        request,
        response,
        execution_time: int
    ):
        """记录时序使用量数据"""
        try:
            # 记录API调用
            await self.service.record_usage_timeseries(
                session=session,
                organization_id=organization_id,
                resource_type=ResourceType.API_CALL,
                metric_name=MetricName.COUNT,
                metric_value=1,
                user_id=user_id,
                resource_id=request.url.path,
                tags={
                    "method": request.method,
                    "status_code": response.status_code,
                    "endpoint": request.url.path,
                    "user_agent": request.headers.get("user-agent"),
                    "ip_address": request.client.host if request.client else None
                }
            )
            
            # 记录执行时间
            await self.service.record_usage_timeseries(
                session=session,
                organization_id=organization_id,
                resource_type=ResourceType.EXECUTION_TIME,
                metric_name=MetricName.MILLISECONDS,
                metric_value=execution_time,
                user_id=user_id,
                resource_id=request.url.path,
                tags={
                    "method": request.method,
                    "endpoint": request.url.path
                }
            )
            
        except Exception as e:
            print(f"Failed to record timeseries usage: {e}")


# 依赖注入
def get_timescale_usage_service() -> TimescaleUsageService:
    return TimescaleUsageService()
```

#### 2. 高级分析API

```python
# src/backend/base/langflow/api/v1/usage_analytics.py
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
from typing import Optional

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.middleware.tenant_context import require_organization_context
from .timescale_service import TimescaleUsageService, get_timescale_usage_service
from .models import ResourceType, MetricName

router = APIRouter(prefix="/usage-analytics", tags=["Usage Analytics"])

@router.get("/trends")
async def get_usage_trends(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    resource_type: Optional[ResourceType] = None,
    metric_name: Optional[MetricName] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    granularity: str = Query("1 hour", regex="^(1 minute|5 minutes|15 minutes|1 hour|1 day)$"),
    timescale_service: TimescaleUsageService = Depends(get_timescale_usage_service)
):
    """获取使用量趋势分析"""
    try:
        trends = await timescale_service.get_usage_trends(
            session=session,
            organization_id=organization_id,
            resource_type=resource_type,
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
            granularity=granularity
        )
        return {
            "organization_id": organization_id,
            "granularity": granularity,
            "trends": trends
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics")
async def get_usage_analytics(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    timescale_service: TimescaleUsageService = Depends(get_timescale_usage_service)
):
    """获取完整的使用量分析报告"""
    try:
        analytics = await timescale_service.get_usage_analytics(
            session=session,
            organization_id=organization_id,
            start_time=start_time,
            end_time=end_time
        )
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quota-check-advanced")
async def advanced_quota_check(
    *,
    session: DbSession,
    organization_id: str = Depends(require_organization_context),
    resource_type: ResourceType,
    metric_name: MetricName,
    time_window_hours: int = Query(24, ge=1, le=8760),  # 1小时到1年
    additional_usage: int = Query(1, ge=0),
    timescale_service: TimescaleUsageService = Depends(get_timescale_usage_service)
):
    """高级配额检查（支持自定义时间窗口）"""
    try:
        time_window = timedelta(hours=time_window_hours)
        quota_check = await timescale_service.check_quota_with_window(
            session=session,
            organization_id=organization_id,
            resource_type=resource_type,
            metric_name=metric_name,
            time_window=time_window,
            additional_usage=additional_usage
        )
        
        quota_check["time_window_hours"] = time_window_hours
        return quota_check
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 方案三优势
- ✅ **专业时序处理**: 专为时间序列数据优化
- ✅ **高效压缩**: 自动数据压缩，节省存储空间
- ✅ **强大分析**: 丰富的时间序列查询和分析功能
- ✅ **自动管理**: 自动分区、压缩、数据保留
- ✅ **SQL兼容**: 使用标准SQL查询，学习成本低
- ✅ **连续聚合**: 实时预聚合提高查询性能

### 方案三劣势
- ❌ **存储成本**: 需要更多存储空间
- ❌ **复杂配置**: 需要配置压缩、保留策略等
- ❌ **依赖扩展**: 依赖TimescaleDB扩展
- ❌ **查询复杂**: 复杂的时序查询学习成本

---

## 方案对比总结

| 特性 | 方案一：数据库 | 方案二：Redis | 方案三：时序DB |
|------|----------------|---------------|----------------|
| **性能** | 中等 | 优秀 | 中等-优秀 |
| **实时性** | 秒级 | 毫秒级 | 秒级 |
| **并发能力** | 中等 | 优秀 | 优秀 |
| **数据一致性** | 强 | 最终一致 | 强 |
| **查询能力** | 优秀 | 有限 | 专业 |
| **存储成本** | 中等 | 高(内存) | 中等 |
| **运维复杂度** | 低 | 高 | 中等 |
| **扩展性** | 有限 | 优秀 | 优秀 |
| **适用规模** | 中小型 | 大型 | 大型 |

## 推荐选择

- **中小型项目(< 100万API调用/天)**: 选择方案一
- **高并发项目(> 1000万API调用/天)**: 选择方案二
- **重分析和监控项目**: 选择方案三
- **预算充足的企业项目**: 方案二+方案三混合使用