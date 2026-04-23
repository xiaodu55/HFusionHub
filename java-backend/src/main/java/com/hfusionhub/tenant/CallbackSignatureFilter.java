package com.hfusionhub.tenant;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Verifies the Python→Java callback signature (X-Callback-Secret + HMAC over
 * the raw body) BEFORE the tenant interceptor trusts {@code X-Tenant-Id}.
 *
 * <p>This is the hardened enforcement for the tenant context: the interceptor
 * only honours {@code X-Tenant-Id} on callback URLs whose signature has been
 * verified here.  Without this filter, any unauthenticated caller could forge
 * {@code X-Tenant-Id} on a callback-shaped URL and poison the tenant context.</p>
 *
 * <p>The request body is buffered in a {@link RepeatableReadRequestWrapper} so it
 * can be read once for verification here and re-read by the controller (which
 * performs its own defence-in-depth check).  This filter runs at servlet
 * level, i.e. before the Spring MVC interceptor chain.</p>
 *
 * <p>Only the callback route /vectorize/{id}/callback is signature-checked;
 * nothing else is affected.</p>
 */
@Slf4j
@Order(0)
@Component
public class CallbackSignatureFilter extends OncePerRequestFilter {

    static final String CALLBACK_PATH_PREFIX = "/vectorize/";
    static final String CALLBACK_PATH_SUFFIX = "/callback";

    /** Set on the request by this filter after signature verification. */
    static final String VERIFIED_ATTR = "hfusionhub.callback.verified";

    @Value("${python-ai.callback-secret:}")
    private String callbackSecret;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) throws ServletException {
        String path = request.getServletPath();
        if (path == null) {
            path = request.getRequestURI();
        }
        if (path == null) {
            return true;
        }
        return !(path.startsWith(CALLBACK_PATH_PREFIX) && path.endsWith(CALLBACK_PATH_SUFFIX));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        RepeatableReadRequestWrapper wrapping = new RepeatableReadRequestWrapper(request);
        try {
            // Buffer the body once; it is re-served to the controller
            // (defence-in-depth) via the replayable wrapper.
            byte[] body = wrapping.getBody();

            String secret = request.getHeader("X-Callback-Secret");
            String signature = request.getHeader("X-Callback-Signature");
            boolean verified;
            if (callbackSecret == null
                    || callbackSecret.isBlank()
                    || secret == null
                    || !MessageDigest.isEqual(
                            callbackSecret.getBytes(StandardCharsets.UTF_8), secret.getBytes(StandardCharsets.UTF_8))) {
                verified = false;
                log.warn("Callback secret mismatch on {} {}", request.getMethod(), request.getRequestURI());
            } else {
                verified = verifyHmacSignature(body, callbackSecret, signature);
                if (!verified) {
                    log.warn("Callback HMAC mismatch on {} {}", request.getMethod(), request.getRequestURI());
                }
            }
            wrapping.setAttribute(VERIFIED_ATTR, verified);
        } catch (Exception e) {
            log.warn("Callback signature verification error: {}", e.getMessage());
            wrapping.setAttribute(VERIFIED_ATTR, false);
        }
        filterChain.doFilter(wrapping, response);
    }

    private boolean verifyHmacSignature(byte[] payload, String secret, String signature) {
        if (signature == null || signature.isBlank()) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            SecretKeySpec keySpec = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
            mac.init(keySpec);
            byte[] computed = mac.doFinal(payload);
            String expected = Base64.getEncoder().encodeToString(computed);
            return MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.UTF_8), signature.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            log.error("HMAC signature verification failed", e);
            return false;
        }
    }
}
