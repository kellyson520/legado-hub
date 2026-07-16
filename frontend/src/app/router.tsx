import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth } from '@/app/router/RequireAuth'
import { RequirePermission } from '@/app/router/RequirePermission'

const AdminAuditPage = lazy(() => import('@/features/admin/AdminAuditPage').then(({ AdminAuditPage }) => ({ default: AdminAuditPage })))
const AdminUsersPage = lazy(() => import('@/features/admin/AdminUsersPage').then(({ AdminUsersPage }) => ({ default: AdminUsersPage })))
const ApiKeysPage = lazy(() => import('@/features/admin/ApiKeysPage').then(({ ApiKeysPage }) => ({ default: ApiKeysPage })))
const AITasksPage = lazy(() => import('@/features/ai/AITasksPage').then(({ AITasksPage }) => ({ default: AITasksPage })))
const AIWorkspacePage = lazy(() => import('@/features/ai/AIWorkspacePage').then(({ AIWorkspacePage }) => ({ default: AIWorkspacePage })))
const EngineRunsPage = lazy(() => import('@/features/engine/EngineRunsPage').then(({ EngineRunsPage }) => ({ default: EngineRunsPage })))
const LoginPage = lazy(() => import('@/features/auth/LoginPage').then(({ LoginPage }) => ({ default: LoginPage })))
const NovelTasksPage = lazy(() => import('@/features/novel/NovelTasksPage').then(({ NovelTasksPage }) => ({ default: NovelTasksPage })))
const WorkAnalysisPage = lazy(() => import('@/features/novel-analysis/WorkAnalysisPage').then(({ WorkAnalysisPage }) => ({ default: WorkAnalysisPage })))
const AgentRunsPage = lazy(() => import('@/features/operations/AgentRunsPage').then(({ AgentRunsPage }) => ({ default: AgentRunsPage })))
const EventDeliveriesPage = lazy(() => import('@/features/operations/EventDeliveriesPage').then(({ EventDeliveriesPage }) => ({ default: EventDeliveriesPage })))
const JobsPage = lazy(() => import('@/features/operations/JobsPage').then(({ JobsPage }) => ({ default: JobsPage })))
const ReviewQueuePage = lazy(() => import('@/features/operations/ReviewQueuePage').then(({ ReviewQueuePage }) => ({ default: ReviewQueuePage })))
const SourceBuildsPage = lazy(() => import('@/features/operations/SourceBuildsPage').then(({ SourceBuildsPage }) => ({ default: SourceBuildsPage })))
const SourceHealthPage = lazy(() => import('@/features/sources/SourceHealthPage').then(({ SourceHealthPage }) => ({ default: SourceHealthPage })))
const SourceHealthDetailPage = lazy(() => import('@/features/sources/SourceHealthDetailPage').then(({ SourceHealthDetailPage }) => ({ default: SourceHealthDetailPage })))
const SourceListPage = lazy(() => import('@/features/sources/SourceListPage').then(({ SourceListPage }) => ({ default: SourceListPage })))
const SourceRuleEditorPage = lazy(() => import('@/features/sources/SourceRuleEditorPage').then(({ SourceRuleEditorPage }) => ({ default: SourceRuleEditorPage })))
const SystemSettingsRoutePage = lazy(() => import('@/features/system/SystemSettingsRoutePage').then(({ SystemSettingsRoutePage }) => ({ default: SystemSettingsRoutePage })))
const TranslationJobsPage = lazy(() => import('@/features/translation/TranslationJobsPage').then(({ TranslationJobsPage }) => ({ default: TranslationJobsPage })))

