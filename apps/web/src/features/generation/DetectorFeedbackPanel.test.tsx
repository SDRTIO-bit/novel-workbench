import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GenerationRun } from '../../types'
import DetectorFeedbackPanel from './DetectorFeedbackPanel'
import * as detectorFeedbacksApi from '../../api/detectorFeedbacks'

vi.mock('../../api/detectorFeedbacks', () => ({
  listDetectorFeedbacks: vi.fn(),
  createDetectorFeedback: vi.fn(),
  updateDetectorFeedback: vi.fn(),
  deleteDetectorFeedback: vi.fn(),
}))

const run: GenerationRun = {
  id: 'run-1',
  project_id: 'project-1',
  chapter_id: 'chapter-1',
  scene_instruction: '测试反馈录入',
  status: 'completed',
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
  steps: [
    {
      id: 'writer-step', run_id: 'run-1', stage: 'writer', status: 'completed',
      selected_candidate_id: 'writer-candidate', created_at: '', updated_at: '',
      candidates: [{
        id: 'writer-candidate', step_id: 'writer-step', attempt_number: 1,
        raw_response: '', text_output: '正文', run_override: '', rendered_system_prompt: '',
        rendered_user_prompt: '', is_selected: true, created_at: '',
      }],
    },
    {
      id: 'judge-step', run_id: 'run-1', stage: 'judge', status: 'completed',
      selected_candidate_id: 'judge-candidate', created_at: '', updated_at: '',
      candidates: [{
        id: 'judge-candidate', step_id: 'judge-step', attempt_number: 1,
        raw_response: '', text_output: '', run_override: '', rendered_system_prompt: '',
        rendered_user_prompt: '', is_selected: true, created_at: '',
        parsed_output_json: JSON.stringify({ decision: 'accept_merged' }),
      }],
    },
  ],
}

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DetectorFeedbackPanel projectId="project-1" chapterId="chapter-1" run={run} />
    </QueryClientProvider>,
  )
}

describe('DetectorFeedbackPanel', () => {
  beforeEach(() => {
    vi.mocked(detectorFeedbacksApi.listDetectorFeedbacks).mockResolvedValue([
      {
        id: 'feedback-1', project_id: 'project-1', chapter_id: 'chapter-1', run_id: 'run-1',
        candidate_id: 'writer-candidate', chapter_version_id: null, detector_name: '旧检测器',
        human_ratio: 20, suspected_ai_ratio: 30, ai_ratio: 50, spans_json: '[]', notes: '',
        created_at: '', updated_at: '',
      },
    ])
    vi.mocked(detectorFeedbacksApi.createDetectorFeedback).mockResolvedValue({} as never)
    vi.mocked(detectorFeedbacksApi.deleteDetectorFeedback).mockResolvedValue(undefined)
  })

  it('creates feedback for the selected Judge candidate', async () => {
    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: '展开外部检测反馈' }))
    fireEvent.change(screen.getByLabelText('检测对象'), { target: { value: 'candidate:judge-candidate' } })
    fireEvent.change(screen.getByLabelText('检测器名称'), { target: { value: '特邀测试' } })
    fireEvent.change(screen.getByLabelText('人工特征比例'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('疑似 AI 比例'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('AI 特征比例'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: '保存检测反馈' }))

    await waitFor(() => expect(detectorFeedbacksApi.createDetectorFeedback).toHaveBeenCalledWith(
      expect.objectContaining({
        project_id: 'project-1',
        chapter_id: 'chapter-1',
        run_id: 'run-1',
        candidate_id: 'judge-candidate',
        ai_ratio: 100,
      }),
    ))
  })

  it('offers prose candidates but excludes the planner contract', async () => {
    const withPlanner: GenerationRun = {
      ...run,
      steps: [{
        id: 'planner-step', run_id: 'run-1', stage: 'planner', status: 'completed',
        selected_candidate_id: 'planner-candidate', created_at: '', updated_at: '',
        candidates: [{
          id: 'planner-candidate', step_id: 'planner-step', attempt_number: 1,
          raw_response: '', text_output: '', run_override: '', rendered_system_prompt: '',
          rendered_user_prompt: '', is_selected: true, created_at: '',
        }],
      }, ...run.steps],
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><DetectorFeedbackPanel projectId="project-1" chapterId="chapter-1" run={withPlanner} /></QueryClientProvider>)

    fireEvent.click(screen.getByRole('button', { name: '展开外部检测反馈' }))

    expect(screen.queryByRole('option', { name: 'planner候选' })).toBeNull()
    expect(screen.getByRole('option', { name: '初稿候选' })).not.toBeNull()
    expect(screen.getByRole('option', { name: 'Judge 合并稿候选' })).not.toBeNull()
  })

  it('offers the accepted chapter version after a run is committed', () => {
    const acceptedRun: GenerationRun = { ...run, accepted_version_id: 'version-1' }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={queryClient}><DetectorFeedbackPanel projectId="project-1" chapterId="chapter-1" run={acceptedRun} /></QueryClientProvider>)

    fireEvent.click(screen.getByRole('button', { name: '展开外部检测反馈' }))

    const option = screen.getByRole('option', { name: '已采用章节版本' }) as HTMLOptionElement
    expect(option.value).toBe('version:version-1')
  })

  it('deletes a saved feedback record', async () => {
    renderPanel()

    fireEvent.click(screen.getByRole('button', { name: '展开外部检测反馈' }))
    await screen.findByText('旧检测器')
    fireEvent.click(screen.getByRole('button', { name: '删除检测反馈 feedback-1' }))

    await waitFor(() => expect(detectorFeedbacksApi.deleteDetectorFeedback.mock.calls[0]?.[0]).toBe('feedback-1'))
  })
})
