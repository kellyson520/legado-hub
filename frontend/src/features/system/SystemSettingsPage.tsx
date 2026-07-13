import { FormEvent, useEffect, useState } from 'react'

import {
  getLLMSettings,
  listProviders,
  listQuotaPolicies,
  updateLLMSettings,
  type LLMSettings,
  type ProviderRow,
  type QuotaPolicyRow,
} from '@/api/modules/system'
import { ConsoleLayout } from '@/components/layout/ConsoleLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

function getProviderName(settings: LLMSettings | null) {
  return settings?.providerName ?? settings?.provider_name ?? 'local-llm'
}

function getBaseUrl(settings: LLMSettings | null) {
  return settings?.baseUrl ?? settings?.base_url ?? ''
}

function isApiKeyConfigured(settings: LLMSettings | null) {
  return Boolean(settings?.apiKeyConfigured ?? settings?.api_key_configured)
}

export function SystemSettingsPage() {
  const [providers, setProviders] = useState<ProviderRow[]>([])
  const [quotas, setQuotas] = useState<QuotaPolicyRow[]>([])
  const [llmSettings, setLLMSettings] = useState<LLMSettings | null>(null)
  const [providerName, setProviderName] = useState('local-llm')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('gpt-4.1-mini')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

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
    return () => {
      mounted = false
    }
  }, [])

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
      setMessage('LLM settings saved')
    } catch {
      setMessage('Failed to save LLM settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <ConsoleLayout
      eyebrow="System"
      title="Provider control room"
      description="统一展示 provider 健康、配额策略和 LLM API 配置，保证写源、AI、translation、novel 任务都有真实模型调用入口。"
    >
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
    </ConsoleLayout>
  )
}
