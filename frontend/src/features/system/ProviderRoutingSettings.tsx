import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { ArrowDown, ArrowUp, Pencil, Plus, RefreshCw } from 'lucide-react'

import {
  createProvider,
  discoverProviderModels,
  getProviderRoute,
  listProviders,
  updateProvider,
  updateProviderRoute,
  type ProviderConfigurationInput,
  type ProviderRouteEntry,
  type ProviderRow,
} from '@/api/modules/system'
import { StatusMessage } from '@/components/data/StatusMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

const ROUTE_GROUPS = [
  { id: 'default', label: 'General' },
  { id: 'ai', label: 'AI analysis' },
  { id: 'source_build', label: 'Source build Agent' },
  { id: 'translation', label: 'Translation' },
  { id: 'novel', label: 'Novel analysis' },
  { id: 'novel_extract', label: 'Novel extractor' },
  { id: 'novel_verify', label: 'Novel verifier' },
  { id: 'novel_adjudicate', label: 'Novel adjudicator' },
  { id: 'novel_audit', label: 'Novel auditor' },
] as const

type ProviderForm = ProviderConfigurationInput & { id: string | null; apiKeyMasked: string }
type RouteDraft = { providerAccountId: string; model: string }

const emptyProviderForm = (): ProviderForm => ({
  id: null,
  name: '',
  baseUrl: '',
  apiKey: '',
  defaultModel: '',
  enabled: true,
  apiKeyMasked: '',
})

function getProviderBaseUrl(provider: ProviderRow) {
  return provider.baseUrl ?? provider.base_url ?? ''
}

function getProviderDefaultModel(provider: ProviderRow) {
  return provider.defaultModel ?? provider.default_model ?? ''
}

function isApiKeyConfigured(provider: ProviderRow) {
  return Boolean(provider.apiKeyConfigured ?? provider.api_key_configured)
}

function getApiKeyMasked(provider: ProviderRow) {
  return provider.apiKeyMasked ?? provider.api_key_masked ?? ''
}

function getRouteProviderId(entry: ProviderRouteEntry) {
  return entry.providerAccountId ?? entry.provider_account_id ?? ''
}

function getRouteProviderName(entry: ProviderRouteEntry, providers: ProviderRow[]) {
  return entry.providerName ?? entry.provider_name ?? providers.find((provider) => provider.id === getRouteProviderId(entry))?.name ?? 'Unknown provider'
}

function toForm(provider: ProviderRow): ProviderForm {
  return {
    id: provider.id,
    name: provider.name,
    baseUrl: getProviderBaseUrl(provider),
    apiKey: '',
    defaultModel: getProviderDefaultModel(provider),
    enabled: provider.enabled ?? provider.status !== 'disabled',
    apiKeyMasked: getApiKeyMasked(provider),
  }
}

function normalizeRouteEntries(entries: ProviderRouteEntry[]) {
  return entries.map((entry) => ({
    ...entry,
    providerAccountId: getRouteProviderId(entry),
    enabled: entry.enabled !== false,
  }))
}

