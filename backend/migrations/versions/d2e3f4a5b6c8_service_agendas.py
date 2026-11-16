"""Service agendas (the vaccination room) and the doses given in an appointment.

* ``service_agendas``: a clinic service with its own schedule, not tied to a doctor.
* ``appointments.agenda_id``: who attends an appointment is now a doctor or an agenda, never
  both (``doctor_id`` becomes nullable, with a CHECK keeping exactly one of the two). Code that
  predates the column always inserts a doctor, which satisfies the CHECK.
* ``doctor_availability.agenda_id``: the same rule for a schedule, one per agenda.
* ``vaccination_records.appointment_id``: the appointment a dose was given in (nullable).

The new references are composite ``(tenant_id, ...)`` foreign keys, so a row can never point
at another clinic's agenda or appointment; that needs ``UNIQUE (tenant_id, id)`` on the
referenced tables (``appointments`` and ``locations`` get one too).

Downgrade refuses to run while agenda or vaccination data exists instead of deleting it.

Revision ID: d2e3f4a5b6c8
Revises: c1d2e3f4a5b7
Create Date: 2026-11-15 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2e3f4a5b6c8"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_locations_tenant_id", "locations", ["tenant_id", "id"])
    op.create_unique_constraint("uq_appointments_tenant_id", "appointments", ["tenant_id", "id"])
    op.create_table(
        "service_agendas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"],
            name="fk_service_agendas_tenant_location",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_service_agendas_tenant_id"),
    )
    op.create_index(
        "uq_service_agendas_tenant_name", "service_agendas",
        ["tenant_id", sa.text("lower(name)")], unique=True,
    )

    op.add_column(
        "appointments", sa.Column("agenda_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_appointments_tenant_agenda", "appointments", "service_agendas",
        ["tenant_id", "agenda_id"], ["tenant_id", "id"],
    )
    op.alter_column("appointments", "doctor_id", nullable=True)
    op.create_check_constraint(
        "ck_appointments_one_assignee", "appointments", "num_nonnulls(doctor_id, agenda_id) = 1"
    )
    op.create_index(
        "ix_appointments_agenda_day", "appointments", ["agenda_id", "scheduled_start"]
    )

    op.add_column(
        "doctor_availability",
        sa.Column("agenda_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_availability_tenant_agenda", "doctor_availability", "service_agendas",
        ["tenant_id", "agenda_id"], ["tenant_id", "id"],
    )
    op.alter_column("doctor_availability", "doctor_id", nullable=True)
    op.create_check_constraint(
        "ck_availability_one_assignee", "doctor_availability",
        "num_nonnulls(doctor_id, agenda_id) = 1",
    )
    # The doctor's own UNIQUE (tenant_id, doctor_id) keeps working: NULL doctors never clash.
    op.create_index(
        "uq_availability_tenant_agenda", "doctor_availability", ["tenant_id", "agenda_id"],
        unique=True, postgresql_where=sa.text("agenda_id IS NOT NULL"),
    )

    op.add_column(
        "vaccination_records",
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_vaccination_records_tenant_appointment", "vaccination_records", "appointments",
        ["tenant_id", "appointment_id"], ["tenant_id", "id"],
    )
    op.create_index(
        "ix_vaccination_records_appointment", "vaccination_records",
        ["tenant_id", "appointment_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM appointments WHERE agenda_id IS NOT NULL) "
        "+ (SELECT count(*) FROM appointments WHERE type = 'vaccination') "
        "+ (SELECT count(*) FROM doctor_availability WHERE agenda_id IS NOT NULL) "
        "+ (SELECT count(*) FROM vaccination_records WHERE appointment_id IS NOT NULL) "
        "+ (SELECT count(*) FROM service_agendas)"
    )).scalar_one()
    if in_use:
        raise RuntimeError(
            "cannot downgrade: service agendas, vaccination appointments or doses linked to an "
            "appointment exist; move or remove them first, nothing is deleted automatically"
        )

    op.drop_index("ix_vaccination_records_appointment", table_name="vaccination_records")
    op.drop_constraint(
        "fk_vaccination_records_tenant_appointment", "vaccination_records", type_="foreignkey"
    )
    op.drop_column("vaccination_records", "appointment_id")

    op.drop_index("uq_availability_tenant_agenda", table_name="doctor_availability")
    op.drop_constraint("ck_availability_one_assignee", "doctor_availability", type_="check")
    op.alter_column("doctor_availability", "doctor_id", nullable=False)
    op.drop_constraint("fk_availability_tenant_agenda", "doctor_availability", type_="foreignkey")
    op.drop_column("doctor_availability", "agenda_id")

    op.drop_index("ix_appointments_agenda_day", table_name="appointments")
    op.drop_constraint("ck_appointments_one_assignee", "appointments", type_="check")
    op.alter_column("appointments", "doctor_id", nullable=False)
    op.drop_constraint("fk_appointments_tenant_agenda", "appointments", type_="foreignkey")
    op.drop_column("appointments", "agenda_id")

    op.drop_index("uq_service_agendas_tenant_name", table_name="service_agendas")
    op.drop_table("service_agendas")
    op.drop_constraint("uq_appointments_tenant_id", "appointments", type_="unique")
    op.drop_constraint("uq_locations_tenant_id", "locations", type_="unique")
