import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import * as runsApi from '../api/runs'
import { STAGE_LABELS } from '../types'
import type { GenerationRunList } from '../types'

export default function RunHistoryPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [expandedRun, setExpandedRun] = useState<string | null>(null)

  const { data: runs, isLoading } = useQuery({
    queryKey: ['runs', projectId],
    queryFn: () => runsApi.listRuns(projectId!),
    enabled: !!projectId,
  })

  const { data: expandedRunData } = useQuery({
    queryKey: ['run', expandedRun],
    queryFn: () => runsApi.getRun(expandedRun!),
    enabled: !!expandedRun,
  })

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-spin rounded-full h-6 w-6 border-2 border-indigo-600 border-t-transparent mx-auto" />
      </div>
    )
  }

  const runsList = runs || []

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-gray-600">
            ← 返回
          </button>
          <h1 className="text-xl font-bold">运行历史</h1>
        </div>
      </div>

      {runsList.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-400">暂无运行记录</p>
        </div>
      ) : (
        <div className="space-y-2">
          {runsList.map((run: GenerationRunList) => (
            <div
              key={run.id}
              className="bg-white rounded-lg border border-gray-200 overflow-hidden"
            >
              <button
                onClick={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-50"
              >
                <div>
                  <p className="text-sm font-medium text-gray-800 truncate max-w-md">
                    {run.scene_instruction || '（无场景要求）'}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {new Date(run.created_at).toLocaleString('zh-CN')}
                  </p>
                </div>
                <span
                  className={`px-2 py-0.5 text-xs rounded-full ${
                    run.status === 'completed'
                      ? 'bg-green-100 text-green-700'
                      : run.status === 'running'
                        ? 'bg-blue-100 text-blue-700'
                        : run.status === 'failed'
                          ? 'bg-red-100 text-red-700'
                          : run.status === 'cancelled'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {run.status}
                </span>
              </button>

              {expandedRun === run.id && expandedRunData?.steps && (
                <div className="border-t border-gray-100 px-4 py-3 bg-gray-50">
                  {expandedRunData.steps.map((step) => (
                    <div key={step.id} className="mb-2 last:mb-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-700">
                          {STAGE_LABELS[step.stage as keyof typeof STAGE_LABELS]}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 text-xs rounded-full ${
                            step.status === 'completed'
                              ? 'bg-green-100 text-green-700'
                              : step.status === 'failed'
                                ? 'bg-red-100 text-red-700'
                                : step.status === 'stale'
                                  ? 'bg-yellow-100 text-yellow-700'
                                  : 'bg-gray-100 text-gray-500'
                          }`}
                        >
                          {step.status}
                        </span>
                        {step.candidates && step.candidates.length > 0 && (
                          <span className="text-xs text-gray-400">
                            {step.candidates.length} 个候选
                          </span>
                        )}
                      </div>
                      {step.candidates?.map((c) => (
                        <div
                          key={c.id}
                          className={`ml-4 mb-1 p-2 rounded text-xs border ${
                            c.error_code
                              ? 'bg-red-50 border-red-100'
                              : c.is_selected
                                ? 'bg-green-50 border-green-200'
                                : 'bg-white border-gray-100'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-gray-500">#{c.attempt_number}</span>
                            {c.model_id && (
                              <span className="text-gray-400">{c.model_id}</span>
                            )}
                            {c.error_code ? (
                              <span className="text-red-600">{c.error_code}: {c.error_message}</span>
                            ) : (
                              <>
                                <span className="text-gray-400">
                                  输入 {c.input_tokens}t 输出 {c.output_tokens}t
                                </span>
                                <span className="text-gray-400">{c.latency_ms}ms</span>
                              </>
                            )}
                            {c.is_selected && (
                              <span className="text-green-600 font-medium">✓ 已选</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