function getRequestErrorMessage(error: unknown, fallback: string) {
  if (!isAxiosError(error)) return fallback
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

export function ProviderRoutingSettings({ onProviderSaved }: { onProviderSaved: () => Promise<void> | void }) {
  const [providers, setProviders] = useState<ProviderRow[]>([])
  const [routes, setRoutes] = useState<Record<string, ProviderRouteEntry[]>>({})
  const [routeAvailability, setRouteAvailability] = useState<Record<string, boolean>>({})
  const [drafts, setDrafts] = useState<Record<string, RouteDraft>>({})
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, string[]>>({})
  const [form, setForm] = useState<ProviderForm>(emptyProviderForm)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savingRoute, setSavingRoute] = useState<string | null>(null)
  const [loadingModels, setLoadingModels] = useState<string | null>(null)
  const refreshVersion = useRef(0)

  const refresh = useCallback(async () => {
    const requestVersion = ++refreshVersion.current
    try {
      const providerResponse = await listProviders()
      if (requestVersion !== refreshVersion.current) return
      setProviders(providerResponse.data.filter((provider) => !provider.id.startsWith('runtime:')))
    } catch {
      if (requestVersion === refreshVersion.current) setError('Failed to refresh Provider configuration')
      return
    }

    const routeResults = await Promise.allSettled(
      ROUTE_GROUPS.map((group) => getProviderRoute(group.id)),
    )
    if (requestVersion !== refreshVersion.current) return

    const nextRoutes: Record<string, ProviderRouteEntry[]> = {}
    const nextRouteAvailability: Record<string, boolean> = {}
    routeResults.forEach((result, index) => {
      const group = ROUTE_GROUPS[index]
      if (result.status === 'fulfilled') {
        nextRoutes[result.value.data.group] = normalizeRouteEntries(result.value.data.entries)
        nextRouteAvailability[group.id] = true
      } else {
        nextRouteAvailability[group.id] = false
      }
    })
    setRoutes(nextRoutes)
    setRouteAvailability(nextRouteAvailability)
    if (routeResults.some((result) => result.status === 'rejected')) {
      setError('Provider routes are temporarily unavailable; channel editing and model discovery remain available.')
    } else {
      setError(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleSaveProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setMessage(null)
    setError(null)
    const payload: ProviderConfigurationInput = {
      name: form.name.trim(),
      baseUrl: form.baseUrl.trim(),
      apiKey: form.apiKey,
      defaultModel: form.defaultModel.trim(),
      enabled: form.enabled,
    }
    try {
      const response = form.id ? await updateProvider(form.id, payload) : await createProvider(payload)
      const saved = response.data
      setProviders((current) => {
        const others = current.filter((provider) => provider.id !== saved.id)
        return [...others, saved]
      })
      setForm(toForm(saved))
      setMessage('Provider channel saved')
      await Promise.all([refresh(), Promise.resolve(onProviderSaved())])
    } catch {
      setError('Failed to save Provider channel')
    } finally {
      setSaving(false)
    }
  }

  async function handleLoadModels(provider: ProviderRow) {
    setLoadingModels(provider.id)
    setError(null)
    try {
      const response = await discoverProviderModels(provider.id)
      setModelsByProvider((current) => ({ ...current, [provider.id]: response.data }))
      setForm(toForm(provider))
      setMessage(`Models loaded for ${provider.name}`)
    } catch (error) {
      setError(getRequestErrorMessage(error, `Failed to load models for ${provider.name}`))
    } finally {
      setLoadingModels(null)
    }
  }

  async function saveRoute(group: string, entries: ProviderRouteEntry[]) {
    setSavingRoute(group)
    setError(null)
    try {
      const response = await updateProviderRoute(group, {
        entries: normalizeRouteEntries(entries).map((entry) => ({
          providerAccountId: getRouteProviderId(entry),
          model: entry.model,
          enabled: entry.enabled !== false,
        })),
      })
      setRoutes((current) => ({ ...current, [group]: normalizeRouteEntries(response.data.entries) }))
      setMessage('Functional route saved')
    } catch {
      setError('Failed to save functional route')
    } finally {
      setSavingRoute(null)
    }
  }

  function updateDraft(group: string, patch: Partial<RouteDraft>) {
    setDrafts((current) => ({
      ...current,
      [group]: {
        providerAccountId: current[group]?.providerAccountId ?? '',
        model: current[group]?.model ?? '',
        ...patch,
      },
    }))
  }

  function addRouteEntry(group: string) {
    const draft = drafts[group]
    if (!draft?.providerAccountId || !draft.model.trim()) return
    const entries = routes[group] ?? []
    void saveRoute(group, [
      ...entries,
      { providerAccountId: draft.providerAccountId, model: draft.model.trim(), enabled: true },
    ])
    updateDraft(group, { model: '' })
  }

  function moveRouteEntry(group: string, index: number, direction: -1 | 1) {
    const entries = [...(routes[group] ?? [])]
    const nextIndex = index + direction
    if (nextIndex < 0 || nextIndex >= entries.length) return
    ;[entries[index], entries[nextIndex]] = [entries[nextIndex], entries[index]]
    void saveRoute(group, entries)
  }

  function removeRouteEntry(group: string, index: number) {
    const entries = (routes[group] ?? []).filter((_, entryIndex) => entryIndex !== index)
    if (!entries.length) {
      setError('Each functional route needs at least one fallback')
      return
    }
    void saveRoute(group, entries)
  }

  const selectedModels = form.id ? modelsByProvider[form.id] ?? [] : []

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.1fr)]">
      <section className="border border-border bg-card p-5 shadow-sm" aria-labelledby="provider-channels-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 id="provider-channels-heading" className="text-lg font-semibold text-foreground">Provider channels</h3>
            <p className="mt-1 text-sm text-muted-foreground">管理接口、密钥和模型。密钥只显示安全掩码。</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => setForm(emptyProviderForm())}>
            <Plus className="mr-2 h-4 w-4" />
            Add channel
          </Button>
        </div>

        <form className="mt-5 grid gap-4" onSubmit={handleSaveProvider}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium text-foreground" htmlFor="provider-channel-name">
              Channel name
              <Input id="provider-channel-name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required />
            </label>
            <label className="grid gap-2 text-sm font-medium text-foreground" htmlFor="provider-channel-model">
              Channel default model
              <Input id="provider-channel-model" list="provider-model-options" placeholder="Save, then use Models to discover" value={form.defaultModel} onChange={(event) => setForm((current) => ({ ...current, defaultModel: event.target.value }))} />
            </label>
          </div>
          <label className="grid gap-2 text-sm font-medium text-foreground" htmlFor="provider-channel-base-url">
            Channel Base URL
            <Input id="provider-channel-base-url" value={form.baseUrl} onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))} required />
          </label>
          <label className="grid gap-2 text-sm font-medium text-foreground" htmlFor="provider-channel-api-key">
            Channel API Key
            <Input id="provider-channel-api-key" type="password" placeholder={form.apiKeyMasked ? '已配置，留空则不变' : 'sk-...'} value={form.apiKey} onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))} />
          </label>
          <label className="flex items-center gap-2 text-sm font-medium text-foreground" htmlFor="provider-channel-enabled">
            <input id="provider-channel-enabled" type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} />
            Channel enabled
          </label>
          <datalist id="provider-model-options">
            {selectedModels.map((model) => <option key={model} value={model}>{model}</option>)}
          </datalist>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save channel'}</Button>
            <StatusMessage tone="success" message={message} as="span" className="font-medium" />
          </div>
        </form>

        <div className="mt-6 border-t border-border pt-4">
          <div className="grid divide-y divide-border border-y border-border">
            {providers.map((provider) => (
              <div key={provider.id} className="grid gap-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{provider.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{getProviderBaseUrl(provider)} · {getProviderDefaultModel(provider) || 'No default model'}</p>
                  <p className="mt-1 text-xs text-muted-foreground">API key: {isApiKeyConfigured(provider) ? `configured${getApiKeyMasked(provider) ? ` (${getApiKeyMasked(provider)})` : ''}` : 'not configured'}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" size="sm" aria-label={`Get models for ${provider.name}`} onClick={() => void handleLoadModels(provider)} disabled={loadingModels === provider.id || !isApiKeyConfigured(provider)}>
                    <RefreshCw className="h-4 w-4" />
                    <span className="ml-2">{loadingModels === provider.id ? 'Loading…' : 'Models'}</span>
                  </Button>
                  <Button type="button" variant="outline" size="sm" aria-label={`Edit ${provider.name}`} title={`Edit ${provider.name}`} onClick={() => setForm(toForm(provider))}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
        <StatusMessage tone="error" message={error} className="mt-3 font-medium" />
      </section>

      <section className="border border-border bg-card p-5 shadow-sm" aria-labelledby="functional-routes-heading">
        <div>
          <h3 id="functional-routes-heading" className="text-lg font-semibold text-foreground">Functional routes</h3>
          <p className="mt-1 text-sm text-muted-foreground">每项按顺序尝试渠道与模型，失败时切换到下一项。</p>
        </div>
        <div className="mt-5 grid gap-5">
          {ROUTE_GROUPS.map((group) => {
            const entries = routes[group.id] ?? []
            const draft = drafts[group.id] ?? { providerAccountId: '', model: '' }
            const routeAvailable = routeAvailability[group.id] === true
            return (
              <div key={group.id} className="border-t border-border pt-4 first:border-t-0 first:pt-0">
                <h4 className="text-sm font-semibold text-foreground">{group.label}</h4>
                <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                  <select aria-label={`Provider for ${group.label}`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={draft.providerAccountId} disabled={!routeAvailable} onChange={(event) => updateDraft(group.id, { providerAccountId: event.target.value })}>
                    <option value="">Select provider</option>
                    {providers.filter((provider) => provider.enabled !== false && isApiKeyConfigured(provider)).map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
                  </select>
                  <Input aria-label={`Model for ${group.label}`} placeholder="Model" value={draft.model} disabled={!routeAvailable} onChange={(event) => updateDraft(group.id, { model: event.target.value })} />
                  <Button type="button" variant="outline" size="sm" aria-label={`Add fallback for ${group.label}`} disabled={!routeAvailable || savingRoute === group.id || !draft.providerAccountId || !draft.model.trim()} onClick={() => addRouteEntry(group.id)}>
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                {!routeAvailable ? <p className="mt-2 text-xs text-muted-foreground">Route configuration is unavailable until the backend is updated.</p> : null}
                <div className="mt-3 grid gap-2">
                  {entries.map((entry, index) => {
                    const providerName = getRouteProviderName(entry, providers)
                    return (
                      <div key={`${getRouteProviderId(entry)}-${entry.model}-${index}`} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border border-border bg-muted/30 px-3 py-2 text-sm">
                        <span className="truncate text-foreground">{index + 1}. {providerName} · {entry.model}</span>
                        <div className="flex gap-1">
                          <Button type="button" variant="ghost" size="icon" aria-label={`Move ${providerName} up`} disabled={!routeAvailable || index === 0 || savingRoute === group.id} onClick={() => moveRouteEntry(group.id, index, -1)}><ArrowUp className="h-4 w-4" /></Button>
                          <Button type="button" variant="ghost" size="icon" aria-label={`Move ${providerName} down`} disabled={!routeAvailable || index === entries.length - 1 || savingRoute === group.id} onClick={() => moveRouteEntry(group.id, index, 1)}><ArrowDown className="h-4 w-4" /></Button>
                          <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${providerName}`} disabled={!routeAvailable || entries.length === 1 || savingRoute === group.id} onClick={() => removeRouteEntry(group.id, index)}>Remove</Button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
