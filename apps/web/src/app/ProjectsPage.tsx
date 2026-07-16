import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import {
  listProjects,
  createProject,
  updateProject,
  deleteProject,
  restoreProject,
  duplicateProject,
} from '../api/projects'
import type { ProjectCreate } from '../types'
import { apiPost } from '../api/client'

function ImportButton({ onImported }: { onImported: () => void }) {
  const [importing, setImporting] = useState(false)
  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      await apiPost('/import/project-bundle', data)
      onImported()
    } catch (err) {
      alert('导入失败：' + (err instanceof Error ? err.message : '格式错误'))
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }
  return (
    <label
      className={`px-3 py-2 text-sm font-medium border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer ${importing ? 'opacity-50' : ''}`}
    >
      {importing ? '导入中...' : '导入项目'}
      <input type="file" accept=".json" hidden onChange={handleImport} />
    </label>
  )
}

function PenIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
    </svg>
  )
}

function CopyIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  )
}

export default function ProjectsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [createName, setCreateName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const { data: projects, isLoading, error, refetch } = useQuery({
    queryKey: ['projects'],
    queryFn: () => listProjects(true),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['projects'] })

  const createMutation = useMutation({
    mutationFn: (data: ProjectCreate) => createProject(data),
    onSuccess: () => {
      invalidate()
      setShowCreate(false)
      setCreateName('')
    },
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateProject(id, { name }),
    onSuccess: () => {
      invalidate()
      setEditingId(null)
      setEditingName('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      invalidate()
      setConfirmDeleteId(null)
    },
  })

  const restoreMutation = useMutation({
    mutationFn: (id: string) => restoreProject(id),
    onSuccess: () => invalidate(),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => duplicateProject(id),
    onSuccess: () => invalidate(),
  })

  const handleCreate = () => {
    if (!createName.trim()) return
    createMutation.mutate({ name: createName.trim() })
  }

  const handleRename = (id: string) => {
    if (!editingName.trim() || editingName.trim() === projects?.find(p => p.id === id)?.name) {
      setEditingId(null)
      return
    }
    renameMutation.mutate({ id, name: editingName.trim() })
  }

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })

  const activeProjects = projects?.filter(p => !p.deleted_at) ?? []
  const deletedProjects = projects?.filter(p => p.deleted_at) ?? []

  if (isLoading) return <Spinner />

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-500">
        <p className="mb-4">加载失败，请检查网络连接</p>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          重试
        </button>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">小说项目</h1>
        <div className="flex gap-2">
          <ImportButton onImported={() => queryClient.invalidateQueries({ queryKey: ['projects'] })} />
          <button
            onClick={() => { setShowCreate(v => !v); setCreateName('') }}
            className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            新建项目
          </button>
        </div>
      </div>

      {showCreate && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="flex gap-3">
            <input
              autoFocus
              value={createName}
              onChange={e => setCreateName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setShowCreate(false) }}
              placeholder="输入项目名称"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
            <button
              onClick={handleCreate}
              disabled={!createName.trim() || createMutation.isPending}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {createMutation.isPending ? '创建中...' : '确认创建'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {activeProjects.length === 0 && deletedProjects.length === 0 && (
        <div className="flex items-center justify-center py-16 border-2 border-dashed border-gray-300 rounded-xl">
          <p className="text-gray-400 text-sm">还没有小说项目，点击上方按钮创建第一个</p>
        </div>
      )}

      <div className="space-y-2">
        {activeProjects.map(project => (
          <div
            key={project.id}
            className={`flex items-center gap-4 px-4 py-3 bg-white rounded-xl border border-gray-200 shadow-sm transition-shadow hover:shadow-md ${
              project.deleted_at ? 'opacity-60' : ''
            }`}
          >
            <div className="flex-1 min-w-0">
              {editingId === project.id ? (
                <div className="flex gap-2">
                  <input
                    autoFocus
                    value={editingName}
                    onChange={e => setEditingName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handleRename(project.id); if (e.key === 'Escape') setEditingId(null) }}
                    onBlur={() => handleRename(project.id)}
                    className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              ) : (
                <button
                  onClick={() => navigate(`/projects/${project.id}/write`)}
                  className={`text-sm font-semibold text-gray-900 hover:text-indigo-600 transition-colors text-left truncate block ${
                    project.deleted_at ? 'line-through' : ''
                  }`}
                >
                  {project.name}
                </button>
              )}
              <div className="flex items-center gap-2 mt-1">
                {project.genre && (
                  <span className="px-2 py-0.5 text-xs font-medium bg-indigo-50 text-indigo-700 rounded-full">
                    {project.genre}
                  </span>
                )}
                <span className="text-xs text-gray-400">{formatDate(project.updated_at)}</span>
              </div>
            </div>

            {!project.deleted_at && (
              <div className="flex items-center gap-1 shrink-0">
                {editingId !== project.id && (
                  <>
                    <button
                      onClick={() => { setEditingId(project.id); setEditingName(project.name) }}
                      className="p-2 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                      title="重命名"
                    >
                      <PenIcon />
                    </button>
                    <button
                      onClick={() => duplicateMutation.mutate(project.id)}
                      disabled={duplicateMutation.isPending}
                      className="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                      title="复制"
                    >
                      <CopyIcon />
                    </button>
                    {confirmDeleteId === project.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => deleteMutation.mutate(project.id)}
                          disabled={deleteMutation.isPending}
                          className="px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 rounded transition-colors"
                        >
                          确认删除
                        </button>
                        <button
                          onClick={() => setConfirmDeleteId(null)}
                          className="px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded transition-colors"
                        >
                          取消
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmDeleteId(project.id)}
                        className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="删除"
                      >
                        <TrashIcon />
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {deletedProjects.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-gray-500 mb-3">已删除的项目</h2>
          <div className="space-y-2">
            {deletedProjects.map(project => (
              <div
                key={project.id}
                className="flex items-center gap-4 px-4 py-3 bg-gray-50 rounded-xl border border-gray-200"
              >
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-semibold text-gray-400 line-through block truncate">
                    {project.name}
                  </span>
                  <div className="flex items-center gap-2 mt-1">
                    {project.genre && (
                      <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-400 rounded-full">
                        {project.genre}
                      </span>
                    )}
                    <span className="text-xs text-gray-400">{formatDate(project.updated_at)}</span>
                  </div>
                </div>
                <button
                  onClick={() => restoreMutation.mutate(project.id)}
                  disabled={restoreMutation.isPending}
                  className="px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors shrink-0"
                >
                  恢复
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
