package com.hfusionhub.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import io.minio.BucketExistsArgs;
import io.minio.GetPresignedObjectUrlArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.StatObjectArgs;
import io.minio.StatObjectResponse;
import java.io.ByteArrayInputStream;
import java.time.Duration;
import okhttp3.Headers;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * MinioArtifactStore 单元测试 — R15-28 租户桶隔离与旧对象回退。
 */
class MinioArtifactStoreTest {

    private static final Long TENANT_ID = 7L;

    private MinioClient minioClient;
    private MinioArtifactStore store;

    @BeforeEach
    void setUp() throws Exception {
        store = new MinioArtifactStore("http://localhost:9002", "minioadmin", "minioadmin");
        minioClient = mock(MinioClient.class);
        ReflectionTestUtils.setField(store, "minioClient", minioClient);
        ReflectionTestUtils.setField(store, "bucketName", "hfusionhub");
        when(minioClient.bucketExists(any(BucketExistsArgs.class))).thenReturn(true);
        Mockito.doAnswer(inv -> null).when(minioClient).makeBucket(any(MakeBucketArgs.class));
    }

    @Test
    void uploadWithTenantWritesToTenantBucket() throws Exception {
        Mockito.doAnswer(inv -> null).when(minioClient).putObject(any(PutObjectArgs.class));

        store.uploadWheel(
                TENANT_ID, "demo", "1.0.0", "abcdef1234567890",
                new ByteArrayInputStream(new byte[] {1, 2, 3}), 3);

        ArgumentCaptor<PutObjectArgs> captor = ArgumentCaptor.forClass(PutObjectArgs.class);
        Mockito.verify(minioClient).putObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("hfusionhub-t7");
    }

    @Test
    void uploadWithoutTenantWritesToDefaultBucket() throws Exception {
        Mockito.doAnswer(inv -> null).when(minioClient).putObject(any(PutObjectArgs.class));

        store.uploadWheel("demo", "1.0.0", "abcdef1234567890",
                new ByteArrayInputStream(new byte[] {1}), 1);

        ArgumentCaptor<PutObjectArgs> captor = ArgumentCaptor.forClass(PutObjectArgs.class);
        Mockito.verify(minioClient).putObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("hfusionhub");
    }

    @Test
    void presignFallsBackToDefaultBucketForLegacyObject() throws Exception {
        // 租户桶 stat 未命中，默认桶命中（隔离上线前的旧对象）
        when(minioClient.statObject(any(StatObjectArgs.class)))
                .thenThrow(new RuntimeException("missing"))
                .thenReturn(new StatObjectResponse(
                        Headers.of(java.util.Map.of("last-modified", "Wed, 21 Oct 2026 07:28:00 GMT")), "hfusionhub", "us-east-1", "plugins/demo/1.0.0/demo-1.0.0-abcdef12.whl"));
        when(minioClient.getPresignedObjectUrl(any(GetPresignedObjectUrlArgs.class)))
                .thenReturn("http://minio/hfusionhub/signed");

        String url = store.getPresignedUrl(
                TENANT_ID, "plugins/demo/1.0.0/demo-1.0.0-abcdef12.whl", Duration.ofMinutes(5));

        assertThat(url).isEqualTo("http://minio/hfusionhub/signed");
        ArgumentCaptor<GetPresignedObjectUrlArgs> captor =
                ArgumentCaptor.forClass(GetPresignedObjectUrlArgs.class);
        Mockito.verify(minioClient).getPresignedObjectUrl(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("hfusionhub");
    }

    @Test
    void presignUsesTenantBucketWhenObjectFoundThere() throws Exception {
        StatObjectResponse hit = new StatObjectResponse(
                Headers.of(java.util.Map.of("last-modified", "Wed, 21 Oct 2026 07:28:00 GMT")), "hfusionhub-t7", "us-east-1", "plugins/demo/1.0.0/demo-1.0.0-abcdef12.whl");
        when(minioClient.statObject(any(StatObjectArgs.class))).thenReturn(hit);
        when(minioClient.getPresignedObjectUrl(any(GetPresignedObjectUrlArgs.class)))
                .thenReturn("http://minio/signed");

        store.getPresignedUrl(
                TENANT_ID, "plugins/demo/1.0.0/demo-1.0.0-abcdef12.whl", Duration.ofMinutes(5));

        ArgumentCaptor<GetPresignedObjectUrlArgs> captor =
                ArgumentCaptor.forClass(GetPresignedObjectUrlArgs.class);
        Mockito.verify(minioClient).getPresignedObjectUrl(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("hfusionhub-t7");
    }

    @Test
    void deleteRemovesFromTenantBucketWhenPresent() throws Exception {
        StatObjectResponse hit = new StatObjectResponse(
                Headers.of(java.util.Map.of("last-modified", "Wed, 21 Oct 2026 07:28:00 GMT")), "hfusionhub-t7", "us-east-1", "plugins/demo/1.0.0/x.whl");
        when(minioClient.statObject(any(StatObjectArgs.class))).thenReturn(hit);
        Mockito.doAnswer(inv -> null).when(minioClient).removeObject(any(RemoveObjectArgs.class));

        store.deleteWheel(TENANT_ID, "plugins/demo/1.0.0/x.whl");

        ArgumentCaptor<RemoveObjectArgs> captor = ArgumentCaptor.forClass(RemoveObjectArgs.class);
        Mockito.verify(minioClient).removeObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo("hfusionhub-t7");
    }
}
