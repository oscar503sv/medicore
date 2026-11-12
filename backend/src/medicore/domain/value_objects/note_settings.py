"""NoteSettings value object — which note templates a clinic uses and when.

``enabled`` are the templates doctors may pick; ``default`` is used when no rule applies;
``rules`` map an appointment type (or ``first_visit``, the patient's first visit to the
clinic) to a template; ``locked`` makes the resolved template mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from medicore.domain.enums import AppointmentType
from medicore.domain.shared.errors import InvalidValueObject

FIRST_VISIT = "first_visit"
RULE_KEYS = (FIRST_VISIT, *(str(t) for t in AppointmentType))
DEFAULT_TEMPLATE = "soap"


@dataclass(frozen=True, slots=True)
class NoteSettings:
    enabled: tuple[str, ...] = ()  # empty: every template available
    default: str = DEFAULT_TEMPLATE
    rules: dict[str, str] = field(default_factory=dict, hash=False)
    locked: bool = False

    def __post_init__(self) -> None:
        bad = sorted(set(self.rules) - set(RULE_KEYS))
        if bad:
            raise InvalidValueObject(f"Unknown note rules: {bad}", code="note.invalid_rule")
        if self.enabled:
            if self.default not in self.enabled:
                raise InvalidValueObject(
                    "The default template must be enabled", code="note.default_not_enabled"
                )
            if any(v not in self.enabled for v in self.rules.values()):
                raise InvalidValueObject(
                    "Rules may only use enabled templates", code="note.rule_not_enabled"
                )

    def allows(self, template: str) -> bool:
        return not self.enabled or template in self.enabled

    def without(self, gone: set[str]) -> NoteSettings:
        """The same settings with templates that no longer exist taken out (an archived
        custom template, or custom ones after a plan without them)."""
        if not gone & {self.default, *self.enabled, *self.rules.values()}:
            return self
        enabled = tuple(k for k in self.enabled if k not in gone)
        if self.enabled and not enabled:
            enabled = (DEFAULT_TEMPLATE,)
        default = self.default if self.default not in gone else (
            enabled[0] if enabled else DEFAULT_TEMPLATE)
        rules = {k: v for k, v in self.rules.items() if v not in gone}
        return NoteSettings(enabled=enabled, default=default, rules=rules, locked=self.locked)
