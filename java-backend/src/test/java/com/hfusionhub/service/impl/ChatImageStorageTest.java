package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.hfusionhub.common.exception.BusinessException;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

/**
 * 对话图片存储测试：魔数校验、大小/数量上限、URL 签发与回源、JSON 往返。
 */
class ChatImageStorageTest {

    @TempDir
    Path tempDir;

    private ChatImageStorage storage() {
        return new ChatImageStorage(tempDir.toString());
    }

    private byte[] pngBytes(int size) {
        byte[] b = new byte[size];
        b[0] = (byte) 0x89;
        b[1] = 'P';
        b[2] = 'N';
        b[3] = 'G';
        return b;
    }

    @Test
    void save_accepts_png_magic_and_issues_relative_url() {
        String url = storage().save(new MockMultipartFile("file", "a.png", "image/png", pngBytes(64)));
        assertTrue(url.startsWith("/api/conversation/chat-image/"), url);
        assertTrue(url.endsWith(".png"), url);
    }

    @Test
    void save_rejects_non_image_bytes() {
        MockMultipartFile file = new MockMultipartFile("file", "a.png", "image/png", "hello text".getBytes());
        BusinessException e = assertThrows(BusinessException.class, () -> storage().save(file));
        assertTrue(e.getMessage().contains("JPG"));
    }

    @Test
    void save_rejects_oversized_image() {
        MockMultipartFile file = new MockMultipartFile("file", "a.png", "image/png", pngBytes(6 * 1024 * 1024));
        BusinessException e = assertThrows(BusinessException.class, () -> storage().save(file));
        assertTrue(e.getMessage().contains("5MB"));
    }

    @Test
    void resolve_rejects_foreign_url() {
        assertThrows(BusinessException.class, () -> storage().resolve("/etc/passwd"));
        assertThrows(BusinessException.class, () -> storage().resolve("/api/conversation/chat-image/../../app.yml"));
    }

    @Test
    void resolve_rejects_missing_file() {
        ChatImageStorage s = storage();
        String url = s.save(new MockMultipartFile("file", "a.png", "image/png", pngBytes(32)));
        String name = url.substring(url.lastIndexOf('/') + 1);
        java.io.File disk = tempDir.resolve(name).toFile();
        assertTrue(disk.delete());
        assertThrows(BusinessException.class, () -> s.resolve(url));
    }

    @Test
    void to_data_urls_round_trip() {
        ChatImageStorage s = storage();
        String url = s.save(new MockMultipartFile("file", "a.png", "image/png", pngBytes(32)));
        var dataUrls = s.toDataUrls(java.util.List.of(url));
        assertEquals(1, dataUrls.size());
        assertTrue(dataUrls.get(0).startsWith("data:image/png;base64,"));
    }

    @Test
    void validate_and_resolve_rejects_more_than_four() {
        ChatImageStorage s = storage();
        var urls = new java.util.ArrayList<String>();
        for (int i = 0; i < 5; i++) {
            urls.add(s.save(new MockMultipartFile("file", "a.png", "image/png", pngBytes(16 + i))));
        }
        BusinessException e = assertThrows(BusinessException.class, () -> s.validateAndResolve(urls));
        assertTrue(e.getMessage().contains("4张"));
    }

    @Test
    void json_round_trip() {
        ChatImageStorage s = storage();
        var urls = java.util.List.of("/api/conversation/chat-image/a.png");
        assertEquals(urls, s.fromJson(s.toJson(urls)));
        assertEquals(java.util.List.of(), s.fromJson(null));
        assertEquals(java.util.List.of(), s.fromJson("{broken"));
    }
}
