package com.hfusionhub.tenant;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.UnsupportedEncodingException;
import java.nio.charset.StandardCharsets;

/**
 * A request wrapper that buffers the full body once and re-serves it on every
 * {@link #getInputStream()}/{@link #getReader()} call.
 *
 * <p>Unlike Spring's {@link org.springframework.web.util.ContentCachingRequestWrapper}
 * (which only caches content that has already been consumed and therefore cannot
 * replay it downstream), this wrapper is safe to read once for signature
 * verification in a filter and read again later by the controller for
 * {@code @RequestBody} binding.</p>
 *
 * @author HFusionHub Team
 */
public class RepeatableReadRequestWrapper extends HttpServletRequestWrapper {

    private final byte[] body;

    public RepeatableReadRequestWrapper(HttpServletRequest request) throws IOException {
        super(request);
        this.body = request.getInputStream().readAllBytes();
    }

    /** Raw buffered body — safe to call any number of times. */
    public byte[] getBody() {
        return body;
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream buffer = new ByteArrayInputStream(body);
        return new ServletInputStream() {
            @Override
            public int read() {
                return buffer.read();
            }

            @Override
            public int read(byte[] b, int off, int len) {
                return buffer.read(b, off, len);
            }

            @Override
            public boolean isFinished() {
                return buffer.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener readListener) {
                throw new UnsupportedOperationException("Blocking read only");
            }
        };
    }

    @Override
    public BufferedReader getReader() throws UnsupportedEncodingException {
        String encoding = getCharacterEncoding();
        if (encoding == null) {
            encoding = StandardCharsets.UTF_8.name();
        }
        return new BufferedReader(new InputStreamReader(getInputStream(), encoding));
    }

    @Override
    public int getContentLength() {
        return body.length;
    }

    @Override
    public long getContentLengthLong() {
        return body.length;
    }
}
