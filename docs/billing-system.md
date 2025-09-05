# Langflow 订阅计费系统实现文档

## 概述

本文档详细描述了为Langflow实现的完整订阅计费系统，包括数据库设计、API实现、前端界面和Stripe支付集成。该系统支持多租户架构、分层定价、使用量追踪和企业级功能。

## 系统架构

### 核心组件

1. **数据模型层** - SQLModel/SQLAlchemy数据库模型
2. **业务服务层** - Stripe集成和使用量追踪服务
3. **API接口层** - FastAPI RESTful端点
4. **前端界面层** - React/TypeScript用户界面
5. **中间件层** - 使用量监控和配额限制

### 技术栈

- **后端**: Python 3.10+, FastAPI, SQLAlchemy, Alembic
- **数据库**: PostgreSQL (生产) / SQLite (开发)
- **支付**: Stripe API v8+
- **前端**: React 18, TypeScript, Tailwind CSS
- **图表**: Recharts
- **状态管理**: React Hooks + Custom Hooks

## 数据库设计

### 核心数据表

#### 1. Organization (组织表)
```sql
CREATE TABLE organization (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(500),
    logo_url VARCHAR,
    website VARCHAR,
    industry VARCHAR,
    owner_id UUID REFERENCES user(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**用途**: 支持多租户架构，每个组织独立计费和管理用户

#### 2. SubscriptionPlan (订阅计划表)
```sql
CREATE TABLE subscriptionplan (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    plan_type VARCHAR NOT NULL, -- 'free', 'basic', 'professional', 'enterprise'
    price DECIMAL(10,2) NOT NULL,
    yearly_price DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'USD',
    stripe_price_id VARCHAR UNIQUE,
    stripe_yearly_price_id VARCHAR UNIQUE,
    limits JSON, -- {"api_calls": 10000, "storage_mb": 1000}
    features JSON, -- ["advanced_analytics", "sso"]
    is_active BOOLEAN DEFAULT TRUE,
    is_popular BOOLEAN DEFAULT FALSE
);
```

**预设计划**:
- **Free**: $0, 1K API调用, 基础功能
- **Basic**: $29/月, 25K API调用, 团队功能
- **Professional**: $99/月, 100K API调用, 高级功能
- **Enterprise**: $299/月, 无限使用, 企业功能

#### 3. Subscription (订阅表)
```sql
CREATE TABLE subscription (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organization(id),
    plan_id UUID REFERENCES subscriptionplan(id),
    stripe_customer_id VARCHAR,
    stripe_subscription_id VARCHAR UNIQUE,
    status VARCHAR NOT NULL, -- 'active', 'canceled', 'past_due'
    is_yearly BOOLEAN DEFAULT FALSE,
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    trial_end TIMESTAMP,
    cancel_at_period_end BOOLEAN DEFAULT FALSE
);
```

#### 4. UsageMetric (使用量追踪表)
```sql
CREATE TABLE usagemetric (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organization(id),
    metric_type VARCHAR NOT NULL, -- 'api_calls', 'flow_executions', 'storage_mb'
    value INTEGER NOT NULL,
    recorded_at TIMESTAMP DEFAULT NOW(),
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    metadata JSON -- 额外信息如用户ID、流程ID
);
```

### 数据库迁移

```bash
# 创建迁移
alembic revision -m "Add subscription tables"

# 应用迁移
alembic upgrade head
```

迁移文件位置: `src/backend/base/langflow/alembic/versions/create_subscription_tables.py`

## API设计

### 端点概览

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/billing/organizations` | GET, POST | 组织管理 |
| `/api/v1/billing/plans` | GET | 获取定价计划 |
| `/api/v1/billing/organizations/{id}/subscription` | GET, POST, PUT, DELETE | 订阅管理 |
| `/api/v1/billing/organizations/{id}/usage` | GET | 使用量统计 |
| `/api/v1/billing/organizations/{id}/invoices` | GET | 发票历史 |
| `/api/v1/billing/webhooks/stripe` | POST | Stripe Webhook |

### 关键API实现

#### 创建订阅
```python
@router.post("/organizations/{org_id}/subscription")
async def create_subscription(
    org_id: str,
    request: CreateSubscriptionRequest,
    current_user: CurrentActiveUser,
    session: DbSession
) -> Dict:
    # 验证组织权限
    # 检查现有订阅
    # 创建Stripe订阅
    # 保存数据库记录
    # 返回支付信息
```

#### 使用量追踪
```python
@router.get("/organizations/{org_id}/usage")
async def get_usage_summary(
    org_id: str,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    current_user: CurrentActiveUser,
    session: DbSession
) -> UsageSummary:
    # 获取指定期间的使用量统计
    # 计算使用率和剩余配额
    # 返回格式化数据
```

## Stripe集成

### 服务类设计

```python
class StripeService:
    def __init__(self, settings_service: SettingsService):
        stripe.api_key = settings_service.stripe_secret_key
        
    async def create_subscription(self, session, org_id, plan_id, **options):
        # 创建Stripe客户
        # 创建订阅
        # 处理支付方式
        # 同步数据库
        
    async def handle_webhook(self, payload, signature, session):
        # 验证签名
        # 处理不同事件类型
        # 更新本地数据
```

### Webhook处理

支持的事件类型:
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

### 环境配置

```python
# settings/base.py
class Settings(BaseSettings):
    # Stripe配置
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None
    
    # 计费配置
    billing_enabled: bool = False
    default_trial_days: int = 14
    usage_tracking_enabled: bool = True
```

## 使用量监控

### 中间件实现

```python
class UsageTrackingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, usage_service: UsageService):
        super().__init__(app)
        self.usage_service = usage_service
        
    async def dispatch(self, request: Request, call_next):
        # 检查是否需要追踪
        # 验证配额
        # 处理请求
        # 记录使用量
```

