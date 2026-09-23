package com.hfusionhub.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
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
import org.springframework.test.util.ReflectionTestUtils;

/**
 * Unit tests for {@link EvalHarnessInternalController}'s tenant handling.
 *
 * <p>{@code /internal/eval-harness/**} is excluded from both the Sa-Token login check
 * and {@code TenantContextInterceptor}, so the inbound {@code X-Tenant-Id} header is the
 * <b>only</b> thing that decides which tenant a run row or an imported corpus belongs to.
 * A missing header must therefore be rejected, never defaulted.</p>
 */
class EvalHarnessInternalControllerTest {

    private EvalHarnessRunMapper evalHarnessRunMapper;
    private EvalCorpusImportService evalCorpusImportService;
    private EvalHarnessInternalController controller;

    @BeforeEach
    void setUp() {
        evalHarnessRunMapper = mock(EvalHarnessRunMapper.class);
        evalCorpusImportService = mock(EvalCorpusImportService.class);
        controller = new EvalHarnessInternalController(evalHarnessRunMapper, evalCorpusImportService);
        ReflectionTestUtils.setField(controller, "expectedToken", "test-internal-token");
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
        R<Map<String, Object>> response = controller.record("wrong-token", null, Map.of("run_file", "a.jsonl"));

        assertEquals(StatusCode.FORBIDDEN, response.getCode());
        verify(evalHarnessRunMapper, never()).insert(any(EvalHarnessRun.class));
    }
}
