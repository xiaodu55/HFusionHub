package com.hfusionhub.service.impl;

import com.hfusionhub.common.exception.BusinessException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

/**
 * 对话图片输入（实验特性）的图片存储：上传校验、相对 URL 签发、
 * URL→base64 转换（供 Python 视觉管线）与回源读取。
 *
 * <p>安全边界：文件名由本类签发（UUID + 白名单扩展名），回源按白名单
 * 正则校验并 normalize 后限制在根目录内，杜绝路径穿越；魔数校验
 * （JPEG/PNG/WEBP）防止改扩展名的伪造上传。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
public class ChatImageStorage {

    private static final long MAX_IMAGE_BYTES = 5L * 1024 * 1024;
    private static final int MAX_IMAGES_PER_MESSAGE = 4;
    private static final String URL_PREFIX = "/api/conversation/chat-image/";
    private static final Pattern SAFE_NAME =
            Pattern.compile("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.(png|jpe?g|webp)$");

    private final Path root;
    private final com.fasterxml.jackson.databind.ObjectMapper mapper =
            new com.fasterxml.jackson.databind.ObjectMapper();

    public ChatImageStorage(@Value("${app.chat-image-dir:uploads/chat-images}") String dir) {
        this.root = Path.of(dir);
    }

    /** 保存上传图片，返回相对 URL；魔数（JPEG/PNG/WEBP）与大小（≤5MB）校验。 */
    public String save(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new BusinessException("图片内容为空");
        }
        if (file.getSize() > MAX_IMAGE_BYTES) {
            throw new BusinessException("单张图片不能超过5MB");
        }
        byte[] bytes;
        try {
            bytes = file.getBytes();
        } catch (IOException e) {
            throw new BusinessException("图片读取失败，请重试");
        }
        String ext = detectExtension(bytes);
        if (ext == null) {
            throw new BusinessException("仅支持 JPG / PNG / WEBP 图片");
        }
        try {
            Files.createDirectories(root);
            String name = UUID.randomUUID() + ext;
            Files.write(root.resolve(name), bytes);
            return URL_PREFIX + name;
        } catch (IOException e) {
            log.error("对话图片保存失败", e);
            throw new BusinessException("图片保存失败，请稍后重试");
        }
    }

    /** 校验 URL 列表（数量上限 + 本类签发 + 文件存在）；不合法抛业务异常。 */
    public List<Path> validateAndResolve(List<String> urls) {
        if (urls == null || urls.isEmpty()) {
            return List.of();
        }
        if (urls.size() > MAX_IMAGES_PER_MESSAGE) {
            throw new BusinessException("每次最多携带4张图片");
        }
        return urls.stream().map(this::resolve).toList();
    }

    /** 相对 URL 列表 → base64 data URL 列表（供 Python 视觉管线）。 */
    public List<String> toDataUrls(List<String> urls) {
        return validateAndResolve(urls).stream().map(this::toDataUrl).toList();
    }

    public String toDataUrl(Path path) {
        try {
            byte[] bytes = Files.readAllBytes(path);
            return "data:" + contentType(path.getFileName().toString()) + ";base64,"
                    + Base64.getEncoder().encodeToString(bytes);
        } catch (IOException e) {
            throw new BusinessException("图片读取失败，请重试");
        }
    }

    /** URL → 本地文件 Path；名称/归属/存在性校验。 */
    public Path resolve(String url) {
        String name = url == null ? "" : url.substring(url.lastIndexOf('/') + 1);
        if (!url.startsWith(URL_PREFIX) || !SAFE_NAME.matcher(name).matches()) {
            throw new BusinessException("图片地址不合法");
        }
        Path path = root.resolve(name).normalize();
        if (!path.startsWith(root) || !Files.exists(path)) {
            throw new BusinessException("图片不存在或已过期");
        }
        return path;
    }

    /** 回源读取图片字节（名称按白名单校验）。 */
    public byte[] read(String name) {
        try {
            return Files.readAllBytes(resolve(URL_PREFIX + name));
        } catch (BusinessException e) {
            throw e;
        } catch (IOException e) {
            throw new BusinessException("图片读取失败");
        }
    }

    public String contentType(String name) {
        return name.endsWith(".png") ? "image/png"
                : name.endsWith(".webp") ? "image/webp" : "image/jpeg";
    }

    /** URL 列表 → JSON 字符串（message.images 落库格式）。 */
    public String toJson(List<String> urls) {
        try {
            return mapper.writeValueAsString(urls);
        } catch (Exception e) {
            throw new BusinessException("图片信息序列化失败");
        }
    }

    /** message.images 落库字符串 → URL 列表；空/损坏返回空列表。 */
    public List<String> fromJson(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return mapper.readValue(json, mapper.getTypeFactory()
                    .constructCollectionType(List.class, String.class));
        } catch (Exception e) {
            log.warn("message.images 反序列化失败，按无图片处理: {}", e.getMessage());
            return List.of();
        }
    }

    private String detectExtension(byte[] b) {
        if (b.length >= 3 && (b[0] & 0xFF) == 0xFF && (b[1] & 0xFF) == 0xD8 && (b[2] & 0xFF) == 0xFF) {
            return ".jpg";
        }
        if (b.length >= 8 && (b[0] & 0xFF) == 0x89 && b[1] == 'P' && b[2] == 'N' && b[3] == 'G') {
            return ".png";
        }
        if (b.length >= 12 && b[0] == 'R' && b[1] == 'I' && b[2] == 'F' && b[3] == 'F'
                && b[8] == 'W' && b[9] == 'E' && b[10] == 'B' && b[11] == 'P') {
            return ".webp";
        }
        return null;
    }
}
