"""Usage tracking and quota management service"""
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.database.models.subscription.crud import (
    UsageMetricCRUD, SubscriptionCRUD, OrganizationCRUD
)
from langflow.services.database.models.subscription.model import (
    MetricType, UsageMetric, UsageSummary
)

logger = logging.getLogger(__name__)


class UsageService:
    """使用量追踪和配额管理服务"""
    
    def __init__(self):
        pass
    
    async def track_api_call(
        self,
        session: AsyncSession,
        organization_id: str,
        endpoint: str,
        user_id: Optional[str] = None,
        flow_id: Optional[str] = None
    ) -> bool:
        """追踪API调用，返回是否成功记录"""
        return await self._track_usage(
            session, organization_id, MetricType.API_CALLS, 1,
            metadata={
                'endpoint': endpoint,
                'user_id': user_id,
                'flow_id': flow_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        )
    
    async def track_flow_execution(
        self,
        session: AsyncSession,
        organization_id: str,
        flow_id: str,
        execution_time_ms: int,
        user_id: Optional[str] = None
    ) -> bool:
        """追踪流程执行"""
        # 记录执行次数
        success = await self._track_usage(
            session, organization_id, MetricType.FLOW_EXECUTIONS, 1,
            metadata={
                'flow_id': flow_id,
                'user_id': user_id,
                'execution_time_ms': execution_time_ms
            }
        )
        
        # 记录计算时间（以分钟为单位）
        compute_minutes = max(1, execution_time_ms // 60000)  # 至少1分钟
        await self._track_usage(
            session, organization_id, MetricType.COMPUTE_MINUTES, compute_minutes,
            metadata={
                'flow_id': flow_id,
                'user_id': user_id,
                'execution_time_ms': execution_time_ms
            }
        )
        
        return success
    
    async def track_storage_usage(
        self,
        session: AsyncSession,
        organization_id: str,
        size_mb: int,
        file_type: str,
        user_id: Optional[str] = None,
        file_id: Optional[str] = None
    ) -> bool:
        """追踪存储使用量"""
        return await self._track_usage(
            session, organization_id, MetricType.STORAGE_MB, size_mb,
            metadata={
                'file_type': file_type,
                'user_id': user_id,
                'file_id': file_id,
                'size_mb': size_mb
            }
        )
    
    async def track_team_member(
        self,
        session: AsyncSession,
        organization_id: str,
        action: str,  # 'add' or 'remove'
        member_user_id: str,
        admin_user_id: str
    ) -> bool:
        """追踪团队成员变化"""
        value = 1 if action == 'add' else -1
        return await self._track_usage(
            session, organization_id, MetricType.TEAM_MEMBERS, value,
            metadata={
                'action': action,
                'member_user_id': member_user_id,
                'admin_user_id': admin_user_id
            }
        )
    
    async def check_quota(
        self,
        session: AsyncSession,
        organization_id: str,
        metric_type: MetricType,
        requested_amount: int = 1
    ) -> Tuple[bool, Dict]:
        """检查配额是否足够
        
        Returns:
            Tuple[bool, Dict]: (是否允许, 配额信息)
        """
        try:
            can_use, current_usage, limit = await UsageMetricCRUD.check_usage_limit(
                session, organization_id, metric_type, requested_amount
            )
            
            quota_info = {
                'metric_type': metric_type.value,
                'current_usage': current_usage,
                'limit': limit,
                'requested_amount': requested_amount,
                'remaining': limit - current_usage if limit > 0 else -1,
                'unlimited': limit == -1
            }
            
            return can_use, quota_info
            
        except Exception as e:
            logger.error(f"Failed to check quota for {organization_id}: {e}")
            # 如果检查失败，默认允许使用（避免阻塞业务）
            return True, {
                'error': str(e),
                'default_allowed': True
            }
    
    async def get_usage_summary(
        self,
        session: AsyncSession,
        organization_id: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> UsageSummary:
        """获取使用量汇总"""
        return await UsageMetricCRUD.get_usage_summary(
            session, organization_id, period_start, period_end
        )
    
    async def get_usage_trends(
        self,
        session: AsyncSession,
        organization_id: str,
        metric_type: MetricType,
        days: int = 30
    ) -> List[Dict]:
        """获取使用量趋势数据"""
        # 这里需要实现按日期聚合的查询逻辑
        # 暂时返回示例数据
        return [
            {
                'date': '2025-01-01',
                'value': 100
            },
            {
                'date': '2025-01-02', 
                'value': 150
            }
            # ... 更多趋势数据
        ]
    
    async def reset_usage_for_period(
        self,
        session: AsyncSession,
        organization_id: str,
        period_start: datetime,
        period_end: datetime
    ) -> bool:
        """重置指定周期的使用量（用于计费周期重置）"""
        try:
            # 这里需要实现重置逻辑
            # 通常在新的计费周期开始时调用
            logger.info(f"Resetting usage for org {organization_id} period {period_start} - {period_end}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset usage: {e}")
            return False
    
    async def generate_usage_report(
        self,
        session: AsyncSession,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        format: str = 'json'
    ) -> Dict:
        """生成使用量报告"""
        try:
            summary = await self.get_usage_summary(session, organization_id, period_start, period_end)
            
            # 获取组织信息
            org = await OrganizationCRUD.get_organization_by_id(session, organization_id)
            subscription = await SubscriptionCRUD.get_organization_subscription(session, organization_id)
            
            report = {
                'organization': {
                    'id': organization_id,
                    'name': org.name if org else 'Unknown',
                    'slug': org.slug if org else 'unknown'
                },
                'subscription': {
                    'plan_name': subscription.plan.name if subscription else 'Free',
                    'plan_type': subscription.plan.plan_type.value if subscription else 'free'
                },
                'period': {
                    'start': period_start.isoformat(),
                    'end': period_end.isoformat()
                },
                'usage': {
                    'api_calls': {
                        'used': summary.metrics.get(MetricType.API_CALLS, 0),
                        'limit': summary.limits.get('api_calls', 0),
                        'usage_percentage': summary.usage_percentage.get(MetricType.API_CALLS, 0)
                    },
                    'flow_executions': {
                        'used': summary.metrics.get(MetricType.FLOW_EXECUTIONS, 0),
                        'limit': summary.limits.get('flow_executions', 0),
                        'usage_percentage': summary.usage_percentage.get(MetricType.FLOW_EXECUTIONS, 0)
                    },
                    'storage_mb': {
                        'used': summary.metrics.get(MetricType.STORAGE_MB, 0),
                        'limit': summary.limits.get('storage_mb', 0),
                        'usage_percentage': summary.usage_percentage.get(MetricType.STORAGE_MB, 0)
                    },
                    'compute_minutes': {
                        'used': summary.metrics.get(MetricType.COMPUTE_MINUTES, 0),
                        'limit': summary.limits.get('compute_minutes', 0),
                        'usage_percentage': summary.usage_percentage.get(MetricType.COMPUTE_MINUTES, 0)
                    },
                    'team_members': {
                        'used': summary.metrics.get(MetricType.TEAM_MEMBERS, 0),
                        'limit': summary.limits.get('team_members', 1),
                        'usage_percentage': summary.usage_percentage.get(MetricType.TEAM_MEMBERS, 0)
                    }
                },
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate usage report: {e}")
            raise
    
    async def _track_usage(
        self,
        session: AsyncSession,
        organization_id: str,
        metric_type: MetricType,
        value: int,
        metadata: Optional[Dict] = None
    ) -> bool:
        """内部使用量追踪方法"""
        try:
            # 首先检查是否超出配额
            can_use, quota_info = await self.check_quota(
                session, organization_id, metric_type, value
            )
            
            # 如果超出配额且不是无限制计划，记录但不阻止（记录超量使用）
            if not can_use and quota_info.get('limit', 0) != -1:
                logger.warning(f"Usage limit exceeded for {organization_id}: {quota_info}")
                # 可以选择是否阻止超量使用
                # return False
            
            # 记录使用量
            await UsageMetricCRUD.record_usage(
                session, organization_id, metric_type, value, metadata
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to track usage: {e}")
            return False
    
    async def get_quota_alerts(
        self,
        session: AsyncSession,
        organization_id: str,
        warning_threshold: float = 0.8  # 80%
    ) -> List[Dict]:
        """获取配额告警信息"""
        try:
            summary = await self.get_usage_summary(session, organization_id)
            alerts = []
            
            for metric_type, usage_pct in summary.usage_percentage.items():
                if usage_pct >= warning_threshold * 100:  # 转换为百分比
                    severity = 'critical' if usage_pct >= 95 else 'warning'
                    alerts.append({
                        'metric_type': metric_type.value,
                        'usage_percentage': usage_pct,
                        'current_usage': summary.metrics.get(metric_type, 0),
                        'limit': summary.limits.get(metric_type.value, 0),
                        'severity': severity,
                        'message': f"{metric_type.value} usage is at {usage_pct:.1f}% of quota"
                    })
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to get quota alerts: {e}")
            return []