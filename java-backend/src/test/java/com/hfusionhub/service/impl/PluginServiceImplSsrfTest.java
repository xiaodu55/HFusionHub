package com.hfusionhub.service.impl;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 声明式插件端点 SSRF 校验（第十五轮 R15-19）。
 *
 * 直接测字面量判断路径（不依赖 DNS）；域名解析路径在联网环境由
 * getAllByName 覆盖，离线环境 UnknownHostException 一律拒绝（fail-closed）。
 */
class PluginServiceImplSsrfTest {

    private boolean isPrivateHost(String host) throws Exception {
        Method m = PluginServiceImpl.class.getDeclaredMethod("isPrivateHost", String.class);
        m.setAccessible(true);
        PluginServiceImpl service = new PluginServiceImpl(null, null, null, null);
        return (boolean) m.invoke(service, host);
    }

    @Test
    void ipv4LiteralPrivateRangesAreRejected() throws Exception {
        assertTrue(isPrivateHost("10.0.0.5"), "10/8");
        assertTrue(isPrivateHost("172.16.0.1"), "172.16/12");
        assertTrue(isPrivateHost("172.31.255.255"), "172.16/12 上界");
        assertTrue(isPrivateHost("192.168.1.1"), "192.168/16");
        assertTrue(isPrivateHost("127.0.0.1"), "loopback");
        assertTrue(isPrivateHost("169.254.169.254"), "云元数据地址");
        assertTrue(isPrivateHost("100.64.1.1"), "CGNAT");
        assertTrue(isPrivateHost("0.0.0.0"), "unspecified");
        assertTrue(isPrivateHost("224.0.0.1"), "multicast");
        assertTrue(isPrivateHost("255.255.255.255"), "reserved");
    }

    @Test
    void ipv4LiteralPublicAddressAccepted() throws Exception {
        // 1.x-9.x、11-126 的公网段不拦（DNS 解析路径会再校验实际地址）
        assertFalse(isPrivateHost("93.184.216.34"));
        assertFalse(isPrivateHost("8.8.8.8"));
        assertFalse(isPrivateHost("1.1.1.1"));
        assertFalse(isPrivateHost("172.32.0.1"), "172.16/12 之外");
        assertFalse(isPrivateHost("100.63.0.1"), "CGNAT 之外");
        assertFalse(isPrivateHost("198.51.100.7"), "TEST-NET-2 可解析场景放行");
    }

    @Test
    void ipv6LiteralRules() throws Exception {
        assertTrue(isPrivateHost("::1"), "IPv6 loopback");
        assertTrue(isPrivateHost("::"), "unspecified");
        assertTrue(isPrivateHost("fc00::1"), "ULA");
        assertTrue(isPrivateHost("fd12:3456::1"), "ULA fd");
        assertTrue(isPrivateHost("fe80::1"), "link-local");
        assertTrue(isPrivateHost("::ffff:192.168.1.1"), "IPv4-mapped 私网");
        assertTrue(isPrivateHost("::ffff:10.0.0.1"), "IPv4-mapped 私网");
    }

    @Test
    void localhostVariantsRejectedByLiteralOrResolution() throws Exception {
        // localhost/.local 由 validateDeclarativeEndpoint 前置拦截；
        // 这里验证 DNS 解析层兜底（localhost 解析必回 loopback）
        assertTrue(isPrivateHost("localhost"));
    }

    @Test
    void malformedIpv4Rejected() throws Exception {
        assertTrue(isPrivateHost("999.1.1.1"), "越界段按保守拒绝");
    }
}
