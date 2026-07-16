import { FormEvent, useEffect, useState } from 'react'

import {
  getInteractiveBrowserSettings,
  getSourceBuildAgentSettings,
  getLLMSettings,
  listProviders,
  listQuotaPolicies,
  updateInteractiveBrowserSettings,
  updateSourceBuildAgentSettings,
  updateLLMSettings,
  type InteractiveBrowserSettings,
  type LLMSettings,
  type ProviderRow,
  type QuotaPolicyRow,
  type SourceBuildAgentSettings,
} from '@/api/modules/system'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ProviderRoutingSettings } from './ProviderRoutingSettings'

function getProviderName(settings: LLMSettings | null) {
  return settings?.providerName ?? settings?.provider_name ?? 'local-llm'
}

function getBaseUrl(settings: LLMSettings | null) {
  return settings?.baseUrl ?? settings?.base_url ?? ''
}

function isApiKeyConfigured(settings: LLMSettings | null) {
  return Boolean(settings?.apiKeyConfigured ?? settings?.api_key_configured)
}

function isSourceBuildAgentProviderConfigured(settings: SourceBuildAgentSettings | null) {
  return Boolean(settings?.providerConfigured ?? settings?.provider_configured)
}

export function ProviderSettingsContent() {
  const [providers, setProviders] = useState<ProviderRow[]>([])
  const [quotas, setQuotas] = useState<QuotaPolicyRow[]>([])
  const [llmSettings, setLLMSettings] = useState<LLMSettings | null>(null)
  const [sourceBuildAgentSettings, setSourceBuildAgentSettings] = useState<SourceBuildAgentSettings | null>(null)
  const [sourceBuildAgentLoaded, setSourceBuildAgentLoaded] = useState(false)
  const [interactiveBrowserSettings, setInteractiveBrowserSettings] = useState<InteractiveBrowserSettings | null>(null)
  const [interactiveBrowserSettingsLoaded, setInteractiveBrowserSettingsLoaded] = useState(false)
  const [providerName, setProviderName] = useState('local-llm')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('gpt-4.1-mini')
  const [saving, setSaving] = useState(false)
  const [savingSourceBuildAgent, setSavingSourceBuildAgent] = useState(false)
  const [savingInteractiveBrowser, setSavingInteractiveBrowser] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [sourceBuildAgentMessage, setSourceBuildAgentMessage] = useState<string | null>(null)
  const [sourceBuildAgentError, setSourceBuildAgentError] = useState<string | null>(null)
  const [interactiveBrowserMessage, setInteractiveBrowserMessage] = useState<string | null>(null)
  const [interactiveBrowserLoadError, setInteractiveBrowserLoadError] = useState<string | null>(null)
  const [interactiveBrowserSaveError, setInteractiveBrowserSaveError] = useState<string | null>(null)
  const [settingsRefreshVersion, setSettingsRefreshVersion] = useState(0)
  const [interactiveBrowserRefreshVersion, setInteractiveBrowserRefreshVersion] = useState(0)
  const interactiveBrowserSettingsEditable = interactiveBrowserSettingsLoaded && interactiveBrowserSettings !== null

  async function refreshSourceBuildAgentSettings() {
    try {
      const response = await getSourceBuildAgentSettings()
      setSourceBuildAgentSettings(response.data)
      setSourceBuildAgentError(null)
    } catch {
      setSourceBuildAgentError('Failed to load source build Agent settings')
    } finally {
      setSourceBuildAgentLoaded(true)
    }
  }

  useEffect(() => {
    let mounted = true

    async function load() {
      const [providersResponse, quotasResponse, llmResponse] = await Promise.all([
        listProviders(),
        listQuotaPolicies(),
        getLLMSettings(),
      ])
      if (!mounted) return
      setProviders(providersResponse.data)
      setQuotas(quotasResponse.data)
      setLLMSettings(llmResponse.data)
      setProviderName(getProviderName(llmResponse.data))
      setBaseUrl(getBaseUrl(llmResponse.data))
      setModel(llmResponse.data.model || 'gpt-4.1-mini')
    }

    void load()
    void refreshSourceBuildAgentSettings()
    return () => {
      mounted = false
    }
  }, [settingsRefreshVersion])

  useEffect(() => {
    let active = true
    setInteractiveBrowserSettingsLoaded(false)

    async function loadInteractiveBrowserSettings() {
      try {
        const response = await getInteractiveBrowserSettings()
        if (!active) return
        setInteractiveBrowserSettings(response.data)
        setInteractiveBrowserLoadError(null)
      } catch {
        if (!active) return
        setInteractiveBrowserLoadError('Failed to load interactive browser settings')
      } finally {
        if (active) {
          setInteractiveBrowserSettingsLoaded(true)
        }
      }
    }

    void loadInteractiveBrowserSettings()
    return () => {
      active = false
    }
  }, [interactiveBrowserRefreshVersion])

  async function handleSaveLLM(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      const response = await updateLLMSettings({
        providerName,
        baseUrl,
        apiKey,
        model,
      })
      setLLMSettings(response.data)
      setProviderName(getProviderName(response.data))
      setBaseUrl(getBaseUrl(response.data))
      setModel(response.data.model || model)
      setApiKey('')
      await refreshSourceBuildAgentSettings()
      setSettingsRefreshVersion((current) => current + 1)
      setMessage('LLM settings saved')
    } catch {
      setMessage('Failed to save LLM settings')
    } finally {
      setSaving(false)
    }
  }

  async function handleSourceBuildAgentToggle() {
    const enabled = !Boolean(sourceBuildAgentSettings?.enabled)
    setSavingSourceBuildAgent(true)
    setSourceBuildAgentMessage(null)
    setSourceBuildAgentError(null)
    try {
      const response = await updateSourceBuildAgentSettings({ enabled })
      setSourceBuildAgentSettings(response.data)
      setSourceBuildAgentMessage('Source build Agent settings saved')
    } catch {
      setSourceBuildAgentError('Failed to save source build Agent settings')
    } finally {
      setSavingSourceBuildAgent(false)
    }
  }

  async function handleSaveInteractiveBrowserSettings() {
    if (!interactiveBrowserSettings) return

    setSavingInteractiveBrowser(true)
    setInteractiveBrowserMessage(null)
    setInteractiveBrowserSaveError(null)
    try {
      const response = await updateInteractiveBrowserSettings({
        enabled: interactiveBrowserSettings.enabled,
        automaticEnabled: interactiveBrowserSettings.automaticEnabled,
        maxSessions: Math.min(3, Math.max(1, Math.trunc(interactiveBrowserSettings.maxSessions))),
        sessionTimeoutSeconds: Math.min(600, Math.max(60, Math.trunc(interactiveBrowserSettings.sessionTimeoutSeconds))),
      })
      setInteractiveBrowserSettings(response.data)
      setInteractiveBrowserMessage('Interactive browser settings saved')
    } catch {
      setInteractiveBrowserSaveError('Failed to save interactive browser settings')
    } finally {
      setSavingInteractiveBrowser(false)
    }
  }

  function handleRetryInteractiveBrowserSettings() {
    setInteractiveBrowserLoadError(null)
    setInteractiveBrowserSettingsLoaded(false)
    setInteractiveBrowserRefreshVersion((current) => current + 1)
  }

  async function handleProviderSaved() {
    await refreshSourceBuildAgentSettings()
    setSettingsRefreshVersion((current) => current + 1)
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.1fr)]">
        <section className="rounded-md border border-border bg-card p-5 shadow-sm">
          <h3 className="text-lg font-semibold text-foreground">LLM API configuration</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            配置 OpenAI-compatible endpoint 后，后端 ProviderRegistry 会把该 provider 注册到 default / ai /
            translation / novel 分组。
          </p>
          <form className="mt-5 space-y-4" onSubmit={handleSaveLLM}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="llm-provider-name">
                Provider name
              </label>
              <Input
                id="llm-provider-name"
                value={providerName}
                onChange={(event) => setProviderName(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="llm-base-url">
                Base URL
              </label>
              <Input
                id="llm-base-url"
                placeholder="https://api.openai.com/v1"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="llm-api-key">
                API Key
              </label>
              <Input
                id="llm-api-key"
                type="password"
                placeholder={isApiKeyConfigured(llmSettings) ? '已配置，留空则不变' : 'sk-...'}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground" htmlFor="llm-model">
                Model
              </label>
              <Input
                id="llm-model"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                required
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={saving}>
                Save LLM settings
              </Button>
              <span className="text-xs text-muted-foreground">
                API key: {isApiKeyConfigured(llmSettings) ? 'configured' : 'not configured'}
              </span>
              {message ? (
                <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">{message}</span>
              ) : null}
            </div>
          </form>

          <div className="mt-5 border-t border-border pt-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">Agent-enhanced source build</h4>
                <p className="text-sm text-muted-foreground">
                  仅当确定性书源构建失败后才会调用 Agent / Agent runs only after deterministic source build fails.
                </p>
                <p
                  className={
                    isSourceBuildAgentProviderConfigured(sourceBuildAgentSettings)
                      ? 'text-xs font-medium text-emerald-600 dark:text-emerald-400'
                      : 'text-xs font-medium text-amber-600 dark:text-amber-400'
                  }
                >
                  {isSourceBuildAgentProviderConfigured(sourceBuildAgentSettings)
                    ? 'LLM provider 已配置 / Provider configured'
                    : 'LLM provider 未配置 / Provider not configured'}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                role="switch"
                aria-checked={Boolean(sourceBuildAgentSettings?.enabled)}
                aria-label="Agent-enhanced source build"
                disabled={saving || savingSourceBuildAgent || !sourceBuildAgentLoaded}
                onClick={handleSourceBuildAgentToggle}
              >
                {!sourceBuildAgentLoaded ? 'Loading…' : savingSourceBuildAgent ? 'Saving…' : sourceBuildAgentSettings?.enabled ? 'Enabled' : 'Disabled'}
              </Button>
            </div>
            {sourceBuildAgentMessage ? (
              <p role="status" className="mt-3 text-sm font-medium text-emerald-600 dark:text-emerald-400">
                {sourceBuildAgentMessage}
              </p>
            ) : null}
            {sourceBuildAgentError ? (
              <p role="alert" className="mt-3 text-sm font-medium text-destructive">
                {sourceBuildAgentError}
              </p>
            ) : null}
          </div>

          <div className="mt-5 border-t border-border pt-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-foreground">Interactive browser verification</h4>
                <p className="text-sm text-muted-foreground">
                  在普通浏览器访问仍需人工验证时，提供受限的交互式验证会话。
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                role="switch"
                aria-checked={Boolean(interactiveBrowserSettings?.enabled)}
                aria-label="Interactive browser verification"
                disabled={savingInteractiveBrowser || !interactiveBrowserSettingsEditable}
                onClick={() =>
                  setInteractiveBrowserSettings((current) =>
                    current ? { ...current, enabled: !current.enabled } : current,
                  )
                }
              >
                {!interactiveBrowserSettingsLoaded
                  ? 'Loading…'
                  : interactiveBrowserSettings?.enabled
                    ? 'Enabled'
                    : 'Disabled'}
              </Button>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/40 p-3">
                <span className="text-sm font-medium text-foreground">Automatically attempt verification</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  role="switch"
                  aria-checked={Boolean(interactiveBrowserSettings?.automaticEnabled)}
                  aria-label="Automatically attempt verification"
                  disabled={
                    savingInteractiveBrowser ||
                    !interactiveBrowserSettingsEditable ||
                    !interactiveBrowserSettings?.enabled
                  }
                  onClick={() =>
                    setInteractiveBrowserSettings((current) =>
                      current ? { ...current, automaticEnabled: !current.automaticEnabled } : current,
                    )
                  }
                >
                  {interactiveBrowserSettings?.automaticEnabled ? 'Enabled' : 'Disabled'}
                </Button>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground" htmlFor="interactive-browser-max-sessions">
                  Maximum sessions
                </label>
                <Input
                  id="interactive-browser-max-sessions"
                  type="number"
                  min={1}
                  max={3}
                  step={1}
                  value={interactiveBrowserSettings?.maxSessions ?? ''}
                  disabled={savingInteractiveBrowser || !interactiveBrowserSettingsEditable}
                  onChange={(event) =>
                    setInteractiveBrowserSettings((current) =>
                      current ? { ...current, maxSessions: Number(event.target.value) } : current,
                    )
                  }
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground" htmlFor="interactive-browser-session-timeout">
                  Session timeout (seconds)
                </label>
                <Input
                  id="interactive-browser-session-timeout"
                  type="number"
                  min={60}
                  max={600}
                  step={1}
                  value={interactiveBrowserSettings?.sessionTimeoutSeconds ?? ''}
                  disabled={savingInteractiveBrowser || !interactiveBrowserSettingsEditable}
                  onChange={(event) =>
                    setInteractiveBrowserSettings((current) =>
                      current ? { ...current, sessionTimeoutSeconds: Number(event.target.value) } : current,
                    )
                  }
                />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                type="button"
                disabled={savingInteractiveBrowser || !interactiveBrowserSettingsEditable}
                onClick={handleSaveInteractiveBrowserSettings}
              >
                {savingInteractiveBrowser ? 'Saving…' : 'Save interactive browser settings'}
              </Button>
              {interactiveBrowserMessage ? (
                <p role="status" className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                  {interactiveBrowserMessage}
                </p>
              ) : null}
              {interactiveBrowserSaveError ? (
                <p role="alert" className="text-sm font-medium text-destructive">
                  {interactiveBrowserSaveError}
                </p>
              ) : null}
              {interactiveBrowserLoadError ? (
                <p role="alert" className="text-sm font-medium text-destructive">
                  {interactiveBrowserLoadError}
                </p>
              ) : null}
              {interactiveBrowserLoadError && interactiveBrowserSettings === null ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={savingInteractiveBrowser}
                  onClick={handleRetryInteractiveBrowserSettings}
                >
                  Retry interactive browser settings
                </Button>
              ) : null}
            </div>
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-md border border-border bg-card p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-foreground">Provider health</h3>
            <div className="mt-4 space-y-3">
              {providers.map((provider) => (
                <div key={provider.id} className="rounded-md border border-border bg-muted/40 p-4 text-sm text-foreground">
                  {provider.name} · {provider.status}
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-md border border-border bg-card p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-foreground">Quota policies</h3>
            <div className="mt-4 space-y-3">
              {quotas.map((quota) => (
                <div key={quota.id} className="rounded-md border border-border bg-muted/40 p-4 text-sm text-foreground">
                  {quota.scope} · ${quota.dailyCostLimit}/day
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
      <ProviderRoutingSettings onProviderSaved={handleProviderSaved} />
    </div>
  )
}

export function SystemSettingsPage() {
  return (
    <ConsoleLayout
      eyebrow="System"
      title="Provider control room"
      description="统一展示 provider 健康、配额策略和 LLM API 配置，保证写源、AI、translation、novel 任务都有真实模型调用入口。"
    >
      <ProviderSettingsContent />
    </ConsoleLayout>
  )
}
