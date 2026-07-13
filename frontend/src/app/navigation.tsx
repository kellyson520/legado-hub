import type { LucideIcon } from 'lucide-react'
import { BookOpen, Bot, ClipboardCheck, ClipboardList, FileText, Gauge, HeartPulse, ListChecks, RadioTower, Settings, ShieldCheck, SlidersHorizontal, Users, Wrench } from 'lucide-react'

export interface NavigationItem { label: string; to: string; icon: LucideIcon; permission: string; adminOnly?: boolean }
export interface NavigationGroup { label: string; items: NavigationItem[] }
export const navigationGroups: NavigationGroup[] = [
  { label: '资源', items: [{ label: '书源', to: '/sources', icon: BookOpen, permission: 'book_sources.read' }, { label: '健康诊断', to: '/sources/health', icon: HeartPulse, permission: 'book_sources.read' }] },
  { label: '运营', items: [{ label: '规则引擎', to: '/engine', icon: Gauge, permission: 'engine.test' }, { label: 'AI 任务', to: '/ai/tasks', icon: Bot, permission: 'ai.run' }, { label: '翻译任务', to: '/translation/jobs', icon: FileText, permission: 'translation.run' }, { label: '小说任务', to: '/novel/tasks', icon: ClipboardList, permission: 'novel.manage' }] },
  { label: '操作', items: [{ label: '任务队列', to: '/operations/jobs', icon: ListChecks, permission: 'system.jobs.manage' }, { label: 'Agent 运行记录', to: '/operations/agent-runs', icon: Bot, permission: 'agent_runs.read' }, { label: '事件投递', to: '/operations/deliveries', icon: RadioTower, permission: 'system.jobs.manage' }, { label: '书源构建', to: '/operations/source-builds', icon: Wrench, permission: 'book_sources.read' }, { label: '审核队列', to: '/operations/review-queue', icon: ClipboardCheck, permission: 'agent_runs.read' }] },
  { label: '管理', items: [{ label: '用户管理', to: '/admin/users', icon: Users, permission: 'users.read', adminOnly: true }, { label: '审计日志', to: '/admin/audit', icon: ShieldCheck, permission: 'system.audit.read', adminOnly: true }, { label: '系统设置', to: '/system/settings', icon: Settings, permission: 'system.settings.manage', adminOnly: true }] },
]
export function findNavigationItem(pathname: string) { return navigationGroups.flatMap((group) => group.items).sort((a, b) => b.to.length - a.to.length).find((item) => pathname === item.to || pathname.startsWith(`${item.to}/`)) }
export const consoleMark = SlidersHorizontal
