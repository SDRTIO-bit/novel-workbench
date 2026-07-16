import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { GenerationRun } from '../../types'
import { STAGES } from '../../types'
import * as runsApi from '../../api/runs'
import StageStepper from './StageStepper'
import StagePanel from './StagePanel'

interface Props {
  projectId: string
  chapterId: string | null
  onAccept: () => void
}

export default function WorkflowPanel({ projectId, chapterId, onAccept }: Props) {
  const queryClient = useQueryClient()
  const [runId, setRunId] = useState<string | null>(null)
  const [instruction, setInstruction] = useState('')

  const { data: run } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.getRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 2000 : false,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      runsApi.createRun({
        project_id: projectId,
        chapter_id: chapterId || undefined,
        scene_instruction: instruction.trim(),
      }),
    onSuccess: (newRun) => {
      setRunId(newRun.id)
      setInstruction('')
    },
  })

  const acceptMutation = useMutation({
    mutationFn: () => runsApi.acceptFinal(runId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['run', runId] })
      setRunId(null)
      onAccept()
    },
  })

  if (!runId) {
    return (
      <div className="p-4">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="输入场景要求..."
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500"
          rows={4}
        />
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending || !instruction.trim()}
          className="mt-3 w-full px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {createMutation.isPending ? '创建中...' : '新建场景生成'}
        </button>
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-3 border-gray-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    )
  }

  const currentStage = findCurrentStage(run)

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200 bg-white shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-gray-500">场景要求:</p>
            <p className="text-xs text-gray-800 truncate">{run.scene_instruction}</p>
          </div>
          <button
            onClick={() => setRunId(null)}
            className="ml-2 px-2 py-1 text-xs text-gray-400 hover:text-gray-600 shrink-0"
          >
            关闭
          </button>
        </div>

        <StageStepper run={run} currentStage={currentStage} />
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {STAGES.map((stage) => {
          const step = run.steps.find((s) => s.stage === stage)
          if (!step) {
            return (
              <div
                key={stage}
                className="p-3 bg-white rounded-xl border border-gray-200 shadow-sm opacity-50"
              >
                <p className="text-xs text-gray-400 italic">阶段尚未初始化</p>
              </div>
            )
          }
          return <StagePanel key={stage} runId={run.id} stage={stage} step={step} />
        })}
      </div>

      {writerHasOutput(run) && (
        <div className="p-3 border-t border-gray-200 bg-white shrink-0">
          <button
            onClick={() => acceptMutation.mutate()}
            disabled={acceptMutation.isPending}
            className="w-full px-4 py-2 text-sm font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {acceptMutation.isPending ? '接受中...' : '采用生成结果'}
          </button>
        </div>
      )}
    </div>
  )
}

function findCurrentStage(run: GenerationRun) {
  for (const stage of STAGES) {
    const step = run.steps.find((s) => s.stage === stage)
    if (step?.status === 'running') return stage
  }
  for (let i = STAGES.length - 1; i >= 0; i--) {
    const step = run.steps.find((s) => s.stage === STAGES[i])
    if (step?.status === 'completed') return STAGES[i]
  }
  return null
}

function writerHasOutput(run: GenerationRun) {
  const step = run.steps.find((s) => s.stage === 'writer')
  return step?.candidates?.some((c) => c.is_selected && c.text_output)
}
