package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.exception.GlobalExceptionHandler;
import com.hfusionhub.common.result.R;
import com.hfusionhub.dto.EvalCorpusImportResultDTO;
import com.hfusionhub.entity.EvalHarnessRun;
import com.hfusionhub.mapper.EvalHarnessRunMapper;
import com.hfusionhub.service.EvalCorpusImportService;
import com.hfusionhub.tenant.TenantContext;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.MediaType;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * Unit tests for {@link EvalHarnessInternalController}'s tenant handling.
 *
 * <p>{@code /internal/eval-harness/**} is excluded from both the Sa-Token login check
 * and {@code TenantContextInterceptor}, so the inbound {@code X-Tenant-Id} header is the
 * <b>only</b> thing that decides which tenant a run row or an imported corpus belongs to.
 * A missing header must therefore be rejected, never defaulted.</p>
 *
 * <p>The caller (python-ai) only inspects the HTTP status, so the last three cases drive the
 * endpoints through {@code MockMvc} with the real {@code GlobalExceptionHandler} attached:
 * a rejection has to be a <b>real</b> 403, not an {@code R.fail(403)} served over HTTP 200.</p>
 */
class EvalHarnessInternalControllerTest {

    private EvalHarnessRunMapper evalHarnessRunMapper;
    private EvalCorpusImportService evalCorpusImportService;
    private EvalHarnessInternalController controller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        evalHarnessRunMapper = mock(EvalHarnessRunMapper.class);
        evalCorpusImportService = mock(EvalCorpusImportService.class);
        controller = new EvalHarnessInternalController(evalHarnessRunMapper, evalCorpusImportService);
        ReflectionTestUtils.setField(controller, "expectedToken", "test-internal-token");
        // 挂上真实的全局异常处理器：本类的拒绝形状要按 HTTP 状态而非信封码验收
        mockMvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @AfterEach
    void tearDown() {
        TenantContext.clear();
    }

    @Test
    void recordRejectsMissingTenantHeaderInsteadOfDefaultingToTenant1() {
        BusinessException exception = assertThrows(
                BusinessException.class, () -> controller.record("test-internal-token", null, Map.of("run_file", "a.jsonl")));

        assertEquals(StatusCode.FORBIDDEN, exception.getCode());
        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void recordRejectsBlankTenantHeader() {
        BusinessException exception = assertThrows(BusinessException.class,
                () -> controller.record("test-internal-token", "   ", Map.of("run_file", "a.jsonl")));

        assertEquals(StatusCode.FORBIDDEN, exception.getCode());
        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void recordRejectsNonNumericTenantHeader() {
        BusinessException exception = assertThrows(BusinessException.class,
                () -> controller.record("test-internal-token", "seven", Map.of("run_file", "a.jsonl")));

        assertEquals(StatusCode.FORBIDDEN, exception.getCode());
        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void recordRejectsNonPositiveTenantHeader() {
        assertThrows(BusinessException.class,
                () -> controller.record("test-internal-token", "0", Map.of("run_file", "a.jsonl")));
        assertThrows(BusinessException.class,
                () -> controller.record("test-internal-token", "-3", Map.of("run_file", "a.jsonl")));

        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void recordInsertsUnderTheTenantFromTheHeader() {
        long[] seenTenant = new long[1];
        when(evalHarnessRunMapper.insert(any(EvalHarnessRun.class))).thenAnswer(invocation -> {
            seenTenant[0] = TenantContext.requireTenantId();
            return 1;
        });

        R<Map<String, Object>> response =
                controller.record("test-internal-token", "7", Map.of("run_file", "a.jsonl", "record_count", 12));

        assertEquals(StatusCode.SUCCESS, response.getCode());
        assertEquals(7L, seenTenant[0]);
        ArgumentCaptor<EvalHarnessRun> captor = ArgumentCaptor.forClass(EvalHarnessRun.class);
        verify(evalHarnessRunMapper).insert(captor.capture());
        assertEquals("a.jsonl", captor.getValue().getRunFile());
        assertEquals(12, captor.getValue().getRecordCount());
    }

    @Test
    void importCorpusRejectsMissingTenantHeader() {
        BusinessException exception = assertThrows(
                BusinessException.class, () -> controller.importCorpus("test-internal-token", null, "1"));

        assertEquals(StatusCode.FORBIDDEN, exception.getCode());
        verify(evalCorpusImportService, never()).importCorpus(any());
    }

    @Test
    void importCorpusRejectsMissingUserHeader() {
        BusinessException exception = assertThrows(
                BusinessException.class, () -> controller.importCorpus("test-internal-token", "7", null));

        assertEquals(StatusCode.FORBIDDEN, exception.getCode());
        verify(evalCorpusImportService, never()).importCorpus(any());
    }

    @Test
    void importCorpusRunsUnderTheProvidedTenantAndUser() {
        TenantContext.setTenantId(99L);
        when(evalCorpusImportService.importCorpus(4L)).thenReturn(new EvalCorpusImportResultDTO());

        controller.importCorpus("test-internal-token", "9", "4");

        verify(evalCorpusImportService).importCorpus(4L);
        // runAs 必须把外层上下文（99）还原，而不是留下 9 给后续同线程工作
        assertEquals(99L, TenantContext.requireTenantId());
    }

    @Test
    void invalidTokenIsRejectedBeforeTenantValidation() {
        BusinessException exception = assertThrows(BusinessException.class,
                () -> controller.record("wrong-token", null, Map.of("run_file", "a.jsonl")));

        assertEquals(StatusCode.FORBIDDEN, exception.getCode());
        // 顺序契约：先认身份再认租户，令牌无效时不应泄露"缺租户"这条内部口径
        assertEquals("Forbidden: invalid or missing X-Internal-Token", exception.getMessage());
        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void invalidTokenRejectsWithARealHttp403NotADefault200() throws Exception {
        // 旧实现返回 R.fail(403,...)：HTTP 200 + 信封码，python-ai 的 _notify_java_record 只判
        // status_code >= 400，于是被拒的回调会记成 "callback ok"、摘要静默丢失
        mockMvc.perform(post("/internal/eval-harness/record")
                        .header("X-Internal-Token", "wrong-token")
                        .header("X-Tenant-Id", "7")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"run_file\":\"a.jsonl\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(StatusCode.FORBIDDEN));

        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void missingTenantHeaderRejectsWithARealHttp403() throws Exception {
        mockMvc.perform(post("/internal/eval-harness/record")
                        .header("X-Internal-Token", "test-internal-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"run_file\":\"a.jsonl\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(StatusCode.FORBIDDEN));

        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }

    @Test
    void acceptedCallbackStillReturnsHttp200WithOkEnvelope() throws Exception {
        when(evalHarnessRunMapper.insert(any(EvalHarnessRun.class))).thenReturn(1);

        mockMvc.perform(post("/internal/eval-harness/record")
                        .header("X-Internal-Token", "test-internal-token")
                        .header("X-Tenant-Id", "7")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"run_file\":\"a.jsonl\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(StatusCode.SUCCESS))
                .andExpect(jsonPath("$.data.recorded").value(true));
    }
}
