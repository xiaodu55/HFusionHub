import { test as base, expect, type APIRequestContext } from '@playwright/test'
import {
  apiRegister,
  apiLoginAs,
  apiCreateKB,
  ensureAdmin,
  uid,
} from '../helpers'

const JAVA_API = process.env.JAVA_BASE_URL || 'http://localhost:8080/api'

type TestUser = {
  username: string
  password: string
  token: string
  headers: Record<string, string>
}

type TestFixtures = {
  userA: TestUser
  userB: TestUser
  admin: TestUser
  testKB: any
  javaApi: APIRequestContext
}

export const test = base.extend<TestFixtures>({
  userA: async ({ javaApi }, use) => {
    const { username, password } = await apiRegister(javaApi)
    const { token, headers } = await apiLoginAs(javaApi, username, password)
    await use({ username, password, token, headers })
  },

  userB: async ({ javaApi }, use) => {
    const { username, password } = await apiRegister(javaApi)
    const { token, headers } = await apiLoginAs(javaApi, username, password)
    await use({ username, password, token, headers })
  },

  admin: async ({ javaApi }, use) => {
    const { token, headers } = await ensureAdmin(javaApi)
    await use({ username: process.env.ADMIN_USERNAME || 'admin', password: process.env.ADMIN_PASSWORD || 'admin123', token, headers })
  },

  testKB: async ({ userA, javaApi }, use) => {
    const kb = await apiCreateKB(javaApi, userA.headers)
    await use(kb)
  },

  javaApi: async ({ playwright }, use) => {
    const api = await playwright.request.newContext({
      baseURL: JAVA_API + '/',
    })
    await use(api)
    await api.dispose()
  },
})

export { expect }
