"""Clinical note templates.

* ``consultations.soap`` and ``medical_records.soap`` become ``note``: the snapshot of the
  template the note was written with plus each section's text. Existing SOAP notes are
  converted to the built-in SOAP template, text untouched.
* ``tenants.note_settings``: the templates the clinic enables, its default, its rules per
  appointment type and whether the format is mandatory. Empty means the defaults.

Downgrade folds every note back into SOAP by section role (problems, history and free
text, which SOAP lacks, are dropped).

Revision ID: b8c9d0e1f2a4
Revises: a7b8c9d0e1f3
Create Date: 2026-11-13 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a4"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("consultations", "medical_records")
_SOAP = (("subjective", "Subjetivo"), ("objective", "Objetivo"),
         ("assessment", "Análisis"), ("plan", "Plan"))


def _section(key: str, title: str) -> str:
    return (
        f"jsonb_build_object('key', '{key}', 'role', '{key}', 'title', '{title}', "
        f"'required', true, 'text', coalesce(note->>'{key}', ''))"
    )


def upgrade() -> None:
    sections = ", ".join(_section(k, t) for k, t in _SOAP)
    for table in _TABLES:
        op.alter_column(table, "soap", new_column_name="note")
        op.execute(sa.text(
            f"UPDATE {table} SET note = jsonb_build_object("
            f"'template', 'soap', 'name', 'SOAP', 'sections', jsonb_build_array({sections}))"
        ))
    op.add_column("tenants", sa.Column(
        "note_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ))


def downgrade() -> None:
    op.drop_column("tenants", "note_settings")
    fields = ", ".join(
        f"'{key}', coalesce((SELECT string_agg(s->>'text', E'\\n\\n') "
        f"FROM jsonb_array_elements(note->'sections') s "
        f"WHERE s->>'role' = '{key}' AND btrim(s->>'text') <> ''), '')"
        for key, _ in _SOAP
    )
    for table in _TABLES:
        op.execute(sa.text(f"UPDATE {table} SET note = jsonb_build_object({fields})"))
        op.alter_column(table, "note", new_column_name="soap")
