"""Stripe billing service for handling payments and subscriptions"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import stripe
from sqlmodel.ext.asyncio import AsyncSession

from langflow.services.database.models.subscription.crud import (
    OrganizationCRUD, SubscriptionCRUD, InvoiceCRUD
)
from langflow.services.database.models.subscription.model import (
    Organization, Subscription, SubscriptionPlan, SubscriptionStatus
)
from langflow.services.settings.service import SettingsService

logger = logging.getLogger(__name__)


class StripeService:
    """Stripe集成服务"""
    
    def __init__(self, settings_service: SettingsService):
        self.settings = settings_service
        # 从设置中获取Stripe密钥
        stripe.api_key = getattr(settings_service, 'STRIPE_SECRET_KEY', None)
        self.webhook_secret = getattr(settings_service, 'STRIPE_WEBHOOK_SECRET', None)
        
        if not stripe.api_key:
            logger.warning("Stripe API key not configured")
    
    async def create_customer(
        self,
        organization: Organization,
        email: Optional[str] = None
    ) -> stripe.Customer:
        """为组织创建Stripe客户"""
        try:
            customer = stripe.Customer.create(
                name=organization.name,
                email=email,
                metadata={
                    'organization_id': organization.id,
                    'organization_slug': organization.slug
                }
            )
            return customer
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise
    
    async def create_subscription(
        self,
        session: AsyncSession,
        organization_id: str,
        plan_id: str,
        customer_id: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        trial_days: Optional[int] = None,
        is_yearly: bool = False
    ) -> Dict:
        """创建订阅"""
        try:
            # 获取组织和计划信息
            org = await OrganizationCRUD.get_organization_by_id(session, organization_id)
            plan = await SubscriptionCRUD.get_plan_by_id(session, plan_id)
            
            if not org or not plan:
                raise ValueError("Organization or plan not found")
            
            # 创建或获取Stripe客户
            if not customer_id:
                customer = await self.create_customer(org)
                customer_id = customer.id
            
            # 选择价格ID（月付或年付）
            price_id = plan.stripe_yearly_price_id if is_yearly else plan.stripe_price_id
            if not price_id:
                raise ValueError(f"Stripe price ID not configured for plan {plan.name}")
            
            # 创建订阅参数
            subscription_params = {
                'customer': customer_id,
                'items': [{'price': price_id}],
                'metadata': {
                    'organization_id': organization_id,
                    'plan_id': plan_id
                },
                'expand': ['latest_invoice.payment_intent']
            }
            
            # 添加默认支付方式
            if payment_method_id:
                subscription_params['default_payment_method'] = payment_method_id
            
            # 添加试用期
            if trial_days:
                subscription_params['trial_period_days'] = trial_days
            
            # 在Stripe中创建订阅
            stripe_subscription = stripe.Subscription.create(**subscription_params)
            
            # 在数据库中创建订阅记录
            db_subscription = await SubscriptionCRUD.create_subscription(
                session=session,
                organization_id=organization_id,
                plan_id=plan_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=stripe_subscription.id,
                status=SubscriptionStatus(stripe_subscription.status),
                is_yearly=is_yearly,
                trial_end=datetime.fromtimestamp(
                    stripe_subscription.trial_end, tz=timezone.utc
                ) if stripe_subscription.trial_end else None
            )
            
            return {
                'subscription_id': db_subscription.id,
                'client_secret': stripe_subscription.latest_invoice.payment_intent.client_secret
                if stripe_subscription.latest_invoice.payment_intent else None,
                'status': stripe_subscription.status
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe subscription creation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Subscription creation failed: {e}")
            raise
    
    async def cancel_subscription(
        self,
        session: AsyncSession,
        subscription_id: str,
        cancel_immediately: bool = False
    ) -> Subscription:
        """取消订阅"""
        try:
            # 获取数据库订阅记录
            subscription = await SubscriptionCRUD.get_organization_subscription(
                session, subscription_id
            )
            if not subscription or not subscription.stripe_subscription_id:
                raise ValueError("Subscription not found")
            
            # 在Stripe中取消订阅
            if cancel_immediately:
                stripe.Subscription.delete(subscription.stripe_subscription_id)
            else:
                stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
            
            # 更新数据库记录
            updates = {
                'cancel_at_period_end': not cancel_immediately,
                'canceled_at': datetime.now(timezone.utc) if cancel_immediately else None,
                'status': SubscriptionStatus.CANCELED if cancel_immediately else subscription.status
            }
            
            updated_subscription = await SubscriptionCRUD.update_subscription_from_stripe(
                session, subscription.id, **updates
            )
            
            return updated_subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe subscription cancellation failed: {e}")
            raise
    
    async def update_subscription(
        self,
        session: AsyncSession,
        subscription_id: str,
        new_plan_id: str,
        proration_behavior: str = 'create_prorations'
    ) -> Subscription:
        """更新订阅计划"""
        try:
            # 获取订阅和新计划信息
            subscription = await SubscriptionCRUD.get_organization_subscription(
                session, subscription_id
            )
            new_plan = await SubscriptionCRUD.get_plan_by_id(session, new_plan_id)
            
            if not subscription or not new_plan:
                raise ValueError("Subscription or plan not found")
            
            # 获取Stripe订阅
            stripe_subscription = stripe.Subscription.retrieve(
                subscription.stripe_subscription_id
            )
            
            # 选择新的价格ID
            new_price_id = (new_plan.stripe_yearly_price_id 
                          if subscription.is_yearly 
                          else new_plan.stripe_price_id)
            
            # 更新Stripe订阅
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                items=[{
                    'id': stripe_subscription['items']['data'][0].id,
                    'price': new_price_id,
                }],
                proration_behavior=proration_behavior
            )
            
            # 更新数据库记录
            updated_subscription = await SubscriptionCRUD.update_subscription_from_stripe(
                session, subscription.id, plan_id=new_plan_id
            )
            
            return updated_subscription
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe subscription update failed: {e}")
            raise
    
    async def create_payment_method(
        self,
        customer_id: str,
        payment_method_data: Dict
    ) -> stripe.PaymentMethod:
        """创建支付方式"""
        try:
            payment_method = stripe.PaymentMethod.create(
                type='card',
                card=payment_method_data,
                metadata={'customer_id': customer_id}
            )
            
            # 附加到客户
            payment_method.attach(customer=customer_id)
            
            return payment_method
        except stripe.error.StripeError as e:
            logger.error(f"Payment method creation failed: {e}")
            raise
    
    async def get_customer_payment_methods(
        self,
        customer_id: str
    ) -> List[stripe.PaymentMethod]:
        """获取客户的支付方式列表"""
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type='card'
            )
            return payment_methods.data
        except stripe.error.StripeError as e:
            logger.error(f"Failed to retrieve payment methods: {e}")
            raise
    
    async def create_billing_portal_session(
        self,
        customer_id: str,
        return_url: str
    ) -> stripe.billing_portal.Session:
        """创建客户门户会话"""
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url
            )
            return session
        except stripe.error.StripeError as e:
            logger.error(f"Failed to create billing portal session: {e}")
            raise
    
    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str,
        session: AsyncSession
    ) -> Dict:
        """处理Stripe webhook事件"""
        try:
            # 验证webhook签名
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            
            # 根据事件类型处理
            event_type = event['type']
            event_data = event['data']['object']
            
            logger.info(f"Processing Stripe webhook event: {event_type}")
            
            if event_type == 'customer.subscription.created':
                await self._handle_subscription_created(session, event_data)
            elif event_type == 'customer.subscription.updated':
                await self._handle_subscription_updated(session, event_data)
            elif event_type == 'customer.subscription.deleted':
                await self._handle_subscription_deleted(session, event_data)
            elif event_type == 'invoice.payment_succeeded':
                await self._handle_invoice_payment_succeeded(session, event_data)
            elif event_type == 'invoice.payment_failed':
                await self._handle_invoice_payment_failed(session, event_data)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
            
            return {'status': 'success', 'event_type': event_type}
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            raise
    
    async def _handle_subscription_created(self, session: AsyncSession, data: Dict):
        """处理订阅创建事件"""
        subscription_id = data.get('metadata', {}).get('subscription_id')
        if subscription_id:
            await SubscriptionCRUD.update_subscription_from_stripe(
                session, subscription_id,
                stripe_subscription_id=data['id'],
                status=SubscriptionStatus(data['status']),
                current_period_start=datetime.fromtimestamp(
                    data['current_period_start'], tz=timezone.utc
                ),
                current_period_end=datetime.fromtimestamp(
                    data['current_period_end'], tz=timezone.utc
                )
            )
    
    async def _handle_subscription_updated(self, session: AsyncSession, data: Dict):
        """处理订阅更新事件"""
        # 通过Stripe订阅ID查找本地订阅
        stmt = f"SELECT id FROM subscription WHERE stripe_subscription_id = '{data['id']}'"
        # 这里需要更复杂的查询逻辑，暂时简化
        
        updates = {
            'status': SubscriptionStatus(data['status']),
            'current_period_start': datetime.fromtimestamp(
                data['current_period_start'], tz=timezone.utc
            ),
            'current_period_end': datetime.fromtimestamp(
                data['current_period_end'], tz=timezone.utc
            ),
            'cancel_at_period_end': data.get('cancel_at_period_end', False)
        }
        
        # 这里需要实现通过stripe_subscription_id查找和更新的逻辑
        logger.info(f"Subscription updated: {data['id']}")
    
    async def _handle_subscription_deleted(self, session: AsyncSession, data: Dict):
        """处理订阅删除事件"""
        logger.info(f"Subscription deleted: {data['id']}")
        # 实现订阅删除逻辑
    
    async def _handle_invoice_payment_succeeded(self, session: AsyncSession, data: Dict):
        """处理发票支付成功事件"""
        # 根据subscription字段查找订阅
        subscription_stripe_id = data['subscription']
        # 这里需要实现发票记录创建逻辑
        logger.info(f"Invoice payment succeeded: {data['id']}")
    
    async def _handle_invoice_payment_failed(self, session: AsyncSession, data: Dict):
        """处理发票支付失败事件"""
        logger.info(f"Invoice payment failed: {data['id']}")
        # 实现支付失败处理逻辑