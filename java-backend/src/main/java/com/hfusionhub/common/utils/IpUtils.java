package com.hfusionhub.common.utils;

import jakarta.servlet.http.HttpServletRequest;

/**
 * IP address utility methods.
 *
 * @author HFusionHub Team
 */
public final class IpUtils {

    private static final String[] IP_HEADER_CANDIDATES = {
            "X-Forwarded-For",
            "Proxy-Client-IP",
            "WL-Proxy-Client-IP",
            "HTTP_X_FORWARDED_FOR",
            "HTTP_CLIENT_IP"
    };

    private IpUtils() {
        // utility class
    }

    /**
     * Extract the remote peer IP from a servlet request.
     */
    public static String getClientIp(HttpServletRequest request) {
        return getClientIp(request, false);
    }

    /**
     * Extract the client IP from a servlet request.
     *
     * <p>Proxy headers are user-controlled unless the application is deployed
     * behind a trusted reverse proxy that sanitizes them.
     */
    public static String getClientIp(HttpServletRequest request, boolean trustProxyHeaders) {
        if (!trustProxyHeaders) {
            return request.getRemoteAddr();
        }

        for (String header : IP_HEADER_CANDIDATES) {
            String ip = request.getHeader(header);
            if (ip != null && !ip.isBlank() && !"unknown".equalsIgnoreCase(ip)) {
                // X-Forwarded-For may contain a comma-separated chain; use the
                // left-most (original client) address.
                int comma = ip.indexOf(',');
                return comma > 0 ? ip.substring(0, comma).trim() : ip.trim();
            }
        }
        return request.getRemoteAddr();
    }
}
