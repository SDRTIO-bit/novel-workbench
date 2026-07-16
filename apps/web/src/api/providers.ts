import { apiGet, apiPost, apiPatch, apiDelete } from './client';
import type { Provider, ProviderCreate, ProviderUpdate, ModelUpdate } from '../types';

export const listProviders = () => apiGet<Provider[]>('/providers');
export const createProvider = (data: ProviderCreate) => apiPost<Provider>('/providers', data);
export const updateProvider = (id: string, data: ProviderUpdate) => apiPatch<Provider>(`/providers/${id}`, data);
export const deleteProvider = (id: string) => apiDelete(`/providers/${id}`);
export const testProvider = (id: string) => apiPost<{ status: string; message: string }>(`/providers/${id}/test`);
export const syncModels = (id: string) => apiPost<Provider>(`/providers/${id}/sync-models`);
export const addModel = (providerId: string, data: { model_id: string; display_name?: string }) => apiPost<Provider>(`/providers/${providerId}/models`, data);
export const updateModel = (providerId: string, modelId: string, data: ModelUpdate) => apiPatch<Provider>(`/providers/${providerId}/models/${modelId}`, data);
