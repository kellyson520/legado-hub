import { Outlet } from 'react-router-dom'
import { useAuth } from '@/app/providers/AuthProvider'

export function RequirePermission({ permission }: { permission: string }) {
  const { hasPermission } = useAuth()
  return hasPermission(permission) ? <Outlet /> : <p className="p-6 text-sm text-rose-300">Access denied</p>
}
