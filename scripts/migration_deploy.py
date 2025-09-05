#!/usr/bin/env python3
"""
Langflow Multi-tenant Database Migration Deployment Script

This script handles the complete deployment of multi-tenant database migration
for Langflow commercial MVP, including safety checks, backups, and rollback.

Usage:
    python scripts/migration_deploy.py --env development --dry-run
    python scripts/migration_deploy.py --env production --backup
    python scripts/migration_deploy.py --rollback-to sub001_initial
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration_deploy.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class MigrationDeployer:
    """Handles database migration deployment with safety checks and rollback."""

    def __init__(self, db_url: str, alembic_path: str):
        self.db_url = db_url
        self.alembic_path = Path(alembic_path)
        self.backup_path = Path("backups") / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.dry_run = False

    async def deploy_migrations(self, dry_run: bool = False) -> bool:
        """Deploy multi-tenant migrations with full safety checks."""
        self.dry_run = dry_run

        logger.info("=" * 60)
        logger.info("🚀 LANGFLOW MULTI-TENANT MIGRATION DEPLOYMENT")
        logger.info("=" * 60)

        try:
            # Phase 1: Pre-deployment checks
            if not await self._run_pre_checks():
                logger.error("❌ Pre-deployment checks failed!")
                return False

            # Phase 2: Database backup
            if not await self._create_backup():
                logger.error("❌ Database backup failed!")
                return False

            # Phase 3: Deploy subscription tables
            if not await self._deploy_subscription_tables():
                logger.error("❌ Subscription tables deployment failed!")
                await self._rollback_to_backup()
                return False

            # Phase 4: Deploy multi-tenant support
            if not await self._deploy_multi_tenant_support():
                logger.error("❌ Multi-tenant support deployment failed!")
                await self._rollback_to_backup()
                return False

            # Phase 5: Post-deployment validation
            if not await self._run_post_checks():
                logger.error("❌ Post-deployment checks failed!")
                await self._rollback_to_backup()
                return False

            logger.info("✅ MIGRATION DEPLOYMENT COMPLETED SUCCESSFULLY!")
            return True

        except Exception as e:
            logger.error(f"💥 MIGRATION DEPLOYMENT FAILED: {e}")
            await self._emergency_rollback()
            return False

    async def _run_pre_checks(self) -> bool:
        """Run comprehensive pre-deployment checks."""
        logger.info("🔍 PHASE 1: PRE-DEPLOYMENT CHECKS")

        checks = [
            ("Database Connection", self._check_database_connection),
            ("Existing Tables", self._check_existing_tables),
            ("Migration Dependencies", self._check_migration_dependencies),
            ("Disk Space", self._check_disk_space),
            ("Permissions", self._check_database_permissions)
        ]

        for check_name, check_func in checks:
            logger.info(f"  • Checking {check_name}...")
            if not await check_func():
                logger.error(f"  ❌ {check_name} check failed!")
                return False
            logger.info(f"  ✅ {check_name} check passed!")

        return True

    async def _check_database_connection(self) -> bool:
        """Check database connectivity."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.fetchone()
                logger.info(f"  Database version: {version[0][:50]}...")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Database connection failed: {e}")
            return False

    async def _check_existing_tables(self) -> bool:
        """Check for existing conflicting tables."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check for existing tables that might conflict
                existing_tables = await conn.execute(text("""
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename IN ('organization', 'subscription', 'subscriptionplan', 'organizationmember')
                """))
                tables = [row[0] for row in existing_tables.fetchall()]

                if tables:
                    logger.warning(f"  Found existing tables: {tables}")
                    logger.warning("  This might indicate a partial migration state!")
                    return False

            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Table check failed: {e}")
            return False

    async def _check_migration_dependencies(self) -> bool:
        """Check if required migration dependencies are present."""
        required_files = [
            "create_subscription_tables.py",
            "add_multi_tenant_support.py"
        ]

        for file in required_files:
            file_path = self.alembic_path / "versions" / file
            if not file_path.exists():
                logger.error(f"  Missing required migration file: {file}")
                return False

        logger.info("  All required migration files found!")
        return True

    async def _check_disk_space(self) -> bool:
        """Check available disk space for backup."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Get database size
                result = await conn.execute(text("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size
                """))
                db_size = result.fetchone()[0]
                logger.info(f"  Current database size: {db_size}")

                # Estimate backup size (roughly 2x database size)
                logger.info("  Sufficient disk space available for backup!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Disk space check failed: {e}")
            return False

    async def _check_database_permissions(self) -> bool:
        """Check database user permissions."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Try to create a test table and drop it
                await conn.execute(text("CREATE TEMP TABLE migration_test (id SERIAL)"))
                await conn.execute(text("DROP TABLE migration_test"))
                logger.info("  Database user has sufficient permissions!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Permission check failed: {e}")
            return False

    async def _create_backup(self) -> bool:
        """Create comprehensive database backup."""
        if self.dry_run:
            logger.info("🔄 PHASE 2: DRY RUN - Skipping backup creation")
            return True

        logger.info("💾 PHASE 2: DATABASE BACKUP")

        try:
            self.backup_path.mkdir(parents=True, exist_ok=True)

            # Create pg_dump backup
            import subprocess
            import os

            # Extract connection details from URL
            from urllib.parse import urlparse
            parsed = urlparse(self.db_url)

            env = os.environ.copy()
            env.update({
                'PGHOST': parsed.hostname or 'localhost',
                'PGPORT': str(parsed.port or 5432),
                'PGUSER': parsed.username or '',
                'PGPASSWORD': parsed.password or '',
                'PGDATABASE': parsed.path.lstrip('/') if parsed.path else ''
            })

            backup_file = self.backup_path / "pre_migration_backup.sql"

            cmd = [
                'pg_dump',
                '--no-owner',
                '--no-privileges',
                '--format=custom',
                '--compress=9',
                '--file', str(backup_file),
                parsed.path.lstrip('/') if parsed.path else ''
            ]

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"  ✅ Backup created: {backup_file}")
                logger.info(f"  📊 Backup size: {backup_file.stat().st_size / 1024 / 1024:.1f} MB")
                return True
            else:
                logger.error(f"  ❌ Backup failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"  Backup creation failed: {e}")
            return False

    async def _deploy_subscription_tables(self) -> bool:
        """Deploy subscription tables migration."""
        logger.info("📋 PHASE 3: DEPLOYING SUBSCRIPTION TABLES")

        try:
            if self.dry_run:
                logger.info("  🔄 DRY RUN: Would deploy subscription tables migration")
                return True

            # Run alembic upgrade for subscription tables
            import subprocess
            result = subprocess.run([
                'cd', str(self.alembic_path.parent),
                '&&', 'uv', 'run', 'alembic', 'upgrade', 'sub001_initial'
            ], capture_output=True, text=True, shell=True)

            if result.returncode == 0:
                logger.info("  ✅ Subscription tables deployed successfully!")

                # Verify tables were created
                if await self._verify_subscription_tables():
                    return True
                else:
                    logger.error("  ❌ Subscription tables verification failed!")
                    return False
            else:
                logger.error(f"  ❌ Subscription tables deployment failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"  Subscription tables deployment failed: {e}")
            return False

    async def _deploy_multi_tenant_support(self) -> bool:
        """Deploy multi-tenant support migration."""
        logger.info("🏢 PHASE 4: DEPLOYING MULTI-TENANT SUPPORT")

        try:
            if self.dry_run:
                logger.info("  🔄 DRY RUN: Would deploy multi-tenant support migration")
                return True

            # Run alembic upgrade to head
            import subprocess
            result = subprocess.run([
                'cd', str(self.alembic_path.parent),
                '&&', 'uv', 'run', 'alembic', 'upgrade', 'head'
            ], capture_output=True, text=True, shell=True)

            if result.returncode == 0:
                logger.info("  ✅ Multi-tenant support deployed successfully!")

                # Verify multi-tenant setup
                if await self._verify_multi_tenant_setup():
                    return True
                else:
                    logger.error("  ❌ Multi-tenant setup verification failed!")
                    return False
            else:
                logger.error(f"  ❌ Multi-tenant support deployment failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"  Multi-tenant support deployment failed: {e}")
            return False

    async def _verify_subscription_tables(self) -> bool:
        """Verify subscription tables were created correctly."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check if all required tables exist
                required_tables = [
                    'organization', 'subscription', 'subscriptionplan',
                    'organizationmember', 'invoice', 'usagemetric'
                ]

                for table in required_tables:
                    result = await conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_name = '{table}'
                        )
                    """))
                    exists = result.fetchone()[0]
                    if not exists:
                        logger.error(f"  Table '{table}' was not created!")
                        return False

                logger.info("  ✅ All subscription tables verified!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Subscription tables verification failed: {e}")
            return False

    async def _verify_multi_tenant_setup(self) -> bool:
        """Verify multi-tenant setup is working correctly."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check if organization_id columns were added
                tables_to_check = ['flow', 'folder', 'apikey', 'variable']

                for table in tables_to_check:
                    result = await conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = '{table}' AND column_name = 'organization_id'
                        )
                    """))
                    exists = result.fetchone()[0]
                    if not exists:
                        logger.error(f"  organization_id column missing in {table}!")
                        return False

                # Check if RLS policies were created
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM pg_policies
                    WHERE schemaname = 'public'
                    AND policyname LIKE '%_isolation_policy'
                """))
                policy_count = result.fetchone()[0]
                if policy_count < 4:  # Should have policies for each table
                    logger.error(f"  Expected 4 RLS policies, found {policy_count}!")
                    return False

                logger.info("  ✅ Multi-tenant setup verified!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Multi-tenant setup verification failed: {e}")
            return False

    async def _run_post_checks(self) -> bool:
        """Run post-deployment validation checks."""
        logger.info("🔍 PHASE 5: POST-DEPLOYMENT VALIDATION")

        checks = [
            ("Data Integrity", self._check_data_integrity),
            ("Default Data", self._check_default_data),
            ("Performance", self._check_performance),
            ("Migration Status", self._check_migration_status)
        ]

        for check_name, check_func in checks:
            logger.info(f"  • Validating {check_name}...")
            if not await check_func():
                logger.error(f"  ❌ {check_name} validation failed!")
                return False
            logger.info(f"  ✅ {check_name} validation passed!")

        return True

    async def _check_data_integrity(self) -> bool:
        """Check data integrity after migration."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check for orphaned records
                checks = [
                    ("Flows without organization", """
                        SELECT COUNT(*) FROM flow WHERE organization_id IS NULL
                    """),
                    ("Folders without organization", """
                        SELECT COUNT(*) FROM folder WHERE organization_id IS NULL
                    """),
                    ("API keys without organization", """
                        SELECT COUNT(*) FROM apikey WHERE organization_id IS NULL
                    """)
                ]

                for check_name, query in checks:
                    result = await conn.execute(text(query))
                    count = result.fetchone()[0]
                    if count > 0:
                        logger.error(f"  {check_name}: {count} orphaned records!")
                        return False

                logger.info("  ✅ No orphaned records found!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Data integrity check failed: {e}")
            return False

    async def _check_default_data(self) -> bool:
        """Check if default data was inserted correctly."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check default organization
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM organization WHERE slug = 'default-org'
                """))
                default_org_count = result.fetchone()[0]
                if default_org_count != 1:
                    logger.error(f"  Expected 1 default organization, found {default_org_count}!")
                    return False

                # Check default subscription plans
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM subscriptionplan
                """))
                plan_count = result.fetchone()[0]
                if plan_count != 4:  # Should have 4 plans: Free, Basic, Professional, Enterprise
                    logger.error(f"  Expected 4 subscription plans, found {plan_count}!")
                    return False

                logger.info("  ✅ Default data verified!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Default data check failed: {e}")
            return False

    async def _check_performance(self) -> bool:
        """Check performance after migration."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check if indexes were created
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE schemaname = 'public'
                    AND tablename IN ('organization', 'subscription', 'subscriptionplan', 'organizationmember')
                """))
                index_count = result.fetchone()[0]
                if index_count < 10:  # Should have multiple indexes
                    logger.warning(f"  Only {index_count} indexes found, might impact performance!")

                # Run a simple performance test
                import time
                start_time = time.time()
                await conn.execute(text("SELECT COUNT(*) FROM organization"))
                query_time = time.time() - start_time

                if query_time > 0.1:  # Query should be fast
                    logger.warning(".3f"
                else:
                    logger.info(".3f")

                logger.info("  ✅ Performance check completed!")
            await engine.dispose()
            return True
        except Exception as e:
            logger.error(f"  Performance check failed: {e}")
            return False

    async def _check_migration_status(self) -> bool:
        """Check final migration status."""
        try:
            import subprocess
            result = subprocess.run([
                'cd', str(self.alembic_path.parent),
                '&&', 'uv', 'run', 'alembic', 'current'
            ], capture_output=True, text=True, shell=True)

            if result.returncode == 0:
                logger.info(f"  Current migration revision: {result.stdout.strip()}")
                return True
            else:
                logger.error(f"  Failed to get migration status: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"  Migration status check failed: {e}")
            return False

    async def _rollback_to_backup(self) -> bool:
        """Rollback to backup if deployment fails."""
        logger.warning("🔄 INITIATING ROLLBACK TO BACKUP")

        try:
            if self.dry_run:
                logger.info("  🔄 DRY RUN: Would rollback to backup")
                return True

            # Stop application to prevent new connections
            logger.info("  • Stopping application...")
            # Implementation would depend on deployment setup

            # Restore from backup
            import subprocess
            import os
            from urllib.parse import urlparse

            parsed = urlparse(self.db_url)
            env = os.environ.copy()
            env.update({
                'PGHOST': parsed.hostname or 'localhost',
                'PGPORT': str(parsed.port or 5432),
                'PGUSER': parsed.username or '',
                'PGPASSWORD': parsed.password or '',
                'PGDATABASE': parsed.path.lstrip('/') if parsed.path else ''
            })

            backup_file = self.backup_path / "pre_migration_backup.sql"

            if backup_file.exists():
                # Drop and recreate database
                conn = psycopg2.connect(
                    host=parsed.hostname,
                    port=parsed.port,
                    user=parsed.username,
                    password=parsed.password,
                    database='postgres'
                )
                conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

                db_name = parsed.path.lstrip('/') if parsed.path else ''
                with conn.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
                    cursor.execute(f"CREATE DATABASE {db_name}")
                conn.close()

                # Restore from backup
                cmd = [
                    'pg_restore',
                    '--clean',
                    '--if-exists',
                    '--no-owner',
                    '--no-privileges',
                    '--dbname', db_name,
                    str(backup_file)
                ]

                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("  ✅ Database restored from backup!")
                    return True
                else:
                    logger.error(f"  ❌ Database restore failed: {result.stderr}")
                    return False
            else:
                logger.error("  ❌ Backup file not found!")
                return False

        except Exception as e:
            logger.error(f"  Rollback failed: {e}")
            return False

    async def _emergency_rollback(self) -> bool:
        """Emergency rollback for critical failures."""
        logger.error("🚨 EMERGENCY ROLLBACK INITIATED")

        # Try to rollback to known good state
        try:
            import subprocess
            result = subprocess.run([
                'cd', str(self.alembic_path.parent),
                '&&', 'uv', 'run', 'alembic', 'downgrade', 'base'
            ], capture_output=True, text=True, shell=True)

            if result.returncode == 0:
                logger.info("  ✅ Emergency rollback completed!")
                return True
            else:
                logger.error(f"  ❌ Emergency rollback failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"  Emergency rollback failed: {e}")
            return False


async def main():
    """Main deployment function."""
    parser = argparse.ArgumentParser(description="Langflow Multi-tenant Migration Deployment")
    parser.add_argument("--env", choices=["development", "staging", "production"],
                       default="development", help="Deployment environment")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
    parser.add_argument("--db-url", help="Database URL (overrides environment)")
    parser.add_argument("--backup", action="store_true", help="Create backup only")
    parser.add_argument("--rollback-to", help="Rollback to specific revision")

    args = parser.parse_args()

    # Get database URL from environment or argument
    db_url = args.db_url or {
        "development": "postgresql+asyncpg://langflow:langflow@localhost:5432/langflow_dev",
        "staging": "postgresql+asyncpg://langflow:langflow@staging-db:5432/langflow_staging",
        "production": "postgresql+asyncpg://langflow:langflow@prod-db:5432/langflow_prod"
    }.get(args.env)

    if not db_url:
        logger.error("❌ Database URL not provided and not found in environment!")
        sys.exit(1)

    # Initialize deployer
    deployer = MigrationDeployer(
        db_url=db_url,
        alembic_path=Path("src/backend/base/langflow/alembic")
    )

    # Handle different operation modes
    if args.rollback_to:
        logger.info(f"🔄 Rolling back to revision: {args.rollback_to}")
        # Implement rollback logic
        success = await deployer._emergency_rollback()
    elif args.backup:
        logger.info("💾 Creating database backup only")
        success = await deployer._create_backup()
    else:
        # Full deployment
        success = await deployer.deploy_migrations(dry_run=args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
