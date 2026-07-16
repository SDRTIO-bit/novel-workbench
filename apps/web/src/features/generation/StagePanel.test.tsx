import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GenerationStep } from '../../types'
import StagePanel from './StagePanel'
import * as runsApi from '../../api/runs'

vi.mock('../../api/providers', () => ({
  listProviders: vi.fn().mockResolvedValue([]),
}))

vi.mock('../../api/runs', () => ({
  executeStage: vi.fn(),
  previewStage: vi.fn(),
  selectCandidate: vi.fn(),
  selectIssues: vi.fn(),
}))

const criticStep: GenerationStep = {
  id: 'step-1',
  run_id: 'run-1',
  stage: 'critic',
  status: 'completed',
  selected_candidate_id: 'candidate-1',
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
  candidates: [
    {
      id: 'candidate-1',
      step_id: 'step-1',
      attempt_number: 1,
      raw_response: '',
      text_output: '',
      run_override: '',
      rendered_system_prompt: '',
      rendered_user_prompt: '',
      is_selected: true,
      created_at: '2026-07-17T00:00:00Z',
      parsed_output_json: JSON.stringify({
        issues: [
          {
            issue_id: 'I01',
            problem: '这句对白像作者在解释人物设定。',
            recommended_operation: 'tighten',
          },
          {
            issue_id: 'I02',
            problem: '角色说话方式与当前关系不符。',
            recommended_operation: 'voice_align',
          },
        ],
      }),
    },
  ],
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <StagePanel runId="run-1" stage="critic" step={criticStep} />
    </QueryClientProvider>,
  )
}

describe('StagePanel revision operations', () => {
  beforeEach(() => {
    vi.mocked(runsApi.selectIssues).mockReset()
    vi.mocked(runsApi.selectIssues).mockResolvedValue({ status: 'ok' })
  })

  it('initialises a selected issue from the critic recommendation', () => {
    renderPanel()

    fireEvent.click(screen.getByLabelText('选择 I01'))

    expect((screen.getByLabelText('修订操作 I01') as HTMLSelectElement).value).toBe('tighten')
  })

  it('submits the author-selected operation for each selected critic issue', async () => {
    renderPanel()

    fireEvent.click(screen.getByLabelText('选择 I01'))
    fireEvent.change(screen.getByLabelText('修订操作 I01'), {
      target: { value: 'voice_align' },
    })
    fireEvent.click(screen.getByRole('button', { name: '确认问题' }))

    await waitFor(() => {
      expect(runsApi.selectIssues).toHaveBeenCalledWith('run-1', {
        issue_ids: ['I01'],
        operation_by_issue: { I01: 'voice_align' },
      })
    })
  })
})
