import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Stage, GenerationStep, GenerationCandidate, Provider } from '../../types'
import { STAGE_LABELS } from '../../types'
import { REVISION_OPERATIONS, type RevisionOperation } from '../../types/generation'
import * as runsApi from '../../api/runs'
import { listProviders } from '../../api/providers'
import CandidateView from './CandidateView'

interface Props {
  runId: string
  stage: Stage
  step: GenerationStep
}

interface PreviewData {
  rendered_system_prompt: string
  rendered_user_prompt: string
}

const REVISION_OPERATION_LABELS: Record<RevisionOperation, string> = {
  naturalize: '自然化',
  tighten: '删冗聚焦',
  clarify: '信息清理',
  voice_align: '角色语气',
  ground_detail: '补足有效细节',
  rhythm_adjust: '节奏校准',
  diction_refine: '用词校准',
  project_style_align: '项目文风对齐',
  withhold_inference: '删除解释',
  causalize: '因果化',
  de_label: '去标签',
  de_chain: '打断传送带',
}

export default function StagePanel({ runId, stage, step }: Props) {
  const queryClient = useQueryClient()
  const [override, setOverride] = useState('')
  const [preview, setPreview] = useState<PreviewData | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set())
  const [operationByIssue, setOperationByIssue] = useState<Record<string, RevisionOperation>>({})

  const [showAdvanced, setShowAdvanced] = useState(false)
  const [advanced, setAdvanced] = useState({
    providerId: '',
    modelId: '',
    promptVersionId: '',
    temperature: NaN,
    topP: NaN,
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['run', runId] })

  const buildOverride = () => ({
    run_override: override.trim() || undefined,
    provider_id: advanced.providerId || undefined,
    model_id: advanced.modelId || undefined,
    prompt_version_id: advanced.promptVersionId || undefined,
    temperature: isNaN(advanced.temperature) ? undefined : advanced.temperature,
    top_p: isNaN(advanced.topP) ? undefined : advanced.topP,
  })

  const executeMutation = useMutation({
    mutationFn: () => runsApi.executeStage(runId, stage, buildOverride()),
    onSuccess: () => { invalidate(); setOverride('') },
  })

  const previewMutation = useMutation({
    mutationFn: () => runsApi.previewStage(runId, stage, buildOverride()),
    onSuccess: (data) => { setPreview(data as PreviewData); setShowPreview(true) },
  })

  const selectMutation = useMutation({
    mutationFn: (candidateId: string) => runsApi.selectCandidate(runId, stage, candidateId),
    onSuccess: () => invalidate(),
  })

  const issuesMutation = useMutation({
    mutationFn: () => {
      const issueIds = Array.from(selectedIssues)
      const operations = Object.fromEntries(
        issueIds.map((issueId) => [issueId, operationByIssue[issueId]]),
      ) as Record<string, RevisionOperation>
      return runsApi.selectIssues(runId, {
        issue_ids: issueIds,
        operation_by_issue: operations,
      })
    },
    onSuccess: () => { invalidate(); setSelectedIssues(new Set()) },
  })

  const statusColor =
    step.status === 'completed'
      ? 'bg-green-100 text-green-700'
      : step.status === 'running'
        ? 'bg-blue-100 text-blue-700'
        : step.status === 'failed'
          ? 'bg-red-100 text-red-700'
          : 'bg-gray-100 text-gray-500'

  const selectedCandidate = step.candidates.find((c) => c.is_selected)
  const issues = stage === 'critic' ? parseIssues(selectedCandidate) : null
  const structuredOutput = parseStructuredOutput(selectedCandidate)

  useEffect(() => {
    setSelectedIssues(new Set())
    setOperationByIssue({})
  }, [selectedCandidate?.id])

  return (
    <div className="p-3 bg-white rounded-xl border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-800">{STAGE_LABELS[stage]}</h3>
          <span className={`px-1.5 py-0.5 text-xs rounded-full ${statusColor}`}>
            {step.status}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {!previewMutation.isPending ? (
            <button
              onClick={() => previewMutation.mutate()}
              className="px-2.5 py-1 text-xs text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
            >
              预览上下文
            </button>
          ) : (
            <span className="text-xs text-gray-400">加载中...</span>
          )}
          <button
            onClick={() => executeMutation.mutate()}
            disabled={executeMutation.isPending}
            className="px-3 py-1 text-xs font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {executeMutation.isPending ? '执行中...' : step.status === 'failed' ? '重试' : '执行'}
          </button>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className={`px-2 py-1 text-xs rounded transition-colors ${showAdvanced ? 'bg-gray-200 text-gray-700' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}`}
          >
            ⚙ 高级
          </button>
        </div>
      </div>

      <textarea
        value={override}
        onChange={(e) => setOverride(e.target.value)}
        placeholder="此次附加要求（可选）..."
        className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-indigo-400 mb-3"
        rows={2}
      />

      {structuredOutput && <CausalSummary stage={stage} output={structuredOutput} />}

      {showAdvanced && (
        <div className="mb-3 p-3 border border-gray-200 rounded-lg bg-gray-50">
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-gray-600">
              提供商
              <select
                value={advanced.providerId}
                onChange={(e) => setAdvanced((a) => ({ ...a, providerId: e.target.value }))}
                className="mt-0.5 w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-white"
              >
                <option value="">默认</option>
                {providers?.map((p: Provider) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-gray-600">
              模型
              <input
                value={advanced.modelId}
                onChange={(e) => setAdvanced((a) => ({ ...a, modelId: e.target.value }))}
                placeholder="默认"
                className="mt-0.5 w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-white"
              />
            </label>
            <label className="text-xs text-gray-600">
              Prompt 版本
              <input
                value={advanced.promptVersionId}
                onChange={(e) => setAdvanced((a) => ({ ...a, promptVersionId: e.target.value }))}
                placeholder="默认"
                className="mt-0.5 w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-indigo-400 bg-white"
              />
            </label>
            <label className="text-xs text-gray-600">
              温度 ({isNaN(advanced.temperature) ? '-' : advanced.temperature.toFixed(1)})
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={isNaN(advanced.temperature) ? 1 : advanced.temperature}
                onChange={(e) => setAdvanced((a) => ({ ...a, temperature: parseFloat(e.target.value) }))}
                className="mt-0.5 w-full h-1 accent-indigo-600"
              />
            </label>
            <label className="text-xs text-gray-600 col-span-2">
              Top P ({isNaN(advanced.topP) ? '-' : advanced.topP.toFixed(2)})
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={isNaN(advanced.topP) ? 1 : advanced.topP}
                onChange={(e) => setAdvanced((a) => ({ ...a, topP: parseFloat(e.target.value) }))}
                className="mt-0.5 w-full h-1 accent-indigo-600"
              />
            </label>
          </div>
        </div>
      )}

      {showPreview && preview && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-gray-600">上下文预览</span>
            <button
              onClick={() => setShowPreview(false)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              收起
            </button>
          </div>
          <div className="space-y-2">
            <PreviewBlock label="System Prompt" content={preview.rendered_system_prompt} />
            <PreviewBlock label="User Prompt" content={preview.rendered_user_prompt} />
          </div>
        </div>
      )}

      {issues && issues.length > 0 && (
        <div className="mb-3 p-2 bg-amber-50 rounded-lg border border-amber-200">
          <p className="text-xs font-medium text-amber-800 mb-1.5">选择问题:</p>
          <div className="space-y-1">
            {issues.map((issue) => {
              const isChecked = selectedIssues.has(issue.id)
              return (
                <div key={issue.id} className="rounded border border-amber-100 bg-white/60 p-2">
                  <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
                    <input
                      type="checkbox"
                      aria-label={`选择 ${issue.id}`}
                      checked={isChecked}
                      onChange={() => {
                        setSelectedIssues((prev) => {
                          const next = new Set(prev)
                          if (next.has(issue.id)) {
                            next.delete(issue.id)
                            setOperationByIssue((operations) => {
                              const nextOperations = { ...operations }
                              delete nextOperations[issue.id]
                              return nextOperations
                            })
                          } else {
                            next.add(issue.id)
                            setOperationByIssue((operations) => ({
                              ...operations,
                              [issue.id]: issue.recommendedOperation,
                            }))
                          }
                          return next
                        })
                      }}
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="font-medium">{issue.id}</span>
                    <span>{issue.description}</span>
                  </label>
                  {isChecked && (
                    <label className="mt-2 flex items-center gap-2 text-xs text-amber-900">
                      修订操作
                      <select
                        aria-label={`修订操作 ${issue.id}`}
                        value={operationByIssue[issue.id] ?? issue.recommendedOperation}
                        onChange={(event) => setOperationByIssue((operations) => ({
                          ...operations,
                          [issue.id]: event.target.value as RevisionOperation,
                        }))}
                        className="rounded border border-amber-200 bg-white px-2 py-1 text-xs"
                      >
                        {REVISION_OPERATIONS.map((operation) => (
                          <option key={operation} value={operation}>
                            {REVISION_OPERATION_LABELS[operation]}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              )
            })}
          </div>
          <button
            onClick={() => issuesMutation.mutate()}
            disabled={selectedIssues.size === 0 || issuesMutation.isPending}
            className="mt-2 px-3 py-1 text-xs font-medium bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 transition-colors"
          >
            {issuesMutation.isPending ? '确认中...' : '确认问题'}
          </button>
        </div>
      )}

      {step.candidates.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500">
            候选结果 ({step.candidates.length})
          </p>
          {step.candidates.map((c) => (
            <CandidateView
              key={c.id}
              candidate={c}
              stage={stage}
              isSelected={c.is_selected}
              onSelect={() => selectMutation.mutate(c.id)}
            />
          ))}
        </div>
      )}

      {step.candidates.length === 0 && (
        <p className="text-xs text-gray-400 italic">尚无候选结果，点击"执行"开始生成</p>
      )}
    </div>
  )
}

function PreviewBlock({ label, content }: { label: string; content?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-gray-200 rounded overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-2 py-1 text-xs font-medium text-gray-500 bg-gray-50 hover:bg-gray-100"
      >
        {label}
        <span>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <pre className="p-2 text-xs whitespace-pre-wrap max-h-48 overflow-y-auto bg-gray-900 text-green-300">
          {content || '(空)'}
        </pre>
      )}
    </div>
  )
}

function parseIssues(candidate?: GenerationCandidate): { id: string; description: string; recommendedOperation: RevisionOperation }[] {
  if (!candidate?.parsed_output_json) return []
  try {
    let parsed: unknown = candidate.parsed_output_json
    if (typeof parsed === 'string') {
      parsed = JSON.parse(parsed)
    }
    const obj = parsed as Record<string, unknown>
    const list = Array.isArray(obj)
      ? obj
      : Array.isArray(obj.issues)
        ? obj.issues
        : null
    if (!Array.isArray(list)) return []
    return list
      .map((item: unknown, idx: number) => {
        if (item && typeof item === 'object') {
          const itemObj = item as Record<string, unknown>
          const recommendedOperation = itemObj.recommended_operation
          if (!isRevisionOperation(recommendedOperation)) return null
          return {
            id: String(itemObj.issue_id ?? itemObj.id ?? `issue-${idx}`),
            description: String(itemObj.problem ?? itemObj.description ?? itemObj.title ?? JSON.stringify(item)),
            recommendedOperation,
          }
        }
        return null
      })
      .filter((issue): issue is { id: string; description: string; recommendedOperation: RevisionOperation } => Boolean(issue?.description))
  } catch {
    return []
  }
}

function isRevisionOperation(value: unknown): value is RevisionOperation {
  return typeof value === 'string' && (REVISION_OPERATIONS as readonly string[]).includes(value)
}

function parseStructuredOutput(candidate?: GenerationCandidate): Record<string, unknown> | null {
  if (!candidate?.parsed_output_json) return null
  try {
    const parsed = typeof candidate.parsed_output_json === 'string'
      ? JSON.parse(candidate.parsed_output_json)
      : candidate.parsed_output_json
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null
  } catch {
    return null
  }
}

function CausalSummary({ stage, output }: { stage: Stage; output: Record<string, unknown> }) {
  if (stage === 'planner') return <PlannerCausalCards transitions={asRecords(output.causal_transitions)} />
  if (stage === 'critic') return <CriticCausalAudit checks={asRecords(output.causal_transition_check)} protectedStrengths={asRecords(output.protected_strengths)} />
  if (stage === 'judge') return <JudgeCausalVerdict output={output} />
  return null
}

function PlannerCausalCards({ transitions }: { transitions: Record<string, unknown>[] }) {
  if (transitions.length === 0) return null
  return (
    <section className="mb-3 rounded-lg border border-indigo-200 bg-indigo-50 p-2">
      <p className="mb-2 text-xs font-medium text-indigo-800">因果转折</p>
      <div className="space-y-2">
        {transitions.map((transition, index) => {
          const kind = String(transition.kind ?? '')
          return (
            <div key={String(transition.id ?? index)} className="rounded border border-indigo-100 bg-white p-2 text-xs text-gray-700">
              <p className="font-medium text-indigo-700">{kind === 'evidence_to_action' ? '证据 → 行动' : '约束 → 选择'} {transition.id ? `· ${String(transition.id)}` : ''}</p>
              <CausalLine label="可见触发" value={transition.visible_trigger} />
              <CausalLine label="人物下一步" value={transition.character_next_action} />
              <CausalLine label="留给读者的推论" value={transition.reader_must_infer} />
              <CausalLine label="立即后果" value={transition.immediate_consequence} />
              <CausalLine label="新约束" value={transition.next_constraint} />
            </div>
          )
        })}
      </div>
    </section>
  )
}

function CriticCausalAudit({ checks, protectedStrengths }: { checks: Record<string, unknown>[]; protectedStrengths: Record<string, unknown>[] }) {
  if (checks.length === 0 && protectedStrengths.length === 0) return null
  return (
    <section className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 p-2 text-xs">
      {checks.length > 0 && <>
        <p className="mb-1 font-medium text-emerald-800">因果转折审计</p>
        {checks.map((check, index) => <p key={String(check.transition_id ?? index)} className="text-emerald-700">{String(check.transition_id ?? `CT${index + 1}`)}：{auditLabel(check.result)} {check.comment ? `— ${String(check.comment)}` : ''}</p>)}
      </>}
      {protectedStrengths.length > 0 && <p className="mt-1 text-emerald-700">受保护段落：{protectedStrengths.map((strength) => displayParagraphs(strength.paragraph_ids ?? strength.paragraph_id)).filter(Boolean).join('；')}</p>}
    </section>
  )
}

function JudgeCausalVerdict({ output }: { output: Record<string, unknown> }) {
  const lost = output.necessary_information_lost === true
  const results = asRecords(output.causal_transition_results)
  const hasFlags = ['reader_inference_preserved', 'decision_consequence_preserved', 'narrator_management_reduced', 'necessary_information_lost'].some((key) => key in output)
  if (!hasFlags && results.length === 0) return null
  return (
    <section className={`mb-3 rounded-lg border p-2 text-xs ${lost ? 'border-red-300 bg-red-50 text-red-800' : 'border-blue-200 bg-blue-50 text-blue-800'}`}>
      {lost && <p className="font-medium">修订稿丢失必要信息</p>}
      {hasFlags && <p>{flagText('读者推论保留', output.reader_inference_preserved)} · {flagText('选择后果保留', output.decision_consequence_preserved)} · {flagText('叙述者管理减少', output.narrator_management_reduced)}</p>}
      {results.map((result, index) => <p key={String(result.transition_id ?? index)} className="mt-1">{String(result.transition_id ?? `CT${index + 1}`)}：原稿 {String(result.original_status ?? '-')} / 修订 {String(result.revision_status ?? '-')}，建议 {preferredLabel(result.preferred_version)}</p>)}
    </section>
  )
}

function CausalLine({ label, value }: { label: string; value: unknown }) {
  if (!value) return null
  return <p className="mt-1"><span className="text-gray-500">{label}：</span>{String(value)}</p>
}

function asRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : []
}

function auditLabel(value: unknown) { return value === 'pass' ? '通过' : value === 'fail' ? '未通过' : value === 'not_present' ? '未呈现' : String(value ?? '-') }
function preferredLabel(value: unknown) { return value === 'original' ? '保留原稿' : value === 'revision' ? '采用修订' : value === 'manual_review' ? '人工判断' : String(value ?? '-') }
function flagText(label: string, value: unknown) { return `${label}${value === true ? '✓' : value === false ? '✕' : '—'}` }
function displayParagraphs(value: unknown) { return Array.isArray(value) ? value.map(String).join(', ') : value ? String(value) : '' }
