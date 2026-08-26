import { describe, it, expect, vi } from 'vitest'
import { useChatSending } from '../useChatSending'

describe('useChatSending', () => {
  it('runs task when idle and resets sending afterwards', async () => {
    const { sending, runExclusive } = useChatSending()

    let duringTask: boolean | null = null
    const started = await runExclusive(async () => {
      duringTask = sending.value
    })

    expect(started).toBe(true)
    expect(duringTask).toBe(true)
    expect(sending.value).toBe(false)
  })

  it('rejects concurrent send while one is running', async () => {
    const { sending, runExclusive } = useChatSending()
    expect(sending.value).toBe(false)

    let releaseFirst!: () => void
    const gate = new Promise<void>((resolve) => { releaseFirst = resolve })
    const first = runExclusive(() => gate)
    await vi.waitFor(() => expect(sending.value).toBe(true))

    const second = await runExclusive(async () => {
      throw new Error('不应执行')
    })
    expect(second).toBe(false)

    releaseFirst()
    await first
    expect(sending.value).toBe(false)
  })

  it('resets sending even when the task throws', async () => {
    const { sending, runExclusive } = useChatSending()

    await expect(
      runExclusive(async () => {
        throw new Error('boom')
      }),
    ).rejects.toThrow('boom')

    expect(sending.value).toBe(false)
  })

  it('forceIdle releases the guard mid-task', async () => {
    const { sending, runExclusive, forceIdle } = useChatSending()

    let releaseTask!: () => void
    const gate = new Promise<void>((resolve) => { releaseTask = resolve })
    const running = runExclusive(() => gate)
    await vi.waitFor(() => expect(sending.value).toBe(true))

    forceIdle()
    expect(sending.value).toBe(false)

    // 强制释放后新任务可立即进入（与旧"停止生成"行为一致）
    const second = await runExclusive(async () => {})
    expect(second).toBe(true)

    releaseTask()
    await running
    // 旧任务的 finally 不得把新任务持有的守卫位错误复位
    expect(sending.value).toBe(false)
  })

  it('forceIdle is a no-op when idle', () => {
    const { sending, forceIdle } = useChatSending()

    expect(() => forceIdle()).not.toThrow()
    expect(sending.value).toBe(false)
  })

  it('allows sequential runs after completion', async () => {
    const { sending, runExclusive } = useChatSending()

    expect(await runExclusive(async () => {})).toBe(true)
    expect(await runExclusive(async () => {})).toBe(true)
    expect(sending.value).toBe(false)
  })
})
