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

function renderStage(stage: GenerationStep['stage'], step: GenerationStep) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <StagePanel runId="run-1" stage={stage} step={step} />
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

  it('renders a planner causal transition as a readable card', () => {
    const plannerStep: GenerationStep = {
      ...criticStep,
      id: 'planner-step',
      stage: 'planner',
      candidates: [{
        ...criticStep.candidates[0],
        id: 'planner-candidate',
        step_id: 'planner-step',
        parsed_output_json: JSON.stringify({
          causal_transitions: [{
            id: 'CT01',
            kind: 'evidence_to_action',
            visible_trigger: '接线盒上出现 GR-0713。',
            character_next_action: '陆衡转头询问许栀父亲的名字。',
            reader_must_infer: '编号与未来工单有关。',
            narrator_must_not_state: ['两个编号相同。'],
            immediate_consequence: '许栀开始警惕。',
            next_constraint: '陆衡不能泄露工单。',
          }],
        }),
      }],
    }

    renderStage('planner', plannerStep)

    expect(screen.getByText(/证据 → 行动/)).toBeTruthy()
    expect(screen.getAllByText(/接线盒上出现 GR-0713。/).length).toBeGreaterThan(1)
    expect(screen.getByText(/留给读者的推论/)).toBeTruthy()
  })

  it('shows a Judge warning when revision loses necessary information', () => {
    const judgeStep: GenerationStep = {
      ...criticStep,
      id: 'judge-step',
      stage: 'judge',
      candidates: [{
        ...criticStep.candidates[0],
        id: 'judge-candidate',
        step_id: 'judge-step',
        parsed_output_json: JSON.stringify({
          decision: 'accept_original',
          necessary_information_lost: true,
          reader_inference_preserved: false,
          decision_consequence_preserved: false,
          narrator_management_reduced: true,
          causal_transition_results: [],
        }),
      }],
    }

    renderStage('judge', judgeStep)

    expect(screen.getByText('修订稿丢失必要信息')).toBeTruthy()
  })
})
