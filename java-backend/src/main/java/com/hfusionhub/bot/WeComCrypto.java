package com.hfusionhub.bot;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.List;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * 企业微信回调消息加解密（Batch 6）—— 按官方协议实现，零第三方依赖。
 *
 * <ul>
 *   <li>签名：{@code msg_signature = SHA1(sort(token, timestamp, nonce, encrypt))}</li>
 *   <li>密文：Base64(AES-256-CBC(随机 16B + msg_len(4B 网络序) + msg + receiveId))，
 *       key = Base64Decode(EncodingAESKey + "=")，IV = key 前 16 字节，PKCS7 填充</li>
 * </ul>
 */
public final class WeComCrypto {

    private WeComCrypto() {
    }

    /** 回调签名校验（常量时间比较）。 */
    public static boolean verifySignature(String token, String timestamp, String nonce,
                                          String encrypt, String msgSignature) {
        String expected = signature(token, timestamp, nonce, encrypt);
        if (expected == null || msgSignature == null) {
            return false;
        }
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8),
                msgSignature.getBytes(StandardCharsets.UTF_8));
    }

    public static String signature(String token, String timestamp, String nonce, String encrypt) {
        List<String> parts = new ArrayList<>();
        Collections.addAll(parts, token, timestamp, nonce, encrypt);
        Collections.sort(parts);
        try {
            MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
            byte[] digest = sha1.digest(String.join("", parts).getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : digest) {
                hex.append(String.format("%02x", b));
            }
            return hex.toString();
        } catch (Exception e) {
            throw new IllegalStateException("SHA-1 unavailable", e);
        }
    }

    /** 解密 encrypt 字段，返回明文 XML。 */
    public static String decrypt(String encodingAesKey, String encrypt) {
        try {
            byte[] aesKey = Base64.getDecoder().decode(encodingAesKey + "=");
            if (aesKey.length != 32) {
                throw new IllegalArgumentException("EncodingAESKey 非法（解码后须为 32 字节）");
            }
            Cipher cipher = Cipher.getInstance("AES/CBC/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    new SecretKeySpec(aesKey, "AES"),
                    new IvParameterSpec(aesKey, 0, 16));
            byte[] decrypted = cipher.doFinal(Base64.getDecoder().decode(encrypt));
            // PKCS7 去填充
            int pad = decrypted[decrypted.length - 1];
            if (pad < 1 || pad > 32) {
                throw new IllegalArgumentException("PKCS7 填充非法");
            }
            int end = decrypted.length - pad;
            // 明文结构：16B 随机 + 4B 网络序消息长度 + 消息 + receiveId
            int msgLen = ((decrypted[16] & 0xFF) << 24) | ((decrypted[17] & 0xFF) << 16)
                    | ((decrypted[18] & 0xFF) << 8) | (decrypted[19] & 0xFF);
            if (msgLen < 0 || 20 + msgLen > end) {
                throw new IllegalArgumentException("消息长度字段非法");
            }
            return new String(decrypted, 20, msgLen, StandardCharsets.UTF_8);
        } catch (IllegalStateException | IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("WeCom decrypt failed: " + e.getMessage(), e);
        }
    }

    /** 加密（测试 round-trip 与需要被动回复的场景使用）。 */
    public static String encrypt(String encodingAesKey, String plainXml, String receiveId) {
        try {
            byte[] aesKey = Base64.getDecoder().decode(encodingAesKey + "=");
            byte[] random = new byte[16];
            new java.security.SecureRandom().nextBytes(random);
            byte[] msg = plainXml.getBytes(StandardCharsets.UTF_8);
            byte[] receive = receiveId.getBytes(StandardCharsets.UTF_8);
            int msgLen = msg.length;
            int total = 16 + 4 + msgLen + receive.length;
            int pad = 32 - total % 32;
            byte[] plain = new byte[total + pad];
            System.arraycopy(random, 0, plain, 0, 16);
            plain[16] = (byte) ((msgLen >> 24) & 0xFF);
            plain[17] = (byte) ((msgLen >> 16) & 0xFF);
            plain[18] = (byte) ((msgLen >> 8) & 0xFF);
            plain[19] = (byte) (msgLen & 0xFF);
            System.arraycopy(msg, 0, plain, 20, msgLen);
            System.arraycopy(receive, 0, plain, 20 + msgLen, receive.length);
            for (int i = 0; i < pad; i++) {
                plain[total + i] = (byte) pad;
            }
            Cipher cipher = Cipher.getInstance("AES/CBC/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(aesKey, "AES"),
                    new IvParameterSpec(aesKey, 0, 16));
            return Base64.getEncoder().encodeToString(cipher.doFinal(plain));
        } catch (Exception e) {
            throw new IllegalStateException("WeCom encrypt failed: " + e.getMessage(), e);
        }
    }
}
