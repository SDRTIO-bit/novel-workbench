import { Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from './AppShell'
import ProjectsPage from './ProjectsPage'
import WritePage from './WritePage'
import ProvidersPage from './ProvidersPage'
import PromptsPage from './PromptsPage'
import WorkflowsPage from './WorkflowsPage'

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId/write" element={<WritePage />} />
        <Route path="/settings/providers" element={<ProvidersPage />} />
        <Route path="/settings/prompts" element={<PromptsPage />} />
        <Route path="/settings/workflows" element={<WorkflowsPage />} />
      </Route>
    </Routes>
  )
}
