import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/shell/AppLayout'
import { RequireAuth } from '@/components/RequireAuth'
import { ToastViewport } from '@/components/ui/Toast'
import { AppointmentsPage } from '@/pages/AppointmentsPage'
import { AvailabilityPage } from '@/pages/AvailabilityPage'
import { ConsultationPage } from '@/pages/ConsultationPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { LoginPage } from '@/pages/LoginPage'
import { PatientDetailPage } from '@/pages/PatientDetailPage'
import { PatientsPage } from '@/pages/PatientsPage'
import { RecordsPage } from '@/pages/RecordsPage'
import { SchedulePage } from '@/pages/SchedulePage'
import { SettingsPage } from '@/pages/SettingsPage'
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
          <Route path="/availability" element={<AvailabilityPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <ToastViewport />
    </>
  )
}
