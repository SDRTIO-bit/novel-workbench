export type Stage = "planner" | "writer" | "critic" | "reviser" | "judge";

export const STAGES: Stage[] = ["planner", "writer", "critic", "reviser", "judge"];

export const REVISION_OPERATIONS = [
  "naturalize",
  "tighten",
  "clarify",
  "voice_align",
  "ground_detail",
  "rhythm_adjust",
  "diction_refine",
  "project_style_align",
  "withhold_inference",
  "causalize",
] as const;

export type RevisionOperation = (typeof REVISION_OPERATIONS)[number];

export interface CriticIssue {
  issue_id: string;
  problem: string;
  recommended_operation: RevisionOperation;
}

export const STAGE_LABELS: Record<Stage, string> = {
  planner: "场景规划",
  writer: "场景写作",
  critic: "场景诊断",
  reviser: "定点修订",
  judge: "对比验收",
};

export interface StageOverride {
  run_override: unknown;
  provider_id?: string;
  model_id?: string;
  prompt_version_id?: string;
  temperature?: number;
  top_p?: number;
  max_output_tokens?: number;
  timeout_seconds?: number;
}

export interface GenerationCandidate {
  id: string;
  step_id: string;
  attempt_number: number;
  provider_id?: string;
  model_id?: string;
  prompt_version_id?: string;
  parameters_json?: unknown;
  run_override: unknown;
  rendered_system_prompt: string;
  rendered_user_prompt: string;
  raw_response: string;
  parsed_output_json?: unknown;
  text_output: string;
  error_code?: string;
  error_message?: string;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
  is_selected: boolean;
  created_at: string;
}

export interface GenerationStep {
  id: string;
  run_id: string;
  stage: Stage;
  status: string;
  selected_candidate_id?: string;
  selected_issue_ids_json?: string;
  input_snapshot_json?: string;
  created_at: string;
  updated_at: string;
  candidates: GenerationCandidate[];
}

export interface GenerationRun {
  id: string;
  project_id: string;
  chapter_id?: string;
  workflow_profile_id?: string;
  scene_instruction: string;
  status: string;
  accepted_at?: string;
  accepted_type?: string;
  accepted_version_id?: string;
  created_at: string;
  updated_at: string;
  steps: GenerationStep[];
}

export interface DetectorSpan {
  label: string;
  start_paragraph: number;
  end_paragraph: number;
  transition_ids: string[];
  excerpt: string;
}

export interface DetectorFeedback {
  id: string;
  project_id: string;
  chapter_id?: string | null;
  run_id?: string | null;
  candidate_id?: string | null;
  chapter_version_id?: string | null;
  detector_name: string;
  human_ratio?: number | null;
  suspected_ai_ratio?: number | null;
  ai_ratio?: number | null;
  spans_json: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface DetectorFeedbackCreate {
  project_id: string;
  chapter_id?: string;
  run_id?: string;
  candidate_id?: string;
  chapter_version_id?: string;
  detector_name: string;
  human_ratio?: number;
  suspected_ai_ratio?: number;
  ai_ratio?: number;
  spans: DetectorSpan[];
  notes?: string;
}

export type DetectorFeedbackUpdate = Omit<DetectorFeedbackCreate, 'project_id' | 'chapter_id' | 'run_id' | 'candidate_id' | 'chapter_version_id'>;

export interface GenerationRunList {
  id: string;
  project_id: string;
  chapter_id?: string;
  workflow_profile_id?: string;
  scene_instruction: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SelectIssues {
  issue_ids: string[];
  operation_by_issue?: Record<string, RevisionOperation>;
}

export interface CreateRun {
  project_id: string;
  chapter_id?: string;
  workflow_profile_id?: string;
  scene_instruction: string;
}
