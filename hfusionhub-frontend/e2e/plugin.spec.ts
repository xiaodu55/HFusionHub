import { test, expect } from './fixtures/base'
import { assertJson, uid } from './helpers'

const FAKE_ARTIFACT_HASH = 'a'.repeat(64)

test.describe('Plugin Management', () => {
  // ── API-level tests (require live backend) ──────────────────────────

  const runLive = process.env.HFUSIONHUB_RUN_PLUGIN_LIVE === 'true'

  test('plugin list endpoint exists and returns a paged list', async ({ javaApi, userA }) => {
    const res = await javaApi.get('plugin/list', {
      headers: userA.headers,
      params: { page: 1, pageSize: 20 },
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(body.data).toBeTruthy()
    expect(Array.isArray(body.data.records)).toBe(true)
    expect(typeof body.data.total).toBe('number')
  })

  test('plugin list is shared consistently inside the same tenant', async ({ javaApi, userA, userB }) => {
    const [a, b] = await Promise.all([
      javaApi.get('plugin/list', { headers: userA.headers, params: { page: 1, pageSize: 20 } }),
      javaApi.get('plugin/list', { headers: userB.headers, params: { page: 1, pageSize: 20 } }),
    ])
    const [bodyA, bodyB] = await Promise.all([assertJson(a), assertJson(b)])
    expect(bodyA.code).toBe(200)
    expect(bodyB.code).toBe(200)
    const idsA = bodyA.data.records.map((plugin: any) => plugin.pluginId).sort()
    const idsB = bodyB.data.records.map((plugin: any) => plugin.pluginId).sort()
    expect(idsA).toEqual(idsB)
  })

  test('install then uninstall a plugin', async ({ javaApi, userA }) => {
    test.skip(!runLive, 'requires live backend')
    const pluginName = uid('e2e_install')
    const manifest = {
      name: pluginName,
      version: '1.0.0',
      description: 'E2E test plugin for plugin management',
      author: 'e2e',
      artifact_hash: FAKE_ARTIFACT_HASH,
    }

    // Install
    const installRes = await javaApi.post('plugin/install', {
      headers: userA.headers,
      data: manifest,
    })
    const installBody = await assertJson(installRes)
    expect(installBody.code).toBe(200)
    const pluginId = installBody.data.pluginId as string
    expect(pluginId).toBeTruthy()

    // List should now show the plugin
    const listRes = await javaApi.get('plugin/list', {
      headers: userA.headers,
      params: { page: 1, pageSize: 20 },
    })
    const listBody = await assertJson(listRes)
    expect(listBody.data.records.length).toBe(1)
    expect(listBody.data.records[0].pluginId).toBe(pluginId)

    // Get detail
    const detailRes = await javaApi.get(`plugin/${pluginId}`, {
      headers: userA.headers,
    })
    const detailBody = await assertJson(detailRes)
    expect(detailBody.code).toBe(200)
    expect(detailBody.data.name).toBe(pluginName)

    // Enable (already active)
    const enableRes = await javaApi.post(`plugin/${pluginId}/enable`, {
      headers: userA.headers,
    })
    const enableBody = await assertJson(enableRes)
    expect(enableBody.code).toBe(200)

    // Disable
    const disableRes = await javaApi.post(`plugin/${pluginId}/disable`, {
      headers: userA.headers,
      data: { reason: 'E2E test disable' },
    })
    const disableBody = await assertJson(disableRes)
    expect(disableBody.code).toBe(200)

    // Uninstall
    const uninstallRes = await javaApi.post(`plugin/${pluginId}/uninstall`, {
      headers: userA.headers,
      data: { reason: 'E2E test complete' },
    })
    const uninstallBody = await assertJson(uninstallRes)
    expect(uninstallBody.code).toBe(200)
  })

  test('install duplicate plugin returns 409', async ({ javaApi, userA }) => {
    test.skip(!runLive, 'requires live backend')
    const pluginName = uid('e2e_dup')
    const manifest = {
      name: pluginName,
      version: '1.0.0',
      description: 'Duplicate test',
      artifact_hash: FAKE_ARTIFACT_HASH,
    }

    // First install
    const res1 = await javaApi.post('plugin/install', {
      headers: userA.headers,
      data: manifest,
    })
    const body1 = await assertJson(res1)
    expect(body1.code).toBe(200)
    const pluginId = body1.data.pluginId

    // Duplicate install
    const res2 = await javaApi.post('plugin/install', {
      headers: userA.headers,
      data: manifest,
    })
    const body2 = await assertJson(res2)
    expect(body2.code).toBe(409)

    // Cleanup
    await javaApi.post(`plugin/${pluginId}/uninstall`, {
      headers: userA.headers,
      data: { reason: 'cleanup' },
    })
  })

  test('install with missing required fields returns 400', async ({ javaApi, userA }) => {
    test.skip(!runLive, 'requires live backend')
    const res = await javaApi.post('plugin/install', {
      headers: userA.headers,
      data: { name: 'incomplete' }, // missing version and description
    })
    const body = await assertJson(res)
    expect(body.code).toBe(400)
  })

  test('audit logs recorded for plugin operations', async ({ javaApi, userA }) => {
    test.skip(!runLive, 'requires live backend')
    const pluginName = uid('e2e_audit')
    const manifest = {
      name: pluginName,
      version: '1.0.0',
      description: 'Audit test',
      artifact_hash: FAKE_ARTIFACT_HASH,
    }

    // Install
    const installRes = await javaApi.post('plugin/install', {
      headers: userA.headers,
      data: manifest,
    })
    const installBody = await assertJson(installRes)
    const pluginId = installBody.data.pluginId

    // Check audit logs
    const auditRes = await javaApi.get(`plugin/${pluginId}/audit-logs`, {
      headers: userA.headers,
      params: { limit: 10 },
    })
    const auditBody = await assertJson(auditRes)
    expect(auditBody.code).toBe(200)
    expect(auditBody.data.length).toBeGreaterThanOrEqual(1)
    expect(auditBody.data[0].action).toBe('install')

    // Cleanup
    await javaApi.post(`plugin/${pluginId}/uninstall`, {
      headers: userA.headers,
      data: { reason: 'cleanup' },
    })
  })

  // ── UI rendering tests (mocked route) ───────────────────────────────

  test('plugins page explains creation and package upload', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/plugin/list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { records: [], total: 0 } }),
      }),
    )
    await page.goto('/builder/plugins')
    await expect(page.getByRole('main').getByRole('heading', { name: '插件与工具' })).toBeVisible()
    await expect(page.getByRole('button', { name: '新建插件' })).toBeVisible()
    await expect(page.getByRole('button', { name: '上传插件包' })).toBeVisible()
  })

  test('plugins page shows empty state when no plugins', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/plugin/list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { records: [], total: 0 } }),
      }),
    )
    await page.goto('/builder/plugins')
    await expect(page.getByText('暂无插件')).toBeVisible()
  })

  test('plugins page shows plugin cards when data exists', async ({ page, admin }) => {
    const mockPlugins = [
      {
        id: 1,
        pluginId: 'test-plugin-1',
        name: 'test_plugin',
        displayName: 'Test Plugin',
        description: 'A test plugin',
        version: '1.0.0',
        author: 'tester',
        source: 'local',
        status: 'active',
        enabled: true,
        permissions: '["web_access"]',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
    ]

    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/plugin/list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { records: mockPlugins, total: 1 } }),
      }),
    )
    await page.goto('/builder/plugins')
    await expect(page.getByRole('heading', { name: 'Test Plugin' })).toBeVisible()
    await expect(page.getByText('test_plugin@1.0.0')).toBeVisible()
    await expect(page.getByText('运行中', { exact: true })).toBeVisible()
  })

  test('status filter tabs show correct counts', async ({ page, admin }) => {
    const mockPlugins = [
      { id: 1, pluginId: 'p1', name: 'a', displayName: 'A', version: '1.0.0', source: 'local', status: 'active', enabled: true, createdAt: '', updatedAt: '' },
      { id: 2, pluginId: 'p2', name: 'b', displayName: 'B', version: '1.0.0', source: 'local', status: 'disabled', enabled: false, createdAt: '', updatedAt: '' },
    ]

    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/plugin/list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { records: mockPlugins, total: 2 } }),
      }),
    )
    await page.goto('/builder/plugins')
    await expect(page.getByRole('button', { name: /2 全部/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /1 运行中/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /1 已禁用/ })).toBeVisible()
  })

  test('install dialog opens and validates input', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/plugin/list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { records: [], total: 0 } }),
      }),
    )
    await page.goto('/builder/plugins')

    // Open install dialog via the header button
    await page.getByRole('button', { name: '上传插件包' }).click()
    await expect(page.getByText('插件名称 *')).toBeVisible()

    // Install button should be disabled when fields are empty
    const installBtn = page.getByRole('button', { name: '安装', exact: true })
    await expect(installBtn).toBeDisabled()

    // Fill in name
    await page.getByPlaceholder('e.g. github_connector').fill('test_plugin')
    await expect(installBtn).toBeDisabled()

    // Fill in version
    await page.getByPlaceholder('e.g. 1.0.0').fill('1.0.0')
    // Still disabled — artifact hash not yet provided
    await expect(installBtn).toBeDisabled()

    // Upload a dummy file to trigger SHA-256 computation
    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles({
      name: 'test_plugin-1.0.0.whl',
      mimeType: 'application/zip',
      buffer: Buffer.from('dummy wheel content'),
    })
    // Wait for hash computation to complete
    await expect(page.getByText('SHA-256:')).toBeVisible()
    // Now the install button should be enabled
    await expect(installBtn).toBeEnabled()
  })

  test('low-code creator loads a complete weather example', async ({ page, admin }) => {
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('satoken', token), admin.token)
    await page.route('**/api/plugin/list**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, data: { records: [], total: 0 } }),
      }),
    )
    await page.goto('/builder/plugins')

    await page.getByRole('button', { name: '新建插件' }).click()
    await expect(page.getByRole('heading', { name: '新建插件' })).toBeVisible()
    await page.getByRole('button', { name: '使用示例' }).click()

    await expect(page.getByPlaceholder('例如：天气查询助手')).toHaveValue('天气查询助手')
    await expect(page.getByPlaceholder('例如：weather_helper')).toHaveValue('weather_helper')
    await expect(page.getByPlaceholder('https://api.example.com/search')).toHaveValue('https://api.open-meteo.com/v1/forecast')
    await expect(page.getByRole('button', { name: '创建并启用' })).toBeEnabled()
  })
})
