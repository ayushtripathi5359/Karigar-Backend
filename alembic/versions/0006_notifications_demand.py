"""notifications, push outbox, campaigns, and demand requests

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-16
"""
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'transaction'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'supplier_upload'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'supplier_update'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'demand_request'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'promotion'")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS device_push_tokens (
          token_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id       UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
          provider      TEXT NOT NULL DEFAULT 'expo',
          push_token    TEXT NOT NULL,
          platform      TEXT,
          device_id     TEXT,
          app_version   TEXT,
          is_active     BOOLEAN NOT NULL DEFAULT TRUE,
          last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          deleted_at    TIMESTAMPTZ,
          CONSTRAINT chk_push_provider CHECK (provider IN ('expo','stub'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_device_push_token_active
          ON device_push_tokens (provider, push_token)
          WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_device_push_tokens_user_active
          ON device_push_tokens (user_id, is_active)
          WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_outbox (
          outbox_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          notification_id      UUID NOT NULL REFERENCES notifications (notification_id) ON DELETE CASCADE,
          token_id             UUID REFERENCES device_push_tokens (token_id) ON DELETE SET NULL,
          channel              TEXT NOT NULL DEFAULT 'push',
          status               TEXT NOT NULL DEFAULT 'pending',
          attempt_count        INT NOT NULL DEFAULT 0,
          next_attempt_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_error           TEXT,
          provider_message_id  TEXT,
          created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
          delivered_at         TIMESTAMPTZ,
          CONSTRAINT chk_notification_outbox_channel CHECK (channel IN ('push')),
          CONSTRAINT chk_notification_outbox_status CHECK (status IN ('pending','sent','failed','skipped'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending
          ON notification_outbox (status, next_attempt_at)
          WHERE status = 'pending'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_outbox_notification
          ON notification_outbox (notification_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_campaigns (
          campaign_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          created_by          UUID REFERENCES users (user_id) ON DELETE SET NULL,
          title               TEXT NOT NULL,
          body                TEXT,
          image_url           TEXT,
          deep_link           TEXT,
          target_role         TEXT NOT NULL DEFAULT 'buyer',
          target_supplier_id  UUID REFERENCES suppliers (supplier_id) ON DELETE SET NULL,
          status              TEXT NOT NULL DEFAULT 'draft',
          published_at        TIMESTAMPTZ,
          created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
          deleted_at          TIMESTAMPTZ,
          CONSTRAINT chk_campaign_target_role CHECK (target_role IN ('all','buyer','supplier','admin','karigar_staff')),
          CONSTRAINT chk_campaign_status CHECK (status IN ('draft','published','cancelled'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notification_campaigns_status
          ON notification_campaigns (status, created_at DESC)
          WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS demand_requests (
          demand_request_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          buyer_id               UUID NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
          stone_id               UUID NOT NULL REFERENCES supplier_master (id) ON DELETE CASCADE,
          supplier_id            UUID NOT NULL REFERENCES suppliers (supplier_id) ON DELETE CASCADE,
          requested_discount_pct NUMERIC(6,2),
          requested_price_inr    NUMERIC(14,2),
          message                TEXT,
          status                 TEXT NOT NULL DEFAULT 'open',
          response_note          TEXT,
          offered_price_inr      NUMERIC(14,2),
          resolved_by            UUID REFERENCES users (user_id) ON DELETE SET NULL,
          created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
          resolved_at            TIMESTAMPTZ,
          deleted_at             TIMESTAMPTZ,
          CONSTRAINT chk_demand_request_amount CHECK (
            requested_discount_pct IS NOT NULL OR requested_price_inr IS NOT NULL
          ),
          CONSTRAINT chk_demand_request_discount CHECK (
            requested_discount_pct IS NULL OR requested_discount_pct BETWEEN 0 AND 100
          ),
          CONSTRAINT chk_demand_request_status CHECK (
            status IN ('open','countered','accepted','rejected','cancelled')
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_demand_requests_buyer
          ON demand_requests (buyer_id, created_at DESC)
          WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_demand_requests_supplier
          ON demand_requests (supplier_id, status, created_at DESC)
          WHERE deleted_at IS NULL
        """
    )

    op.execute("ALTER TABLE device_push_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_campaigns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE demand_requests ENABLE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY users_notification_recipient_read ON users
          FOR SELECT USING (
            current_user_id() IS NOT NULL
            AND role IN ('admin','karigar_staff')
            AND deleted_at IS NULL
          )
        """
    )

    op.execute("DROP POLICY IF EXISTS notifications_owner ON notifications")
    op.execute(
        """
        CREATE POLICY notifications_owner_read ON notifications
          FOR SELECT USING (user_id = current_user_id() OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY notifications_owner_update ON notifications
          FOR UPDATE USING (user_id = current_user_id() OR is_admin())
          WITH CHECK (user_id = current_user_id() OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY notifications_service_insert ON notifications
          FOR INSERT WITH CHECK (current_user_id() IS NOT NULL OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY notifications_admin_delete ON notifications
          FOR DELETE USING (is_admin())
        """
    )

    op.execute(
        """
        CREATE POLICY device_push_tokens_delivery_read ON device_push_tokens
          FOR SELECT USING (current_user_id() IS NOT NULL OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY device_push_tokens_owner_insert ON device_push_tokens
          FOR INSERT WITH CHECK (user_id = current_user_id() OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY device_push_tokens_owner_update ON device_push_tokens
          FOR UPDATE USING (user_id = current_user_id() OR is_admin())
          WITH CHECK (user_id = current_user_id() OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY device_push_tokens_owner_delete ON device_push_tokens
          FOR DELETE USING (user_id = current_user_id() OR is_admin())
        """
    )

    op.execute(
        """
        CREATE POLICY notification_outbox_admin_read ON notification_outbox
          FOR SELECT USING (is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY notification_outbox_service_insert ON notification_outbox
          FOR INSERT WITH CHECK (current_user_id() IS NOT NULL OR is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY notification_outbox_admin_update ON notification_outbox
          FOR UPDATE USING (is_admin())
          WITH CHECK (is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY notification_campaigns_admin ON notification_campaigns
          FOR ALL USING (is_admin())
          WITH CHECK (is_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY demand_requests_scope ON demand_requests
          FOR ALL USING (
            buyer_id = current_user_id()
            OR is_admin()
            OR EXISTS (
              SELECT 1 FROM supplier_user_mappings m
              WHERE m.supplier_id = demand_requests.supplier_id
                AND m.user_id = current_user_id()
                AND m.deleted_at IS NULL
            )
          )
          WITH CHECK (
            buyer_id = current_user_id()
            OR is_admin()
            OR EXISTS (
              SELECT 1 FROM supplier_user_mappings m
              WHERE m.supplier_id = demand_requests.supplier_id
                AND m.user_id = current_user_id()
                AND m.deleted_at IS NULL
            )
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS demand_requests_scope ON demand_requests")
    op.execute("DROP POLICY IF EXISTS notification_campaigns_admin ON notification_campaigns")
    op.execute("DROP POLICY IF EXISTS notification_outbox_admin_update ON notification_outbox")
    op.execute("DROP POLICY IF EXISTS notification_outbox_service_insert ON notification_outbox")
    op.execute("DROP POLICY IF EXISTS notification_outbox_admin_read ON notification_outbox")
    op.execute("DROP POLICY IF EXISTS device_push_tokens_owner_delete ON device_push_tokens")
    op.execute("DROP POLICY IF EXISTS device_push_tokens_owner_update ON device_push_tokens")
    op.execute("DROP POLICY IF EXISTS device_push_tokens_owner_insert ON device_push_tokens")
    op.execute("DROP POLICY IF EXISTS device_push_tokens_delivery_read ON device_push_tokens")
    op.execute("DROP POLICY IF EXISTS notifications_admin_delete ON notifications")
    op.execute("DROP POLICY IF EXISTS notifications_service_insert ON notifications")
    op.execute("DROP POLICY IF EXISTS notifications_owner_update ON notifications")
    op.execute("DROP POLICY IF EXISTS notifications_owner_read ON notifications")
    op.execute("DROP POLICY IF EXISTS users_notification_recipient_read ON users")
    op.execute(
        """
        CREATE POLICY notifications_owner ON notifications
          FOR ALL USING (user_id = current_user_id() OR is_admin())
          WITH CHECK (user_id = current_user_id() OR is_admin())
        """
    )
    op.execute("DROP TABLE IF EXISTS demand_requests")
    op.execute("DROP TABLE IF EXISTS notification_campaigns")
    op.execute("DROP TABLE IF EXISTS notification_outbox")
    op.execute("DROP TABLE IF EXISTS device_push_tokens")
