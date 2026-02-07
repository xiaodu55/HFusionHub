package com.hfusionhub.controller;

import com.hfusionhub.common.result.R;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class HealthControllerTest {

    @Test
    void healthReturnsUpStatus() {
        R<Map<String, Object>> response = new HealthController().health();

        assertEquals(200, response.getCode());
        assertEquals("UP", response.getData().get("status"));
        assertNotNull(response.getData().get("timestamp"));
    }
}
