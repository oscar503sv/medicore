import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/shell/AppLayout'
import { PlatformLayout } from '@/components/shell/PlatformLayout'
import { RequireAuth } from '@/components/RequireAuth'
import { RequirePlatformAuth } from '@/components/RequirePlatformAuth'
import { ToastViewport } from '@/components/ui/ToastViewport'
import { UpdateNotice } from '@/components/UpdateNotice'
import { AppointmentsPage } from '@/pages/AppointmentsPage'
import { AuditPage } from '@/pages/AuditPage'
import { AvailabilityPage } from '@/pages/AvailabilityPage'
import { FeesPage } from '@/pages/FeesPage'
import { AnalyticsPage } from '@/pages/AnalyticsPage'
import { ChangePasswordPage } from '@/pages/ChangePasswordPage'
import { ApplicationsPage } from '@/pages/ApplicationsPage'
import { ProcedureDetailPage } from '@/pages/ProcedureDetailPage'
import { ProcedureCatalogPage } from '@/pages/ProcedureCatalogPage'
import { ProceduresPage } from '@/pages/ProceduresPage'
import { ConsultationPage } from '@/pages/ConsultationPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { InsurersPage } from '@/pages/InsurersPage'
import { LoginPage } from '@/pages/LoginPage'
import { NotificationsPage } from '@/pages/NotificationsPage'
import { PatientDetailPage } from '@/pages/PatientDetailPage'
import { PatientsPage } from '@/pages/PatientsPage'
import { PrintPage } from '@/pages/PrintPage'
import { ClinicDetailPage } from '@/pages/platform/ClinicDetailPage'
import { ClinicsListPage } from '@/pages/platform/ClinicsListPage'
import { GlobalAuditPage } from '@/pages/platform/GlobalAuditPage'
import { BusinessPage } from '@/pages/platform/BusinessPage'
import { MonitoringPage } from '@/pages/platform/MonitoringPage'
import { PlansPage } from '@/pages/platform/PlansPage'
import { PlatformLoginPage } from '@/pages/platform/PlatformLoginPage'
import { RecordsPage } from '@/pages/RecordsPage'
import { SchedulePage } from '@/pages/SchedulePage'
import { SettingsPage } from '@/pages/SettingsPage'
import { PermissionsPage } from '@/pages/PermissionsPage'
import { UsersPage } from '@/pages/UsersPage'
import { VaccinationPage } from '@/pages/VaccinationPage'
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
          <Route path="/platform/plans" element={<PlansPage />} />
          <Route path="/platform/business" element={<BusinessPage />} />
          <Route path="/platform/monitoring" element={<MonitoringPage />} />
          <Route path="/platform/stats" element={<Navigate to="/platform/business" replace />} />
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

        {/* Printable documents, opened in their own tab (no shell chrome) */}
        <Route
          path="/print/:kind/:id"
          element={
            <RequireAuth>
              <PrintPage />
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
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/procedures" element={<ProceduresPage />} />
          <Route path="/procedures/catalog" element={<ProcedureCatalogPage />} />
          <Route path="/procedures/:id" element={<ProcedureDetailPage />} />
          <Route path="/vaccination" element={<VaccinationPage />} />
          <Route path="/availability" element={<AvailabilityPage />} />
          <Route path="/fees" element={<FeesPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/permissions" element={<PermissionsPage />} />
          <Route path="/insurers" element={<InsurersPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastViewport />
      <UpdateNotice />
    </>
  )
}
