# 多租户架构实现文档

## 概述

本文档详细介绍了Langflow项目中基于PostgreSQL行级安全(RLS)的多租户架构实现。该架构支持组织级别的数据隔离，确保不同租户之间的数据安全性和隐私性。

## 架构设计

### 核心原理

多租户架构采用**单数据库、行级安全(RLS)**的设计模式：

1. **数据隔离**: 使用PostgreSQL RLS在数据库层面自动过滤数据
2. **租户上下文**: 通过中间件自动设置当前组织上下文
3. **权限控制**: 基于用户组织关系进行访问控制
4. **跨租户功能**: 支持公共资源的跨组织共享

### 技术栈

- **后端**: FastAPI + SQLAlchemy + PostgreSQL RLS
- **前端**: React + TypeScript + Tailwind CSS
- **数据库**: PostgreSQL 13+
- **认证**: JWT + 组织成员关系验证

## 数据库设计

### 表结构变更

为支持多租户，以下核心表添加了`organization_id`字段：

```sql
-- 流程表
ALTER TABLE flow ADD COLUMN organization_id VARCHAR NOT NULL;
ALTER TABLE flow ADD CONSTRAINT fk_flow_organization 
  FOREIGN KEY (organization_id) REFERENCES organization(id);

-- 文件夹表  
ALTER TABLE folder ADD COLUMN organization_id VARCHAR NOT NULL;
ALTER TABLE folder ADD CONSTRAINT fk_folder_organization 
  FOREIGN KEY (organization_id) REFERENCES organization(id);

-- 变量表
ALTER TABLE variable ADD COLUMN organization_id VARCHAR NOT NULL;
ALTER TABLE variable ADD CONSTRAINT fk_variable_organization 
  FOREIGN KEY (organization_id) REFERENCES organization(id);
```

### RLS策略

创建行级安全策略确保数据隔离：

```sql
-- 启用RLS
ALTER TABLE flow ENABLE ROW LEVEL SECURITY;
ALTER TABLE folder ENABLE ROW LEVEL SECURITY;
ALTER TABLE variable ENABLE ROW LEVEL SECURITY;

-- 创建策略
CREATE POLICY flow_tenant_policy ON flow
  USING (organization_id = get_current_tenant());

CREATE POLICY folder_tenant_policy ON folder
  USING (organization_id = get_current_tenant());

CREATE POLICY variable_tenant_policy ON variable
  USING (organization_id = get_current_tenant());
```

### 租户上下文函数

```sql
-- 设置当前租户
CREATE OR REPLACE FUNCTION set_current_tenant(tenant_id TEXT)
RETURNS VOID AS $$
BEGIN
  PERFORM set_config('app.current_organization_id', tenant_id, false);
END;
$$ LANGUAGE plpgsql;

-- 获取当前租户
CREATE OR REPLACE FUNCTION get_current_tenant()
RETURNS TEXT AS $$
BEGIN
  RETURN current_setting('app.current_organization_id', true);
END;
$$ LANGUAGE plpgsql;
```

## 后端实现

### 1. 租户上下文中间件

位置: `src/backend/base/langflow/middleware/tenant_context.py`

**TenantContextMiddleware**负责：
- 从请求中提取组织ID（优先级：请求头 > 路径参数 > 查询参数 > 用户会话）
- 验证用户对组织的访问权限
- 设置数据库会话的租户上下文

```python
class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 提取组织ID
        org_id = await self._extract_organization_id(request)
        
        if org_id:
            # 验证访问权限
            if await self._validate_organization_access(request, org_id):
                # 设置租户上下文
                await self._set_tenant_context(request, org_id)
                request.state.current_organization_id = org_id
        
        return await call_next(request)
```

### 2. 多租户CRUD操作

#### FlowCRUD (流程管理)
位置: `src/backend/base/langflow/services/database/models/flow/crud.py`

主要功能：
- `create_flow()`: 创建流程，自动分配organization_id
- `get_flows_by_user()`: 获取用户在组织内的流程
- `search_flows()`: 支持跨组织公共流程搜索
- `duplicate_flow()`: 流程复制功能

