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

    @Test
    void emptyStringsAreTreatedAsBlank() {
        assertNull(ConversationServiceImpl.normalizeRequestId(""));
        assertNull(ConversationServiceImpl.normalizeRequestId("\t  \n"));
    }

    @Test
    void exactlySixtyFourCharRequestIdStaysUnchanged() {
        String exactly64 = "r".repeat(64);
        String result = ConversationServiceImpl.normalizeRequestId(exactly64);
        assertEquals(exactly64, result);
    }

    @Test
    void assistantRequestIdAppendsSuffixForShortIds() {
        String result = ConversationServiceImpl.assistantRequestId("abc");
        assertEquals("abc:assistant", result);
    }

    @Test
    void assistantRequestIdHashesLongClientIds() {
        String longId = ConversationServiceImpl.normalizeRequestId("x".repeat(200));
        String assistant = ConversationServiceImpl.assistantRequestId(longId);
        assertTrue(assistant.length() <= 64);
        assertTrue(assistant.startsWith("a:"));
    }

    @Test
    void nullInputsReturnNullForBothMethods() {
        assertNull(ConversationServiceImpl.normalizeRequestId(null));
        assertNull(ConversationServiceImpl.assistantRequestId(null));
    }

    @Test
    void differentInputsProduceDifferentHashes() {
        String a = ConversationServiceImpl.normalizeRequestId("a".repeat(200));
        String b = ConversationServiceImpl.normalizeRequestId("b".repeat(200));
        assertNotEquals(a, b);
    }
}
