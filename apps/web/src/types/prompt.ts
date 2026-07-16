export interface PromptVersion {
  id: string;
  profile_id: string;
  version_number: number;
  system_template: string;
  user_template: string;
  output_mode: string;
  output_schema_name?: string;
  created_at: string;
}

export interface PromptProfile {
  id: string;
  stage: string;
  name: string;
  description: string;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
  latest_version?: PromptVersion;
}

export interface PromptProfileList {
  id: string;
  stage: string;
  name: string;
  description: string;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromptCreate {
  stage: string;
  name: string;
  description?: string;
  system_template?: string;
  user_template?: string;
  output_mode?: string;
  output_schema_name?: string;
}

export interface PromptVersionCreate {
  system_template?: string;
  user_template?: string;
  output_mode?: string;
  output_schema_name?: string;
}

export interface RenderPreviewRequest {
  system_template: string;
  user_template: string;
  variables: Record<string, string>;
}

export interface RenderPreviewResponse {
  system_prompt: string;
  user_prompt: string;
}
