import { useState } from 'react'
import { Copy, KeyRound, Trash2 } from 'lucide-react'
import { createApiKey, deleteApiKey, disableApiKey, listApiKeys, type ApiKeyRow } from '@/api/modules/admin'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { PaginationToolbar } from '@/components/data/PaginationToolbar'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useServerPagination } from '@/hooks/useServerPagination'

const scopes = ['read.work', 'read.toc', 'read.chapter', 'jobs.submit', 'events.read', 'source.submit']

export function ApiKeysPage() {
  const pagination = useServerPagination<ApiKeyRow>({
    pageSize: 20,
    load: ({ page, pageSize, search }) => listApiKeys({ page, page_size: pageSize, search }),
  })
  const { rows: keys, meta, loading, error: loadError } = pagination
  const [name, setName] = useState(''); const [permissions, setPermissions] = useState<string[]>(['read.work']); const [revealed, setRevealed] = useState(''); const [error, setError] = useState('')
  const load = () => { setError(''); pagination.reload() }
  const create = async () => { if (!name.trim()) return; try { const result = await createApiKey({ name: name.trim(), permissions }); setRevealed(result.data.raw_key || ''); setName(''); load() } catch { setError('创建 API Key 失败') } }
  const toggle = (scope: string) => setPermissions((current) => current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope])
  return <ConsoleLayout eyebrow="Access" title="API Key 分发" description="为外部客户端创建最小权限凭证。原始密钥仅在创建后显示一次。">
    <section className="grid gap-4 border-b border-border pb-5 lg:grid-cols-[1fr_auto]"><div className="grid gap-3"><Input aria-label="API Key 名称" placeholder="例如：阅读客户端" value={name} onChange={(e) => setName(e.target.value)} /><div className="flex flex-wrap gap-2">{scopes.map((scope) => <label key={scope} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"><input type="checkbox" checked={permissions.includes(scope)} onChange={() => toggle(scope)} />{scope}</label>)}</div></div><Button onClick={() => void create()} disabled={!name.trim() || permissions.length === 0}><KeyRound className="mr-2 h-4 w-4" />创建密钥</Button></section>
    {revealed ? <section className="border border-amber-500/40 bg-amber-500/10 p-4"><p className="text-sm font-medium">请立即保存此密钥，它不会再次显示。</p><div className="mt-3 flex gap-2"><code className="min-w-0 flex-1 break-all rounded bg-background p-3 text-sm">{revealed}</code><Button aria-label="复制 API Key" variant="outline" size="icon" onClick={() => void navigator.clipboard?.writeText(revealed)}><Copy className="h-4 w-4" /></Button></div><Button className="mt-3" size="sm" variant="ghost" onClick={() => setRevealed('')}>关闭</Button></section> : null}
    <PaginationToolbar
      page={meta.page}
      totalPages={meta.total_pages}
      total={meta.total}
      searchInput={pagination.searchInput}
      appliedSearch={pagination.appliedSearch}
      loading={loading}
      searchLabel="搜索 API Key"
      onSearchInput={pagination.setSearchInput}
      onSearch={() => pagination.submitSearch()}
      onClearSearch={pagination.clearSearch}
      onPageChange={pagination.goToPage}
    />
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    {loadError ? <Card className="flex items-center gap-3 p-4 text-sm text-destructive" role="alert"><span>无法加载 API Key</span><button type="button" className="underline" onClick={() => pagination.retry()}>重试</button></Card> : null}
    <div className="space-y-3">{keys.map((key) => <article key={key.id} className="flex flex-wrap items-center justify-between gap-3 border border-border bg-card p-4"><div><p className="font-medium">{key.name}</p><p className="mt-1 text-xs text-muted-foreground">{key.permissions.join(' · ') || '无权限'} · {key.is_enabled ? '启用' : '已禁用'}</p></div><div className="flex gap-2">{key.is_enabled ? <Button size="sm" variant="outline" onClick={() => void disableApiKey(key.id).then(load)}>禁用</Button> : null}<Button size="icon" variant="destructive" aria-label={`删除 ${key.name}`} onClick={() => void deleteApiKey(key.id).then(load)}><Trash2 className="h-4 w-4" /></Button></div></article>)}</div>
  </ConsoleLayout>
}
