# Billing API 参考文档

本文档详细描述了Langflow订阅计费系统的所有API端点。

## 基础信息

- **Base URL**: `/api/v1/billing`
- **认证方式**: Bearer Token (JWT)
- **Content-Type**: `application/json`
- **响应格式**: JSON

## 组织管理 API

### 创建组织

**POST** `/organizations`

创建新的组织。

#### 请求体
```json
{
  "name": "My Organization",
  "slug": "my-org",
  "description": "Organization description (optional)"
}
```

#### 响应
```json
{
  "id": "org_123456",
  "name": "My Organization", 
  "slug": "my-org",
  "description": "Organization description",
  "created_at": "2025-01-04T12:00:00Z"
}
```

#### 状态码
- `201` - 创建成功
- `400` - 请求参数错误或slug已存在
- `401` - 未认证
- `500` - 服务器错误

### 获取用户组织列表

**GET** `/organizations`

获取当前用户所属的所有组织。

#### 响应
```json
[
  {
    "id": "org_123456",
    "name": "My Organization",
    "slug": "my-org", 
    "description": "Organization description",
    "created_at": "2025-01-04T12:00:00Z"
  }
]
```

### 获取组织详情

**GET** `/organizations/{org_id}`

获取指定组织的详细信息。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 响应
```json
{
  "id": "org_123456",
  "name": "My Organization",
  "slug": "my-org",
  "description": "Organization description", 
  "logo_url": "https://example.com/logo.png",
  "website": "https://example.com",
  "industry": "Technology",
  "created_at": "2025-01-04T12:00:00Z"
}
```

## 订阅计划 API

### 获取订阅计划列表

**GET** `/plans`

获取所有可用的订阅计划。

#### 响应
```json
[
  {
    "id": "plan_free",
    "name": "Free Plan",
    "plan_type": "free",
    "description": "Perfect for individuals getting started",
    "price": 0.00,
    "yearly_price": 0.00,
    "currency": "USD",
    "limits": {
      "api_calls": 1000,
      "flow_executions": 100,
      "storage_mb": 100,
      "team_members": 1
    },
    "features": [
      "basic_components",
      "community_support"
    ],
    "is_active": true,
    "is_popular": false
  },
  {
    "id": "plan_professional", 
    "name": "Professional Plan",
    "plan_type": "professional",
    "description": "Ideal for professional teams",
    "price": 99.00,
    "yearly_price": 990.00,
    "currency": "USD",
    "limits": {
      "api_calls": 100000,
      "flow_executions": 10000,
      "storage_mb": 5000,
      "team_members": 10
    },
    "features": [
      "premium_components",
      "priority_support", 
      "advanced_analytics",
      "sso"
    ],
    "is_active": true,
    "is_popular": true
  }
]
```

## 订阅管理 API

### 创建订阅

**POST** `/organizations/{org_id}/subscription`

为组织创建新的订阅。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 请求体
```json
{
  "plan_id": "plan_professional",
  "payment_method_id": "pm_123456", // 可选，Stripe支付方式ID
  "is_yearly": false,
  "trial_days": 14 // 可选，试用天数
}
```

#### 响应
```json
{
  "subscription_id": "sub_123456",
  "client_secret": "pi_123456_secret_xyz", // 用于Stripe支付确认
  "status": "trialing"
}
```

#### 状态码
- `201` - 创建成功
- `400` - 组织已有活跃订阅或参数错误
- `404` - 组织或计划不存在
- `500` - 创建失败

### 获取组织订阅

**GET** `/organizations/{org_id}/subscription`

获取组织的当前订阅信息。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 响应
```json
{
  "id": "sub_123456",
  "status": "active", 
  "is_yearly": false,
  "current_period_start": "2025-01-01T00:00:00Z",
  "current_period_end": "2025-02-01T00:00:00Z",
  "trial_end": "2025-01-15T00:00:00Z", // 如果有试用期
  "cancel_at_period_end": false,
  "plan": {
    "id": "plan_professional",
    "name": "Professional Plan",
    "plan_type": "professional",
    "price": 99.00,
    "limits": {
      "api_calls": 100000,
      "flow_executions": 10000,
      "storage_mb": 5000,
      "team_members": 10
    }
  }
}
```

