# 多租户API接口文档

## 概述

本文档详细介绍了Langflow多租户架构中新增的API接口。这些接口都自动应用组织上下文，确保数据隔离和安全性。

## 认证和授权

### 组织上下文设置

所有租户感知的API请求需要包含组织标识，支持以下方式：

#### 1. 请求头（推荐）
```http
GET /api/v1/tenant/flows
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json
```

#### 2. 查询参数
```http
GET /api/v1/tenant/flows?org_id=org-123
```

#### 3. 路径参数
```http
GET /api/v1/organizations/org-123/flows
```

### 权限模型

- **admin**: 完全控制权限，可管理组织设置
- **member**: 可创建和管理自己的资源
- **viewer**: 只读权限

## 租户流程API

基础路径: `/api/v1/tenant/flows`

### 创建流程

```http
POST /api/v1/tenant/flows
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "name": "My Flow",
  "description": "A sample flow",
  "data": {
    "nodes": [...],
    "edges": [...]
  },
  "folder_id": "folder-uuid",
  "is_component": false,
  "access_type": "PRIVATE"
}

Response (201):
{
  "id": "flow-uuid",
  "name": "My Flow",
  "description": "A sample flow",
  "user_id": "user-uuid",
  "organization_id": "org-123",
  "folder_id": "folder-uuid",
  "is_component": false,
  "access_type": "PRIVATE",
  "created_at": "2024-03-15T10:30:00Z",
  "updated_at": "2024-03-15T10:30:00Z"
}
```

### 获取流程列表

```http
GET /api/v1/tenant/flows
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  folder_id: string (optional) - 筛选指定文件夹的流程
  limit: int (optional, default: 50) - 返回数量限制
  offset: int (optional, default: 0) - 偏移量

Response (200):
[
  {
    "id": "flow-uuid",
    "name": "My Flow",
    "description": "A sample flow",
    "user_id": "user-uuid",
    "folder_id": "folder-uuid",
    "is_component": false,
    "access_type": "PRIVATE",
    "updated_at": "2024-03-15T10:30:00Z"
  }
]
```

### 获取组织所有流程（管理员视图）

```http
GET /api/v1/tenant/flows/organization
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  limit: int (optional, default: 50)
  offset: int (optional, default: 0)
  search_query: string (optional) - 搜索关键词

Response (200):
[
  {
    "id": "flow-uuid",
    "name": "Team Flow",
    "description": "Created by team member",
    "user_id": "other-user-uuid",
    "folder_id": "folder-uuid",
    "is_component": true,
    "access_type": "PRIVATE",
    "updated_at": "2024-03-15T09:15:00Z"
  }
]
```

### 获取公共流程

```http
GET /api/v1/tenant/flows/public
Query Parameters:
  limit: int (optional, default: 50)
  offset: int (optional, default: 0)

Response (200):
[
  {
    "id": "public-flow-uuid",
    "name": "Public Template",
    "description": "A public flow template",
    "user_id": "creator-uuid",
    "organization_id": "other-org-123",
    "access_type": "PUBLIC",
    "updated_at": "2024-03-15T08:00:00Z"
  }
]
```

### 搜索流程

```http
GET /api/v1/tenant/flows/search
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  query: string (required) - 搜索关键词
  user_id: string (optional) - 筛选特定用户的流程
  include_public: boolean (optional, default: true) - 是否包含公共流程
  limit: int (optional, default: 20)

Response (200):
[
  {
    "id": "flow-uuid",
    "name": "Matching Flow",
    "description": "Flow matching search criteria",
    "user_id": "user-uuid",
    "organization_id": "org-123",
    "access_type": "PRIVATE",
    "updated_at": "2024-03-15T10:30:00Z"
  }
]
```

### 获取流程统计

```http
GET /api/v1/tenant/flows/statistics
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Response (200):
{
  "total_flows": 45,
  "total_components": 12,
  "public_flows": 3,
  "top_creators": [
    {
      "user_id": "user-123",
      "flow_count": 15
    },
    {
      "user_id": "user-456",
      "flow_count": 8
    }
  ]
}
```

### 获取单个流程

```http
GET /api/v1/tenant/flows/{flow_id}
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Response (200):
{
  "id": "flow-uuid",
  "name": "My Flow",
  "description": "A sample flow",
  "data": {
    "nodes": [...],
    "edges": [...]
  },
  "user_id": "user-uuid",
  "organization_id": "org-123",
  "folder_id": "folder-uuid",
  "is_component": false,
  "access_type": "PRIVATE",
  "created_at": "2024-03-15T10:30:00Z",
  "updated_at": "2024-03-15T10:30:00Z"
}
```

### 更新流程

```http
PATCH /api/v1/tenant/flows/{flow_id}
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "name": "Updated Flow Name",
  "description": "Updated description",
  "data": {
    "nodes": [...],
    "edges": [...]
  }
}

Response (200):
{
  "id": "flow-uuid",
  "name": "Updated Flow Name",
  "description": "Updated description",
  "updated_at": "2024-03-15T11:00:00Z"
  // ... other fields
}
```

### 删除流程

