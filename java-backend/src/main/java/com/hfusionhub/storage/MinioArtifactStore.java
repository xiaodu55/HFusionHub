package com.hfusionhub.storage;

import io.minio.*;
import io.minio.http.Method;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import java.io.InputStream;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;

/**
 * MinIO artifact storage for plugin wheel files.
 *
 * @author HFusionHub Team
 */
@Slf4j
@Component
public class MinioArtifactStore {

    private final MinioClient minioClient;

    @Value("${minio.bucket-name:hfusionhub}")
    private String bucketName;

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
        try {
            boolean exists = minioClient.bucketExists(BucketExistsArgs.builder()
                    .bucket(bucketName).build());
            if (!exists) {
                minioClient.makeBucket(MakeBucketArgs.builder()
                        .bucket(bucketName).build());
                log.info("Created MinIO bucket: {}", bucketName);
            }
        } catch (Exception e) {
            log.warn("MinIO not available, artifact storage disabled: {}", e.getMessage());
        }
    }

    /**
     * Upload a plugin wheel to MinIO.
     *
     * @param pluginName  plugin machine name
     * @param version     semver version
     * @param artifactHash expected SHA-256 hash
     * @param data        wheel file input stream
     * @param size        wheel file size in bytes
     * @return MinIO object key
     */
    public String uploadWheel(String pluginName, String version, String artifactHash,
                              InputStream data, long size) {
        String objectKey = buildObjectKey(pluginName, version, artifactHash);
        try {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucketName)
                    .object(objectKey)
                    .stream(data, size, -1)
                    .contentType("application/zip")
                    .build());
            log.info("Uploaded plugin wheel: {} ({} bytes)", objectKey, size);
            return objectKey;
        } catch (Exception e) {
            throw new RuntimeException("Failed to upload artifact to MinIO: " + e.getMessage(), e);
        }
    }

    /**
     * Download a plugin wheel from MinIO.
     */
    public InputStream downloadWheel(String objectKey) {
        try {
            return minioClient.getObject(GetObjectArgs.builder()
                    .bucket(bucketName)
                    .object(objectKey)
                    .build());
        } catch (Exception e) {
            throw new RuntimeException("Failed to download artifact from MinIO: " + e.getMessage(), e);
        }
    }

    /**
     * Generate a presigned download URL.
     */
    public String getPresignedUrl(String objectKey, Duration expiry) {
        try {
            return minioClient.getPresignedObjectUrl(GetPresignedObjectUrlArgs.builder()
                    .method(Method.GET)
                    .bucket(bucketName)
                    .object(objectKey)
                    .expiry((int) expiry.getSeconds())
                    .build());
        } catch (Exception e) {
            throw new RuntimeException("Failed to generate presigned URL: " + e.getMessage(), e);
        }
    }

    /**
     * Check if an artifact exists in MinIO.
     */
    public boolean exists(String objectKey) {
        try {
            minioClient.statObject(StatObjectArgs.builder()
                    .bucket(bucketName)
                    .object(objectKey)
                    .build());
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Delete a plugin wheel from MinIO.
     */
    public void deleteWheel(String objectKey) {
        try {
            minioClient.removeObject(RemoveObjectArgs.builder()
                    .bucket(bucketName)
                    .object(objectKey)
                    .build());
            log.info("Deleted plugin wheel: {}", objectKey);
        } catch (Exception e) {
            log.warn("Failed to delete artifact from MinIO: {}", e.getMessage());
        }
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
        String shortHash = artifactHash != null && artifactHash.length() >= 8
                ? artifactHash.substring(0, 8) : "unknown";
        return String.format("plugins/%s/%s/%s-%s-%s.whl", pluginName, version, pluginName, version, shortHash);
    }
}
