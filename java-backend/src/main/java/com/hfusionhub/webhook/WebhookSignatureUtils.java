package com.hfusionhub.webhook;

import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Webhook 请求签名工具
 *
 * <p>对原始请求体（JSON 字符串）以订阅密钥计算 HMAC-SHA256，输出形如
 * {@code sha256=<hex>} 的签名，放在 {@value #SIGNATURE_HEADER} 请求头中，
 * 供接收方校验请求确实来自本平台且未被篡改。</p>
 *
 * @author HFusionHub Team
 */
public final class WebhookSignatureUtils {

    /** 签名请求头名称 */
    public static final String SIGNATURE_HEADER = "X-HFusionHub-Signature";

    /** 事件类型请求头名称 */
    public static final String EVENT_HEADER = "X-HFusionHub-Event";

    private static final String HMAC_ALGORITHM = "HmacSHA256";

    private WebhookSignatureUtils() {}

    /**
     * 计算 HMAC-SHA256 签名
     *
     * @param secret  订阅密钥（为空时返回 null，表示不签名）
     * @param payload 原始请求体
     * @return {@code sha256=<hex>} 格式签名，或 null
     */
    public static String sign(String secret, String payload) {
        if (secret == null || secret.isBlank() || payload == null) {
            return null;
        }
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), HMAC_ALGORITHM));
            byte[] digest = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            return "sha256=" + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException | InvalidKeyException e) {
            throw new IllegalStateException("HMAC-SHA256 签名计算失败", e);
        }
    }
}
