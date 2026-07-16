import { test, expect } from '@playwright/test'

test.describe('Novel Workbench E2E', () => {
  test('health check returns 200', async ({ request }) => {
    const resp = await request.get('http://localhost:8766/api/health')
    expect(resp.status()).toBe(200)
    const body = await resp.json()
    expect(body.status).toBe('ok')
  })

  test('frontend loads without error', async ({ page }) => {
    await page.goto('http://localhost:8765')
    await expect(page.locator('text=小说项目')).toBeVisible()
  })

  test('can create and navigate project', async ({ page }) => {
    await page.goto('http://localhost:8765/projects')
    await page.click('text=新建项目')
    await page.fill('input[placeholder="输入项目名称"]', 'E2E测试项目')
    await page.click('text=确认')
    await expect(page.locator('text=E2E测试项目')).toBeVisible()
  })

  test('settings pages load', async ({ page }) => {
    await page.goto('http://localhost:8765/settings/providers')
    await expect(page.locator('text=服务商管理')).toBeVisible()

    await page.goto('http://localhost:8765/settings/prompts')
    await expect(page.locator('text=提示词管理')).toBeVisible()

    await page.goto('http://localhost:8765/settings/workflows')
    await expect(page.locator('text=工作流管理')).toBeVisible()
  })
})
