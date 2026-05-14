package com.hfusionhub.dto;

import static org.assertj.core.api.Assertions.assertThat;

import com.hfusionhub.entity.MemoryEntry;
import com.hfusionhub.entity.SystemNotice;
import com.hfusionhub.entity.WebhookSubscription;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * 验证 P1-1.4 新增的写接口校验约束在 @Valid 下能正确拦截非法输入。
 * （约束仅在控制器层 @Valid 时生效；部分更新的 PUT 端点不加 @Valid，不受影响。）
 */
class WriteEndpointValidationTest {

    private static final Validator VALIDATOR = Validation.buildDefaultValidatorFactory().getValidator();

    private static Set<String> violations(Object bean) {
        return VALIDATOR.validate(bean).stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void approvalDecisionRequiresApprovalIdAndValidDecision() {
        ApprovalDecisionDTO dto = new ApprovalDecisionDTO();

        Set<String> paths = violations(dto);

        assertThat(paths).contains("approvalId", "decision");
    }

    @Test
    void approvalDecisionRejectsInvalidDecisionValue() {
        ApprovalDecisionDTO dto = new ApprovalDecisionDTO();
        dto.setApprovalId("a-1");
        dto.setDecision("maybe");

        assertThat(violations(dto)).contains("decision");
    }

    @Test
    void tenantMemberAddRequiresUserId() {
        TenantMemberAddDTO dto = new TenantMemberAddDTO();
        dto.setRole("member");

        assertThat(violations(dto)).contains("userId");
    }

    @Test
    void tenantMemberAddAcceptsValidPayload() {
        TenantMemberAddDTO dto = new TenantMemberAddDTO();
        dto.setUserId(7L);
        dto.setRole("member");

        assertThat(violations(dto)).isEmpty();
    }

    @Test
    void memoryEntryCreateRequiresTypeAndContent() {
        MemoryEntry entry = new MemoryEntry();

        assertThat(violations(entry)).contains("type", "content");
    }

    @Test
    void systemNoticeRequiresTitleAndContent() {
        SystemNotice notice = new SystemNotice();

        assertThat(violations(notice)).contains("title", "content");
    }

    @Test
    void webhookCreateRequiresNameUrlAndEvents() {
        WebhookSubscription sub = new WebhookSubscription();

        Set<String> paths = violations(sub);

        assertThat(paths).contains("name", "url", "events");
    }

    @Test
    void webhookCreateAcceptsValidPayload() {
        WebhookSubscription sub = new WebhookSubscription();
        sub.setName("新消息通知");
        sub.setUrl("https://example.com/hook");
        sub.setEvents(List.of("message.created"));

        assertThat(violations(sub)).isEmpty();
    }
}