### 装饰器支持

```python
# 配额检查装饰器
@check_quota(MetricType.API_CALLS, amount=1)
async def api_endpoint():
    # 自动检查API调用配额
    pass

# 使用量追踪装饰器
@track_usage(MetricType.FLOW_EXECUTIONS)
async def execute_flow():
    # 自动记录流程执行
    pass

# 订阅等级要求
@require_subscription("professional")
async def advanced_feature():
    # 需要专业版或以上订阅
    pass
```

### 使用量类型

```python
class MetricType(str, Enum):
    API_CALLS = "api_calls"           # API调用次数
    FLOW_EXECUTIONS = "flow_executions"  # 流程执行次数
    STORAGE_MB = "storage_mb"         # 存储空间使用
    COMPUTE_MINUTES = "compute_minutes"  # 计算时间
    TEAM_MEMBERS = "team_members"     # 团队成员数量
```

## 前端界面

### 组件架构

```
components/billing/
├── BillingDashboard.tsx      # 主面板
├── PricingCard.tsx           # 定价卡片
├── UsageChart.tsx            # 使用量图表
└── UsageAlert.tsx            # 配额告警
```

### 主要功能

#### 1. BillingDashboard
- 组织切换
- 订阅状态显示
- 使用量可视化
- 计费历史
- 计划升级

#### 2. PricingCard
- 响应式定价展示
- 功能对比
- 订阅按钮
- 当前计划标识

#### 3. UsageChart
- Recharts图表展示
- 进度条显示
- 配额使用率
- 多指标对比

### 自定义Hook

```typescript
export const useBilling = (organizationId?: string) => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [currentSubscription, setCurrentSubscription] = useState<CurrentSubscription | null>(null);
  
  // 数据加载方法
  const loadOrganizations = async () => { /* ... */ };
  const createSubscription = async (orgId: string, planId: string) => { /* ... */ };
  
  return {
    organizations,
    plans,
    currentSubscription,
    // ... 方法
  };
};
```

## 部署配置

### 1. 环境变量设置

```bash
# Stripe配置
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# 计费功能开关
BILLING_ENABLED=true
USAGE_TRACKING_ENABLED=true
DEFAULT_TRIAL_DAYS=14
```

### 2. 数据库初始化

```bash
# 运行迁移
alembic upgrade head

# 初始化订阅计划（已在迁移中自动执行）
# Free, Basic, Professional, Enterprise计划会自动创建
```

### 3. Stripe配置

#### 创建产品和价格
```bash
# 使用Stripe CLI或Dashboard创建产品
# 设置月度和年度价格
# 配置Webhook端点: /api/v1/billing/webhooks/stripe
```

#### Webhook事件订阅
- customer.subscription.created
- customer.subscription.updated  
- customer.subscription.deleted
- invoice.payment_succeeded
- invoice.payment_failed

### 4. 前端路由配置

```typescript
// 添加到路由配置
{
  path: "/billing",
  component: BillingPage,
  protected: true
}
```

## 安全考虑

### 1. 数据访问控制
- 组织级数据隔离
- 用户权限验证
- API密钥管理

### 2. 支付安全
- Webhook签名验证
- HTTPS强制要求
- PCI DSS合规性

### 3. 使用量保护
- 软限制 + 硬限制
- 渐进式警告
- 优雅降级

## 监控和日志

### 1. 关键指标监控
- 订阅创建/取消率
- 使用量趋势
- 支付成功率
- API响应时间

### 2. 日志记录
- 所有计费操作
- Webhook事件处理
- 配额超限事件
- 错误和异常

### 3. 告警配置
- 支付失败
- Webhook处理失败
- 使用量异常
- 系统错误

## 测试策略

### 1. 单元测试
- 数据模型验证
- 业务逻辑测试
- API端点测试

### 2. 集成测试
- Stripe API集成
- 数据库操作
- Webhook处理

### 3. 端到端测试
- 完整订阅流程
- 支付流程测试
- 前端交互测试

## 性能优化

### 1. 数据库优化
- 合适的索引策略
- 查询优化
- 连接池配置

### 2. 缓存策略
- 订阅计划缓存
- 使用量汇总缓存
- Redis集群支持

### 3. API优化
- 响应时间监控
- 并发限制
- 异步处理

## 扩展计划

### Phase 2 功能
- 按量计费模式
- 企业级SSO集成
- 高级分析报表
- API使用分析

### Phase 3 功能
- 多币种支持
- 税务计算
- 发票定制
- 合规报告

### 技术改进
- 微服务架构
- 事件驱动设计
- 自动扩缩容
- 多区域部署

## 故障排除

### 常见问题

#### 1. Webhook失败
- 检查签名验证
- 验证端点可达性
- 查看错误日志

#### 2. 支付失败
- 检查Stripe密钥配置
- 验证支付方式
- 查看客户状态

#### 3. 使用量不准确
- 检查中间件配置
- 验证追踪逻辑
- 查看数据完整性

### 调试工具
- Stripe CLI测试Webhook
- 数据库查询工具
- 日志聚合分析
- 性能监控面板

## 总结

本实现为Langflow提供了企业级的订阅计费系统，具备以下特点：

✅ **完整的商业化基础** - 从免费到企业版的完整定价体系
✅ **灵活的架构设计** - 支持多租户和扩展需求
✅ **可靠的支付处理** - Stripe集成确保支付安全
✅ **实时监控能力** - 使用量追踪和配额管理
✅ **现代化用户界面** - 直观的计费管理体验
✅ **企业级特性** - 安全、合规、可扩展

该系统已准备好投入生产环境，为Langflow的商业化转型提供强有力的支持。