"""Value objects — immutable, identity-less domain types."""

from medicore.domain.value_objects.blood_type import BloodType
from medicore.domain.value_objects.clinical_note import ClinicalNote
from medicore.domain.value_objects.contact_info import ContactInfo
from medicore.domain.value_objects.date_range import DateRange
from medicore.domain.value_objects.icd_code import IcdCode
from medicore.domain.value_objects.money import Money
from medicore.domain.value_objects.slug import Slug
from medicore.domain.value_objects.time_range import TimeRange
from medicore.domain.value_objects.user_preferences import (
    NotificationPreferences,
    UserPreferences,
)
from medicore.domain.value_objects.vitals import Vitals

__all__ = [
    "BloodType",
    "ClinicalNote",
    "ContactInfo",
    "DateRange",
    "IcdCode",
    "Money",
    "NotificationPreferences",
    "Slug",
    "TimeRange",
    "UserPreferences",
    "Vitals",
]