```http
DELETE /api/v1/tenant/flows/{flow_id}
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Response (200):
{
  "message": "Flow deleted successfully"
}
```

### 复制流程

```http
POST /api/v1/tenant/flows/{flow_id}/duplicate
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "new_name": "Copied Flow",
  "target_folder_id": "target-folder-uuid"
}

Response (201):
{
  "id": "new-flow-uuid",
  "name": "Copied Flow",
  "user_id": "user-uuid",
  "organization_id": "org-123",
  "folder_id": "target-folder-uuid",
  // ... other fields copied from original
}
```

### 移动流程到文件夹

```http
PATCH /api/v1/tenant/flows/{flow_id}/move
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "target_folder_id": "target-folder-uuid"
}

Response (200):
{
  "id": "flow-uuid",
  "folder_id": "target-folder-uuid",
  // ... other fields
}
```

## 租户项目API

基础路径: `/api/v1/tenant/projects`

### 创建项目

```http
POST /api/v1/tenant/projects
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "name": "My Project",
  "description": "A sample project"
}

Response (201):
{
  "id": "project-uuid",
  "name": "My Project",
  "description": "A sample project",
  "user_id": "user-uuid",
  "organization_id": "org-123",
  "parent_id": null,
  "created_at": "2024-03-15T10:30:00Z"
}
```

### 获取项目列表

```http
GET /api/v1/tenant/projects
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  parent_id: string (optional) - 获取指定父项目下的子项目
  limit: int (optional, default: 50)
  offset: int (optional, default: 0)
  search_query: string (optional)

Response (200):
[
  {
    "id": "project-uuid",
    "name": "My Project",
    "description": "A sample project",
    "user_id": "user-uuid",
    "parent_id": null
  }
]
```

### 获取组织所有项目（管理员视图）

```http
GET /api/v1/tenant/projects/organization
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  parent_id: string (optional)
  limit: int (optional, default: 50)
  offset: int (optional, default: 0)
  search_query: string (optional)

Response (200):
[
  {
    "id": "project-uuid",
    "name": "Team Project",
    "description": "Created by team member",
    "user_id": "other-user-uuid",
    "parent_id": null
  }
]
```

### 获取项目树形结构

```http
GET /api/v1/tenant/projects/tree
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  root_folder_id: string (optional) - 指定根文件夹

Response (200):
[
  {
    "id": "root-project-uuid",
    "name": "Root Project",
    "description": "Root level project",
    "user_id": "user-uuid",
    "parent_id": null,
    "children": [
      {
        "id": "child-project-uuid",
        "name": "Child Project",
        "description": "Nested project",
        "user_id": "user-uuid",
        "parent_id": "root-project-uuid",
        "children": []
      }
    ]
  }
]
```

### 获取项目统计

```http
GET /api/v1/tenant/projects/statistics
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Response (200):
{
  "total_folders": 25,
  "root_folders": 5,
  "max_depth": 4,
  "average_depth": 2.3,
  "top_users": [
    {
      "user_id": "user-123",
      "folder_count": 8
    }
  ]
}
```

### 移动项目

```http
PATCH /api/v1/tenant/projects/{project_id}/move
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "target_parent_id": "target-parent-uuid"
}

Response (200):
{
  "id": "project-uuid",
  "parent_id": "target-parent-uuid",
  // ... other fields
}
```

## 租户变量API

基础路径: `/api/v1/tenant/variables`

### 创建变量

```http
POST /api/v1/tenant/variables
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "name": "API_KEY",
  "value": "encrypted_api_key_value",
  "type": "CREDENTIAL",
  "default_fields": ["field1", "field2"]
}

Response (201):
{
  "id": "variable-uuid",
  "name": "API_KEY",
  "value": "encrypted_api_key_value",
  "type": "CREDENTIAL",
  "default_fields": ["field1", "field2"],
  "user_id": "user-uuid",
  "created_at": "2024-03-15T10:30:00Z",
  "updated_at": "2024-03-15T10:30:00Z"
}
```

### 获取变量列表

```http
GET /api/v1/tenant/variables
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  limit: int (optional, default: 50)
  offset: int (optional, default: 0)

Response (200):
[
  {
    "id": "variable-uuid",
    "name": "API_KEY",
    "type": "CREDENTIAL",
    "value": null, // 敏感信息不返回
    "default_fields": ["field1", "field2"]
  }
]
```

### 按类型获取变量

```http
GET /api/v1/tenant/variables/by-type/{variable_type}
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  user_id: string (optional) - 筛选特定用户的变量
  limit: int (optional, default: 50)

Response (200):
[
  {
    "id": "variable-uuid",
    "name": "API_KEY",
    "type": "CREDENTIAL",
    "value": null,
    "default_fields": ["field1", "field2"]
  }
]
```

### 按名称获取变量

```http
GET /api/v1/tenant/variables/by-name/{variable_name}
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  user_id: string (optional)

Response (200):
{
  "id": "variable-uuid",
  "name": "API_KEY",
  "type": "CREDENTIAL",
  "value": "decrypted_value_if_authorized",
  "default_fields": ["field1", "field2"],
  "user_id": "user-uuid"
}
```

### 获取变量统计

