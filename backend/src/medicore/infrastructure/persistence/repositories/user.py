"""SQLAlchemy UserRepository and DoctorProfileRepository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from medicore.domain.entities.user import DoctorProfile, User
from medicore.domain.repositories._support import Page, Paging, UserFilter
from medicore.domain.shared.identifiers import TenantId, UserId
from medicore.infrastructure.persistence.mappers.entities import to_doctor_profile, to_user
from medicore.infrastructure.persistence.models.user import DoctorProfileModel, UserModel


def _prefs_to_json(user: User) -> dict:
    p = user.preferences
    n = p.notifications
    return {
        "theme": str(p.theme),
        "language": str(p.language),
        "notifications": {
            "appointments": str(n.appointments),
            "reminders": str(n.reminders),
            "lab_results": str(n.lab_results),
            "internal_messages": str(n.internal_messages),
            "weekly_reports": str(n.weekly_reports),
        },
    }


class SqlUserRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def _q(self):
        return self._s.query(UserModel).filter(UserModel.tenant_id == self._tid)

    def get_by_id(self, user_id: UserId) -> User | None:
        row = self._q().filter(UserModel.id == user_id.value).first()
        return to_user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._q().filter(UserModel.email == email.strip().lower()).first()
        return to_user(row) if row else None

    def list(self, filter: UserFilter | None = None, paging: Paging | None = None) -> Page[User]:
        q = self._q().order_by(UserModel.name)
        if filter and filter.role:
            q = q.filter(UserModel.role == filter.role)
        if filter and filter.status:
            q = q.filter(UserModel.status == filter.status)
        total = q.count()
        pg = paging or Paging()
        rows = q.offset(pg.offset).limit(pg.limit).all()
        return Page(items=[to_user(r) for r in rows], total=total, offset=pg.offset, limit=pg.limit)

    def save(self, user: User) -> None:
        row = self._s.get(UserModel, user.id.value)
        if row is None:
            row = UserModel(id=user.id.value)
            self._s.add(row)
        row.tenant_id = user.tenant_id.value
        row.name = user.name
        row.email = user.email.lower()
        row.password_hash = user.password_hash
        row.role = str(user.role)
        row.status = str(user.status)
        row.specialty = user.specialty
        row.phone = user.phone
        row.preferences = _prefs_to_json(user)
        row.last_seen_at = user.last_seen_at
        row.joined_at = user.joined_at


class SqlDoctorProfileRepository:
    def __init__(self, session: Session, tenant_id: TenantId) -> None:
        self._s = session
        self._tid = tenant_id.value

    def get_by_user_id(self, user_id: UserId) -> DoctorProfile | None:
        row = (
            self._s.query(DoctorProfileModel)
            .filter(
                DoctorProfileModel.tenant_id == self._tid,
                DoctorProfileModel.user_id == user_id.value,
            )
            .first()
        )
        return to_doctor_profile(row) if row else None

    def save(self, profile: DoctorProfile) -> None:
        row = self._s.get(DoctorProfileModel, profile.id.value)
        if row is None:
            row = DoctorProfileModel(id=profile.id.value)
            self._s.add(row)
        row.user_id = profile.user_id.value
        row.tenant_id = profile.tenant_id.value
        row.bio = profile.bio
        if profile.default_location_id:
            row.default_location_id = profile.default_location_id.value
        else:
            row.default_location_id = None
