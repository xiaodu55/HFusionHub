package com.hfusionhub.storage;

import io.minio.*;
import io.minio.http.Method;
import jakarta.annotation.PostConstruct;
import java.io.InputStream;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * MinIO artifact storage for plugin wheel files.
 *
 * <p>R15-28 租户隔离：上传始终写入租户专属桶 {@code <bucket>-t<tenantId>}，
 * 不同租户的工件互不可见；读取/删除优先命租户桶，未命中时回退默认桶以兼容
 * 隔离上线前已存在的旧对象。{@code tenantId == null} 时退化为默认桶（内部
 * /演示路径）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class MinioArtifactStore {

    private final MinioClient minioClient;

    @Value("${minio.bucket-name:hfusionhub}")
    private String bucketName;

    /** 已确认存在的桶缓存，避免每次上传都做 bucketExists 往返 */
    private final Set<String> knownBuckets = ConcurrentHashMap.newKeySet();

    public MinioArtifactStore(
            @Value("${minio.endpoint:http://localhost:9002}") String endpoint,
            @Value("${minio.access-key:minioadmin}") String accessKey,
            @Value("${minio.secret-key:minioadmin}") String secretKey) {
        this.minioClient = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
    }

    @PostConstruct
    public void init() {
        ensureBucket(bucketName);
    }

    /** 租户隔离桶名：tenantId 为空时使用默认桶 */
    private String resolveBucket(Long tenantId) {
        return tenantId == null ? bucketName : bucketName + "-t" + tenantId;
    }

    private void ensureBucket(String bucket) {
        if (!knownBuckets.add(bucket)) {
            return;
        }
        try {
            boolean exists = minioClient.bucketExists(
                    BucketExistsArgs.builder().bucket(bucket).build());
            if (!exists) {
                minioClient.makeBucket(
                        MakeBucketArgs.builder().bucket(bucket).build());
                log.info("Created MinIO bucket: {}", bucket);
            }
        } catch (Exception e) {
            knownBuckets.remove(bucket);
            log.warn("MinIO not available, artifact storage disabled (bucket {}): {}",
                    bucket, e.getMessage());
        }
    }

    /**
     * Upload a plugin wheel to MinIO.
     *
     * @param tenantId    owner tenant ({@code null} → default bucket)
     * @param pluginName  plugin machine name
     * @param version     semver version
     * @param artifactHash expected SHA-256 hash
     * @param data        wheel file input stream
     * @param size        wheel file size in bytes
     * @return MinIO object key
     */
    public String uploadWheel(Long tenantId, String pluginName, String version, String artifactHash,
                              InputStream data, long size) {
        String objectKey = buildObjectKey(pluginName, version, artifactHash);
        String bucket = resolveBucket(tenantId);
        ensureBucket(bucket);
        try {
            minioClient.putObject(PutObjectArgs.builder().bucket(bucket).object(objectKey).stream(data, size, -1)
                    .contentType("application/zip")
                    .build());
            log.info("Uploaded plugin wheel to {}: {} ({} bytes)", bucket, objectKey, size);
            return objectKey;
        } catch (Exception e) {
            throw new RuntimeException("Failed to upload artifact to MinIO: " + e.getMessage(), e);
        }
    }

    /**
     * @deprecated 租户隔离前旧签名；等价于写入默认桶。新代码请用
     * {@link #uploadWheel(Long, String, String, String, InputStream, long)}。
     */
    @Deprecated
    public String uploadWheel(String pluginName, String version, String artifactHash, InputStream data, long size) {
        return uploadWheel(null, pluginName, version, artifactHash, data, size);
    }

    /**
     * Download a plugin wheel from MinIO（优先租户桶，旧对象回退默认桶）。
     */
    public InputStream downloadWheel(Long tenantId, String objectKey) {
        try {
            return minioClient.getObject(GetObjectArgs.builder()
                    .bucket(resolveObjectBucket(tenantId, objectKey))
                    .object(objectKey)
                    .build());
        } catch (Exception e) {
            throw new RuntimeException("Failed to download artifact from MinIO: " + e.getMessage(), e);
        }
    }

    /** @deprecated 租户隔离前旧签名；等价于从默认桶下载。 */
    @Deprecated
    public InputStream downloadWheel(String objectKey) {
        return downloadWheel(null, objectKey);
    }

    /**
     * Generate a presigned download URL（桶按对象实际所在解析）。
     */
    public String getPresignedUrl(Long tenantId, String objectKey, Duration expiry) {
        try {
            return minioClient.getPresignedObjectUrl(GetPresignedObjectUrlArgs.builder()
                    .method(Method.GET)
                    .bucket(resolveObjectBucket(tenantId, objectKey))
                    .object(objectKey)
                    .expiry((int) expiry.getSeconds())
                    .build());
        } catch (Exception e) {
            throw new RuntimeException("Failed to generate presigned URL: " + e.getMessage(), e);
        }
    }

    /** @deprecated 租户隔离前旧签名；等价于默认桶。 */
    @Deprecated
    public String getPresignedUrl(String objectKey, Duration expiry) {
        return getPresignedUrl(null, objectKey, expiry);
    }

    /**
     * Check if an artifact exists in MinIO.
     */
    public boolean exists(Long tenantId, String objectKey) {
        try {
            minioClient.statObject(StatObjectArgs.builder()
                    .bucket(resolveObjectBucket(tenantId, objectKey))
                    .object(objectKey)
                    .build());
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /** @deprecated 租户隔离前旧签名；等价于默认桶。 */
    @Deprecated
    public boolean exists(String objectKey) {
        return exists(null, objectKey);
    }

    /**
     * Delete a plugin wheel from MinIO（优先租户桶，旧对象回退默认桶）。
     */
    public void deleteWheel(Long tenantId, String objectKey) {
        try {
            minioClient.removeObject(RemoveObjectArgs.builder()
                    .bucket(resolveObjectBucket(tenantId, objectKey))
                    .object(objectKey)
                    .build());
            log.info("Deleted plugin wheel: {}", objectKey);
        } catch (Exception e) {
            log.warn("Failed to delete artifact from MinIO: {}", e.getMessage());
        }
    }

    /** @deprecated 租户隔离前旧签名；等价于从默认桶删除。 */
    @Deprecated
    public void deleteWheel(String objectKey) {
        deleteWheel(null, objectKey);
    }

    /**
     * Compute SHA-256 hash of a stream.
     */
    public static String computeSha256(InputStream data) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];
        int bytesRead;
        while ((bytesRead = data.read(buffer)) != -1) {
            digest.update(buffer, 0, bytesRead);
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private String buildObjectKey(String pluginName, String version, String artifactHash) {
        String shortHash =
                artifactHash != null && artifactHash.length() >= 8 ? artifactHash.substring(0, 8) : "unknown";
        return String.format("plugins/%s/%s/%s-%s-%s.whl", pluginName, version, pluginName, version, shortHash);
    }

    /**
     * 解析对象实际所在桶：租户桶命中则用之；未命中且租户桶不同于默认桶时
     * 回退默认桶（兼容隔离上线前的旧对象）。解析成功即纳入桶缓存。
     */
    private String resolveObjectBucket(Long tenantId, String objectKey) {
        String tenantBucket = resolveBucket(tenantId);
        if (objectInBucket(tenantBucket, objectKey)) {
            return tenantBucket;
        }
        String defaultBucket = resolveBucket(null);
        if (!defaultBucket.equals(tenantBucket) && objectInBucket(defaultBucket, objectKey)) {
            return defaultBucket;
        }
        return tenantBucket;
    }

    private boolean objectInBucket(String bucket, String objectKey) {
        try {
            minioClient.statObject(StatObjectArgs.builder().bucket(bucket).object(objectKey).build());
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