#### 状态码
- `200` - 获取成功
- `404` - 订阅不存在
- `403` - 无权访问

### 更新订阅

**PUT** `/organizations/{org_id}/subscription`

更新组织的订阅计划。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 请求体
```json
{
  "plan_id": "plan_enterprise",
  "proration_behavior": "create_prorations" // 可选: create_prorations, none, always_invoice
}
```

#### 响应
```json
{
  "message": "Subscription updated successfully",
  "subscription_id": "sub_123456"
}
```

### 取消订阅

**DELETE** `/organizations/{org_id}/subscription`

取消组织的订阅。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 查询参数
- `cancel_immediately` (boolean, optional): 是否立即取消，默认false（期末取消）

#### 响应
```json
{
  "message": "Subscription canceled successfully", 
  "cancel_at_period_end": true
}
```

## 使用量统计 API

### 获取使用量汇总

**GET** `/organizations/{org_id}/usage`

获取组织的使用量统计信息。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 查询参数
- `period_start` (datetime, optional): 统计开始时间，默认当前计费周期
- `period_end` (datetime, optional): 统计结束时间，默认当前计费周期

#### 响应
```json
{
  "period_start": "2025-01-01T00:00:00Z",
  "period_end": "2025-02-01T00:00:00Z", 
  "metrics": {
    "api_calls": 15000,
    "flow_executions": 1200,
    "storage_mb": 2500,
    "compute_minutes": 300,
    "team_members": 5
  },
  "limits": {
    "api_calls": 100000,
    "flow_executions": 10000, 
    "storage_mb": 5000,
    "compute_minutes": -1,
    "team_members": 10
  },
  "usage_percentage": {
    "api_calls": 15.0,
    "flow_executions": 12.0,
    "storage_mb": 50.0,
    "compute_minutes": 0.0,
    "team_members": 50.0
  }
}
```

### 检查配额

**GET** `/organizations/{org_id}/usage/quota`

检查特定指标的配额使用情况。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 查询参数
- `metric_type` (string, required): 指标类型 (`api_calls`, `flow_executions`, `storage_mb`, `compute_minutes`, `team_members`)
- `requested_amount` (integer, optional): 请求使用量，默认1

#### 响应
```json
{
  "can_use": true,
  "quota_info": {
    "metric_type": "api_calls",
    "current_usage": 15000,
    "limit": 100000,
    "requested_amount": 1,
    "remaining": 85000,
    "unlimited": false
  }
}
```

### 获取配额告警

**GET** `/organizations/{org_id}/usage/alerts`

获取配额使用告警信息。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 查询参数
- `warning_threshold` (float, optional): 告警阈值（0.0-1.0），默认0.8（80%）

#### 响应
```json
{
  "alerts": [
    {
      "metric_type": "storage_mb",
      "usage_percentage": 85.5,
      "current_usage": 4275,
      "limit": 5000,
      "severity": "warning",
      "message": "storage_mb usage is at 85.5% of quota"
    }
  ],
  "alert_count": 1,
  "has_critical": false
}
```

### 手动追踪使用量

**POST** `/organizations/{org_id}/usage/track`

手动记录使用量（主要用于测试）。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 请求体
```json
{
  "metric_type": "api_calls",
  "value": 1,
  "metadata": {
    "endpoint": "/api/v1/flows/run",
    "user_id": "user_123"
  }
}
```

#### 响应
```json
{
  "success": true,
  "metric_type": "api_calls",
  "value": 1
}
```

## 发票管理 API

### 获取发票列表

**GET** `/organizations/{org_id}/invoices`

获取组织的发票历史记录。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 查询参数
- `limit` (integer, optional): 返回数量限制，默认50

