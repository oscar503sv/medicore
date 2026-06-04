/** Curated IANA timezones offered when creating/editing a clinic.

Focused on Central America (initial market) plus common Latin America / US / Spain options.
The value is the IANA id stored on the tenant; the label is what the user sees. */
export const TIMEZONES: { value: string; label: string }[] = [
  { value: 'America/El_Salvador', label: 'El Salvador (GMT-6)' },
  { value: 'America/Guatemala', label: 'Guatemala (GMT-6)' },
  { value: 'America/Tegucigalpa', label: 'Honduras (GMT-6)' },
  { value: 'America/Managua', label: 'Nicaragua (GMT-6)' },
  { value: 'America/Costa_Rica', label: 'Costa Rica (GMT-6)' },
  { value: 'America/Panama', label: 'Panamá (GMT-5)' },
  { value: 'America/Mexico_City', label: 'México (GMT-6)' },
  { value: 'America/Bogota', label: 'Colombia (GMT-5)' },
  { value: 'America/Lima', label: 'Perú (GMT-5)' },
  { value: 'America/Santiago', label: 'Chile (GMT-4/-3)' },
  { value: 'America/Argentina/Buenos_Aires', label: 'Argentina (GMT-3)' },
  { value: 'America/New_York', label: 'US Este (GMT-5/-4)' },
  { value: 'America/Chicago', label: 'US Central (GMT-6/-5)' },
  { value: 'America/Los_Angeles', label: 'US Pacífico (GMT-8/-7)' },
  { value: 'Europe/Madrid', label: 'España (GMT+1/+2)' },
  { value: 'UTC', label: 'UTC' },
]
