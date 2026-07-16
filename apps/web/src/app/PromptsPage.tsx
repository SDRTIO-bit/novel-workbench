import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import {
  listPrompts,
  createPrompt,
  getVersions,
  addVersion,
  duplicatePrompt,
  restoreDefault,
  renderPreview,
  exportPrompts,
  importPrompts,
} from '../api/prompts'
import { listProjects } from '../api/projects'
import { listChapters } from '../api/chapters'
import { STAGE_LABELS, STAGES } from '../types'
import type { PromptProfileList, PromptVersion, PromptCreate } from '../types'

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  )
}

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  )
}

const STAGE_TABS = [{ label: '全部', value: '' }, ...STAGES.map(s => ({ label: STAGE_LABELS[s], value: s }))]

export default function PromptsPage() {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [stageFilter, setStageFilter] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ stage: 'planner', name: '', description: '', system_template: '', user_template: '' })
  const [versionFormId, setVersionFormId] = useState<string | null>(null)
  const [versionForm, setVersionForm] = useState({ system_template: '', user_template: '' })
  const [previewProfile, setPreviewProfile] = useState<PromptProfileList | null>(null)
  const [previewData, setPreviewData] = useState({ projectId: '', chapterId: '', varJson: '{}' })
  const [previewResult, setPreviewResult] = useState<{ system_prompt: string; user_prompt: string } | null>(null)

  const { data: prompts, isLoading, error, refetch } = useQuery({
    queryKey: stageFilter ? ['prompts', stageFilter] : ['prompts'],
    queryFn: () => listPrompts(stageFilter || undefined),
  })

  const { data: versions } = useQuery({
    queryKey: ['prompt-versions', expandedId],
    queryFn: () => getVersions(expandedId!),
    enabled: !!expandedId,
  })

  const createMutation = useMutation({
    mutationFn: (data: PromptCreate) => createPrompt(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      setShowCreate(false)
      setCreateForm({ stage: 'planner', name: '', description: '', system_template: '', user_template: '' })
    },
  })

  const addVersionMutation = useMutation({
    mutationFn: ({ profileId, data }: { profileId: string; data: { system_template: string; user_template: string } }) =>
      addVersion(profileId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt-versions', expandedId] })
      setVersionFormId(null)
    },
  })

  const duplicateMutation = useMutation({
    mutationFn: (profileId: string) => duplicatePrompt(profileId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['prompts'] }),
  })

  const restoreMutation = useMutation({
    mutationFn: (profileId: string) => restoreDefault(profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      queryClient.invalidateQueries({ queryKey: ['prompt-versions', expandedId] })
    },
  })

  const previewMutation = useMutation({
    mutationFn: () => {
      const variables = JSON.parse(previewData.varJson)
      const v = versions?.[0]
      return renderPreview({
        system_template: v?.system_template || '',
        user_template: v?.user_template || '',
        variables,
      })
    },
    onSuccess: (data) => setPreviewResult(data),
  })

  const importMutation = useMutation({
    mutationFn: (data: unknown) => importPrompts(data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['prompts'] })
      alert(`成功导入 ${res.imported} 条提示词`)
    },
  })

  const handleExport = async () => {
    const data = await exportPrompts()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'prompts-export.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = () => fileInputRef.current?.click()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string)
        importMutation.mutate(data)
      } catch {
        alert('无效的 JSON 文件')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const openPreview = (profile: PromptProfileList) => {
    setPreviewProfile(profile)
    setPreviewData({ projectId: '', chapterId: '', varJson: '{}' })
    setPreviewResult(null)
  }

  if (isLoading) return <Spinner />

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-500">
        <p className="mb-4">加载失败</p>
        <button onClick={() => refetch()} className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">重试</button>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">提示词管理</h1>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors">导出</button>
          <button onClick={handleImport} className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors">导入</button>
          <input ref={fileInputRef} type="file" accept=".json" onChange={handleFileChange} className="hidden" />
          <button onClick={() => setShowCreate(true)} className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">添加提示词</button>
        </div>
      </div>

      <div className="flex gap-2 mb-6 flex-wrap">
        {STAGE_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setStageFilter(tab.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              stageFilter === tab.value
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {showCreate && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">添加提示词</h3>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">阶段</label>
              <select
                value={createForm.stage}
                onChange={e => setCreateForm(prev => ({ ...prev, stage: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {STAGES.map(s => <option key={s} value={s}>{STAGE_LABELS[s]}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">名称</label>
              <input
                autoFocus
                value={createForm.name}
                onChange={e => setCreateForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="提示词方案名称"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="mb-3">
            <label className="block text-xs text-gray-500 mb-1">描述</label>
            <input
              value={createForm.description}
              onChange={e => setCreateForm(prev => ({ ...prev, description: e.target.value }))}
              placeholder="提示词描述"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">System 模板</label>
              <textarea
                value={createForm.system_template}
                onChange={e => setCreateForm(prev => ({ ...prev, system_template: e.target.value }))}
                rows={4}
                placeholder="系统提示词模板..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">User 模板</label>
              <textarea
                value={createForm.user_template}
                onChange={e => setCreateForm(prev => ({ ...prev, user_template: e.target.value }))}
                rows={4}
                placeholder="用户提示词模板..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => createMutation.mutate({
                stage: createForm.stage,
                name: createForm.name,
                description: createForm.description || undefined,
                system_template: createForm.system_template || undefined,
                user_template: createForm.user_template || undefined,
              })}
              disabled={!createForm.name.trim() || createMutation.isPending}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending ? '创建中...' : '创建'}
            </button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">取消</button>
          </div>
        </div>
      )}

      {!prompts?.length && (
        <div className="flex items-center justify-center py-16 border-2 border-dashed border-gray-300 rounded-xl">
          <p className="text-gray-400 text-sm">暂无提示词方案</p>
        </div>
      )}

      <div className="space-y-3">
        {prompts?.map(profile => (
          <div key={profile.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 flex items-center gap-3">
              <button onClick={() => setExpandedId(expandedId === profile.id ? null : profile.id)} className="shrink-0">
                <ChevronDown open={expandedId === profile.id} />
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">{profile.name}</span>
                  <span className="px-2 py-0.5 text-xs font-medium bg-indigo-50 text-indigo-700 rounded-full">
                    {profile.stage in STAGE_LABELS ? STAGE_LABELS[profile.stage as keyof typeof STAGE_LABELS] : profile.stage}
                  </span>
                  {profile.is_builtin && (
                    <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded-full">内置</span>
                  )}
                </div>
                {profile.description && <p className="text-xs text-gray-400 mt-0.5 truncate">{profile.description}</p>}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => openPreview(profile)} className="px-2 py-1 text-xs text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors">渲染预览</button>
                <button
                  onClick={() => { setVersionFormId(profile.id); setVersionForm({ system_template: '', user_template: '' }) }}
                  className="px-2 py-1 text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                >新建版本</button>
                <button onClick={() => duplicateMutation.mutate(profile.id)} className="px-2 py-1 text-xs text-gray-500 hover:text-green-600 hover:bg-green-50 rounded transition-colors">复制</button>
                {profile.is_builtin && (
                  <button onClick={() => restoreMutation.mutate(profile.id)} className="px-2 py-1 text-xs text-gray-500 hover:text-amber-600 hover:bg-amber-50 rounded transition-colors">恢复默认</button>
                )}
              </div>
            </div>

            {versionFormId === profile.id && (
              <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                <h4 className="text-sm font-medium text-gray-700 mb-2">新建版本</h4>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">System 模板</label>
                    <textarea
                      value={versionForm.system_template}
                      onChange={e => setVersionForm(prev => ({ ...prev, system_template: e.target.value }))}
                      rows={6}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">User 模板</label>
                    <textarea
                      value={versionForm.user_template}
                      onChange={e => setVersionForm(prev => ({ ...prev, user_template: e.target.value }))}
                      rows={6}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => addVersionMutation.mutate({ profileId: profile.id, data: versionForm })}
                    disabled={addVersionMutation.isPending}
                    className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  >
                    {addVersionMutation.isPending ? '创建中...' : '创建版本'}
                  </button>
                  <button onClick={() => setVersionFormId(null)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">取消</button>
                </div>
              </div>
            )}

            {expandedId === profile.id && (
              <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                <h4 className="text-sm font-medium text-gray-700 mb-2">历史版本</h4>
                {versions?.length === 0 && <p className="text-xs text-gray-400">暂无版本</p>}
                <div className="space-y-2 max-h-60 overflow-auto">
                  {versions?.map((v: PromptVersion) => (
                    <div key={v.id} className="p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-gray-600">v{v.version_number}</span>
                        <span className="text-xs text-gray-400">{new Date(v.created_at).toLocaleString('zh-CN')}</span>
                      </div>
                      {v.system_template && (
                        <div className="mb-1">
                          <span className="text-xs text-gray-500">System:</span>
                          <pre className="text-xs text-gray-700 mt-0.5 whitespace-pre-wrap font-mono bg-white p-2 rounded border border-gray-200 max-h-24 overflow-auto">{v.system_template}</pre>
                        </div>
                      )}
                      {v.user_template && (
                        <div>
                          <span className="text-xs text-gray-500">User:</span>
                          <pre className="text-xs text-gray-700 mt-0.5 whitespace-pre-wrap font-mono bg-white p-2 rounded border border-gray-200 max-h-24 overflow-auto">{v.user_template}</pre>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {previewProfile && (
        <RenderPreviewModal
          profile={previewProfile}
          data={previewData}
          onChange={setPreviewData}
          result={previewResult}
          isPending={previewMutation.isPending}
          onRender={() => previewMutation.mutate()}
          onClose={() => { setPreviewProfile(null); setPreviewResult(null) }}
        />
      )}
    </div>
  )
}

function RenderPreviewModal({
  profile, data, onChange, result, isPending, onRender, onClose,
}: {
  profile: PromptProfileList
  data: { projectId: string; chapterId: string; varJson: string }
  onChange: (d: typeof data) => void
  result: { system_prompt: string; user_prompt: string } | null
  isPending: boolean
  onRender: () => void
  onClose: () => void
}) {
  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: () => listProjects(true), staleTime: 30000 })
  const { data: chapters } = useQuery({
    queryKey: ['chapters', data.projectId],
    queryFn: () => listChapters(data.projectId),
    enabled: !!data.projectId,
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-[640px] max-h-[80vh] overflow-auto p-6" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-gray-900 mb-4">渲染预览 - {profile.name}</h3>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">项目</label>
            <select
              value={data.projectId}
              onChange={e => onChange({ ...data, projectId: e.target.value, chapterId: '' })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">选择项目</option>
              {projects?.filter(p => !p.deleted_at).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">章节</label>
            <select
              value={data.chapterId}
              onChange={e => onChange({ ...data, chapterId: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              disabled={!data.projectId}
            >
              <option value="">选择章节</option>
              {chapters?.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </div>
        </div>

        <div className="mb-3">
          <label className="block text-xs text-gray-500 mb-1">变量 (JSON)</label>
          <textarea
            value={data.varJson}
            onChange={e => onChange({ ...data, varJson: e.target.value })}
            rows={4}
            placeholder='{"variable_name": "value"}'
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="flex gap-2 mb-4">
          <button
            onClick={onRender}
            disabled={isPending}
            className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {isPending ? '渲染中...' : '渲染'}
          </button>
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">关闭</button>
        </div>

        {result && (
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">System Prompt</label>
              <pre className="text-xs whitespace-pre-wrap font-mono bg-gray-50 p-3 rounded-lg border border-gray-200 max-h-40 overflow-auto">{result.system_prompt}</pre>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">User Prompt</label>
              <pre className="text-xs whitespace-pre-wrap font-mono bg-gray-50 p-3 rounded-lg border border-gray-200 max-h-40 overflow-auto">{result.user_prompt}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
