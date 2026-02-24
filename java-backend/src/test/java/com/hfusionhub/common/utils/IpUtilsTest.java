package com.hfusionhub.common.utils;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.junit.jupiter.api.Assertions.assertEquals;

class IpUtilsTest {

    @Test
    void usesRemoteAddressByDefault() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr("10.0.0.10");
        request.addHeader("X-Forwarded-For", "203.0.113.5, 10.0.0.1");

        assertEquals("10.0.0.10", IpUtils.getClientIp(request));
    }

    @Test
    void usesForwardedHeaderOnlyWhenTrusted() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr("10.0.0.10");
        request.addHeader("X-Forwarded-For", "203.0.113.5, 10.0.0.1");

        assertEquals("203.0.113.5", IpUtils.getClientIp(request, true));
    }
}
