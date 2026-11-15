"""Documents belong to one patient and their storage key is chosen by the server.

* Documents whose ``record_id`` points to another patient's record, or to none, are unlinked
  (``record_id`` becomes NULL): the file stays with its patient.
* Every ``storage_key`` is rewritten to ``{tenant_id}/{patient_id}/{id}``.
* A unique index on ``storage_key`` is the safety net before files move to object storage.

The downgrade drops the index. The unlinked records and the previous keys are not recovered.

Revision ID: f8a9b0c1d2e4
Revises: f7a8b9c0d1e3
Create Date: 2026-11-15 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f8a9b0c1d2e4"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_medical_documents_storage_key"
_KEY = "tenant_id::text || '/' || patient_id::text || '/' || id::text"


def upgrade() -> None:
    op.execute(
        """
        UPDATE medical_documents d SET record_id = NULL
        WHERE d.record_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM medical_records r
          WHERE r.id = d.record_id AND r.tenant_id = d.tenant_id AND r.patient_id = d.patient_id)
        """
    )
    op.execute(
        f"UPDATE medical_documents SET storage_key = {_KEY} "
        f"WHERE storage_key IS DISTINCT FROM {_KEY}"
    )
    op.create_index(_INDEX, "medical_documents", ["storage_key"], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="medical_documents")
