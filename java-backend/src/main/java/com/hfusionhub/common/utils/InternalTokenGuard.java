package com.hfusionhub.common.utils;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * 内部端点令牌校验（R15-23：原先在 5 个 Internal*Controller 中各有一份
 * 逐字节常量时间比较的复制粘贴实现，收敛于此）。
 *
 * <p>语义与原实现完全一致：expected 为空时一律拒绝（fail-closed）；
 * 比较用双哈希常量时间，防时序侧信道。</p>
 */
public final class InternalTokenGuard {

    private InternalTokenGuard() {
    }

    public static boolean isAuthorized(String expectedToken, String providedToken) {
        return constantTimeEquals(expectedToken, providedToken);
    }

    /**
     * Constant-time string equality: hash both sides with SHA-256 and compare
     * digests in constant time, so length/content of the provided token never
     * leaks through timing.
     */
    private static boolean constantTimeEquals(String expected, String provided) {
        if (expected == null || expected.isEmpty() || provided == null) {
            return false;
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] a = digest.digest(expected.getBytes(StandardCharsets.UTF_8));
            byte[] b = MessageDigest.getInstance("SHA-256")
                    .digest(provided.getBytes(StandardCharsets.UTF_8));
            return MessageDigest.isEqual(a, b);
        } catch (Exception e) {
            return false;
        }
    }
}
