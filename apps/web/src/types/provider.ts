export interface ProviderModel {
  id: string;
  provider_id: string;
  model_id: string;
  display_name: string;
  is_manual: boolean;
  enabled: boolean;
}

export interface Provider {
  id: string;
  name: string;
  provider_type: string;
  base_url?: string;
  has_api_key: boolean;
  enabled: boolean;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
  models: ProviderModel[];
}

export interface ProviderCreate {
  name: string;
  provider_type: string;
  base_url?: string;
  api_key?: string;
  extra_headers_json?: string;
}

export interface ProviderUpdate {
  name?: string;
  base_url?: string;
  api_key?: string;
  clear_api_key?: boolean;
}

export interface ModelUpdate {
  display_name?: string;
  enabled?: boolean;
  mode?: string;
}