export const appRoutes = [
  { path: '/login', element: <LoginPage /> },
  { path: '/sources', element: <SourceListPage /> },
  { path: '/sources/health', element: <SourceHealthPage /> },
  { path: '/sources/health/:sourceId', element: <SourceHealthDetailPage /> },
  { path: '/sources/rules/:sourceVersionId', element: <SourceRuleEditorPage /> },
  { path: '/engine', element: <EngineRunsPage /> },
  { path: '/admin/users', element: <AdminUsersPage /> },
  { path: '/admin/audit', element: <AdminAuditPage /> },
  { path: '/admin/api-keys', element: <ApiKeysPage /> },
  { path: '/ai/tasks', element: <AITasksPage /> },
  { path: '/ai/workspace', element: <AIWorkspacePage /> },
  { path: '/translation/jobs', element: <TranslationJobsPage /> },
  { path: '/novel/tasks', element: <NovelTasksPage /> },
  { path: '/novel-analysis/:workId', element: <WorkAnalysisPage /> },
  { path: '/operations/jobs', element: <JobsPage /> },
  { path: '/operations/agent-runs', element: <AgentRunsPage /> },
  { path: '/operations/deliveries', element: <EventDeliveriesPage /> },
  { path: '/operations/source-builds', element: <SourceBuildsPage /> },
  { path: '/operations/review-queue', element: <ReviewQueuePage /> },
  { path: '/system/settings', element: <Navigate to="/system/settings/models/providers" replace /> },
  { path: '/system/settings/:domain/:tab', element: <SystemSettingsRoutePage /> },
]

export function AppRoutes() {
  return (
    <Suspense fallback={<div className="grid min-h-[40vh] place-items-center text-sm text-muted-foreground">正在加载页面…</div>}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<RequirePermission permission="book_sources.read" />}>
          <Route path="/sources" element={<SourceListPage />} />
          <Route path="/sources/health" element={<SourceHealthPage />} />
          <Route path="/sources/health/:sourceId" element={<SourceHealthDetailPage />} />
          <Route path="/sources/rules/:sourceVersionId" element={<SourceRuleEditorPage />} />
        </Route>
        <Route element={<RequirePermission permission="engine.test" />}><Route path="/engine" element={<EngineRunsPage />} /></Route>
        <Route element={<RequirePermission permission="users.read" />}><Route path="/admin/users" element={<AdminUsersPage />} /></Route>
        <Route element={<RequirePermission permission="system.audit.read" />}><Route path="/admin/audit" element={<AdminAuditPage />} /></Route>
        <Route element={<RequirePermission permission="api_keys.read" />}><Route path="/admin/api-keys" element={<ApiKeysPage />} /></Route>
        <Route element={<RequirePermission permission="ai.run" />}>
          <Route path="/ai/tasks" element={<AITasksPage />} />
          <Route path="/ai/workspace" element={<AIWorkspacePage />} />
        </Route>
        <Route element={<RequirePermission permission="translation.run" />}><Route path="/translation/jobs" element={<TranslationJobsPage />} /></Route>
        <Route element={<RequirePermission permission="novel.manage" />}><Route path="/novel/tasks" element={<NovelTasksPage />} /></Route>
        <Route element={<RequirePermission permission="novel.manage" />}><Route path="/novel-analysis/:workId" element={<WorkAnalysisPage />} /></Route>
        <Route element={<RequirePermission permission="system.jobs.manage" />}><Route path="/operations/jobs" element={<JobsPage />} /></Route>
        <Route element={<RequirePermission permission="agent_runs.read" />}><Route path="/operations/agent-runs" element={<AgentRunsPage />} /></Route>
        <Route element={<RequirePermission permission="system.jobs.manage" />}><Route path="/operations/deliveries" element={<EventDeliveriesPage />} /></Route>
        <Route element={<RequirePermission permission="book_sources.read" />}><Route path="/operations/source-builds" element={<SourceBuildsPage />} /></Route>
        <Route element={<RequirePermission permission="agent_runs.read" />}><Route path="/operations/review-queue" element={<ReviewQueuePage />} /></Route>
        <Route element={<RequirePermission permission="system.settings.manage" />}>
          <Route path="/system/settings" element={<Navigate to="/system/settings/models/providers" replace />} />
          <Route path="/system/settings/:domain/:tab" element={<SystemSettingsRoutePage />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
    </Suspense>
  )
}
