import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/providers/AuthProvider'

export function RequireAuth() {
  const { session, initializing, restoreFailed, retrySessionRestore } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  if (initializing) return <p className="p-6 text-sm text-muted-foreground">正在恢复会话</p>
  if (restoreFailed) {
    return (
      <div className="space-y-3 p-6 text-sm">
        <p className="text-muted-foreground">会话恢复失败，请检查服务连接。</p>
        <div className="flex gap-2">
          <button className="rounded-md border border-input px-3 py-2" onClick={() => void retrySessionRestore()}>重试</button>
          <button className="rounded-md bg-primary px-3 py-2 text-primary-foreground" onClick={() => navigate('/login', { replace: true })}>重新登录</button>
        </div>
      </div>
    )
  }
  return session ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
}