#### FolderCRUD (文件夹管理)
位置: `src/backend/base/langflow/services/database/models/folder/crud.py`

主要功能：
- `get_folder_tree()`: 获取组织内文件夹树形结构
- `move_folder()`: 文件夹移动，防止循环引用
- `check_folder_name_exists()`: 同级文件夹名称唯一性检查

#### VariableCRUD (变量管理)
位置: `src/backend/base/langflow/services/database/models/variable/crud.py`

主要功能：
- `get_variables_by_type()`: 按类型获取变量
- `check_variable_name_exists()`: 用户级别变量名唯一性检查
- `duplicate_variable()`: 变量复制功能

### 3. 租户感知API端点

#### 流程API
位置: `src/backend/base/langflow/api/v1/tenant_flows.py`

端点前缀: `/api/v1/tenant/flows`

主要端点：
- `GET /` - 获取组织流程列表
- `POST /` - 创建新流程
- `GET /organization` - 管理员视图获取所有流程
- `GET /public` - 获取跨组织公共流程
- `GET /search` - 搜索流程
- `POST /{flow_id}/duplicate` - 复制流程

#### 项目API
位置: `src/backend/base/langflow/api/v1/tenant_projects.py`

端点前缀: `/api/v1/tenant/projects`

主要端点：
- `GET /tree` - 获取文件夹树形结构
- `PATCH /{project_id}/move` - 移动项目到其他文件夹

#### 变量API
位置: `src/backend/base/langflow/api/v1/tenant_variables.py`

端点前缀: `/api/v1/tenant/variables`

主要端点：
- `GET /by-type/{variable_type}` - 按类型获取变量
- `GET /by-name/{variable_name}` - 按名称获取变量
- `POST /{variable_id}/duplicate` - 复制变量

## 前端实现

### 1. 租户上下文管理

位置: `src/frontend/src/contexts/TenantContext.tsx`

**TenantProvider**提供：
- 当前组织状态管理
- 组织列表管理
- 组织切换功能
- HTTP请求头自动设置

```typescript
interface TenantContextType {
  currentOrganization: Organization | null;
  organizations: Organization[];
  switchOrganization: (orgId: string) => Promise<void>;
  refreshOrganizations: () => Promise<void>;
}

export const useTenant = (): TenantContextType => {
  // 返回租户上下文
};
```

### 2. 组织选择器组件

位置: `src/frontend/src/components/tenant/TenantSelector.tsx`

功能特性：
- 下拉式组织选择器
- 显示组织类型（个人/团队）和计划等级
- 支持创建新组织
- 响应式设计，支持移动端

### 3. 租户管理页面

位置: `src/frontend/src/pages/TenantManagementPage.tsx`

包含三个主要标签页：
- **概览**: 使用情况统计（流程、变量、API调用、存储空间）
- **成员**: 团队成员管理（仅团队账户）
- **设置**: 组织设置和危险操作

### 4. 租户感知导航栏

位置: `src/frontend/src/components/tenant/TenantAwareNavbar.tsx`

功能特性：
- 集成租户选择器
- 搜索功能
- 用户菜单包含组织设置入口
- 响应式设计

## API集成

### 请求头设置

所有需要租户上下文的API请求都需要包含组织ID：

```typescript
// 方式1：请求头（推荐）
headers: {
  'X-Organization-ID': 'org-123'
}

// 方式2：查询参数
/api/v1/flows?org_id=org-123

// 方式3：路径参数
/api/v1/organizations/org-123/flows
```

### 依赖注入

后端使用FastAPI依赖注入获取组织上下文：

```python
from langflow.middleware.tenant_context import require_organization_context

@router.get("/flows")
async def get_flows(
    organization_id: str = Depends(require_organization_context)
):
    # organization_id 自动从请求上下文中获取
    pass
```

## 使用指南

### 1. 开发环境设置

