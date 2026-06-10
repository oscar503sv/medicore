import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/shell/AppLayout'
import { PlatformLayout } from '@/components/shell/PlatformLayout'
import { RequireAuth } from '@/components/RequireAuth'
import { RequirePlatformAuth } from '@/components/RequirePlatformAuth'
import { ToastViewport } from '@/components/ui/ToastViewport'
import { AppointmentsPage } from '@/pages/AppointmentsPage'
import { AuditPage } from '@/pages/AuditPage'
import { AvailabilityPage } from '@/pages/AvailabilityPage'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { ComingSoonPage } from '@/pages/ComingSoonPage'
import { ConsultationPage } from '@/pages/ConsultationPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { InsurersPage } from '@/pages/InsurersPage'
import { LoginPage } from '@/pages/LoginPage'
import { PatientDetailPage } from '@/pages/PatientDetailPage'
import { PatientsPage } from '@/pages/PatientsPage'
import { ClinicDetailPage } from '@/pages/platform/ClinicDetailPage'
import { ClinicsListPage } from '@/pages/platform/ClinicsListPage'
import { GlobalAuditPage } from '@/pages/platform/GlobalAuditPage'
import { GlobalStatsPage } from '@/pages/platform/GlobalStatsPage'
import { PlatformLoginPage } from '@/pages/platform/PlatformLoginPage'
import { RecordsPage } from '@/pages/RecordsPage'
import { SchedulePage } from '@/pages/SchedulePage'
import { SettingsPage } from '@/pages/SettingsPage'
import { PermissionsPage } from '@/pages/PermissionsPage'
import { UsersPage } from '@/pages/UsersPage'
import { applyTheme, useUIStore } from '@/stores/ui'

export function App() {
  const theme = useUIStore((s) => s.theme)

  // Apply theme + react to system preference changes.
  useEffect(() => {
    applyTheme(theme)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => theme === 'system' && applyTheme('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        {/* Platform (superadmin) console — its own auth, no tenant shell */}
        <Route path="/platform/login" element={<PlatformLoginPage />} />
        <Route
          element={
            <RequirePlatformAuth>
              <PlatformLayout />
            </RequirePlatformAuth>
          }
        >
          <Route path="/platform" element={<Navigate to="/platform/clinics" replace />} />
          <Route path="/platform/clinics" element={<ClinicsListPage />} />
          <Route path="/platform/clinics/:id" element={<ClinicDetailPage />} />
          <Route path="/platform/stats" element={<GlobalStatsPage />} />
          <Route path="/platform/audit" element={<GlobalAuditPage />} />
        </Route>

        {/* Forced password change after a temporary-password invite (no shell chrome) */}
        <Route
          path="/change-password"
          element={
            <RequireAuth>
              <ChangePasswordPage />
            </RequireAuth>
          }
        />

        {/* Full-screen consultation (no shell chrome) */}
        <Route
          path="/consultation/:id"
          element={
            <RequireAuth>
              <div className="h-screen">
                <ConsultationPage />
              </div>
            </RequireAuth>
          }
        />

        {/* App shell routes */}
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/patients" element={<PatientsPage />} />
          <Route path="/patients/:id" element={<PatientDetailPage />} />
          <Route path="/appointments" element={<AppointmentsPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/records" element={<RecordsPage />} />
          <Route path="/applications" element={<ComingSoonPage />} />
          <Route path="/procedures" element={<ComingSoonPage />} />
          <Route path="/vaccination" element={<ComingSoonPage />} />
          <Route path="/availability" element={<AvailabilityPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/permissions" element={<PermissionsPage />} />
          <Route path="/insurers" element={<InsurersPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastViewport />
    </>
  )
}
