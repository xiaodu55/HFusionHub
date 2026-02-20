package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

/**
 * Pure unit test for {@link HealthController}.
 * The health endpoint is a simple POJO call — no Spring context needed.
 */
class HealthControllerTest {

    @Test
    void healthReturnsUpStatus() {
        R<Map<String, Object>> response = new HealthController().health();

        assertEquals(200, response.getCode());
        assertEquals("UP", response.getData().get("status"));
        assertNotNull(response.getData().get("timestamp"));
    }
}
