"""Public source-available baseline for fresh databases.

Revision ID: 0001_public_baseline
Revises:
Create Date: 2026-05-27
"""

from datetime import datetime
from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_public_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_partition_boundaries() -> list[tuple[str, datetime, datetime]]:
    today = datetime.utcnow()
    partitions: list[tuple[str, datetime, datetime]] = []

    for offset in range(4):
        month_index = (today.month - 1) + offset
        year = today.year + month_index // 12
        month = (month_index % 12) + 1
        start_date = datetime(year, month, 1)

        next_month_index = month_index + 1
        next_year = today.year + next_month_index // 12
        next_month = (next_month_index % 12) + 1
        end_date = datetime(next_year, next_month, 1)

        partitions.append((f"alerthistory_y{year}m{month:02d}", start_date, end_date))

    return partitions


def _create_core_tables() -> None:
    op.create_table(
        "group",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_group_id", "group", ["id"], unique=False)

    op.create_table(
        "herald",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("herald_name", sa.String(), nullable=True),
        sa.Column("central_url", sa.String(), nullable=True),
        sa.Column("registered_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("health_status", sa.String(), nullable=True),
        sa.Column("last_ping", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("health_message", sa.String(), nullable=True),
        sa.Column("check_in_interval", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("hostname", sa.String(), nullable=True),
        sa.Column("herald_os", sa.String(), nullable=True),
        sa.Column("os_version", sa.String(), nullable=True),
        sa.Column("architecture", sa.String(), nullable=True),
        sa.Column("cpu_count", sa.Integer(), nullable=True),
        sa.Column("host_total_memory_bytes", sa.BigInteger(), nullable=True),
        sa.Column("herald_version", sa.String(), nullable=True),
        sa.Column(
            "socket_online",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("socket_last_seen", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "unregistered",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("unregistered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("unregistered_reason", sa.String(), nullable=True),
        sa.Column("unregistered_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_herald_id", "herald", ["id"], unique=False)
    op.create_index("ix_herald_health_status", "herald", ["health_status"], unique=False)

    op.create_table(
        "herald_token",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=True),
        sa.Column("herald_name", sa.String(), nullable=True),
        sa.Column("central_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("failure_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("check_in_interval", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_herald_token_id", "herald_token", ["id"], unique=False)
    op.create_index(
        "ix_herald_token_organization_id",
        "herald_token",
        ["organization_id"],
        unique=False,
    )
    op.create_index("ix_herald_token_status", "herald_token", ["status"], unique=False)

    op.create_table(
        "container",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("container_key", sa.String(), nullable=False),
        sa.Column("docker_container_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column(
            "monitoring_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("image_id", sa.String(), nullable=True),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cpu_limit", sa.Float(), nullable=True),
        sa.Column("memory_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("restart_policy", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inventory_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("command", sa.String(), nullable=True),
        sa.Column("entrypoint", sa.String(), nullable=True),
        sa.Column("working_dir", sa.String(), nullable=True),
        sa.Column(
            "environment",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "mounts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "ports",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "networks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("herald_id", sa.String(), nullable=True),
        sa.Column("group_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["herald_id"], ["herald.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["group.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_container_id", "container", ["id"], unique=False)
    op.create_index("ix_container_name", "container", ["name"], unique=False)
    op.create_index("ix_container_container_key", "container", ["container_key"], unique=True)
    op.create_index(
        "ix_container_docker_container_id",
        "container",
        ["docker_container_id"],
        unique=False,
    )
    op.create_index("ix_container_name_group_id", "container", ["name", "group_id"], unique=False)
    op.create_index("ix_container_herald_id", "container", ["herald_id"], unique=False)
    op.create_index("ix_container_herald_name", "container", ["herald_id", "name"], unique=False)

    op.create_table(
        "originpolicyconfig",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "allowed_origins",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_originpolicyconfig_id", "originpolicyconfig", ["id"], unique=False)


def _create_alerting_tables() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS alerting")

    op.create_table(
        "alertrule",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column(
            "trigger_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(), server_default=sa.text("'global'"), nullable=False),
        sa.Column(
            "scope_targets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(), server_default=sa.text("'warning'"), nullable=False),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "annotations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index("ix_alertrule_id", "alertrule", ["id"], unique=False, schema="alerting")
    op.create_index(
        "ix_alertrule_organization_id",
        "alertrule",
        ["organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertrule_enabled_organization_id",
        "alertrule",
        ["enabled", "organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertrule_scope_type_organization_id",
        "alertrule",
        ["scope_type", "organization_id"],
        unique=False,
        schema="alerting",
    )

    op.execute(
        """
        CREATE TABLE alerting.alerthistory (
            id VARCHAR NOT NULL,
            rule_id VARCHAR NOT NULL,
            rule_name VARCHAR NOT NULL,
            severity VARCHAR NOT NULL,
            message TEXT NOT NULL,
            context JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR NOT NULL DEFAULT 'triggered',
            triggered_at TIMESTAMP WITH TIME ZONE NOT NULL,
            acknowledged_at TIMESTAMP WITH TIME ZONE,
            acknowledged_by VARCHAR,
            organization_id VARCHAR NOT NULL,
            PRIMARY KEY (id, triggered_at)
        ) PARTITION BY RANGE (triggered_at)
        """
    )
    op.create_index(
        "ix_alerthistory_rule_id",
        "alerthistory",
        ["rule_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alerthistory_organization_id",
        "alerthistory",
        ["organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alerthistory_status",
        "alerthistory",
        ["status"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alerthistory_severity",
        "alerthistory",
        ["severity"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alerthistory_triggered_at",
        "alerthistory",
        ["triggered_at"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alerthistory_org_triggered_at",
        "alerthistory",
        ["organization_id", "triggered_at"],
        unique=False,
        schema="alerting",
    )

    for partition_name, start_date, end_date in _get_partition_boundaries():
        op.execute(
            f"""
            CREATE TABLE alerting.{partition_name}
            PARTITION OF alerting.alerthistory
            FOR VALUES FROM ('{start_date:%Y-%m-%d}')
            TO ('{end_date:%Y-%m-%d}')
            """
        )

    op.create_table(
        "alertstate",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'firing'"), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column(
            "labels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "annotations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("value", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stacking_key", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("last_trigger_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index("ix_alertstate_id", "alertstate", ["id"], unique=False, schema="alerting")
    op.create_index(
        "ix_alertstate_fingerprint",
        "alertstate",
        ["fingerprint"],
        unique=True,
        schema="alerting",
    )
    op.create_index("ix_alertstate_rule_id", "alertstate", ["rule_id"], unique=False, schema="alerting")
    op.create_index(
        "ix_alertstate_status_organization_id",
        "alertstate",
        ["status", "organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertstate_organization_id",
        "alertstate",
        ["organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertstate_stacking_key",
        "alertstate",
        ["stacking_key"],
        unique=False,
        schema="alerting",
    )
    op.execute(
        "CREATE INDEX ix_alertstate_org_updated "
        "ON alerting.alertstate (organization_id, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_alertstate_org_status_updated "
        "ON alerting.alertstate (organization_id, status, updated_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_alertstate_stacking_key_firing "
        "ON alerting.alertstate (stacking_key) "
        "WHERE status = 'firing'"
    )
    op.execute(
        "CREATE INDEX ix_alertstate_container_key_expr "
        "ON alerting.alertstate ((COALESCE(labels->>'container_key', labels->>'container_id')))"
    )
    op.execute(
        "CREATE INDEX ix_alertstate_host_id_expr "
        "ON alerting.alertstate ((labels->>'host_id'))"
    )
    op.execute(
        "CREATE INDEX ix_alertstate_container_name_expr "
        "ON alerting.alertstate ((labels->>'container_name'))"
    )

    op.create_table(
        "silence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "matchers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("recurring", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("recurrence_rule", sa.String(), nullable=True),
        sa.Column("expired", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index("ix_silence_id", "silence", ["id"], unique=False, schema="alerting")
    op.create_index(
        "ix_silence_organization_id",
        "silence",
        ["organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index("ix_silence_starts_at", "silence", ["starts_at"], unique=False, schema="alerting")
    op.create_index("ix_silence_ends_at", "silence", ["ends_at"], unique=False, schema="alerting")
    op.create_index(
        "ix_silence_active_window",
        "silence",
        ["organization_id", "starts_at", "ends_at"],
        unique=False,
        schema="alerting",
    )

    _create_action_tables()
    _create_alerting_config_tables()
    _create_alerting_functions()


def _create_action_tables() -> None:
    op.create_table(
        "ruleaction",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column(
            "action_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["alerting.alertrule.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index("ix_ruleaction_rule_id", "ruleaction", ["rule_id"], unique=False, schema="alerting")
    op.create_index("ix_ruleaction_enabled", "ruleaction", ["enabled"], unique=False, schema="alerting")

    op.create_table(
        "actionauditlog",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("rule_name", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("container_id", sa.String(), nullable=False),
        sa.Column("herald_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("block_reason", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("initiated_by", sa.String(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index("ix_actionauditlog_rule_id", "actionauditlog", ["rule_id"], unique=False, schema="alerting")
    op.create_index(
        "ix_actionauditlog_triggered_at",
        "actionauditlog",
        ["triggered_at"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_actionauditlog_rule_triggered",
        "actionauditlog",
        ["rule_id", "triggered_at"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_actionauditlog_container_id",
        "actionauditlog",
        ["container_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index("ix_actionauditlog_status", "actionauditlog", ["status"], unique=False, schema="alerting")

    op.create_table(
        "actiongatekeeperstate",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("container_id", sa.String(), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_limit_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index(
        "ix_actiongatekeeperstate_container_id",
        "actiongatekeeperstate",
        ["container_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_actiongatekeeperstate_rule_id",
        "actiongatekeeperstate",
        ["rule_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_actiongatekeeperstate_container_rule",
        "actiongatekeeperstate",
        ["container_id", "rule_id"],
        unique=False,
        schema="alerting",
    )

    op.create_table(
        "ruleauditlog",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("rule_id", sa.String(length=32), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("organization_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.String(length=50), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index("ix_ruleauditlog_rule_id", "ruleauditlog", ["rule_id"], unique=False, schema="alerting")
    op.create_index("ix_ruleauditlog_user_id", "ruleauditlog", ["user_id"], unique=False, schema="alerting")
    op.create_index(
        "ix_ruleauditlog_organization_id",
        "ruleauditlog",
        ["organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index("ix_ruleauditlog_action", "ruleauditlog", ["action"], unique=False, schema="alerting")
    op.create_index("ix_ruleauditlog_timestamp", "ruleauditlog", ["timestamp"], unique=False, schema="alerting")
    op.create_index(
        "ix_ruleauditlog_rule_timestamp",
        "ruleauditlog",
        ["rule_id", "timestamp"],
        unique=False,
        schema="alerting",
    )

    op.create_table(
        "alertoperationlog",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("alert_id", sa.String(length=32), nullable=True),
        sa.Column("alert_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("silence_id", sa.String(length=32), nullable=True),
        sa.Column("rule_id", sa.String(length=32), nullable=True),
        sa.Column("rule_name", sa.String(length=255), nullable=True),
        sa.Column("container_id", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("organization_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("timestamp", sa.String(length=50), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.create_index(
        "ix_alertoperationlog_alert_id",
        "alertoperationlog",
        ["alert_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertoperationlog_silence_id",
        "alertoperationlog",
        ["silence_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertoperationlog_user_id",
        "alertoperationlog",
        ["user_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertoperationlog_organization_id",
        "alertoperationlog",
        ["organization_id"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertoperationlog_operation",
        "alertoperationlog",
        ["operation"],
        unique=False,
        schema="alerting",
    )
    op.create_index(
        "ix_alertoperationlog_timestamp",
        "alertoperationlog",
        ["timestamp"],
        unique=False,
        schema="alerting",
    )


def _create_alerting_config_tables() -> None:
    op.create_table(
        "gatekeeperconfig",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.execute(
        """
        INSERT INTO alerting.gatekeeperconfig (id, settings, updated_at)
        VALUES (
            1,
            '{
                "cooldown_minutes": {
                    "restart": 5,
                    "stop": 10,
                    "start": 2,
                    "kill": 5,
                    "run_script": 5,
                    "notify": 1
                },
                "backoff_delays": [1, 2, 5, 10, 30],
                "max_backoff_minutes": 60,
                "disable_after_failures": 5,
                "disable_duration_minutes": 30,
                "max_actions_per_rule_per_hour": 10,
                "max_actions_per_container_per_hour": 20,
                "verification_delay_seconds": 5
            }'::jsonb,
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )

    op.create_table(
        "alertdataqualityconfig",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.execute(
        """
        INSERT INTO alerting.alertdataqualityconfig (id, settings, updated_at)
        VALUES (
            1,
            '{
                "auto_ack_enabled": false,
                "auto_ack_minutes": 240,
                "retention_mode": "forever",
                "retention_time_days": 30,
                "retention_count": 10000
            }'::jsonb,
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )

    op.create_table(
        "keywordconfig",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="alerting",
    )
    op.execute(
        """
        INSERT INTO alerting.keywordconfig (id, settings, updated_at)
        VALUES (
            1,
            '{
                "case_sensitive": true,
                "multi_mode": "any",
                "ignore_patterns": []
            }'::jsonb,
            NOW()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def _create_alerting_functions() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION alerting.create_alerthistory_partition(
            partition_date DATE
        ) RETURNS VOID AS $$
        DECLARE
            partition_name TEXT;
            start_date DATE;
            end_date DATE;
        BEGIN
            partition_name := 'alerthistory_y' || to_char(partition_date, 'YYYY') || 'm' || to_char(partition_date, 'MM');
            start_date := date_trunc('month', partition_date)::DATE;
            end_date := (date_trunc('month', partition_date) + interval '1 month')::DATE;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'alerting'
                  AND c.relname = partition_name
            ) THEN
                EXECUTE format(
                    'CREATE TABLE alerting.%I PARTITION OF alerting.alerthistory FOR VALUES FROM (%L) TO (%L)',
                    partition_name, start_date, end_date
                );
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION alerting.drop_old_alerthistory_partitions(
            retention_months INTEGER DEFAULT 12
        ) RETURNS VOID AS $$
        DECLARE
            cutoff_date DATE;
            partition_record RECORD;
        BEGIN
            cutoff_date := (date_trunc('month', CURRENT_DATE) - (retention_months || ' months')::INTERVAL)::DATE;

            FOR partition_record IN
                SELECT c.relname AS partition_name
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE i.inhparent = 'alerting.alerthistory'::regclass
                  AND n.nspname = 'alerting'
                  AND c.relname ~ '^alerthistory_y[0-9]{4}m[0-9]{2}$'
            LOOP
                IF to_date(
                    substring(partition_record.partition_name from 'y([0-9]{4})m([0-9]{2})'),
                    'YYYYMM'
                ) < cutoff_date THEN
                    EXECUTE format('DROP TABLE alerting.%I', partition_record.partition_name);
                END IF;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _create_notification_tables() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications")

    op.create_table(
        "notificationchannel",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("channel_type", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="notifications",
    )
    op.create_index(
        "ix_notificationchannel_id",
        "notificationchannel",
        ["id"],
        unique=False,
        schema="notifications",
    )
    op.create_index(
        "ix_notificationchannel_channel_type",
        "notificationchannel",
        ["channel_type"],
        unique=False,
        schema="notifications",
    )

    op.create_table(
        "channelpreset",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("channel_type", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="notifications",
    )
    op.create_index("ix_channelpreset_id", "channelpreset", ["id"], unique=False, schema="notifications")
    op.create_index(
        "ix_channelpreset_channel_type",
        "channelpreset",
        ["channel_type"],
        unique=False,
        schema="notifications",
    )

    op.create_table(
        "notificationgroup",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "target_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="notifications",
    )
    op.create_index(
        "ix_notificationgroup_id",
        "notificationgroup",
        ["id"],
        unique=False,
        schema="notifications",
    )
    op.create_index(
        "ix_notificationgroup_enabled",
        "notificationgroup",
        ["enabled"],
        unique=False,
        schema="notifications",
    )

    op.create_table(
        "notificationpreference",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("quiet_hours_timezone", sa.String(), nullable=True),
        sa.Column("min_severity", sa.String(), server_default=sa.text("'info'"), nullable=False),
        sa.Column(
            "preferred_channels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="notifications",
    )
    op.create_index(
        "ix_notificationpreference_id",
        "notificationpreference",
        ["id"],
        unique=False,
        schema="notifications",
    )

    op.create_table(
        "notificationlog",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("alert_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("channel_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="notifications",
    )
    op.create_index("ix_notificationlog_id", "notificationlog", ["id"], unique=False, schema="notifications")
    op.create_index(
        "ix_notificationlog_alert_id",
        "notificationlog",
        ["alert_id"],
        unique=False,
        schema="notifications",
    )
    op.create_index("ix_notificationlog_status", "notificationlog", ["status"], unique=False, schema="notifications")
    op.create_index(
        "ix_notificationlog_channel_id",
        "notificationlog",
        ["channel_id"],
        unique=False,
        schema="notifications",
    )
    op.create_index(
        "ix_notificationlog_next_retry_at",
        "notificationlog",
        ["next_retry_at"],
        unique=False,
        schema="notifications",
    )

    op.create_table(
        "ai_settings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("ai_enabled", sa.Boolean(), nullable=True),
        sa.Column("ollama_url", sa.String(), nullable=True),
        sa.Column("ollama_model", sa.String(), nullable=True),
        sa.Column("ai_timeout", sa.Integer(), nullable=True),
        sa.Column("ai_cache_ttl", sa.Integer(), nullable=True),
        sa.Column("ai_default_preprompt", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="notifications",
    )
    op.create_index("ix_ai_settings_id", "ai_settings", ["id"], unique=False, schema="notifications")
    op.create_index(
        "ix_ai_settings_organization_id",
        "ai_settings",
        ["organization_id"],
        unique=True,
        schema="notifications",
    )


def upgrade() -> None:
    _create_core_tables()
    _create_alerting_tables()
    _create_notification_tables()


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS alerting.drop_old_alerthistory_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS alerting.create_alerthistory_partition(DATE)")

    op.drop_table("ai_settings", schema="notifications")
    op.drop_table("notificationlog", schema="notifications")
    op.drop_table("notificationpreference", schema="notifications")
    op.drop_table("notificationgroup", schema="notifications")
    op.drop_table("channelpreset", schema="notifications")
    op.drop_table("notificationchannel", schema="notifications")
    op.execute("DROP SCHEMA IF EXISTS notifications")

    op.drop_table("keywordconfig", schema="alerting")
    op.drop_table("alertdataqualityconfig", schema="alerting")
    op.drop_table("gatekeeperconfig", schema="alerting")
    op.drop_table("alertoperationlog", schema="alerting")
    op.drop_table("ruleauditlog", schema="alerting")
    op.drop_table("actiongatekeeperstate", schema="alerting")
    op.drop_table("actionauditlog", schema="alerting")
    op.drop_table("ruleaction", schema="alerting")
    op.drop_table("silence", schema="alerting")
    op.drop_table("alertstate", schema="alerting")
    op.execute("DROP TABLE IF EXISTS alerting.alerthistory CASCADE")
    op.drop_table("alertrule", schema="alerting")
    op.execute("DROP SCHEMA IF EXISTS alerting")

    op.drop_table("originpolicyconfig")
    op.drop_table("container")
    op.drop_table("herald_token")
    op.drop_table("herald")
    op.drop_table("group")
