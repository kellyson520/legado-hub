import { useState } from 'react'
import {
  createUser,
  listUsers,
  resetUserPassword,
  revokeUserSessions,
  setUserEnabled,
  updateUser,
  type AdminUserRow,
} from '@/api/modules/admin'
import { useAuth } from '@/app/providers/AuthProvider'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { useServerPagination } from '@/hooks/useServerPagination'
import { roleText, statusText } from '@/lib/i18n'

type UserRole = 'admin' | 'user'

interface UserForm {
  username: string
  displayName: string
  role: UserRole
  password: string
}

const emptyForm: UserForm = {
  username: '',
  displayName: '',
  role: 'user',
  password: '',
}

export function AdminUsersPage() {
  const { hasPermission } = useAuth()
  const pagination = useServerPagination<AdminUserRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listUsers({ page, page_size: pageSize, search }),
  })
  const { rows: users, meta } = pagination
  const [error, setError] = useState('')
  const [formMode, setFormMode] = useState<'create' | 'edit' | null>(null)
  const [editingUser, setEditingUser] = useState<AdminUserRow | null>(null)
  const [form, setForm] = useState<UserForm>(emptyForm)
  const [passwordTarget, setPasswordTarget] = useState<AdminUserRow | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const canWrite = hasPermission('users.write')

  const load = () => pagination.reload()

  const openCreate = () => {
    setEditingUser(null)
    setForm(emptyForm)
    setFormMode('create')
  }

  const openEdit = (user: AdminUserRow) => {
    setEditingUser(user)
    setForm({
      username: user.username,
      displayName: user.display_name,
      role: user.role,
      password: '',
    })
    setFormMode('edit')
  }

  const closeForm = () => {
    setFormMode(null)
    setEditingUser(null)
    setForm(emptyForm)
  }

  const saveUser = async () => {
    if (!canWrite || busy) return
    setBusy(true)
    try {
      if (formMode === 'create') {
        await createUser({
          username: form.username.trim(),
          display_name: form.displayName.trim(),
          role: form.role,
          password: form.password,
        })
      } else if (editingUser) {
        await updateUser(editingUser.id, {
          display_name: form.displayName.trim(),
          role: form.role,
        })
      }
      closeForm()
      await load()
    } catch {
      setError(formMode === 'create' ? '创建用户失败，请检查填写内容' : '保存用户修改失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  const toggle = async (user: AdminUserRow) => {
    const nextEnabled = user.status !== 'enabled'
    if (!canWrite || busy || !window.confirm(`确定要${nextEnabled ? '启用' : '停用'}用户“${user.username}”吗？`)) return
    setBusy(true)
    try {
      await setUserEnabled(user.id, nextEnabled)
      await load()
    } catch {
      setError('更新用户状态失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = async () => {
    if (!passwordTarget || !canWrite || busy || !newPassword) return
    if (!window.confirm(`确定重置用户“${passwordTarget.username}”的密码吗？该用户的所有会话将失效。`)) return
    setBusy(true)
    try {
      await resetUserPassword(passwordTarget.id, newPassword)
      setPasswordTarget(null)
      setNewPassword('')
    } catch {
      setError('重置密码失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  const revokeSessions = async (user: AdminUserRow) => {
    if (!canWrite || busy || !window.confirm(`确定撤销用户“${user.username}”的全部会话吗？`)) return
    setBusy(true)
    try {
      await revokeUserSessions(user.id)
    } catch {
      setError('撤销会话失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <ConsoleLayout eyebrow="系统管理" title="用户管理" description="集中维护账户、权限角色与登录会话。密码仅能写入，不会在界面或接口响应中回显。">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
        <p className="text-sm text-muted-foreground">共 {meta.total} 名用户 · 可通过撤销会话即时收回访问权限</p>
        {canWrite ? <Button onClick={openCreate}>创建用户</Button> : null}
      </div>
      <PaginatedListControls
        pagination={pagination}
        empty={!pagination.loading && !error && users.length === 0}
        loadingLabel="正在加载用户…"
        errorLabel="加载用户失败，请稍后重试"
        emptyLabel="暂无用户"
        searchLabel="搜索用户"
      />

      {formMode ? (
        <section className="rounded-lg border border-primary/25 bg-accent/30 p-5 shadow-sm">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold">{formMode === 'create' ? '创建用户' : `编辑用户：${editingUser?.username}`}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{formMode === 'create' ? '初始密码只会提交一次，请安全传递给用户。' : '用户名不可修改；保存后角色权限将在下次请求时生效。'}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={closeForm}>取消</Button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium">
              用户名
              <input
                aria-label="用户名"
                className="h-10 rounded-md border bg-background px-3 font-mono text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                value={form.username}
                disabled={formMode === 'edit' || busy}
                onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              显示名称
              <input
                aria-label="显示名称"
                className="h-10 rounded-md border bg-background px-3 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                value={form.displayName}
                disabled={busy}
                onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))}
              />
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              角色
              <select
                aria-label="角色"
                className="h-10 rounded-md border bg-background px-3 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                value={form.role}
                disabled={busy}
                onChange={(event) => setForm((current) => ({ ...current, role: event.target.value as UserRole }))}
              >
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
            </label>
            {formMode === 'create' ? (
              <label className="grid gap-1.5 text-sm font-medium">
                初始密码
                <input
                  aria-label="初始密码"
                  type="password"
                  autoComplete="new-password"
                  className="h-10 rounded-md border bg-background px-3 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                  value={form.password}
                  disabled={busy}
                  onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                />
              </label>
            ) : null}
          </div>
          <div className="mt-5 flex justify-end">
            <Button
              disabled={busy || !form.username.trim() || (formMode === 'create' && form.password.length < 8)}
              onClick={() => void saveUser()}
            >
              {formMode === 'create' ? '确认创建' : '保存修改'}
            </Button>
          </div>
        </section>
      ) : null}

      {passwordTarget ? (
        <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-5 shadow-sm">
          <h2 className="font-semibold">重置密码：{passwordTarget.username}</h2>
          <p className="mt-1 text-sm text-muted-foreground">重置后将撤销该用户的所有登录会话，密码不会被保存或回显。</p>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="grid flex-1 gap-1.5 text-sm font-medium">
              新密码
              <input
                aria-label="新密码"
                type="password"
                autoComplete="new-password"
                className="h-10 rounded-md border bg-background px-3 text-sm outline-none ring-offset-background focus:ring-2 focus:ring-ring"
                value={newPassword}
                disabled={busy}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => { setPasswordTarget(null); setNewPassword('') }}>取消</Button>
              <Button variant="destructive" disabled={busy || newPassword.length < 8} onClick={() => void resetPassword()}>确认重置</Button>
            </div>
          </div>
        </section>
      ) : null}

      {error ? <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p> : null}
      <div className="space-y-3">
        {users.map((user) => (
          <article key={user.id} className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5 shadow-sm md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-semibold">{user.display_name || user.username}</h3>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${user.status === 'enabled' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}`}>{statusText(user.status)}</span>
              </div>
              {user.display_name && user.display_name !== user.username ? <p className="mt-1 font-mono text-xs text-muted-foreground">{user.username}</p> : null}
              <p className="mt-2 text-sm text-muted-foreground">{roleText(user.role)} · 创建于 {user.created_at ? new Date(user.created_at).toLocaleString('zh-CN') : '—'} · 最近登录 {user.last_login_at ? new Date(user.last_login_at).toLocaleString('zh-CN') : '从未登录'}</p>
            </div>
            {canWrite ? (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => openEdit(user)}>编辑</Button>
                <Button size="sm" variant="outline" onClick={() => void toggle(user)}>{user.status === 'enabled' ? '停用' : '启用'}</Button>
                <Button size="sm" variant="outline" onClick={() => { setPasswordTarget(user); setNewPassword('') }}>重置密码</Button>
                <Button size="sm" variant="destructive" onClick={() => void revokeSessions(user)}>撤销会话</Button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </ConsoleLayout>
  )
}
