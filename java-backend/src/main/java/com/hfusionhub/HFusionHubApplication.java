package com.hfusionhub;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * HFusionHub 主启动类
 * Java + Python 混合架构的 AI Agent 智能助手平台
 *
 * @author HFusionHub Team
 */
@SpringBootApplication
public class HFusionHubApplication {

    public static void main(String[] args) {
        SpringApplication.run(HFusionHubApplication.class, args);
        System.out.println("=====================================");
        System.out.println("  HFusionHub 后端服务启动成功！");
        System.out.println("  端口: 8080");
        System.out.println("  文档: http://localhost:8080/doc.html");
        System.out.println("=====================================");
    }
}
