package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.*;

import com.hfusionhub.common.result.R;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.UserMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class InternalPluginQuotaControllerTest {

    private static final String TOKEN = "plugin-quota-token";
    private UsageLedgerService ledger;
    private UserMapper userMapper;
    private InternalPluginQuotaController controller;

    @BeforeEach
    void setUp() {
        ledger = mock(UsageLedgerService.class);
        userMapper = mock(UserMapper.class);
        controller = new InternalPluginQuotaController(ledger, userMapper);
        ReflectionTestUtils.setField(controller, "expectedToken", TOKEN);
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @Test
    void reserveUsesTenantResolvedFromTheAuthenticatedUser() {
        User user = new User();
        user.setTenantId(11L);
        when(userMapper.selectById(7L)).thenReturn(user);
        doAnswer(invocation -> {
                    assertEquals(11L, TenantContext.requireTenantId());
                    return null;
                })
                .when(ledger)
                .reserve(any(), anyString(), anyLong(), anyString(), anyString());

        R<Map<String, Object>> response = controller.transition(payload("RESERVE", 11L), request(TOKEN));

        assertEquals(200, response.getCode());
        assertEquals("reserve", response.getData().get("operation"));
        assertEquals(11L, response.getData().get("tenant_id"));
        verify(ledger).reserve(UsageMeter.PLUGIN_EXECUTIONS, "exec-1", 1L, "PLUGIN_TOOL", "plugin-1:lookup");
    }

    @Test
    void rejectsTenantSpoofingBeforeAnyLedgerTransition() {
        User user = new User();
        user.setTenantId(12L);
        when(userMapper.selectById(7L)).thenReturn(user);

        R<Map<String, Object>> response = controller.transition(payload("RESERVE", 11L), request(TOKEN));

        assertEquals(403, response.getCode());
        verifyNoInteractions(ledger);
    }

    @Test
    void rejectInvalidTokenBeforeLookingUpUser() {
        R<Map<String, Object>> response = controller.transition(payload("RESERVE", 11L), request("wrong"));

        assertEquals(403, response.getCode());
        verifyNoInteractions(userMapper, ledger);
    }

    @Test
    void settleAndReleaseUseFixedOneExecutionAmount() {
        User user = new User();
        user.setTenantId(11L);
        when(userMapper.selectById(7L)).thenReturn(user);

        R<Map<String, Object>> settle = controller.transition(payload("SETTLE", 11L), request(TOKEN));
        R<Map<String, Object>> release = controller.transition(payload("RELEASE", 11L), request(TOKEN));

        assertTrue(settle.getCode() == 200 && release.getCode() == 200);
        verify(ledger).settle(UsageMeter.PLUGIN_EXECUTIONS, "exec-1", 1L, "PLUGIN_TOOL", "plugin-1:lookup");
        verify(ledger).release(UsageMeter.PLUGIN_EXECUTIONS, "exec-1");
    }

    private static Map<String, Object> payload(String operation, Long tenantId) {
        return Map.of(
                "operation",
                operation,
                "tenant_id",
                tenantId,
                "user_id",
                7L,
                "execution_id",
                "exec-1",
                "plugin_id",
                "plugin-1",
                "tool_name",
                "lookup");
    }

    private static HttpServletRequest request(String token) {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getHeader("X-Internal-Token")).thenReturn(token);
        return request;
    }
}
