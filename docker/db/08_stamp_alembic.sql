-- Docker local-dev init: the schema is loaded from sql/*.sql files above.
-- Stamp Alembic so fresh Compose databases report the same current revision.
CREATE TABLE IF NOT EXISTS alembic_version (
  version_num VARCHAR(32) NOT NULL,
  CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num)
VALUES ('0006')
ON CONFLICT (version_num) DO NOTHING;
