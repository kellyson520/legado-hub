export interface SettingsTabDefinition {
  id: string
  label: string
}

export interface SettingsDomainDefinition {
  id: string
  label: string
  tabs: SettingsTabDefinition[]
}

export const SETTINGS_DOMAINS: SettingsDomainDefinition[] = [
  { id: 'general', label: 'General', tabs: [{ id: 'preferences', label: 'Preferences' }] },
  { id: 'security', label: 'Security and access', tabs: [{ id: 'access', label: 'Access' }] },
  { id: 'models', label: 'Models and providers', tabs: [{ id: 'providers', label: 'Providers' }] },
  {
    id: 'agents',
    label: 'Agents and automation',
    tabs: [
      { id: 'overview', label: 'Overview' },
      { id: 'roles', label: 'Roles and models' },
      { id: 'automation', label: 'Automation' },
      { id: 'governance', label: 'Evidence and governance' },
      { id: 'budgets', label: 'Budgets and queue' },
      { id: 'audit', label: 'Audit and tests' },
    ],
  },
  { id: 'sources', label: 'Sources and browser', tabs: [{ id: 'browser', label: 'Browser verification' }] },
  { id: 'storage', label: 'Storage and maintenance', tabs: [{ id: 'maintenance', label: 'Maintenance' }] },
  { id: 'runtime', label: 'Runtime and observability', tabs: [{ id: 'observability', label: 'Observability' }] },
]

export function findSettingsDomain(domainId: string | undefined) {
  return SETTINGS_DOMAINS.find((domain) => domain.id === domainId)
}

export function settingsPath(domainId: string, tabId: string) {
  return `/system/settings/${domainId}/${tabId}`
}
