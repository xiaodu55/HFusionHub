package com.hfusionhub.service.impl;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConversationServiceImplTest {

    @Test
    void blankRequestIdsAreNotPersisted() {
        assertNull(ConversationServiceImpl.normalizeRequestId(null));
        assertNull(ConversationServiceImpl.normalizeRequestId("   "));
        assertNull(ConversationServiceImpl.assistantRequestId(null));
    }

    @Test
    void assistantRequestIdIsDistinctForShortClientIds() {
        String requestId = ConversationServiceImpl.normalizeRequestId("req-123");

        assertEquals("req-123", requestId);
        assertEquals("req-123:assistant", ConversationServiceImpl.assistantRequestId(requestId));
    }

    @Test
    void longRequestIdsStayInsideDatabaseColumnLimit() {
        String requestId = ConversationServiceImpl.normalizeRequestId("x".repeat(120));
        String assistantRequestId = ConversationServiceImpl.assistantRequestId(requestId);

        assertTrue(requestId.length() <= 64);
        assertTrue(assistantRequestId.length() <= 64);
        assertTrue(requestId.startsWith("r:"));
        assertTrue(assistantRequestId.startsWith("a:"));
        assertNotEquals(requestId, assistantRequestId);
    }
}
