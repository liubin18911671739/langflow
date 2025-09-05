"""Add multi-tenant support with organization_id and RLS

Revision ID: mt001_multi_tenant
Revises: sub001_initial
Create Date: 2025-01-04 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'mt001_multi_tenant'
down_revision = 'sub001_initial'
branch_labels = None
depends_on = None


def upgrade():
    """Add organization_id fields to core tables and enable RLS"""
    
    # Add organization_id to flow table
    op.add_column('flow', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_flow_organization_id', 
        'flow', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_flow_organization_id', 'flow', ['organization_id'])
    
    # Add organization_id to folder table
    op.add_column('folder', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_folder_organization_id', 
        'folder', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_folder_organization_id', 'folder', ['organization_id'])
    
    # Add organization_id to api_key table
    op.add_column('apikey', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_apikey_organization_id', 
        'apikey', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_apikey_organization_id', 'apikey', ['organization_id'])
    
    # Add organization_id to variable table
    op.add_column('variable', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_variable_organization_id', 
        'variable', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_variable_organization_id', 'variable', ['organization_id'])
    
    # Add organization_id to file table (if exists)
    op.add_column('file', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_file_organization_id', 
        'file', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_file_organization_id', 'file', ['organization_id'])
    
    # Add organization_id to message table
    op.add_column('message', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_message_organization_id', 
        'message', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_message_organization_id', 'message', ['organization_id'])
    
    # Add organization_id to vertex_builds table
    op.add_column('vertex_builds', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_vertex_builds_organization_id', 
        'vertex_builds', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_vertex_builds_organization_id', 'vertex_builds', ['organization_id'])
    
    # Add organization_id to transactions table (if exists)
    op.add_column('transactions', sa.Column('organization_id', sa.String(), nullable=True))
    op.create_foreign_key(
        'fk_transactions_organization_id', 
        'transactions', 
        'organization', 
        ['organization_id'], 
        ['id']
    )
    op.create_index('ix_transactions_organization_id', 'transactions', ['organization_id'])
    
    # Migrate existing data: create default organization for existing users
    # This ensures all existing data belongs to some organization
    op.execute("""
        -- Create a default organization for migration
        INSERT INTO organization (id, name, slug, owner_id, created_at, updated_at)
        SELECT 
            gen_random_uuid()::text,
            'Default Organization',
            'default-org',
            (SELECT id FROM "user" ORDER BY create_at ASC LIMIT 1),
            now(),
            now()
        WHERE NOT EXISTS (SELECT 1 FROM organization WHERE slug = 'default-org');
        
        -- Get the default organization ID
        WITH default_org AS (
            SELECT id FROM organization WHERE slug = 'default-org' LIMIT 1
        )
        -- Update existing flows
        UPDATE flow SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing folders
        UPDATE folder SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing api keys
        UPDATE apikey SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing variables
        UPDATE variable SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing files
        UPDATE file SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing messages
        UPDATE message SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing vertex builds
        UPDATE vertex_builds SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Update existing transactions
        UPDATE transactions SET organization_id = (SELECT id FROM default_org)
        WHERE organization_id IS NULL;
        
        -- Add all existing users to the default organization as owners
        INSERT INTO organizationmember (id, organization_id, user_id, role, joined_at)
        SELECT 
            gen_random_uuid()::text,
            (SELECT id FROM default_org),
            u.id,
            'owner',
            now()
        FROM "user" u
        WHERE NOT EXISTS (
            SELECT 1 FROM organizationmember 
            WHERE user_id = u.id AND organization_id = (SELECT id FROM default_org)
        );
    """)
    
    # Now make organization_id NOT NULL for all tables
    op.alter_column('flow', 'organization_id', nullable=False)
    op.alter_column('folder', 'organization_id', nullable=False)
    op.alter_column('apikey', 'organization_id', nullable=False)
    op.alter_column('variable', 'organization_id', nullable=False)
    op.alter_column('file', 'organization_id', nullable=False)
    op.alter_column('message', 'organization_id', nullable=False)
    op.alter_column('vertex_builds', 'organization_id', nullable=False)
    op.alter_column('transactions', 'organization_id', nullable=False)


def setup_rls():
    """Enable Row Level Security and create policies"""
    
    # Enable RLS on core tables
    tables_with_rls = [
        'flow', 'folder', 'apikey', 'variable', 
        'file', 'message', 'vertex_builds', 'transactions'
    ]
    
    for table in tables_with_rls:
        # Enable RLS
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        
        # Drop existing policies if they exist
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation_policy ON {table};")
        
        # Create RLS policy for tenant isolation
        op.execute(f"""
            CREATE POLICY {table}_isolation_policy ON {table}
            FOR ALL
            TO public
            USING (organization_id = current_setting('app.current_organization_id', true)::text)
            WITH CHECK (organization_id = current_setting('app.current_organization_id', true)::text);
        """)
    
    # Create function to set tenant context
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_tenant(tenant_id text)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_organization_id', tenant_id, true);
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create function to get current tenant
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_tenant()
        RETURNS text AS $$
        BEGIN
            RETURN current_setting('app.current_organization_id', true);
        END;
        $$ LANGUAGE plpgsql;
    """)


def upgrade_with_rls():
    """Complete upgrade including RLS setup"""
    upgrade()
    setup_rls()


def downgrade():
    """Remove multi-tenant support"""
    
    # Disable RLS and drop policies
    tables_with_rls = [
        'flow', 'folder', 'apikey', 'variable', 
        'file', 'message', 'vertex_builds', 'transactions'
    ]
    
    for table in tables_with_rls:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation_policy ON {table};")
    
    # Drop utility functions
    op.execute("DROP FUNCTION IF EXISTS set_current_tenant(text);")
    op.execute("DROP FUNCTION IF EXISTS get_current_tenant();")
    
    # Drop foreign keys and indexes
    op.drop_constraint('fk_flow_organization_id', 'flow', type_='foreignkey')
    op.drop_index('ix_flow_organization_id', 'flow')
    op.drop_column('flow', 'organization_id')
    
    op.drop_constraint('fk_folder_organization_id', 'folder', type_='foreignkey')
    op.drop_index('ix_folder_organization_id', 'folder')
    op.drop_column('folder', 'organization_id')
    
    op.drop_constraint('fk_apikey_organization_id', 'apikey', type_='foreignkey')
    op.drop_index('ix_apikey_organization_id', 'apikey')
    op.drop_column('apikey', 'organization_id')
    
    op.drop_constraint('fk_variable_organization_id', 'variable', type_='foreignkey')
    op.drop_index('ix_variable_organization_id', 'variable')
    op.drop_column('variable', 'organization_id')
    
    op.drop_constraint('fk_file_organization_id', 'file', type_='foreignkey')
    op.drop_index('ix_file_organization_id', 'file')
    op.drop_column('file', 'organization_id')
    
    op.drop_constraint('fk_message_organization_id', 'message', type_='foreignkey')
    op.drop_index('ix_message_organization_id', 'message')
    op.drop_column('message', 'organization_id')
    
    op.drop_constraint('fk_vertex_builds_organization_id', 'vertex_builds', type_='foreignkey')
    op.drop_index('ix_vertex_builds_organization_id', 'vertex_builds')
    op.drop_column('vertex_builds', 'organization_id')
    
    op.drop_constraint('fk_transactions_organization_id', 'transactions', type_='foreignkey')
    op.drop_index('ix_transactions_organization_id', 'transactions')
    op.drop_column('transactions', 'organization_id')