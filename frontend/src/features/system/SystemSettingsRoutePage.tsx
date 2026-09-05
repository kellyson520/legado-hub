import { useParams } from 'react-router-dom'

import { AgentAuditSettings } from './AgentAuditSettings'
import { AgentAutomationSettings } from './AgentAutomationSettings'
import { AgentBudgetSettings } from './AgentBudgetSettings'
import { AgentGovernanceSettings } from './AgentGovernanceSettings'
import { AgentOverviewSettings } from './AgentOverviewSettings'
import { AgentRoleSettings } from './AgentRoleSettings'
import { ProviderSettingsContent } from './SystemSettingsPage'
import { SettingsPlaceholder } from './SettingsPlaceholder'
import { SystemSettingsLayout } from './SystemSettingsLayout'
import { findSettingsDomain, SETTINGS_DOMAINS } from './settingsRegistry'

function sectionContent(domain: string, tab: string) {
  if (domain === 'models' && tab === 'providers') return <ProviderSettingsContent />
  if (domain !== 'agents') return <SettingsPlaceholder domain={domain} tab={tab} />
  if (tab === 'overview') return <AgentOverviewSettings />
  if (tab === 'roles') return <AgentRoleSettings />
  if (tab === 'automation') return <AgentAutomationSettings />
  if (tab === 'governance') return <AgentGovernanceSettings />
  if (tab === 'budgets') return <AgentBudgetSettings />
  if (tab === 'audit') return <AgentAuditSettings />
  return <SettingsPlaceholder domain={domain} tab={tab} />
}

export function SystemSettingsRoutePage() {
  const { domain: requestedDomain, tab: requestedTab } = useParams()
  const domain = findSettingsDomain(requestedDomain) ?? SETTINGS_DOMAINS[0]
  const tab = domain.tabs.find((item) => item.id === requestedTab) ?? domain.tabs[0]
  return <SystemSettingsLayout>{sectionContent(domain.id, tab.id)}</SystemSettingsLayout>
}
