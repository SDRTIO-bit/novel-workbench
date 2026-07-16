import { describe, it, expect } from 'vitest'
import { ApiError } from '../src/api/client'

describe('ApiError', () => {
  it('constructs from error response', () => {
    const err = new ApiError('TEST_ERROR', '测试错误', 400)
    expect(err.code).toBe('TEST_ERROR')
    expect(err.message).toBe('测试错误')
    expect(err.statusCode).toBe(400)
    expect(err.name).toBe('ApiError')
  })
})
