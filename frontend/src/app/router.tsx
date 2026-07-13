import { Navigate, Route, Routes } from 'react-router-dom'

import { AdminAuditPage } from '@/features/admin/AdminAuditPage'
import { AdminUsersPage } from '@/features/admin/AdminUsersPage'
import { AITasksPage } from '@/features/ai/AITasksPage'
import { AIWorkspacePage } from '@/features/ai/AIWorkspacePage'
import { EngineRunsPage } from '@/features/engine/EngineRunsPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { NovelTasksPage } from '@/features/novel/NovelTasksPage'
import { AgentRunsPage } from '@/features/operations/AgentRunsPage'
import { EventDeliveriesPage } from '@/features/operations/EventDeliveriesPage'
import { JobsPage } from '@/features/operations/JobsPage'
import { ReviewQueuePage } from '@/features/operations/ReviewQueuePage'
import { SourceBuildsPage } from '@/features/operations/SourceBuildsPage'
import { SourceHealthPage } from '@/features/sources/SourceHealthPage'
import { SourceHealthDetailPage } from '@/features/sources/SourceHealthDetailPage'
import { SourceListPage } from '@/features/sources/SourceListPage'
import { SourceRuleEditorPage } from '@/features/sources/SourceRuleEditorPage'
import { SystemSettingsPage } from '@/features/system/SystemSettingsPage'
import { TranslationJobsPage } from '@/features/translation/TranslationJobsPage'
import { RequireAuth } from '@/app/router/RequireAuth'
import { RequirePermission } from '@/app/router/RequirePermission'

export const appRoutes = [
  { path: '/login', element: <LoginPage /> },
  { path: '/sources', element: <SourceListPage /> },
  { path: '/sources/health', element: <SourceHealthPage /> },
  { path: '/sources/health/:sourceId', element: <SourceHealthDetailPage /> },
  { path: '/sources/rules/:sourceVersionId', element: <SourceRuleEditorPage /> },
  { path: '/engine', element: <EngineRunsPage /> },
  { path: '/admin/users', element: <AdminUsersPage /> },
  { path: '/admin/audit', element: <AdminAuditPage /> },
  { path: '/ai/tasks', element: <AITasksPage /> },
  { path: '/ai/workspace', element: <AIWorkspacePage /> },
  { path: '/translation/jobs', element: <TranslationJobsPage /> },
  { path: '/novel/tasks', element: <NovelTasksPage /> },
  { path: '/operations/jobs', element: <JobsPage /> },
  { path: '/operations/agent-runs', element: <AgentRunsPage /> },
  { path: '/operations/deliveries', element: <EventDeliveriesPage /> },
  { path: '/operations/source-builds', element: <SourceBuildsPage /> },
  { path: '/operations/review-queue', element: <ReviewQueuePage /> },
  { path: '/system/settings', element: <SystemSettingsPage /> },
]

export function AppRoutes() {
  return (
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
        <Route element={<RequirePermission permission="ai.run" />}>
          <Route path="/ai/tasks" element={<AITasksPage />} />
          <Route path="/ai/workspace" element={<AIWorkspacePage />} />
        </Route>
        <Route element={<RequirePermission permission="translation.run" />}><Route path="/translation/jobs" element={<TranslationJobsPage />} /></Route>
        <Route element={<RequirePermission permission="novel.manage" />}><Route path="/novel/tasks" element={<NovelTasksPage />} /></Route>
        <Route element={<RequirePermission permission="system.jobs.manage" />}><Route path="/operations/jobs" element={<JobsPage />} /></Route>
        <Route element={<RequirePermission permission="agent_runs.read" />}><Route path="/operations/agent-runs" element={<AgentRunsPage />} /></Route>
        <Route element={<RequirePermission permission="system.jobs.manage" />}><Route path="/operations/deliveries" element={<EventDeliveriesPage />} /></Route>
        <Route element={<RequirePermission permission="book_sources.read" />}><Route path="/operations/source-builds" element={<SourceBuildsPage />} /></Route>
        <Route element={<RequirePermission permission="agent_runs.read" />}><Route path="/operations/review-queue" element={<ReviewQueuePage />} /></Route>
        <Route element={<RequirePermission permission="system.settings.manage" />}><Route path="/system/settings" element={<SystemSettingsPage />} /></Route>
      </Route>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
