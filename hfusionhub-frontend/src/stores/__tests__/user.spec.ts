import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import * as userApi from '@/api/user'
import { useUserStore } from '../user'

vi.mock('@/api/user', () => ({
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  getUserInfo: vi.fn(),
  updateUserInfo: vi.fn(),
}))

const userInfo = {
  id: 1,
  username: 'alice',
  nickname: 'Alice',
  email: 'alice@example.com',
  phone: '13800138000',
  avatar: '',
  status: 0,
  createdAt: '2026-07-28 12:00:00',
}

describe('user store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('persists and clears a token', () => {
    const store = useUserStore()

    store.setToken('token-123')
    expect(store.token).toBe('token-123')
    expect(localStorage.getItem('satoken')).toBe('token-123')
    expect(store.isLoggedIn).toBe(true)

    store.clearToken()
    expect(store.token).toBe('')
    expect(localStorage.getItem('satoken')).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })

  it('hydrates the token from local storage', () => {
    localStorage.setItem('satoken', 'stored-token')

    const store = useUserStore()

    expect(store.token).toBe('stored-token')
    expect(store.isLoggedIn).toBe(true)
  })

  it('logs in, persists the token, and loads the current user', async () => {
    vi.mocked(userApi.login).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: 'token-123',
    })
    vi.mocked(userApi.getUserInfo).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: userInfo,
    })
    const store = useUserStore()

    await store.login('alice', 'secret')

    expect(userApi.login).toHaveBeenCalledWith({
      username: 'alice',
      password: 'secret',
    })
    expect(store.token).toBe('token-123')
    expect(store.userInfo).toEqual(userInfo)
    expect(store.username).toBe('alice')
    expect(store.nickname).toBe('Alice')
  })

  it('clears local authentication even when remote logout fails', async () => {
    vi.mocked(userApi.logout).mockRejectedValue(new Error('offline'))
    const store = useUserStore()
    store.setToken('token-123')
    store.userInfo = userInfo

    await store.logout()

    expect(store.token).toBe('')
    expect(store.userInfo).toBeNull()
    expect(localStorage.getItem('satoken')).toBeNull()
  })

  it('forwards registration data', async () => {
    vi.mocked(userApi.register).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: undefined,
    })
    const store = useUserStore()
    const registration = {
      username: 'alice',
      password: 'secret',
      nickname: 'Alice',
    }

    await store.register(registration)

    expect(userApi.register).toHaveBeenCalledWith(registration)
  })

  it('refreshes current user after a profile update', async () => {
    vi.mocked(userApi.updateUserInfo).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: undefined,
    })
    vi.mocked(userApi.getUserInfo).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { ...userInfo, nickname: 'Updated' },
    })
    const store = useUserStore()

    await store.updateUserInfo({ nickname: 'Updated' })

    expect(userApi.updateUserInfo).toHaveBeenCalledWith({ nickname: 'Updated' })
    expect(userApi.getUserInfo).toHaveBeenCalledOnce()
    expect(store.nickname).toBe('Updated')
  })
})
