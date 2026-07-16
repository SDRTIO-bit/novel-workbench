export class ApiError extends Error {
  code: string
  statusCode: number
  details: unknown

  constructor(code: string, message: string, statusCode: number, details: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.statusCode = statusCode
    this.details = details
  }
}

interface ApiErrorResponse {
  error: {
    code: string
    message: string
    details: unknown
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: ApiErrorResponse | null = null
    try {
      errorData = await response.json()
    } catch {
      // ignore parse errors for non-json responses
    }

    if (errorData?.error) {
      throw new ApiError(
        errorData.error.code,
        errorData.error.message,
        response.status,
        errorData.error.details,
      )
    }

    throw new ApiError('UNKNOWN_ERROR', `HTTP ${response.status}`, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  return handleResponse<T>(response)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(response)
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(response)
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(response)
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`/api${path}`, { method: 'DELETE' })
  await handleResponse<unknown>(response)
}