```bash
# 运行数据库迁移
alembic upgrade head

# 启动后端服务
make backend

# 启动前端服务
make frontend
```

### 2. 创建组织

```python
# 通过API创建新组织
POST /api/v1/billing/organizations
{
  "name": "my-company",
  "display_name": "My Company",
  "plan_id": "professional"
}
```

### 3. 在代码中使用

#### 后端CRUD操作

```python
from langflow.services.database.models.flow.crud import FlowCRUD

# 创建流程
flow = await FlowCRUD.create_flow(
    session=session,
    flow_data=flow_data,
    organization_id=organization_id,
    user_id=user_id
)

# 搜索流程（包含公共流程）
flows = await FlowCRUD.search_flows(
    session=session,
    organization_id=organization_id,
    query="search term",
    include_public=True
)
```

#### 前端组件使用

```typescript
import { useTenant } from '../contexts/TenantContext';

function MyComponent() {
  const { currentOrganization, switchOrganization } = useTenant();
  
  const handleOrgChange = async (newOrgId: string) => {
    await switchOrganization(newOrgId);
    // 页面会自动刷新以加载新组织的数据
  };
  
  return (
    <div>
      <p>Current org: {currentOrganization?.name}</p>
      <TenantSelector 
        currentOrganization={currentOrganization}
        onOrganizationChange={handleOrgChange}
      />
    </div>
  );
}
```

## 安全考虑

### 数据隔离保证

1. **数据库层**: RLS策略确保查询自动过滤
2. **应用层**: 中间件验证用户组织权限
3. **API层**: 依赖注入确保组织上下文正确

### 权限模型

- **个人账户**: 用户拥有完全控制权
- **团队账户**: 基于角色的权限控制
  - `admin`: 可管理组织设置和成员
  - `member`: 可访问组织资源
  - `viewer`: 只读访问权限

### 跨租户功能

某些功能支持跨组织访问：
- **公共流程**: 设置为PUBLIC的流程可被其他组织发现
- **组织间复制**: 支持将资源复制到其他组织

## 性能优化

### 数据库索引

```sql
-- 为多租户查询优化的索引
CREATE INDEX idx_flow_org_user ON flow(organization_id, user_id);
CREATE INDEX idx_folder_org_parent ON folder(organization_id, parent_id);
CREATE INDEX idx_variable_org_type ON variable(organization_id, type);
```

### 查询优化

- RLS策略使用函数索引优化
- 分页查询避免全表扫描
- 适当使用查询缓存

## 监控和日志

### 租户上下文日志

```python
import logging
logger = logging.getLogger(__name__)

async def set_organization_context(session: AsyncSession, org_id: str):
    logger.info(f"Setting tenant context to organization: {org_id}")
    # 设置上下文逻辑
```

### 使用情况监控

- API调用次数按组织统计
- 存储空间使用量监控
- 用户活跃度跟踪

## 故障排除

### 常见问题

1. **RLS策略不生效**
   - 检查`app.current_organization_id`是否正确设置
   - 确认用户有足够权限访问组织

2. **跨租户数据泄露**
   - 验证所有查询都通过租户感知的CRUD操作
   - 检查RLS策略是否正确启用

3. **性能问题**
   - 检查是否创建了适当的索引
   - 考虑查询缓存策略

### 调试工具

```sql
-- 查看当前租户设置
SELECT current_setting('app.current_organization_id', true);

-- 测试RLS策略
SET row_security = off; -- 查看所有数据
SET row_security = on;  -- 查看过滤后数据
```

## 迁移指南

### 从单租户迁移

1. **数据迁移**: 为现有数据分配默认组织ID
2. **API更新**: 逐步迁移到租户感知的端点
3. **前端更新**: 集成租户选择器和上下文

### 版本兼容性

- 保留原有API端点以确保向后兼容
- 新功能优先使用租户感知端点
- 逐步废弃旧端点

---

## 参考资料

- [PostgreSQL行级安全文档](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [FastAPI依赖注入](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [React Context API](https://react.dev/reference/react/createContext)