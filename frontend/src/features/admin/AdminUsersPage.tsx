import { useEffect, useState } from 'react'
import { createUser, listUsers, setUserEnabled, type AdminUserRow } from '@/api/modules/admin'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { roleText, statusText } from '@/lib/i18n'

export function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const load = async () => { try { setUsers((await listUsers()).data); setError('') } catch { setError('加载用户失败，请稍后重试') } }
  useEffect(() => { void load() }, [])
  const add = async () => { await createUser({ username: `user-${Date.now()}`, display_name: '新用户', role: 'user', password: 'ChangeMe123!' }); await load(); setCreating(false) }
  const toggle = async (user: AdminUserRow) => { await setUserEnabled(user.id, user.status !== 'enabled'); await load() }
  return <ConsoleLayout eyebrow="系统管理" title="用户管理" description="创建、启用或停用系统用户。用户密码不会在界面或接口响应中回显。">
    <div className="mb-4 flex justify-end"><Button onClick={() => setCreating(true)}>创建用户</Button></div>
    {creating ? <div className="mb-4 rounded border p-4"><p className="mb-3">将创建一个普通用户（初始密码：ChangeMe123!）。</p><Button onClick={() => void add()}>确认创建</Button></div> : null}
    {error ? <p className="text-sm text-destructive">{error}</p> : null}
    {!error && users.length === 0 ? <p className="text-sm text-muted-foreground">暂无用户</p> : null}
    <div className="space-y-3">{users.map((user) => <article key={user.id} className="flex flex-wrap items-center justify-between gap-4 rounded-md border border-border bg-card p-5"><div><h3 className="text-lg font-semibold">{user.display_name || user.username}</h3><p className="text-sm text-muted-foreground">{user.username} · {roleText(user.role)} · {statusText(user.status)}</p></div><Button variant="outline" onClick={() => void toggle(user)}>{user.status === 'enabled' ? '停用' : '启用'}</Button></article>)}</div>
  </ConsoleLayout>
}
