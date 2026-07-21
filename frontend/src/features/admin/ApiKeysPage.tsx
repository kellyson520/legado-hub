import { useState } from 'react'
import { Copy, KeyRound, Trash2 } from 'lucide-react'
import { createApiKey, deleteApiKey, disableApiKey, listApiKeys, type ApiKeyRow } from '@/api/modules/admin'
import { useLanguage } from '@/app/providers/LanguageProvider'
import { useAuth } from '@/app/providers/AuthProvider'
import { PaginatedListControls } from '@/components/data/PaginatedListControls'
import { StatusBadge } from '@/components/data/StatusBadge'
import { StatusMessage } from '@/components/data/StatusMessage'
import { DetailPanel } from '@/components/detail/DetailPanel'
import { FormActions } from '@/components/form/FormActions'
import { FormField } from '@/components/form/FormField'
import { ConsolePageShell } from '@/components/layout/ConsolePageShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useServerPagination } from '@/hooks/useServerPagination'

const scopes = ['read.work', 'read.toc', 'read.chapter', 'jobs.submit', 'events.read', 'source.submit']

export function ApiKeysPage() {
  const { t } = useLanguage()
  const { hasPermission } = useAuth()
  const canWrite = hasPermission('api_keys.write')
  const pagination = useServerPagination<ApiKeyRow>({
    pageSize: 20,
    load: listApiKeys,
  })
  const { rows: keys } = pagination
  const [name, setName] = useState(''); const [permissions, setPermissions] = useState<string[]>(['read.work']); const [revealed, setRevealed] = useState(''); const [error, setError] = useState('')
  const load = () => { setError(''); pagination.reload() }
  const create = async () => { if (!name.trim()) return; try { const result = await createApiKey({ name: name.trim(), permissions }); setRevealed(result.data.raw_key || ''); setName(''); load() } catch { setError('创建 API Key 失败') } }
  const toggle = (scope: string) => setPermissions((current) => current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope])
  return <ConsolePageShell eyebrow="Access" title="API Key 分发" description="为外部客户端创建最小权限凭证。原始密钥仅在创建后显示一次。">
    {canWrite ? <section className="grid gap-4 border-b border-border pb-5 lg:grid-cols-[1fr_auto]"><div className="grid gap-3"><FormField label={t('API Key 名称')} htmlFor="api-key-name" help={t('请立即保存此密钥，它不会再次显示。')}><Input id="api-key-name" placeholder={t('例如：阅读客户端')} value={name} onChange={(e) => setName(e.target.value)} /></FormField><div className="flex flex-wrap gap-2">{scopes.map((scope) => <label key={scope} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"><input type="checkbox" checked={permissions.includes(scope)} onChange={() => toggle(scope)} />{scope}</label>)}</div></div><FormActions className="items-end"><Button onClick={() => void create()} disabled={!name.trim() || permissions.length === 0}><KeyRound className="mr-2 h-4 w-4" />{t('创建密钥')}</Button></FormActions></section> : null}
    {revealed ? <DetailPanel title={t('创建密钥')} description={t('请立即保存此密钥，它不会再次显示。')} className="border-amber-500/40 bg-amber-500/10"><div className="flex gap-2"><code className="min-w-0 flex-1 break-all rounded bg-background p-3 text-sm">{revealed}</code><Button aria-label={t('复制 API Key')} variant="outline" size="icon" onClick={() => void navigator.clipboard?.writeText(revealed)}><Copy className="h-4 w-4" /></Button></div><FormActions className="mt-3"><Button size="sm" variant="ghost" onClick={() => setRevealed('')}>{t('关闭')}</Button></FormActions></DetailPanel> : null}
    <PaginatedListControls
      pagination={pagination}
      empty={!pagination.loading && keys.length === 0}
      loadingLabel="正在加载 API Key…"
      errorLabel="无法加载 API Key"
      emptyLabel="暂无 API Key"
      searchLabel="搜索 API Key"
    />
    <StatusMessage tone="error" message={error} />
    <div className="space-y-3">{keys.map((key) => <article key={key.id} className="flex flex-wrap items-center justify-between gap-3 border border-border bg-card p-4"><div><p className="font-medium">{key.name}</p><p className="mt-1 text-xs text-muted-foreground">{key.permissions.join(' · ') || t('无权限')}</p></div><div className="flex items-center gap-2"><StatusBadge status={key.is_enabled ? 'enabled' : 'disabled'} />{canWrite && key.is_enabled ? <Button size="sm" variant="outline" onClick={() => void disableApiKey(key.id).then(load)}>{t('禁用')}</Button> : null}{canWrite ? <Button size="icon" variant="destructive" aria-label={`${t('删除')} ${key.name}`} onClick={() => void deleteApiKey(key.id).then(load)}><Trash2 className="h-4 w-4" /></Button> : null}</div></article>)}</div>
  </ConsolePageShell>
}
