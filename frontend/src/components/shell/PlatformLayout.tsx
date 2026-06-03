import { Outlet } from 'react-router-dom'
import { PlatformSidebar } from './PlatformSidebar'
import { PlatformTopbar } from './PlatformTopbar'

export function PlatformLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      <PlatformSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <PlatformTopbar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