```http
GET /api/v1/tenant/variables/statistics
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Response (200):
{
  "total_variables": 35,
  "type_statistics": {
    "CREDENTIAL": 15,
    "GENERIC": 20
  },
  "top_users": [
    {
      "user_id": "user-123",
      "variable_count": 12
    }
  ]
}
```

### 搜索变量

```http
GET /api/v1/tenant/variables/search
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123

Query Parameters:
  query: string (required) - 搜索关键词
  variable_type: string (optional) - 按类型过滤
  user_id: string (optional) - 按用户过滤
  limit: int (optional, default: 20)

Response (200):
[
  {
    "id": "variable-uuid",
    "name": "API_KEY",
    "type": "CREDENTIAL",
    "value": null,
    "default_fields": ["field1", "field2"]
  }
]
```

### 复制变量

```http
POST /api/v1/tenant/variables/{variable_id}/duplicate
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "new_name": "API_KEY_COPY"
}

Response (201):
{
  "id": "new-variable-uuid",
  "name": "API_KEY_COPY",
  "type": "CREDENTIAL",
  "value": "copied_encrypted_value",
  "default_fields": ["field1", "field2"],
  "user_id": "user-uuid"
}
```

## 错误处理

### 标准错误响应

```json
{
  "error": "Error message",
  "detail": "Detailed error description",
  "status_code": 400
}
```

### 常见错误码

| 状态码 | 错误类型 | 描述 |
|--------|----------|------|
| 400 | Bad Request | 请求参数错误 |
| 401 | Unauthorized | 未授权访问 |
| 403 | Forbidden | 权限不足或组织访问被拒绝 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如名称重复） |
| 500 | Internal Server Error | 服务器内部错误 |

### 特定错误示例

#### 组织上下文缺失
```json
{
  "error": "Organization context is required for this operation",
  "status_code": 400
}
```

#### 权限不足
```json
{
  "error": "Access denied to organization",
  "status_code": 403
}
```

#### 资源名称冲突
```json
{
  "error": "Flow name must be unique within the organization",
  "status_code": 400
}
```

## 批量操作

### 批量创建流程

```http
POST /api/v1/tenant/flows/batch/
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
{
  "flows": [
    {
      "name": "Flow 1",
      "data": {...}
    },
    {
      "name": "Flow 2", 
      "data": {...}
    }
  ]
}

Response (201):
[
  {
    "id": "flow-1-uuid",
    "name": "Flow 1",
    // ... other fields
  },
  {
    "id": "flow-2-uuid", 
    "name": "Flow 2",
    // ... other fields
  }
]
```

### 批量下载流程

```http
POST /api/v1/tenant/flows/download/
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: application/json

Request Body:
["flow-1-uuid", "flow-2-uuid", "flow-3-uuid"]

Response (200):
Content-Type: application/x-zip-compressed
Content-Disposition: attachment; filename=20240315_120000_langflow_flows.zip

# ZIP文件包含所有流程的JSON文件
```

## 文件上传

### 上传流程文件

```http
POST /api/v1/tenant/flows/upload/
Headers:
  Authorization: Bearer <jwt_token>
  X-Organization-ID: org-123
  Content-Type: multipart/form-data

Query Parameters:
  folder_id: string (optional) - 指定目标文件夹

Form Data:
  file: JSON文件或包含流程定义的文件

Response (201):
[
  {
    "id": "imported-flow-uuid",
    "name": "Imported Flow",
    // ... other fields
  }
]
```

## 速率限制

根据组织的计划类型应用不同的速率限制：

| 计划类型 | API调用/小时 | 并发请求 |
|----------|--------------|----------|
| FREE | 1000 | 5 |
| STARTER | 10000 | 20 |
| PROFESSIONAL | 50000 | 50 |
| ENTERPRISE | 无限制 | 100 |

超出限制时返回 429 状态码：

```json
{
  "error": "Rate limit exceeded",
  "detail": "Too many requests for organization org-123",
  "status_code": 429,
  "retry_after": 3600
}
```

---

## API测试示例

### 使用curl测试

```bash
# 设置变量
TOKEN="your-jwt-token"
ORG_ID="org-123"
API_BASE="http://localhost:7860/api/v1"

# 获取组织流程列表
curl -X GET "$API_BASE/tenant/flows" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID"

# 创建新流程
curl -X POST "$API_BASE/tenant/flows" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Flow",
    "description": "Created via API",
    "data": {"nodes": [], "edges": []}
  }'
```

### 使用Python requests

```python
import requests

# 配置
API_BASE = "http://localhost:7860/api/v1"
TOKEN = "your-jwt-token"
ORG_ID = "org-123"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "X-Organization-ID": ORG_ID,
    "Content-Type": "application/json"
}

# 获取流程列表
response = requests.get(f"{API_BASE}/tenant/flows", headers=headers)
flows = response.json()

# 创建新流程
flow_data = {
    "name": "Python Created Flow",
    "description": "Created via Python",
    "data": {"nodes": [], "edges": []}
}

response = requests.post(f"{API_BASE}/tenant/flows", 
                        headers=headers, 
                        json=flow_data)
new_flow = response.json()
```