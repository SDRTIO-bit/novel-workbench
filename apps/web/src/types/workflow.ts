export interface WorkflowStepConfig {
  id: string;
  workflow_profile_id: string;
  stage: string;
  provider_id?: string;
  model_id?: string;
  prompt_version_id?: string;
  temperature: number;
  top_p: number;
  max_output_tokens: number;
  timeout_seconds: number;
}

export interface WorkflowProfile {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  steps: WorkflowStepConfig[];
}

export interface WorkflowProfileList {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
}

export interface WorkflowUpdate {
  name?: string;
  description?: string;
}

export interface WorkflowStepUpdate {
  provider_id?: string;
  model_id?: string;
  prompt_version_id?: string;
  temperature?: number;
  top_p?: number;
  max_output_tokens?: number;
  timeout_seconds?: number;
}
