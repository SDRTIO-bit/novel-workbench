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

      {renderJudgeVerdict(run)}
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

const JUDGE_LABELS: Record<string, string> = {
  accept_original: '建议保留初稿',
  accept_revision: '建议采用修订稿',
  accept_merged: '建议合并',
  manual_review: '需要人工判断',
}

function renderJudgeVerdict(run: GenerationRun) {
  const judgeStep = run.steps.find((s) => s.stage === 'judge')
  const judgeCandidate = judgeStep?.candidates.find((c) => c.is_selected)
  if (!judgeCandidate?.parsed_output_json) return null

  let parsed: unknown = judgeCandidate.parsed_output_json
  if (typeof parsed === 'string') {
    try { parsed = JSON.parse(parsed) } catch { return null }
  }
  const obj = parsed as Record<string, unknown>
  const decision = String(obj.decision ?? '')
  const label = JUDGE_LABELS[decision] ?? decision
  const issueResults = obj.issue_results as unknown[] | undefined

  return (
    <div className="p-3 border-t border-gray-200 bg-white shrink-0">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-medium text-gray-600">审稿决策:</span>
        <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-indigo-100 text-indigo-700">
          {label || '暂无判决'}
        </span>
      </div>
      {issueResults && issueResults.length > 0 && (
        <div className="space-y-1 mt-1">
          <p className="text-xs font-medium text-gray-500">问题处理结果:</p>
          {issueResults.map((r, i) => {
            const ir = r as Record<string, unknown>
            return (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-600">
                <span className={`w-1.5 h-1.5 rounded-full ${ir.is_resolved ? 'bg-green-500' : 'bg-red-400'}`} />
                <span className="truncate">{String(ir.issue_id ?? `#${i + 1}`)}</span>
                <span>{ir.is_resolved ? '已解决' : '未解决'}</span>
                {!!ir.note && <span className="text-gray-400">— {String(ir.note)}</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
