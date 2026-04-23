import { test, expect } from './fixtures/base'
import { apiRegister, apiLogin, uid, assertJson } from './helpers'

test.describe('Register & Login', () => {
  test('register new user and redirect to login', async ({ page }) => {
    const username = uid('reg')
    await page.goto('/register')
    await page.waitForLoadState('networkidle')

    await page.getByLabel(/用户名|username/i).fill(username)
    await page.locator('#password').fill('Test1234')
    await page.locator('#confirmPassword').fill('Test1234')
    await page.getByRole('button', { name: /注册|register/i }).click()

    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 })
  })

  test('login with valid credentials redirects to dashboard', async ({ page, javaApi }) => {
    const { username, password } = await apiRegister(javaApi)
    await page.goto('/login')
    await page.waitForLoadState('networkidle')

    await page.getByLabel(/用户名|username/i).fill(username)
    await page.locator('#password').fill(password)
    await page.getByRole('button', { name: /登录|login/i }).click()

    await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 })
  })

  test('unauthenticated access redirects to login', async ({ page }) => {
    await page.goto('/knowledge-base')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 })
  })

  test('unauthenticated access to chat redirects to login', async ({ page }) => {
    await page.goto('/chat')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 })
  })

  test('logged-in user cannot access login page', async ({ page, userA }) => {
    await page.goto('/')
    await page.evaluate((token) => {
      localStorage.setItem('satoken', token)
    }, userA.token)
    await page.goto('/login')
    await page.waitForSelector('#app', { timeout: 10_000 })
    await expect(page).not.toHaveURL(/\/login/, { timeout: 10_000 })
  })

  test('login with wrong password shows error', async ({ page, javaApi }) => {
    const { username } = await apiRegister(javaApi)
    await page.goto('/login')
    await page.waitForSelector('#app', { timeout: 10_000 })

    await page.getByLabel(/用户名|username/i).fill(username)
    await page.locator('#password').fill('WrongPass999')
    await page.getByRole('button', { name: /登录|login/i }).click()

    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
  })

  test('API login returns token', async ({ javaApi }) => {
    const { username, password } = await apiRegister(javaApi)
    const token = await apiLogin(javaApi, username, password)
    expect(token).toBeTruthy()
    expect(typeof token).toBe('string')
    expect(token.length).toBeGreaterThan(10)
  })

  test('API register returns user info (role pending until assigned)', async ({ javaApi }) => {
    const username = uid('api_reg')
    const res = await javaApi.post('user/register', {
      data: { username, password: 'Test1234', nickname: username },
    })
    const body = await assertJson(res)
    expect(body.code).toBe(200)
    expect(body.data.username).toBe(username)
    // 新业务规则：注册即“待分配”(pending)，由 admin 后续提升角色。
    expect(body.data.role).toBe('pending')
  })
})
