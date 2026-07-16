import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  listWorkflows,
  getWorkflow,
  createWorkflow,
  duplicateWorkflow,
  deleteWorkflow,
  updateStep,
  setDefault,
} from '../api/workflows'
import { listProviders } from '../api/providers'
import { listPrompts } from '../api/prompts'
import { STAGES, STAGE_LABELS } from '../types'
import type { WorkflowStepConfig, PromptProfileList } from '../types'

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

const DEFAULT_STEP_CONFIG: WorkflowStepConfig = {
  id: '',
  workflow_profile_id: '',
  stage: '',
  provider_id: undefined,
  model_id: undefined,
  prompt_version_id: undefined,
  temperature: 0.7,
  top_p: 1,
  max_output_tokens: 4096,
  timeout_seconds: 120,
}

export default function WorkflowsPage() {
  const queryClient = useQueryClient()

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ name: '', description: '' })
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [stepChanges, setStepChanges] = useState<Record<string, Partial<WorkflowStepConfig>>>({})

  const { data: workflows, isLoading, error, refetch } = useQuery({
    queryKey: ['workflows'],
    queryFn: listWorkflows,
  })

  const { data: expandedWorkflow } = useQuery({
    queryKey: ['workflow', expandedId],
    queryFn: () => getWorkflow(expandedId!),
    enabled: !!expandedId,
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
    enabled: !!expandedId,
  })

  const { data: allPrompts } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => listPrompts(),
    enabled: !!expandedId,
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description?: string }) => createWorkflow(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setShowCreate(false)
      setCreateForm({ name: '', description: '' })
    },
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => duplicateWorkflow(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workflows'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteWorkflow(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workflows'] }); setConfirmDeleteId(null) },
  })

  const setDefaultMutation = useMutation({
    mutationFn: (id: string) => setDefault(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workflows'] }),
  })

  const updateStepMutation = useMutation({
    mutationFn: ({ workflowId, stage, data }: { workflowId: string; stage: string; data: Record<string, unknown> }) =>
      updateStep(workflowId, stage, data as import('../types').WorkflowStepUpdate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', expandedId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
    },
  })

  const handleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id)
    setStepChanges({})
  }

  const getStepConfig = (stage: string): Partial<WorkflowStepConfig> => {
    if (!expandedWorkflow) return {}
    const step = expandedWorkflow.steps.find(s => s.stage === stage)
    const overrides = stepChanges[stage] || {}
    return step ? { ...step, ...overrides, stage } : { ...DEFAULT_STEP_CONFIG, stage, ...overrides }
  }

  const handleStepChange = (stage: string, field: string, value: string | number | undefined) => {
    setStepChanges(prev => ({
      ...prev,
      [stage]: { ...(prev[stage] || {}), [field]: value },
    }))
  }

  const copyFromPrevStage = (stage: string) => {
    const idx = STAGES.indexOf(stage as typeof STAGES[number])
    if (idx <= 0) return
    const prevStage = STAGES[idx - 1]
    const prevConfig = getStepConfig(prevStage)
    setStepChanges(prev => ({
      ...prev,
      [stage]: { ...(prev[stage] || {}), ...prevConfig, stage: undefined, id: undefined, workflow_profile_id: undefined },
    }))
  }

  const saveStep = (stage: string) => {
    if (!expandedId) return
    const config = getStepConfig(stage)
    updateStepMutation.mutate({
      workflowId: expandedId,
      stage,
      data: {
        provider_id: config.provider_id || null,
        model_id: config.model_id || null,
        prompt_version_id: config.prompt_version_id || null,
        temperature: config.temperature,
        top_p: config.top_p,
        max_output_tokens: config.max_output_tokens,
        timeout_seconds: config.timeout_seconds,
      },
    })
  }

  const getPromptsForStage = (stage: string): PromptProfileList[] =>
    (allPrompts || []).filter(p => p.stage === stage)

  const getModelsForProvider = (providerId?: string) => {
    if (!providers || !providerId) return []
    const p = providers.find(p => p.id === providerId)
    return p?.models?.filter(m => m.enabled) || []
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
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">工作流方案</h1>
        <button
          onClick={() => { setShowCreate(true); setCreateForm({ name: '', description: '' }) }}
          className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          新建方案
        </button>
      </div>

      {showCreate && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">新建工作流方案</h3>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">名称</label>
              <input
                autoFocus
                value={createForm.name}
                onChange={e => setCreateForm(prev => ({ ...prev, name: e.target.value }))}
                onKeyDown={e => { if (e.key === 'Enter') createMutation.mutate({ name: createForm.name, description: createForm.description || undefined }) }}
                placeholder="方案名称"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">描述</label>
              <input
                value={createForm.description}
                onChange={e => setCreateForm(prev => ({ ...prev, description: e.target.value }))}
                onKeyDown={e => { if (e.key === 'Enter') createMutation.mutate({ name: createForm.name, description: createForm.description || undefined }) }}
                placeholder="方案描述"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => createMutation.mutate({ name: createForm.name, description: createForm.description || undefined })}
              disabled={!createForm.name.trim() || createMutation.isPending}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending ? '创建中...' : '创建'}
            </button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">取消</button>
          </div>
        </div>
      )}

      {!workflows?.length && (
        <div className="flex items-center justify-center py-16 border-2 border-dashed border-gray-300 rounded-xl">
          <p className="text-gray-400 text-sm">暂无工作流方案</p>
        </div>
      )}

      <div className="space-y-3">
        {workflows?.map(wf => (
          <div key={wf.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 flex items-center gap-3">
              <button onClick={() => handleExpand(wf.id)} className="shrink-0">
                <ChevronDown open={expandedId === wf.id} />
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">{wf.name}</span>
                  {wf.is_default && (
                    <span className="px-2 py-0.5 text-xs font-medium bg-amber-50 text-amber-700 rounded-full">默认</span>
                  )}
                </div>
                {wf.description && <p className="text-xs text-gray-400 mt-0.5 truncate">{wf.description}</p>}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => duplicateMutation.mutate(wf.id)} className="px-2 py-1 text-xs text-gray-500 hover:text-green-600 hover:bg-green-50 rounded transition-colors">复制</button>
                {!wf.is_default && (
                  <button
                    onClick={() => setDefaultMutation.mutate(wf.id)}
                    className="px-2 py-1 text-xs text-gray-500 hover:text-amber-600 hover:bg-amber-50 rounded transition-colors"
                  >设为默认</button>
                )}
                {confirmDeleteId === wf.id ? (
                  <div className="flex items-center gap-1">
                    <button onClick={() => deleteMutation.mutate(wf.id)} disabled={deleteMutation.isPending} className="px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 rounded transition-colors">确认</button>
                    <button onClick={() => setConfirmDeleteId(null)} className="px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded transition-colors">取消</button>
                  </div>
                ) : (
                  <button onClick={() => setConfirmDeleteId(wf.id)} className="px-2 py-1 text-xs text-gray-500 hover:text-red-600 hover:bg-red-50 rounded transition-colors">删除</button>
                )}
              </div>
            </div>

            {expandedId === wf.id && expandedWorkflow && (
              <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                <div className="grid grid-cols-1 gap-4">
                  {STAGES.map((stage, idx) => {
                    const config = getStepConfig(stage)
                    const stagePrompts = getPromptsForStage(stage)
                    const models = getModelsForProvider(config.provider_id)
                    return (
                      <div key={stage} className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="flex items-center justify-between mb-3">
                          <h4 className="text-sm font-semibold text-gray-700">
                            {STAGE_LABELS[stage]}
                          </h4>
                          <div className="flex items-center gap-2">
                            {idx > 0 && (
                              <button
                                onClick={() => copyFromPrevStage(stage)}
                                className="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
                              >
                                复制上一阶段配置
                              </button>
                            )}
                            <button
                              onClick={() => saveStep(stage)}
                              disabled={updateStepMutation.isPending}
                              className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                            >
                              {updateStepMutation.isPending ? '保存中...' : '保存'}
                            </button>
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-3 mb-2">
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">服务商</label>
                            <select
                              value={config.provider_id || ''}
                              onChange={e => handleStepChange(stage, 'provider_id', e.target.value || undefined)}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            >
                              <option value="">选择服务商</option>
                              {providers?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">模型</label>
                            <select
                              value={config.model_id || ''}
                              onChange={e => handleStepChange(stage, 'model_id', e.target.value || undefined)}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            >
                              <option value="">选择模型</option>
                              {models.map(m => <option key={m.id} value={m.id}>{m.display_name}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">提示词版本</label>
                            <select
                              value={config.prompt_version_id || ''}
                              onChange={e => handleStepChange(stage, 'prompt_version_id', e.target.value || undefined)}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            >
                              <option value="">选择提示词</option>
                              {stagePrompts.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                          </div>
                        </div>

                        <div className="grid grid-cols-4 gap-3">
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">Temperature</label>
                            <input
                              type="number"
                              step={0.1}
                              min={0}
                              max={2}
                              value={config.temperature ?? 0.7}
                              onChange={e => handleStepChange(stage, 'temperature', parseFloat(e.target.value))}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">Top P</label>
                            <input
                              type="number"
                              step={0.1}
                              min={0}
                              max={1}
                              value={config.top_p ?? 1}
                              onChange={e => handleStepChange(stage, 'top_p', parseFloat(e.target.value))}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">Max Tokens</label>
                            <input
                              type="number"
                              value={config.max_output_tokens ?? 4096}
                              onChange={e => handleStepChange(stage, 'max_output_tokens', parseInt(e.target.value))}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">超时 (秒)</label>
                            <input
                              type="number"
                              value={config.timeout_seconds ?? 120}
                              onChange={e => handleStepChange(stage, 'timeout_seconds', parseInt(e.target.value))}
                              className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
