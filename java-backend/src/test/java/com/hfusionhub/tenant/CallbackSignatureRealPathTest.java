package com.hfusionhub.tenant;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.controller.VectorizationController;
import com.hfusionhub.dto.DocumentIndexCallbackDTO;
import com.hfusionhub.service.VectorizationService;
import com.hfusionhub.service.impl.VectorizationCallbackService;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * End-to-end test for the real callback path: {@link CallbackSignatureFilter}
 * buffers the body, verifies the HMAC, then hands the replayable wrapper to
 * {@link VectorizationController}, whose {@code @RequestBody String rawBody}
 * must still receive the FULL payload (regression guard for the P0 where
 * ContentCachingRequestWrapper consumed the stream and starved the controller).
 */
class CallbackSignatureRealPathTest {

    private static final String SECRET = "test-callback-secret";

    private VectorizationService vectorizationService;
    private VectorizationCallbackService vectorizationCallbackService;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        vectorizationService = mock(VectorizationService.class);
        vectorizationCallbackService = mock(VectorizationCallbackService.class);

        CallbackSignatureFilter filter = new CallbackSignatureFilter();
        ReflectionTestUtils.setField(filter, "callbackSecret", SECRET);

        VectorizationController controller =
                new VectorizationController(vectorizationService, vectorizationCallbackService, new ObjectMapper());
        ReflectionTestUtils.setField(controller, "callbackSecret", SECRET);

        mockMvc = MockMvcBuilders.standaloneSetup(controller).addFilters(filter).build();
    }

    @Test
    void validCallbackReachesControllerWithFullBody() throws Exception {
        String body = "{\"status\":\"COMPLETED\",\"chunkCount\":3,\"indexVersion\":\"v2\"}";

        mockMvc.perform(post("/vectorize/42/callback")
                        .contentType("application/json")
                        .header("X-Callback-Secret", SECRET)
                        .header("X-Callback-Signature", hmac(body))
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200));

        verify(vectorizationCallbackService).updateDocumentStatus(eq(42L), any(DocumentIndexCallbackDTO.class));
    }

    @Test
    void invalidSignatureIsRejectedBeforeController() throws Exception {
        String body = "{\"status\":\"COMPLETED\"}";

        mockMvc.perform(post("/vectorize/42/callback")
                        .contentType("application/json")
                        .header("X-Callback-Secret", SECRET)
                        .header("X-Callback-Signature", "tampered-signature")
                        .content(body))
                // 评估 M6：鉴权/签名失败必须返回 401（此前返回 200 + 错误 body
                // 会被 Python 回调客户端误当成功）
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(500));

        verify(vectorizationCallbackService, org.mockito.Mockito.never()).updateDocumentStatus(any(), any());
    }

    private static String hmac(String body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            SecretKeySpec keySpec = new SecretKeySpec(SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
            mac.init(keySpec);
            return Base64.getEncoder().encodeToString(mac.doFinal(body.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
