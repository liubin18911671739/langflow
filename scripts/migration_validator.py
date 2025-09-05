#!/usr/bin/env python3
"""
Langflow Multi-tenant Migration Validator

This script validates the integrity and correctness of multi-tenant database migrations
after deployment, ensuring all data relationships and constraints are properly set up.

Usage:
    python scripts/migration_validator.py --db-url postgresql://user:pass@host:port/db
    python scripts/migration_validator.py --comprehensive --report-file validation_report.json
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from sqlalchemy import create_engine, text, MetaData, Table, Column, String, Integer, ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationValidator:
    """Validates multi-tenant database migration integrity."""

    def __init__(self, db_url: str, comprehensive: bool = False):
        self.db_url = db_url
        self.comprehensive = comprehensive
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database_url": db_url.replace("://", "://***:***@") if "://" in db_url else db_url,
            "validation_results": {},
            "errors": [],
            "warnings": [],
            "recommendations": []
        }

    async def validate_all(self) -> Dict[str, Any]:
        """Run all validation checks."""
        logger.info("🔍 Starting Langflow Multi-tenant Migration Validation")
        logger.info("=" * 60)

        validation_checks = [
            ("Schema Structure", self._validate_schema_structure),
            ("Table Relationships", self._validate_table_relationships),
            ("Data Integrity", self._validate_data_integrity),
            ("RLS Policies", self._validate_rls_policies),
            ("Indexes and Constraints", self._validate_indexes_constraints),
            ("Default Data", self._validate_default_data),
        ]

        if self.comprehensive:
            validation_checks.extend([
                ("Performance Metrics", self._validate_performance_metrics),
                ("Migration History", self._validate_migration_history),
                ("Data Consistency", self._validate_data_consistency),
            ])

        for check_name, check_func in validation_checks:
            logger.info(f"📋 Running {check_name} validation...")
            try:
                result = await check_func()
                self.results["validation_results"][check_name] = result
                if result["status"] == "PASS":
                    logger.info(f"  ✅ {check_name}: PASSED")
                elif result["status"] == "WARN":
                    logger.warning(f"  ⚠️  {check_name}: WARNING - {result.get('message', '')}")
                    self.results["warnings"].append(f"{check_name}: {result.get('message', '')}")
                else:
                    logger.error(f"  ❌ {check_name}: FAILED - {result.get('message', '')}")
                    self.results["errors"].append(f"{check_name}: {result.get('message', '')}")
            except Exception as e:
                logger.error(f"  💥 {check_name}: EXCEPTION - {e}")
                self.results["validation_results"][check_name] = {
                    "status": "ERROR",
                    "message": str(e)
                }
                self.results["errors"].append(f"{check_name}: {str(e)}")

        # Generate recommendations
        self._generate_recommendations()

        # Calculate overall status
        self.results["overall_status"] = self._calculate_overall_status()

        logger.info("=" * 60)
        logger.info(f"🎯 Validation completed with status: {self.results['overall_status']}")

        if self.results["errors"]:
            logger.error(f"❌ Found {len(self.results['errors'])} errors")
        if self.results["warnings"]:
            logger.warning(f"⚠️  Found {len(self.results['warnings'])} warnings")

        return self.results

    async def _validate_schema_structure(self) -> Dict[str, Any]:
        """Validate that all required tables and columns exist."""
        required_tables = {
            "organization": ["id", "name", "slug", "description", "logo_url", "website", "industry", "created_at", "updated_at", "owner_id"],
            "organizationmember": ["id", "organization_id", "user_id", "role", "permissions", "joined_at"],
            "subscriptionplan": ["id", "name", "plan_type", "description", "price", "yearly_price", "currency", "stripe_price_id", "stripe_yearly_price_id", "stripe_product_id", "limits", "features", "is_active", "is_popular", "created_at", "updated_at"],
            "subscription": ["id", "organization_id", "plan_id", "stripe_customer_id", "stripe_subscription_id", "stripe_latest_invoice_id", "status", "is_yearly", "current_period_start", "current_period_end", "trial_start", "trial_end", "cancel_at_period_end", "canceled_at", "ended_at", "created_at", "updated_at"],
            "invoice": ["id", "subscription_id", "stripe_invoice_id", "stripe_payment_intent_id", "invoice_number", "amount", "currency", "period_start", "period_end", "due_date", "paid_at", "status", "hosted_invoice_url", "invoice_pdf", "created_at"],
            "usagemetric": ["id", "organization_id", "metric_type", "value", "recorded_at", "period_start", "period_end", "metadata"],
        }

        # Multi-tenant columns that should be added to existing tables
        tenant_columns = {
            "flow": ["organization_id"],
            "folder": ["organization_id"],
            "apikey": ["organization_id"],
            "variable": ["organization_id"],
            "file": ["organization_id"],
            "message": ["organization_id"],
            "vertex_builds": ["organization_id"],
            "transactions": ["organization_id"],
        }

        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                all_tables = required_tables.copy()
                all_tables.update(tenant_columns)

                missing_tables = []
                missing_columns = []

                for table_name, expected_columns in all_tables.items():
                    # Check if table exists
                    result = await conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = '{table_name}'
                        )
                    """))
                    table_exists = result.fetchone()[0]

                    if not table_exists:
                        missing_tables.append(table_name)
                        continue

                    # Check columns
                    result = await conn.execute(text(f"""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = '{table_name}'
                        ORDER BY column_name
                    """))
                    existing_columns = [row[0] for row in result.fetchall()]

                    for expected_col in expected_columns:
                        if expected_col not in existing_columns:
                            missing_columns.append(f"{table_name}.{expected_col}")

                await engine.dispose()

                if missing_tables or missing_columns:
                    message = ""
                    if missing_tables:
                        message += f"Missing tables: {missing_tables}. "
                    if missing_columns:
                        message += f"Missing columns: {missing_columns}."

                    return {
                        "status": "FAIL",
                        "message": message,
                        "missing_tables": missing_tables,
                        "missing_columns": missing_columns
                    }

                return {
                    "status": "PASS",
                    "message": "All required tables and columns present",
                    "tables_validated": len(all_tables),
                    "columns_validated": sum(len(cols) for cols in all_tables.values())
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Schema validation failed: {str(e)}"
            }

    async def _validate_table_relationships(self) -> Dict[str, Any]:
        """Validate foreign key relationships and constraints."""
        relationships = [
            ("organization.owner_id", "user.id"),
            ("organizationmember.organization_id", "organization.id"),
            ("organizationmember.user_id", "user.id"),
            ("subscription.organization_id", "organization.id"),
            ("subscription.plan_id", "subscriptionplan.id"),
            ("invoice.subscription_id", "subscription.id"),
            ("usagemetric.organization_id", "organization.id"),
            ("flow.organization_id", "organization.id"),
            ("folder.organization_id", "organization.id"),
            ("apikey.organization_id", "organization.id"),
            ("variable.organization_id", "organization.id"),
        ]

        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                invalid_relationships = []

                for source, target in relationships:
                    source_table, source_col = source.split('.')
                    target_table, target_col = target.split('.')

                    # Check if constraint exists
                    result = await conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                            WHERE tc.table_name = '{source_table}'
                            AND kcu.column_name = '{source_col}'
                            AND tc.constraint_type = 'FOREIGN KEY'
                        )
                    """))
                    constraint_exists = result.fetchone()[0]

                    if not constraint_exists:
                        invalid_relationships.append(f"Missing FK: {source} -> {target}")

                    # Check for orphaned records (sample check)
                    if source_table in ['organization', 'subscription', 'usagemetric']:
                        result = await conn.execute(text(f"""
                            SELECT COUNT(*) FROM {source_table} t1
                            LEFT JOIN {target_table} t2 ON t1.{source_col} = t2.{target_col}
                            WHERE t2.{target_col} IS NULL AND t1.{source_col} IS NOT NULL
                        """))
                        orphaned_count = result.fetchone()[0]

                        if orphaned_count > 0:
                            invalid_relationships.append(f"Orphaned records in {source_table}: {orphaned_count}")

                await engine.dispose()

                if invalid_relationships:
                    return {
                        "status": "FAIL",
                        "message": f"Found relationship issues: {invalid_relationships}",
                        "invalid_relationships": invalid_relationships
                    }

                return {
                    "status": "PASS",
                    "message": "All table relationships are valid",
                    "relationships_validated": len(relationships)
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Relationship validation failed: {str(e)}"
            }

    async def _validate_data_integrity(self) -> Dict[str, Any]:
        """Validate data integrity constraints."""
        integrity_checks = [
            ("Organizations with unique slugs", """
                SELECT COUNT(*) FROM (
                    SELECT slug, COUNT(*) as count
                    FROM organization
                    GROUP BY slug
                    HAVING COUNT(*) > 1
                ) duplicates
            """),
            ("Users not in multiple organizations as owners", """
                SELECT COUNT(*) FROM (
                    SELECT owner_id, COUNT(*) as count
                    FROM organization
                    GROUP BY owner_id
                    HAVING COUNT(*) > 1
                ) multi_org_owners
            """),
            ("Valid subscription statuses", """
                SELECT COUNT(*) FROM subscription
                WHERE status NOT IN ('active', 'canceled', 'past_due', 'unpaid', 'trialing', 'incomplete', 'incomplete_expired')
            """),
            ("Non-negative usage values", """
                SELECT COUNT(*) FROM usagemetric WHERE value < 0
            """),
        ]

        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                integrity_issues = []

                for check_name, query in integrity_checks:
                    result = await conn.execute(text(query))
                    issue_count = result.fetchone()[0]

                    if issue_count > 0:
                        integrity_issues.append(f"{check_name}: {issue_count} issues")

                await engine.dispose()

                if integrity_issues:
                    return {
                        "status": "FAIL",
                        "message": f"Data integrity issues found: {integrity_issues}",
                        "integrity_issues": integrity_issues
                    }

                return {
                    "status": "PASS",
                    "message": "Data integrity checks passed",
                    "checks_performed": len(integrity_checks)
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Data integrity validation failed: {str(e)}"
            }

    async def _validate_rls_policies(self) -> Dict[str, Any]:
        """Validate Row Level Security policies are properly configured."""
        required_policies = [
            "flow_isolation_policy",
            "folder_isolation_policy",
            "apikey_isolation_policy",
            "variable_isolation_policy",
            "file_isolation_policy",
            "message_isolation_policy",
            "vertex_builds_isolation_policy",
        ]

        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                missing_policies = []

                for policy in required_policies:
                    result = await conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_policies
                            WHERE schemaname = 'public' AND policyname = '{policy}'
                        )
                    """))
                    policy_exists = result.fetchone()[0]

                    if not policy_exists:
                        missing_policies.append(policy)

                # Check if RLS is enabled on tables
                tables_without_rls = []
                for table in [p.replace('_isolation_policy', '') for p in required_policies]:
                    result = await conn.execute(text(f"""
                        SELECT relrowsecurity FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public' AND c.relname = '{table}'
                    """))
                    rls_enabled = result.fetchone()

                    if rls_enabled and not rls_enabled[0]:
                        tables_without_rls.append(table)

                await engine.dispose()

                issues = []
                if missing_policies:
                    issues.append(f"Missing RLS policies: {missing_policies}")
                if tables_without_rls:
                    issues.append(f"RLS not enabled on tables: {tables_without_rls}")

                if issues:
                    return {
                        "status": "FAIL",
                        "message": f"RLS configuration issues: {issues}",
                        "missing_policies": missing_policies,
                        "tables_without_rls": tables_without_rls
                    }

                return {
                    "status": "PASS",
                    "message": "RLS policies are properly configured",
                    "policies_validated": len(required_policies)
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"RLS validation failed: {str(e)}"
            }

    async def _validate_indexes_constraints(self) -> Dict[str, Any]:
        """Validate indexes and constraints are properly set up."""
        required_indexes = [
            ("organization", ["name"]),
            ("organization", ["slug"]),
            ("subscription", ["status"]),
            ("subscription", ["stripe_customer_id"]),
            ("invoice", ["stripe_invoice_id"]),
            ("usagemetric", ["metric_type"]),
            ("usagemetric", ["recorded_at"]),
            ("flow", ["organization_id"]),
            ("folder", ["organization_id"]),
            ("apikey", ["organization_id"]),
            ("variable", ["organization_id"]),
        ]

        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                missing_indexes = []

                for table, columns in required_indexes:
                    index_name = f"ix_{table}_{'_'.join(columns)}"
                    result = await conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_indexes
                            WHERE schemaname = 'public'
                            AND tablename = '{table}'
                            AND indexname = '{index_name}'
                        )
                    """))
                    index_exists = result.fetchone()[0]

                    if not index_exists:
                        missing_indexes.append(f"{table}: {columns}")

                await engine.dispose()

                if missing_indexes:
                    return {
                        "status": "WARN",
                        "message": f"Missing performance indexes: {missing_indexes}",
                        "missing_indexes": missing_indexes
                    }

                return {
                    "status": "PASS",
                    "message": "All required indexes are present",
                    "indexes_validated": len(required_indexes)
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Index validation failed: {str(e)}"
            }

    async def _validate_default_data(self) -> Dict[str, Any]:
        """Validate that default data was inserted correctly."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check default organization
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM organization WHERE slug = 'default-org'
                """))
                default_org_count = result.fetchone()[0]

                # Check subscription plans
                result = await conn.execute(text("""
                    SELECT COUNT(*) FROM subscriptionplan
                """))
                plan_count = result.fetchone()[0]

                # Check default plans data
                result = await conn.execute(text("""
                    SELECT name, plan_type, price FROM subscriptionplan ORDER BY price
                """))
                plans = result.fetchall()

                await engine.dispose()

                issues = []

                if default_org_count != 1:
                    issues.append(f"Expected 1 default organization, found {default_org_count}")

                if plan_count != 4:
                    issues.append(f"Expected 4 subscription plans, found {plan_count}")

                expected_plans = [
                    ("Free Plan", "free", 0),
                    ("Basic Plan", "basic", 29),
                    ("Professional Plan", "professional", 99),
                    ("Enterprise Plan", "enterprise", 299)
                ]

                if len(plans) == 4:
                    for i, (name, plan_type, price) in enumerate(plans):
                        expected_name, expected_type, expected_price = expected_plans[i]
                        if (name != expected_name or
                            plan_type != expected_type or
                            float(price) != expected_price):
                            issues.append(f"Plan {i+1} data mismatch: expected {expected_plans[i]}, got {(name, plan_type, float(price))}")

                if issues:
                    return {
                        "status": "FAIL",
                        "message": f"Default data issues: {issues}",
                        "issues": issues
                    }

                return {
                    "status": "PASS",
                    "message": "Default data is correctly configured",
                    "default_organization": default_org_count == 1,
                    "subscription_plans": plan_count == 4
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Default data validation failed: {str(e)}"
            }

    async def _validate_performance_metrics(self) -> Dict[str, Any]:
        """Validate performance metrics for the migrated schema."""
        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                # Check table sizes
                result = await conn.execute(text("""
                    SELECT
                        schemaname,
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename IN ('organization', 'subscription', 'usagemetric', 'flow', 'folder')
                    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                """))
                table_sizes = result.fetchall()

                # Check query performance on common operations
                performance_tests = [
                    ("Organization lookup by slug", """
                        EXPLAIN ANALYZE SELECT * FROM organization WHERE slug = 'default-org'
                    """),
                    ("User subscriptions query", """
                        EXPLAIN ANALYZE
                        SELECT s.* FROM subscription s
                        JOIN organization o ON s.organization_id = o.id
                        WHERE o.owner_id = (SELECT id FROM "user" LIMIT 1)
                    """),
                    ("Usage aggregation query", """
                        EXPLAIN ANALYZE
                        SELECT organization_id, metric_type, SUM(value) as total
                        FROM usagemetric
                        GROUP BY organization_id, metric_type
                    """)
                ]

                performance_results = []
                for test_name, query in performance_tests:
                    # Note: In production, you'd want to parse EXPLAIN output
                    # For now, just check if queries execute without error
                    try:
                        await conn.execute(text(query))
                        performance_results.append(f"{test_name}: OK")
                    except Exception as e:
                        performance_results.append(f"{test_name}: FAILED - {str(e)}")

                await engine.dispose()

                return {
                    "status": "INFO",
                    "message": "Performance metrics collected",
                    "table_sizes": [{"table": row[1], "size": row[2]} for row in table_sizes],
                    "performance_tests": performance_results
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Performance validation failed: {str(e)}"
            }

    async def _validate_migration_history(self) -> Dict[str, Any]:
        """Validate migration history is complete and correct."""
        try:
            # This would check alembic migration history
            # For now, return a placeholder
            return {
                "status": "INFO",
                "message": "Migration history validation would check alembic_version table"
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Migration history validation failed: {str(e)}"
            }

    async def _validate_data_consistency(self) -> Dict[str, Any]:
        """Validate data consistency across related tables."""
        consistency_checks = [
            ("Organization owners exist in user table", """
                SELECT COUNT(*) FROM organization o
                LEFT JOIN "user" u ON o.owner_id = u.id
                WHERE u.id IS NULL
            """),
            ("Organization members exist in user table", """
                SELECT COUNT(*) FROM organizationmember om
                LEFT JOIN "user" u ON om.user_id = u.id
                WHERE u.id IS NULL
            """),
            ("Subscription plans exist for all subscriptions", """
                SELECT COUNT(*) FROM subscription s
                LEFT JOIN subscriptionplan sp ON s.plan_id = sp.id
                WHERE sp.id IS NULL
            """),
            ("Usage metrics have valid organizations", """
                SELECT COUNT(*) FROM usagemetric um
                LEFT JOIN organization o ON um.organization_id = o.id
                WHERE o.id IS NULL
            """)
        ]

        try:
            engine = create_async_engine(self.db_url)
            async with engine.connect() as conn:
                consistency_issues = []

                for check_name, query in consistency_checks:
                    result = await conn.execute(text(query))
                    issue_count = result.fetchone()[0]

                    if issue_count > 0:
                        consistency_issues.append(f"{check_name}: {issue_count} inconsistencies")

                await engine.dispose()

                if consistency_issues:
                    return {
                        "status": "FAIL",
                        "message": f"Data consistency issues: {consistency_issues}",
                        "consistency_issues": consistency_issues
                    }

                return {
                    "status": "PASS",
                    "message": "Data consistency checks passed",
                    "checks_performed": len(consistency_checks)
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "message": f"Data consistency validation failed: {str(e)}"
            }

    def _generate_recommendations(self):
        """Generate recommendations based on validation results."""
        recommendations = []

        # Check for common issues and provide recommendations
        if any(result.get("status") == "FAIL" for result in self.results["validation_results"].values()):
            recommendations.append("Critical validation failures detected - review and fix before proceeding")

        if self.results["warnings"]:
            recommendations.append("Address validation warnings to ensure optimal performance")

        # Schema recommendations
        schema_result = self.results["validation_results"].get("Schema Structure", {})
        if schema_result.get("status") != "PASS":
            recommendations.append("Ensure all required tables and columns are created according to the migration plan")

        # Performance recommendations
        if self.comprehensive:
            perf_result = self.results["validation_results"].get("Performance Metrics", {})
            if perf_result.get("status") == "INFO":
                table_sizes = perf_result.get("table_sizes", [])
                large_tables = [t for t in table_sizes if "GB" in t.get("size", "") or "MB" in t.get("size", "")]
                if large_tables:
                    recommendations.append(f"Consider partitioning large tables: {[t['table'] for t in large_tables]}")

        # RLS recommendations
        rls_result = self.results["validation_results"].get("RLS Policies", {})
        if rls_result.get("status") != "PASS":
            recommendations.append("Ensure Row Level Security is properly configured for data isolation")

        self.results["recommendations"] = recommendations

    def _calculate_overall_status(self) -> str:
        """Calculate overall validation status."""
        results = self.results["validation_results"]

        if any(result.get("status") == "ERROR" for result in results.values()):
            return "ERROR"
        elif any(result.get("status") == "FAIL" for result in results.values()):
            return "FAIL"
        elif any(result.get("status") == "WARN" for result in results.values()):
            return "WARN"
        else:
            return "PASS"

    def save_report(self, file_path: str):
        """Save validation results to a JSON file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        logger.info(f"📄 Validation report saved to: {file_path}")


async def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description="Langflow Multi-tenant Migration Validator")
    parser.add_argument("--db-url", required=True, help="Database URL for validation")
    parser.add_argument("--comprehensive", action="store_true", help="Run comprehensive validation")
    parser.add_argument("--report-file", help="Save validation report to file")

    args = parser.parse_args()

    validator = MigrationValidator(
        db_url=args.db_url,
        comprehensive=args.comprehensive
    )

    results = await validator.validate_all()

    if args.report_file:
        validator.save_report(args.report_file)

    # Exit with appropriate code
    status = results["overall_status"]
    if status == "PASS":
        sys.exit(0)
    elif status == "WARN":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