#### 响应
```json
{
  "invoices": [
    {
      "id": "inv_123456",
      "invoice_number": "INV-2025-001",
      "amount": 99.00,
      "currency": "USD",
      "status": "paid",
      "period_start": "2025-01-01T00:00:00Z",
      "period_end": "2025-02-01T00:00:00Z",
      "created_at": "2025-01-01T00:00:00Z",
      "hosted_invoice_url": "https://invoice.stripe.com/i/..."
    }
  ],
  "total": 1
}
```

## 客户门户 API

### 创建客户门户会话

**POST** `/organizations/{org_id}/billing-portal`

创建Stripe客户门户会话，用户可以管理支付方式和订阅。

#### 路径参数
- `org_id` (string, required): 组织ID

#### 请求体
```json
{
  "return_url": "https://app.langflow.org/billing"
}
```

#### 响应
```json
{
  "url": "https://billing.stripe.com/p/session_xyz123"
}
```

## Webhook API

### Stripe Webhook

**POST** `/webhooks/stripe`

接收Stripe Webhook事件通知。

#### 请求头
- `Stripe-Signature` (string, required): Stripe签名

#### 请求体
Stripe事件JSON payload

#### 响应
```json
{
  "status": "success",
  "event_type": "customer.subscription.updated"
}
```

#### 支持的事件类型
- `customer.subscription.created`
- `customer.subscription.updated`  
- `customer.subscription.deleted`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

## 错误处理

### 错误响应格式

```json
{
  "error": "Error message",
  "detail": "Detailed error description",
  "code": "ERROR_CODE"
}
```

### 常见状态码

- `200` - 成功
- `201` - 创建成功  
- `400` - 请求参数错误
- `401` - 未认证
- `403` - 权限不足
- `404` - 资源不存在
- `409` - 资源冲突
- `429` - 配额超限
- `500` - 服务器内部错误

### 特殊错误

#### 配额超限错误 (429)
```json
{
  "error": "Usage quota exceeded",
  "quota_info": {
    "metric_type": "api_calls",
    "current_usage": 10000,
    "limit": 10000,
    "remaining": 0
  }
}
```

#### 订阅错误 (402)
```json
{
  "error": "This feature requires a professional subscription",
  "required_plan": "professional",
  "current_plan": "basic"
}
```

## 使用示例

### JavaScript/TypeScript

```typescript
// 获取订阅计划
const plans = await fetch('/api/v1/billing/plans')
  .then(res => res.json());

// 创建订阅
const subscription = await fetch(`/api/v1/billing/organizations/${orgId}/subscription`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    plan_id: 'plan_professional',
    is_yearly: false,
    trial_days: 14
  })
}).then(res => res.json());

// 检查配额
const quota = await fetch(`/api/v1/billing/organizations/${orgId}/usage/quota?metric_type=api_calls`)
  .then(res => res.json());
```

### Python

```python
import requests

# 获取使用量统计
response = requests.get(
    f'/api/v1/billing/organizations/{org_id}/usage',
    headers={'Authorization': f'Bearer {token}'}
)
usage = response.json()

# 创建客户门户会话
response = requests.post(
    f'/api/v1/billing/organizations/{org_id}/billing-portal',
    json={'return_url': 'https://app.langflow.org/billing'},
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
)
portal_url = response.json()['url']
```

## 速率限制

- 大部分端点: 100 请求/分钟
- Webhook端点: 1000 请求/分钟  
- 使用量查询: 200 请求/分钟

## 测试

### 测试模式

在测试环境中，使用Stripe测试密钥:
- `STRIPE_SECRET_KEY=sk_test_...`
- `STRIPE_PUBLISHABLE_KEY=pk_test_...`

### 测试卡号

- 成功支付: `4242424242424242`
- 支付失败: `4000000000000002`
- 需要3D验证: `4000002500003155`

### Webhook测试

使用Stripe CLI转发Webhook:
```bash
stripe listen --forward-to localhost:7860/api/v1/billing/webhooks/stripe
```