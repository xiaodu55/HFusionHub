package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.service.AgentTaskService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Contract test for POST /internal/agent/approvals/consume.
 *
 * Pins the R&lt;T&gt; wire envelope that the Python ``consume_execution_token()``
 * client parses: ``{"code":200,"message":"success","data":{"consumed":true},...}``.
 * Covers success, duplicate/replayed consumption, wrong execution token,
 * wrong/missing internal token, and the Java-side error contract.
 */
class AgentApprovalInternalControllerTest {

    private static final String VALID_TOKEN = "test-internal-token-1";
    private AgentApprovalInternalController controller;
    private AgentTaskService agentTaskService;
    private ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        agentTaskService = mock(AgentTaskService.class);
        controller = new AgentApprovalInternalController(agentTaskService);
        ReflectionTestUtils.setField(controller, "expectedToken", VALID_TOKEN);
    }

    @AfterEach
    void tearDown() {
        reset(agentTaskService);
    }

    private HttpServletRequest req(String token) {
        HttpServletRequest req = mock(HttpServletRequest.class);
        when(req.getHeader("X-Internal-Token")).thenReturn(token);
        return req;
    }

    private Map<String, String> body(String approvalId, String executionToken) {
        Map<String, String> body = new HashMap<>();
        body.put("approval_id", approvalId);
        body.put("execution_token", executionToken);
        return body;
    }

    @Test
    void consumeSuccessReturns200EnvelopeWithConsumedTrue() throws Exception {
        when(agentTaskService.consumeExecutionToken("appr-1", "tok")).thenReturn(true);

        R<Map<String, Object>> r = controller.consume(body("appr-1", "tok"), req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(Boolean.TRUE, r.getData().get("consumed"));
        verify(agentTaskService).consumeExecutionToken("appr-1", "tok");
    }

    @Test
    void wireFormatMatchesPythonClient() throws Exception {
        when(agentTaskService.consumeExecutionToken("appr-1", "tok")).thenReturn(true);

        R<Map<String, Object>> r = controller.consume(body("appr-1", "tok"), req(VALID_TOKEN));
        String wire = objectMapper.writeValueAsString(r);

        // Python reads: envelope["data"]["consumed"] is True
        JsonNode envelope = objectMapper.readTree(wire);
        assertEquals(200, envelope.get("code").asInt());
        assertEquals("success", envelope.get("message").asText());
        assertTrue(envelope.get("data").get("consumed").asBoolean());
    }

    @Test
    void duplicateReplayedConsumptionReturnsConsumedFalse() {
        when(agentTaskService.consumeExecutionToken("appr-1", "tok")).thenReturn(false);

        R<Map<String, Object>> r = controller.consume(body("appr-1", "tok"), req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(Boolean.FALSE, r.getData().get("consumed"));
    }

    @Test
    void wrongExecutionTokenReturnsConsumedFalse() {
        when(agentTaskService.consumeExecutionToken("appr-1", "wrong")).thenReturn(false);

        R<Map<String, Object>> r = controller.consume(body("appr-1", "wrong"), req(VALID_TOKEN));

        assertEquals(200, r.getCode());
        assertEquals(Boolean.FALSE, r.getData().get("consumed"));
    }

    @Test
    void wrongInternalTokenReturns403WithoutCallingService() {
        R<Map<String, Object>> r = controller.consume(body("appr-1", "tok"), req("not-the-token"));
        assertEquals(403, r.getCode());
        verifyNoInteractions(agentTaskService);
    }

    @Test
    void missingInternalTokenReturns403() {
        R<Map<String, Object>> r = controller.consume(body("appr-1", "tok"), req(null));
        assertEquals(403, r.getCode());
        verifyNoInteractions(agentTaskService);
    }

    @Test
    void partialInternalTokenReturns403() {
        R<Map<String, Object>> r = controller.consume(body("appr-1", "tok"), req(VALID_TOKEN.substring(0, 5)));
        assertEquals(403, r.getCode());
        verifyNoInteractions(agentTaskService);
    }

    @Test
    void missingFieldsRejected() {
        R<Map<String, Object>> r = controller.consume(new HashMap<>(), req(VALID_TOKEN));
        assertEquals(500, r.getCode());
        verifyNoInteractions(agentTaskService);
    }
}
