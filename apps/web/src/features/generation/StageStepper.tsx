import type { GenerationRun, Stage } from '../../types'
import { STAGES, STAGE_LABELS } from '../../types'

interface Props {
  run: GenerationRun
  currentStage: Stage | null
}

function getStageState(
  stage: Stage,
  steps: GenerationRun['steps'],
  currentStage: Stage | null,
): 'completed' | 'running' | 'pending' | 'stale' {
  const step = steps.find((s) => s.stage === stage)
  if (!step) return 'pending'
  if (step.status === 'failed') return 'stale'
  if (step.status === 'running') return 'running'
  if (step.status === 'completed') {
    const currentIdx = currentStage ? STAGES.indexOf(currentStage) : -1
    const stageIdx = STAGES.indexOf(stage)
    if (currentIdx >= 0 && stageIdx < currentIdx) return 'completed'
    if (step.selected_candidate_id) return 'completed'
    return 'pending'
  }
  return 'pending'
}

const stateStyles: Record<string, string> = {
  completed: 'bg-green-500 border-green-500 text-white',
  running: 'bg-blue-500 border-blue-500 text-white animate-pulse',
  pending: 'bg-gray-200 border-gray-300 text-gray-400',
  stale: 'bg-yellow-500 border-yellow-500 text-white',
}

const lineColors: Record<string, string> = {
  completed: 'bg-green-400',
  running: 'bg-blue-300',
  pending: 'bg-gray-200',
  stale: 'bg-yellow-300',
}

export default function StageStepper({ run, currentStage }: Props) {
  const steps = run.steps

  return (
    <div className="flex items-center justify-center gap-0 py-3">
      {STAGES.map((stage, idx) => {
        const state = getStageState(stage, steps, currentStage)

        return (
          <div key={stage} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`w-8 h-8 rounded-full border-2 flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${stateStyles[state]}`}
                title={STAGE_LABELS[stage]}
              >
                {idx + 1}
              </div>
              <span
                className={`text-[10px] leading-tight text-center w-14 ${
                  state === 'completed'
                    ? 'text-green-700 font-medium'
                    : state === 'running'
                      ? 'text-blue-700 font-medium'
                      : state === 'stale'
                        ? 'text-yellow-700 font-medium'
                        : 'text-gray-400'
                }`}
              >
                {STAGE_LABELS[stage]}
              </span>
            </div>

            {idx < STAGES.length - 1 && (
              <div className={`w-8 h-0.5 mx-0.5 mt-[-14px] ${lineColors[state]}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}
