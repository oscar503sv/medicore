"""patient search: trigram GIN indexes over the normalized name, code and phone

The search matches LIKE '%word%' against each expression (OR'ed per word), which a btree
cannot serve. One trigram index per branch lets Postgres combine them. The expressions
must stay identical to ``patient_search_sql`` in models/patient.py, or the planner will
not use them (tests/infrastructure/test_patient_search_sql.py checks the plan).

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-11-10 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = {
    "ix_patients_search_name_trgm": (
        "translate(lower(first_name || ' ' || last_name), "
        "'áàäâãéèëêíìïîóòöôõúùüûñç', 'aaaaaeeeeiiiiooooouuuunc')"
    ),
    "ix_patients_search_code_trgm": "lower(code)",
    "ix_patients_search_phone_trgm": (
        "regexp_replace(coalesce(contact ->> 'phone', ''), '[^0-9]', '', 'g')"
    ),
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, expr in _INDEXES.items():
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON patients USING gin (({expr}) gin_trgm_ops)"
        )


def downgrade() -> None:
    for name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
