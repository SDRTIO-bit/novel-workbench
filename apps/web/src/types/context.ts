export interface ContextSource {
  name: string;
  char_count: number;
  truncated: boolean;
}

export interface ContextPreviewRequest {
  project_id: string;
  chapter_id?: string;
  stage: string;
  workflow_profile_id?: string;
  prompt_version_id?: string;
  scene_instruction: string;
  run_override: unknown;
  scene_plan?: string;
  draft_text: string;
  critic_report?: string;
  selected_issues: unknown;
  revised_text: string;
}

export interface ContextPreviewResponse {
  sources: ContextSource[];
  system_prompt: string;
  user_prompt: string;
  input_snapshot_hash: string;
  total_chars: number;
  truncated: boolean;
}
