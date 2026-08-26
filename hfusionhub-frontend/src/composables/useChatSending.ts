import { ref } from 'vue'

/**
 * 会话发送单飞状态机（R16-18）。
 *
 * 把散落在 chat/Detail.vue 的 sending 手工置位/复位收口为显式状态机。
 * 第三十六批的 retry/regenerate 数据丢失缺陷正是出在这类手工时序上：
 * 守卫位与"先复位再发送"的约定分散在多处，任何一处改动都可能踩坏。
 *
 * - `runExclusive(task)`：唯一进入方式。空闲时置 sending=true 并执行
 *   task，结束（含异常）自动复位；已在发送中返回 false 不执行。
 *   重试/重新生成把"删除旧轮次 + 重发"整体放进同一个 task，守卫
 *   跨越删除在途期，双击竞态防护不再依赖各处手工置位。
 * - `forceIdle()`：用户"停止生成"/页面卸载时的强制释放——立即归还
 *   守卫位。守卫持有权绑定到具体调用：forceIdle 后新任务接管守卫位时，
 *   旧在途任务的收尾不会误清新任务的守卫。
 *
 * `sending` 仍是普通 ref：模板绑定与既有读取点语义不变。
 */
export function useChatSending() {
  const sending = ref(false)
  let releaseCurrent: (() => void) | null = null

  const runExclusive = async (task: () => Promise<void>): Promise<boolean> => {
    if (sending.value) return false
    sending.value = true
    let released = false
    const releaseMine = () => {
      if (released) return
      released = true
      sending.value = false
      if (releaseCurrent === releaseMine) releaseCurrent = null
    }
    releaseCurrent = releaseMine
    try {
      await task()
    } finally {
      if (releaseCurrent === releaseMine) releaseMine()
    }
    return true
  }

  const forceIdle = () => {
    releaseCurrent?.()
  }

  return { sending, runExclusive, forceIdle }
}
