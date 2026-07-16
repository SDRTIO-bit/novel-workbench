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
  const [manualMode, setManualMode] = useState<{ show: boolean; defaultText: string }>({ show: false, defaultText: '' })
  const [manualText, setManualText] = useState('')

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
    mutationFn: ({ acceptType, finalText }: { acceptType: string; finalText?: string }) =>
      runsApi.acceptFinal(runId!, acceptType, finalText),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['run', runId] })
      setRunId(null)
      setManualMode({ show: false, defaultText: '' })
      setManualText('')
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
        <AcceptChoices
          run={run}
          acceptMutation={acceptMutation}
          manualMode={manualMode}
          setManualMode={setManualMode}
          manualText={manualText}
          setManualText={setManualText}
        />
      )}
    </div>
  )
}

function AcceptChoices({
  run,
  acceptMutation,
  manualMode,
  setManualMode,
  manualText,
  setManualText,
}: {
  run: GenerationRun
  acceptMutation: { mutate: (v: { acceptType: string; finalText?: string }) => void; isPending: boolean }
  manualMode: { show: boolean; defaultText: string }
  setManualMode: (v: { show: boolean; defaultText: string }) => void
  manualText: string
  setManualText: (v: string) => void
}) {
  const hasJudge = run.steps.some((s) => s.stage === 'judge' && s.candidates.some((c) => c.is_selected && c.parsed_output_json))
  const hasReviser = run.steps.some((s) => s.stage === 'reviser' && s.candidates.some((c) => c.is_selected && c.text_output))

  const getDefaultText = () => {
    const reviser = run.steps.find((s) => s.stage === 'reviser')
    const writer = run.steps.find((s) => s.stage === 'writer')
    if (reviser) {
      const rev = reviser.candidates.find((c) => c.is_selected)
      if (rev?.text_output) return rev.text_output
    }
    if (writer) {
      const wr = writer.candidates.find((c) => c.is_selected)
      if (wr?.text_output) return wr.text_output
    }
    return ''
  }

  const openManual = () => {
    setManualMode({ show: true, defaultText: getDefaultText() })
    setManualText(getDefaultText())
  }

  if (manualMode.show) {
    return (
      <div className="p-3 border-t border-gray-200 bg-white shrink-0">
        <p className="text-xs font-medium text-gray-600 mb-2">手动编辑最终文本:</p>
        <textarea
          value={manualText}
          onChange={(e) => setManualText(e.target.value)}
          className="w-full px-3 py-2 text-xs border border-gray-300 rounded-lg resize-y focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
          rows={12}
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => setManualMode({ show: false, defaultText: '' })}
            className="flex-1 px-3 py-1.5 text-xs font-medium bg-white text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            取消
          </button>
          <button
            onClick={() => acceptMutation.mutate({ acceptType: 'manual', finalText: manualText })}
            disabled={acceptMutation.isPending || !manualText.trim()}
            className="flex-1 px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {acceptMutation.isPending ? '提交中...' : '确认采用'}
          </button>
        </div>
      </div>
    )
  }

  if (hasJudge) {
    const judgeStep = run.steps.find((s) => s.stage === 'judge')!
    const candidate = judgeStep.candidates.find((c) => c.is_selected)
    let decision = ''
    if (candidate?.parsed_output_json) {
      let parsed = candidate.parsed_output_json
      if (typeof parsed === 'string') {
        try { parsed = JSON.parse(parsed) } catch { /* */ }
      }
      decision = String((parsed as Record<string, unknown>).decision ?? '')
    }

    const buttons: { type: string; label: string }[] = [
      { type: 'original', label: '保留初稿' },
    ]
    if (hasReviser) {
      buttons.push({ type: 'revision', label: '采用修订稿' })
    }
    if (decision === 'accept_merged') {
      buttons.push({ type: 'judge', label: '采纳合并稿' })
    }
    buttons.push({ type: 'manual', label: '手动编辑...' })

    return (
      <div className="p-3 border-t border-gray-200 bg-white shrink-0">
        <p className="text-xs font-medium text-gray-500 mb-2">选择最终版本:</p>
        <div className="grid grid-cols-2 gap-2">
          {buttons.map((b) => (
            <button
              key={b.type}
              onClick={() => {
                if (b.type === 'manual') {
                  openManual()
                } else {
                  acceptMutation.mutate({ acceptType: b.type })
                }
              }}
              disabled={acceptMutation.isPending}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50"
              style={
                b.type === decision
                  ? { background: '#eef2ff', borderColor: '#6366f1', color: '#4338ca' }
                  : { background: '#fff', borderColor: '#d1d5db', color: '#374151' }
              }
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="p-3 border-t border-gray-200 bg-white shrink-0">
      <div className="flex gap-2">
        <button
          onClick={() => acceptMutation.mutate({ acceptType: 'original' })}
          disabled={acceptMutation.isPending}
          className="flex-1 px-3 py-2 text-xs font-medium bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {acceptMutation.isPending ? '...' : '保留初稿'}
        </button>
        {hasReviser && (
          <button
              onClick={() => acceptMutation.mutate({ acceptType: 'revision' })}
            disabled={acceptMutation.isPending}
            className="flex-1 px-3 py-2 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {acceptMutation.isPending ? '...' : '采用修订稿'}
          </button>
        )}
      </div>
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

const JUDGE_STATUS_LABELS: Record<string, string> = {
  resolved: '已解决',
  unresolved: '未解决',
  revision_worse: '修订后退步',
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
  const issueResults = obj.issue_results as Array<Record<string, unknown>> | undefined

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
          {issueResults.map((ir, i) => {
            const status = String(ir.status ?? '')
            const statusLabel = JUDGE_STATUS_LABELS[status] ?? status
            const resolvedColor = status === 'resolved' ? 'bg-green-500' : status === 'unresolved' ? 'bg-red-400' : 'bg-yellow-400'
            return (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-600">
                <span className={`w-1.5 h-1.5 rounded-full ${resolvedColor}`} />
                <span className="truncate">{String(ir.issue_id ?? `#${i + 1}`)}</span>
                <span>{statusLabel}</span>
                {!!ir.comment && <span className="text-gray-400">— {String(ir.comment)}</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
