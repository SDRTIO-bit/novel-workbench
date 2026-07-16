import { Routes, Route, Navigate } from 'react-router-dom'
import { AppShell } from './AppShell'

function ProjectsPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">小说项目</h1></div>
}

function WritePage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">写作工作台</h1></div>
}

function ProvidersPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">服务商管理</h1></div>
}

function PromptsPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">提示词管理</h1></div>
}

function WorkflowsPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">工作流方案</h1></div>
}

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
