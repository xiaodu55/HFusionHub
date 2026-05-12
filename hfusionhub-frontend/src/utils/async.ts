/**
 * Shared async helpers for request-race protection and input throttling.
 *
 * Race protection (request sequencing) is intentionally kept as a tiny local
 * idiom inside pages instead of a shared helper: each caller captures a fresh
 * sequence number and compares it against the module-level "latest" value on
 * response, which is two lines and impossible to get wrong. This module only
 * owns the pure, reusable pieces (debounce) that would otherwise be duplicated.
 */

/**
 * Debounce a function: trailing-edge only. The returned wrapper may be used
 * directly as an event handler; `this` and arguments are forwarded.
 *
 * @param fn    function to run after the quiet period
 * @param wait  quiet period in milliseconds
 */
export function debounce<T extends (...args: never[]) => void>(
  fn: T,
  wait: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timer !== null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      fn(...args)
    }, wait)
  }
}
