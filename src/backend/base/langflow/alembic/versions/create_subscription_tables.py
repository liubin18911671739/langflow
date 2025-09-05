"""Add subscription and billing tables

Revision ID: sub001_initial
Revises: e56d87f8994a
Create Date: 2025-01-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = 'sub001_initial'
down_revision = 'e56d87f8994a'  # 使用最新的revision
branch_labels = None
depends_on = None


def upgrade():
    # Create Organization table
    op.create_table(
        'organization',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('logo_url', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('industry', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('owner_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_organization_name'), 'organization', ['name'], unique=False)
    op.create_index(op.f('ix_organization_slug'), 'organization', ['slug'], unique=False)

    # Create OrganizationMember table
    op.create_table(
        'organizationmember',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create SubscriptionPlan table
    op.create_table(
        'subscriptionplan',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('plan_type', sa.String(), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('yearly_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('stripe_price_id', sa.String(), nullable=True),
        sa.Column('stripe_yearly_price_id', sa.String(), nullable=True),
        sa.Column('stripe_product_id', sa.String(), nullable=True),
        sa.Column('limits', sa.JSON(), nullable=True),
        sa.Column('features', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_popular', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('stripe_price_id'),
        sa.UniqueConstraint('stripe_yearly_price_id')
    )
    op.create_index(op.f('ix_subscriptionplan_name'), 'subscriptionplan', ['name'], unique=False)
    op.create_index(op.f('ix_subscriptionplan_plan_type'), 'subscriptionplan', ['plan_type'], unique=False)

    # Create Subscription table
    op.create_table(
        'subscription',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('plan_id', sa.String(), nullable=False),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('stripe_latest_invoice_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('is_yearly', sa.Boolean(), nullable=False),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('trial_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['subscriptionplan.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_subscription_id')
    )
    op.create_index(op.f('ix_subscription_status'), 'subscription', ['status'], unique=False)
    op.create_index(op.f('ix_subscription_stripe_customer_id'), 'subscription', ['stripe_customer_id'], unique=False)
    op.create_index(op.f('ix_subscription_stripe_subscription_id'), 'subscription', ['stripe_subscription_id'], unique=False)

    # Create Invoice table
    op.create_table(
        'invoice',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('subscription_id', sa.String(), nullable=False),
        sa.Column('stripe_invoice_id', sa.String(), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('invoice_number', sa.String(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('hosted_invoice_url', sa.String(), nullable=True),
        sa.Column('invoice_pdf', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscription.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_invoice_id'),
        sa.UniqueConstraint('invoice_number')
    )
    op.create_index(op.f('ix_invoice_stripe_invoice_id'), 'invoice', ['stripe_invoice_id'], unique=False)
    op.create_index(op.f('ix_invoice_invoice_number'), 'invoice', ['invoice_number'], unique=False)
    op.create_index(op.f('ix_invoice_status'), 'invoice', ['status'], unique=False)

    # Create UsageMetric table
    op.create_table(
        'usagemetric',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('organization_id', sa.String(), nullable=False),
        sa.Column('metric_type', sa.String(), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usagemetric_metric_type'), 'usagemetric', ['metric_type'], unique=False)
    op.create_index(op.f('ix_usagemetric_recorded_at'), 'usagemetric', ['recorded_at'], unique=False)
    op.create_index(op.f('ix_usagemetric_period_start'), 'usagemetric', ['period_start'], unique=False)
    op.create_index(op.f('ix_usagemetric_period_end'), 'usagemetric', ['period_end'], unique=False)

    # Insert default subscription plans
    op.execute("""
        INSERT INTO subscriptionplan (
            id, name, plan_type, description, price, yearly_price, currency,
            limits, features, is_active, is_popular, created_at, updated_at
        ) VALUES 
        (
            gen_random_uuid()::text, 'Free Plan', 'free', 
            'Perfect for individuals getting started with AI workflows',
            0.00, 0.00, 'USD',
            '{"api_calls": 1000, "flow_executions": 100, "storage_mb": 100, "team_members": 1}',
            '["basic_components", "community_support"]',
            true, false, now(), now()
        ),
        (
            gen_random_uuid()::text, 'Basic Plan', 'basic',
            'Great for small teams and growing projects',
            29.00, 290.00, 'USD',
            '{"api_calls": 25000, "flow_executions": 2500, "storage_mb": 1000, "team_members": 3}',
            '["advanced_components", "email_support", "basic_analytics"]',
            true, false, now(), now()
        ),
        (
            gen_random_uuid()::text, 'Professional Plan', 'professional',
            'Ideal for professional teams requiring advanced features',
            99.00, 990.00, 'USD',
            '{"api_calls": 100000, "flow_executions": 10000, "storage_mb": 5000, "team_members": 10}',
            '["premium_components", "priority_support", "advanced_analytics", "custom_integrations", "sso"]',
            true, true, now(), now()
        ),
        (
            gen_random_uuid()::text, 'Enterprise Plan', 'enterprise',
            'Custom solution for large organizations with unlimited usage',
            299.00, 2990.00, 'USD',
            '{"api_calls": -1, "flow_executions": -1, "storage_mb": -1, "team_members": -1}',
            '["unlimited_everything", "dedicated_support", "custom_deployment", "advanced_security", "audit_logs", "white_label"]',
            true, false, now(), now()
        )
    """)


def downgrade():
    # Drop tables in reverse order
    op.drop_table('usagemetric')
    op.drop_table('invoice')
    op.drop_table('subscription')
    op.drop_table('subscriptionplan')
    op.drop_table('organizationmember')
    op.drop_table('organization')