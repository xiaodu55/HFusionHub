package com.hfusionhub.tenant;

import jakarta.servlet.ServletException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Unit tests for {@link CallbackSignatureFilter} — the HMAC gate that must be
 * satisfied before the tenant interceptor trusts X-Tenant-Id on callback URLs.
 */
class CallbackSignatureFilterTest {

    private static final String SECRET = "test-callback-secret";

    private CallbackSignatureFilter filter;

    @BeforeEach
    void setUp() {
        filter = new CallbackSignatureFilter();
        ReflectionTestUtils.setField(filter, "callbackSecret", SECRET);
    }

    // ── shouldNotFilter: only /vectorize/*/callback ──────────────────────

    @Test
    void onlyCallbackRouteIsFiltered() throws ServletException {
        assertFalse(filter.shouldNotFilter(request("/vectorize/42/callback")));
        assertTrue(filter.shouldNotFilter(request("/knowledge-base/list")));
        assertTrue(filter.shouldNotFilter(request("/health")));
    }

    // ── Signature verification ───────────────────────────────────────────

    @Test
    void correctSecretAndSignatureVerified() throws Exception {
        String body = "{\"documentId\":42,\"status\":\"COMPLETED\"}";
        MockHttpServletRequest req = request("/vectorize/42/callback");
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        req.addHeader("X-Callback-Secret", SECRET);
        req.addHeader("X-Callback-Signature", hmac(body));

        RepeatableReadRequestWrapper passed = invokeFilter(req);

        assertEquals(Boolean.TRUE, passed.getAttribute(CallbackSignatureFilter.VERIFIED_ATTR));
    }

    @Test
    void bodyIsReplayableAfterFilterConsumesIt() throws Exception {
        String body = "{\"documentId\":42,\"status\":\"COMPLETED\"}";
        MockHttpServletRequest req = request("/vectorize/42/callback");
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        req.addHeader("X-Callback-Secret", SECRET);
        req.addHeader("X-Callback-Signature", hmac(body));

        RepeatableReadRequestWrapper passed = invokeFilter(req);

        // The wrapper must re-serve the FULL body via both streams — this is the
        // regression guard for the P0 where ContentCachingRequestWrapper consumed
        // the stream and left @RequestBody with an empty payload.
        String viaReader = new String(passed.getReader().readLine().getBytes(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
        String viaStream = new String(passed.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        String viaStreamAgain = new String(passed.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        assertEquals(body, viaReader);
        assertEquals(body, viaStream);
        assertEquals(body, viaStreamAgain);
    }

    @Test
    void wrongSecretNotVerified() throws Exception {
        String body = "{\"documentId\":42}";
        MockHttpServletRequest req = request("/vectorize/42/callback");
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        req.addHeader("X-Callback-Secret", "wrong-secret");
        req.addHeader("X-Callback-Signature", hmac(body));

        RepeatableReadRequestWrapper passed = invokeFilter(req);

        assertEquals(Boolean.FALSE, passed.getAttribute(CallbackSignatureFilter.VERIFIED_ATTR));
    }

    @Test
    void missingSignatureNotVerified() throws Exception {
        String body = "{\"documentId\":42}";
        MockHttpServletRequest req = request("/vectorize/42/callback");
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        req.addHeader("X-Callback-Secret", SECRET);

        RepeatableReadRequestWrapper passed = invokeFilter(req);

        assertEquals(Boolean.FALSE, passed.getAttribute(CallbackSignatureFilter.VERIFIED_ATTR));
    }

    @Test
    void tamperedBodyNotVerified() throws Exception {
        String body = "{\"documentId\":42}";
        MockHttpServletRequest req = request("/vectorize/42/callback");
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        req.addHeader("X-Callback-Secret", SECRET);
        // Signature computed over a DIFFERENT body
        req.addHeader("X-Callback-Signature", hmac("{\"documentId\":99}"));

        RepeatableReadRequestWrapper passed = invokeFilter(req);

        assertEquals(Boolean.FALSE, passed.getAttribute(CallbackSignatureFilter.VERIFIED_ATTR));
    }

    @Test
    void missingSecretHeaderNotVerified() throws Exception {
        String body = "{\"documentId\":42}";
        MockHttpServletRequest req = request("/vectorize/42/callback");
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        req.addHeader("X-Callback-Signature", hmac(body));

        RepeatableReadRequestWrapper passed = invokeFilter(req);

        assertEquals(Boolean.FALSE, passed.getAttribute(CallbackSignatureFilter.VERIFIED_ATTR));
    }

    @Test
    void nonCallbackRouteSkipsVerificationEntirely() throws Exception {
        MockHttpServletRequest req = request("/knowledge-base/list");
        req.addHeader("X-Callback-Secret", "whatever");
        req.addHeader("X-Callback-Signature", "whatever");

        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(req, new MockHttpServletResponse(), chain);

        // Request passes through unwrapped — the filter did not run.
        assertEquals(req, chain.getRequest());
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private static MockHttpServletRequest request(String servletPath) {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api" + servletPath);
        req.setServletPath(servletPath);
        req.setRequestURI("/api" + servletPath);
        req.setContentType("application/json");
        return req;
    }

    /** Runs the filter and returns the wrapper it passed down the chain. */
    private RepeatableReadRequestWrapper invokeFilter(MockHttpServletRequest req) throws Exception {
        MockFilterChain chain = new MockFilterChain();
        filter.doFilter(req, new MockHttpServletResponse(), chain);
        Object request = chain.getRequest();
        if (!(request instanceof RepeatableReadRequestWrapper wrapper)) {
            throw new IllegalStateException("Filter did not wrap request: " + request);
        }
        return wrapper;
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
