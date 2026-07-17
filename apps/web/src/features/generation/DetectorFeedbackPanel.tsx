import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  DetectorFeedback,
  DetectorFeedbackCreate,
  DetectorSpan,
  GenerationRun,
} from '../../types'
import * as detectorFeedbacksApi from '../../api/detectorFeedbacks'

interface Props {
  projectId: string
  chapterId: string | null
  run: GenerationRun
}

interface SpanDraft {
  label: string
  start: string
  end: string
  transitionIds: string
  excerpt: string
}

const emptySpan = (): SpanDraft => ({ label: 'human', start: '', end: '', transitionIds: '', excerpt: '' })

export default function DetectorFeedbackPanel({ projectId, chapterId, run }: Props) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const targets = useMemo(() => feedbackTargets(run), [run])
  const [target, setTarget] = useState(targets[0]?.value ?? '')
  const [detectorName, setDetectorName] = useState('')
  const [humanRatio, setHumanRatio] = useState('')
  const [suspectedRatio, setSuspectedRatio] = useState('')
  const [aiRatio, setAiRatio] = useState('')
  const [notes, setNotes] = useState('')
  const [spans, setSpans] = useState<SpanDraft[]>([])
  const [editing, setEditing] = useState<DetectorFeedback | null>(null)

  const queryKey = ['detector-feedbacks', projectId, chapterId]
  const { data: feedbacks = [] } = useQuery({
    queryKey,
    queryFn: () => detectorFeedbacksApi.listDetectorFeedbacks(projectId, chapterId ?? undefined),
    enabled: open,
  })

  const reset = () => {
    setTarget(targets[0]?.value ?? '')
    setDetectorName('')
    setHumanRatio('')
    setSuspectedRatio('')
    setAiRatio('')
    setNotes('')
    setSpans([])
    setEditing(null)
  }

  const createMutation = useMutation({
    mutationFn: (data: DetectorFeedbackCreate) => detectorFeedbacksApi.createDetectorFeedback(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey }); reset() },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Omit<DetectorFeedbackCreate, 'project_id' | 'chapter_id' | 'run_id' | 'candidate_id' | 'chapter_version_id'> }) =>
      detectorFeedbacksApi.updateDetectorFeedback(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey }); reset() },
  })
  const deleteMutation = useMutation({
    mutationFn: detectorFeedbacksApi.deleteDetectorFeedback,
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  })

  const submit = () => {
    const reference = targetReference(target)
    if (!reference || !detectorName.trim()) return
    const data = {
      detector_name: detectorName.trim(),
      human_ratio: optionalNumber(humanRatio),
      suspected_ai_ratio: optionalNumber(suspectedRatio),
      ai_ratio: optionalNumber(aiRatio),
      spans: spansToPayload(spans),
      notes: notes.trim(),
    }
    if (editing) {
      updateMutation.mutate({ id: editing.id, data })
      return
    }
    createMutation.mutate({
      project_id: projectId,
      chapter_id: chapterId ?? undefined,
      run_id: run.id,
      ...reference,
      ...data,
    })
  }

  const beginEdit = (feedback: DetectorFeedback) => {
    setEditing(feedback)
    setTarget(feedback.candidate_id ? `candidate:${feedback.candidate_id}` : `version:${feedback.chapter_version_id}`)
    setDetectorName(feedback.detector_name)
    setHumanRatio(stringValue(feedback.human_ratio))
    setSuspectedRatio(stringValue(feedback.suspected_ai_ratio))
    setAiRatio(stringValue(feedback.ai_ratio))
    setNotes(feedback.notes)
    setSpans(parseSpans(feedback.spans_json))
  }

  return (
    <section className="border-t border-gray-200 bg-white shrink-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="w-full px-3 py-2 text-left text-xs font-medium text-gray-600 hover:bg-gray-50"
      >
        {open ? '收起外部检测反馈' : '展开外部检测反馈'}
      </button>
      {open && (
        <div className="space-y-3 px-3 pb-3">
          <p className="text-xs text-gray-500">仅保存外部结果用于对照，不会自动触发改稿。</p>
          <label className="block text-xs text-gray-600">
            检测对象
            <select aria-label="检测对象" value={target} onChange={(event) => setTarget(event.target.value)} disabled={Boolean(editing)} className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs">
              {targets.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="block text-xs text-gray-600">
            检测器名称
            <input aria-label="检测器名称" value={detectorName} onChange={(event) => setDetectorName(event.target.value)} className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs" />
          </label>
          <div className="grid grid-cols-3 gap-2">
            <RatioInput label="人工特征比例" value={humanRatio} onChange={setHumanRatio} />
            <RatioInput label="疑似 AI 比例" value={suspectedRatio} onChange={setSuspectedRatio} />
            <RatioInput label="AI 特征比例" value={aiRatio} onChange={setAiRatio} />
          </div>
          <label className="block text-xs text-gray-600">
            备注
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} className="mt-1 w-full resize-none rounded border border-gray-300 px-2 py-1 text-xs" />
          </label>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-gray-600">人工区间（可选）</span>
              <button type="button" onClick={() => setSpans((items) => [...items, emptySpan()])} className="text-xs text-indigo-600">添加区间</button>
            </div>
            {spans.map((span, index) => (
              <div key={index} className="grid grid-cols-2 gap-1 rounded border border-gray-200 p-2">
                <input aria-label={`区间 ${index + 1} 起始段落`} type="number" min="1" value={span.start} onChange={(event) => setSpans((items) => replaceSpan(items, index, { start: event.target.value }))} placeholder="起始段落" className="rounded border border-gray-300 px-1 py-1 text-xs" />
                <input aria-label={`区间 ${index + 1} 结束段落`} type="number" min="1" value={span.end} onChange={(event) => setSpans((items) => replaceSpan(items, index, { end: event.target.value }))} placeholder="结束段落" className="rounded border border-gray-300 px-1 py-1 text-xs" />
                <input value={span.transitionIds} onChange={(event) => setSpans((items) => replaceSpan(items, index, { transitionIds: event.target.value }))} placeholder="关联转折，如 CT01" className="col-span-2 rounded border border-gray-300 px-1 py-1 text-xs" />
                <button type="button" onClick={() => setSpans((items) => items.filter((_, itemIndex) => itemIndex !== index))} className="col-span-2 text-left text-xs text-red-600">删除此区间</button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={submit} disabled={!target || !detectorName.trim() || createMutation.isPending || updateMutation.isPending} className="flex-1 rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
              {editing ? '更新检测反馈' : '保存检测反馈'}
            </button>
            {editing && <button type="button" onClick={reset} className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-600">取消编辑</button>}
          </div>
          {(createMutation.error || updateMutation.error) && <p className="text-xs text-red-600">保存失败，请检查比例和区间。</p>}
          {feedbacks.length > 0 && (
            <div className="space-y-1 border-t border-gray-100 pt-2">
              <p className="text-xs font-medium text-gray-500">已记录结果</p>
              {feedbacks.map((feedback) => (
                <div key={feedback.id} className="rounded border border-gray-200 p-2 text-xs text-gray-600">
                  <div className="flex items-center justify-between gap-2"><span className="font-medium">{feedback.detector_name}</span><span>{formatRatios(feedback)}</span></div>
                  {feedback.notes && <p className="mt-1 text-gray-500">{feedback.notes}</p>}
                  <div className="mt-1 flex gap-2"><button type="button" onClick={() => beginEdit(feedback)} className="text-indigo-600">编辑</button><button type="button" aria-label={`删除检测反馈 ${feedback.id}`} onClick={() => deleteMutation.mutate(feedback.id)} className="text-red-600">删除</button></div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function RatioInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="text-xs text-gray-600">{label}<input aria-label={label} type="number" min="0" max="100" value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-xs" /></label>
}

function feedbackTargets(run: GenerationRun) {
  const result = run.steps.filter((step) => ['writer', 'reviser', 'judge'].includes(step.stage)).flatMap((step) => {
    const candidate = step.candidates.find((item) => item.is_selected)
    return candidate ? [{ value: `candidate:${candidate.id}`, label: `${stageLabel(step.stage)}候选`, candidate_id: candidate.id }] : []
  })
  if (run.accepted_version_id) result.push({ value: `version:${run.accepted_version_id}`, label: '已采用章节版本', chapter_version_id: run.accepted_version_id })
  return result
}

function stageLabel(stage: string) {
  return ({ writer: '初稿', reviser: '修订稿', judge: 'Judge 合并稿' } as Record<string, string>)[stage] ?? stage
}

function targetReference(value: string) {
  if (value.startsWith('candidate:')) return { candidate_id: value.slice('candidate:'.length) }
  if (value.startsWith('version:')) return { chapter_version_id: value.slice('version:'.length) }
  return null
}

function optionalNumber(value: string) { return value.trim() === '' ? undefined : Number(value) }
function stringValue(value: number | null | undefined) { return value == null ? '' : String(value) }
function replaceSpan(items: SpanDraft[], index: number, change: Partial<SpanDraft>) { return items.map((item, itemIndex) => itemIndex === index ? { ...item, ...change } : item) }
function spansToPayload(items: SpanDraft[]): DetectorSpan[] {
  return items.filter((item) => item.start && item.end).map((item) => ({ label: item.label, start_paragraph: Number(item.start), end_paragraph: Number(item.end), transition_ids: item.transitionIds.split(',').map((id) => id.trim()).filter(Boolean), excerpt: item.excerpt }))
}
function parseSpans(value: string): SpanDraft[] {
  try { return (JSON.parse(value) as DetectorSpan[]).map((span) => ({ label: span.label, start: String(span.start_paragraph), end: String(span.end_paragraph), transitionIds: span.transition_ids.join(', '), excerpt: span.excerpt })) } catch { return [] }
}
function formatRatios(feedback: DetectorFeedback) { return `人工 ${feedback.human_ratio ?? '-'}% · 疑似 ${feedback.suspected_ai_ratio ?? '-'}% · AI ${feedback.ai_ratio ?? '-'}%` }
