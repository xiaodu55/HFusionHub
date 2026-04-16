package com.hfusionhub.common.utils;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

class ModelCredentialCipherTest {

    @Test
    void encryptsAndDecryptsWithoutPersistingPlaintext() {
        ModelCredentialCipher cipher = new ModelCredentialCipher();
        ReflectionTestUtils.setField(cipher, "encryptionSecret", "test-encryption-secret");

        String encrypted = cipher.encrypt("sk-private-value");

        assertThat(encrypted).startsWith("v1:");
        assertThat(encrypted).doesNotContain("sk-private-value");
        assertThat(cipher.decrypt(encrypted)).isEqualTo("sk-private-value");
    }
}

