import { apiDelete, apiGet, apiPatch, apiPost } from './client'
import type { DetectorFeedback, DetectorFeedbackCreate, DetectorFeedbackUpdate } from '../types'

export const listDetectorFeedbacks = (projectId: string, chapterId?: string) => {
  const params = new URLSearchParams({ project_id: projectId })
  if (chapterId) params.set('chapter_id', chapterId)
  return apiGet<DetectorFeedback[]>(`/detector-feedbacks?${params.toString()}`)
}

export const createDetectorFeedback = (data: DetectorFeedbackCreate) =>
  apiPost<DetectorFeedback>('/detector-feedbacks', data)

export const updateDetectorFeedback = (id: string, data: Partial<DetectorFeedbackUpdate>) =>
  apiPatch<DetectorFeedback>(`/detector-feedbacks/${id}`, data)

export const deleteDetectorFeedback = (id: string) => apiDelete(`/detector-feedbacks/${id}`)
