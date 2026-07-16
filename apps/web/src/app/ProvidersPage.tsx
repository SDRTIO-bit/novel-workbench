import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  listProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  testProvider,
  syncModels,
  addModel,
  updateModel,
} from '../api/providers'
import type { Provider, ProviderCreate, ProviderUpdate } from '../types'

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="w-8 h-8 border-4 border-gray-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  )
}

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`}
      fill="none" stroke="currentColor" viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
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

interface ProviderForm {
  name: string
  provider_type: string
  base_url: string
  api_key: string
}

const EMPTY_FORM: ProviderForm = { name: '', provider_type: 'openai_compatible', base_url: '', api_key: '' }

export default function ProvidersPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<ProviderForm>(EMPTY_FORM)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, string>>({})
  const [newModelForm, setNewModelForm] = useState<Record<string, { model_id: string; display_name: string }>>({})
  const [syncingId, setSyncingId] = useState<string | null>(null)

  const { data: providers, isLoading, error, refetch } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['providers'] })

  const createMutation = useMutation({
    mutationFn: (data: ProviderCreate) => createProvider(data),
    onSuccess: () => { invalidate(); resetForm() },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProviderUpdate }) => updateProvider(id, data),
    onSuccess: () => { invalidate(); resetForm() },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProvider(id),
    onSuccess: () => { invalidate(); setConfirmDeleteId(null) },
  })

  const testMutation = useMutation({
    mutationFn: (id: string) => testProvider(id),
    onSuccess: (result, id) => {
      setTestResult(prev => ({ ...prev, [id]: result.status === 'ok' ? '连接成功' : result.message }))
    },
  })

  const syncMutation = useMutation({
    mutationFn: (id: string) => syncModels(id),
    onSuccess: () => invalidate(),
  })

  const addModelMutation = useMutation({
    mutationFn: ({ providerId, data }: { providerId: string; data: { model_id: string; display_name?: string } }) =>
      addModel(providerId, data),
    onSuccess: (_, { providerId }) => {
      invalidate()
      setNewModelForm(prev => {
        const next = { ...prev }
        delete next[providerId]
        return next
      })
    },
  })

  const updateModelMutation = useMutation({
    mutationFn: ({ providerId, modelId, data }: { providerId: string; modelId: string; data: { enabled: boolean } }) =>
      updateModel(providerId, modelId, data),
    onSuccess: () => invalidate(),
  })

  const resetForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  const openAddForm = () => {
    setEditingId(null)
    setForm({ ...EMPTY_FORM, provider_type: 'openai_compatible' })
    setShowForm(true)
  }

  const openEditForm = (p: Provider) => {
    setEditingId(p.id)
    setForm({ name: p.name, provider_type: p.provider_type, base_url: p.base_url || '', api_key: '' })
    setShowForm(true)
  }

  const handleSubmit = () => {
    if (!form.name.trim()) return
    const payload: ProviderCreate = {
      name: form.name.trim(),
      provider_type: form.provider_type,
      base_url: form.base_url.trim() || undefined,
      api_key: form.api_key || undefined,
    }
    if (editingId) {
      const updatePayload: ProviderUpdate = { name: payload.name, base_url: payload.base_url }
      if (payload.api_key) updatePayload.api_key = payload.api_key
      updateMutation.mutate({ id: editingId, data: updatePayload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const ensureNewModelForm = (providerId: string) => {
    if (!newModelForm[providerId]) {
      setNewModelForm(prev => ({ ...prev, [providerId]: { model_id: '', display_name: '' } }))
    }
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
        <h1 className="text-2xl font-bold text-gray-900">服务商管理</h1>
        <button onClick={openAddForm} className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
          添加服务商
        </button>
      </div>

      {showForm && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">{editingId ? '编辑服务商' : '添加服务商'}</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">名称</label>
              <input
                autoFocus
                value={form.name}
                onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="服务商名称"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">类型</label>
              <select
                value={form.provider_type}
                onChange={e => setForm(prev => ({ ...prev, provider_type: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="openai_compatible">OpenAI 兼容</option>
                <option value="mock">Mock</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Base URL</label>
              <input
                value={form.base_url}
                onChange={e => setForm(prev => ({ ...prev, base_url: e.target.value }))}
                placeholder="https://api.openai.com/v1"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">API Key</label>
              <input
                type="password"
                value={form.api_key}
                onChange={e => setForm(prev => ({ ...prev, api_key: e.target.value }))}
                placeholder={editingId ? '留空则不修改' : '输入 API Key'}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button
              onClick={handleSubmit}
              disabled={!form.name.trim() || createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {editingId ? (updateMutation.isPending ? '保存中...' : '保存') : (createMutation.isPending ? '创建中...' : '创建')}
            </button>
            <button onClick={resetForm} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">取消</button>
          </div>
        </div>
      )}

      {!providers?.length && (
        <div className="flex items-center justify-center py-16 border-2 border-dashed border-gray-300 rounded-xl">
          <p className="text-gray-400 text-sm">暂无服务商，点击上方按钮添加</p>
        </div>
      )}

      <div className="space-y-3">
        {providers?.map(provider => (
          <div key={provider.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 flex items-center gap-3">
              <button
                onClick={() => setExpandedId(expandedId === provider.id ? null : provider.id)}
                className="shrink-0"
              >
                <ChevronDown open={expandedId === provider.id} />
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900 truncate">{provider.name}</span>
                  <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                    provider.provider_type === 'mock'
                      ? 'bg-yellow-50 text-yellow-700'
                      : 'bg-blue-50 text-blue-700'
                  }`}>
                    {provider.provider_type === 'mock' ? 'Mock' : 'OpenAI'}
                  </span>
                  {provider.is_builtin && (
                    <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded-full">内置</span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                  {provider.base_url && <span>{provider.base_url}</span>}
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                    provider.has_api_key ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-500'
                  }`}>
                    {provider.has_api_key ? '已配置' : '未配置'}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => openEditForm(provider)}
                  className="px-2 py-1 text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                >
                  编辑
                </button>
                <button
                  onClick={() => testMutation.mutate(provider.id)}
                  disabled={testMutation.isPending}
                  className="px-2 py-1 text-xs text-gray-500 hover:text-green-600 hover:bg-green-50 rounded transition-colors"
                >
                  {testMutation.isPending ? '测试中...' : '测试连接'}
                </button>
                <button
                  onClick={() => { setSyncingId(provider.id); syncMutation.mutate(provider.id) }}
                  disabled={syncMutation.isPending}
                  className="px-2 py-1 text-xs text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                >
                  {syncMutation.isPending && syncingId === provider.id ? '同步中...' : '同步模型'}
                </button>
                {confirmDeleteId === provider.id ? (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => deleteMutation.mutate(provider.id)}
                      disabled={deleteMutation.isPending}
                      className="px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 rounded transition-colors"
                    >
                      确认
                    </button>
                    <button onClick={() => setConfirmDeleteId(null)} className="px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded transition-colors">取消</button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDeleteId(provider.id)}
                    disabled={provider.is_builtin}
                    className={`p-1 text-gray-400 rounded transition-colors ${
                      provider.is_builtin ? 'opacity-30 cursor-not-allowed' : 'hover:text-red-600 hover:bg-red-50'
                    }`}
                    title={provider.is_builtin ? '内置服务商不可删除' : '删除'}
                  >
                    <TrashIcon />
                  </button>
                )}
              </div>
            </div>

            {testResult[provider.id] && (
              <div className="px-4 pb-2 text-xs text-green-600">{testResult[provider.id]}</div>
            )}

            {expandedId === provider.id && (
              <div className="px-4 pb-4 border-t border-gray-100 pt-3">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium text-gray-700">可用模型</h4>
                  <button
                    onClick={() => ensureNewModelForm(provider.id)}
                    className="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
                  >
                    手动添加模型
                  </button>
                </div>

                {newModelForm[provider.id] && (
                  <div className="flex gap-2 mb-3 p-3 bg-gray-50 rounded-lg">
                    <input
                      autoFocus
                      value={newModelForm[provider.id].model_id}
                      onChange={e => setNewModelForm(prev => ({
                        ...prev,
                        [provider.id]: { ...prev[provider.id], model_id: e.target.value },
                      }))}
                      placeholder="模型 ID (如 gpt-4o)"
                      className="flex-1 px-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <input
                      value={newModelForm[provider.id].display_name}
                      onChange={e => setNewModelForm(prev => ({
                        ...prev,
                        [provider.id]: { ...prev[provider.id], display_name: e.target.value },
                      }))}
                      placeholder="显示名称"
                      className="w-36 px-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                      onClick={() => {
                        const m = newModelForm[provider.id]
                        if (!m.model_id.trim()) return
                        addModelMutation.mutate({ providerId: provider.id, data: { model_id: m.model_id.trim(), display_name: m.display_name.trim() || undefined } })
                      }}
                      disabled={!newModelForm[provider.id].model_id.trim() || addModelMutation.isPending}
                      className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      添加
                    </button>
                    <button
                      onClick={() => setNewModelForm(prev => { const n = { ...prev }; delete n[provider.id]; return n })}
                      className="px-2 py-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                    >
                      取消
                    </button>
                  </div>
                )}

                {provider.models?.length === 0 && !newModelForm[provider.id] && (
                  <p className="text-xs text-gray-400 py-2">暂无模型</p>
                )}

                <div className="space-y-1">
                  {provider.models?.map(model => (
                    <div key={model.id} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-gray-50">
                      <span className="text-sm text-gray-700 flex-1">{model.display_name}</span>
                      <span className="text-xs text-gray-400">{model.model_id}</span>
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={model.enabled}
                          onChange={e => updateModelMutation.mutate({
                            providerId: provider.id,
                            modelId: model.id,
                            data: { enabled: e.target.checked },
                          })}
                          className="w-3.5 h-3.5 text-indigo-600 rounded"
                        />
                        <span className="text-xs text-gray-500">启用</span>
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
