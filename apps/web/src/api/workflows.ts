import { apiGet, apiPost, apiPatch, apiPut, apiDelete } from './client';
import type { WorkflowProfileList, WorkflowProfile, WorkflowCreate, WorkflowUpdate, WorkflowStepUpdate } from '../types';

export const listWorkflows = () => apiGet<WorkflowProfileList[]>('/workflows');
export const getWorkflow = (id: string) => apiGet<WorkflowProfile>(`/workflows/${id}`);
export const createWorkflow = (data: WorkflowCreate) => apiPost<WorkflowProfile>('/workflows', data);
export const updateWorkflow = (id: string, data: WorkflowUpdate) => apiPatch<WorkflowProfile>(`/workflows/${id}`, data);
export const duplicateWorkflow = (id: string) => apiPost<WorkflowProfile>(`/workflows/${id}/duplicate`);
export const deleteWorkflow = (id: string) => apiDelete(`/workflows/${id}`);
export const updateStep = (workflowId: string, stage: string, data: WorkflowStepUpdate) => apiPut<WorkflowProfile>(`/workflows/${workflowId}/steps/${stage}`, data);
export const setDefault = (id: string) => apiPost<WorkflowProfile>(`/workflows/${id}/set-default`);
