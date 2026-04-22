package com.hfusionhub.config;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

/**
 * 虚拟线程执行器工厂。
 *
 * <p>项目编译目标为 JDK 17（CI 亦用 17），但生产运行时可能是 JDK 21+。
 * 这里用反射创建"每任务一个虚拟线程"的执行器：JDK 21+ 生效（毫秒级创建、内存极小，
 * 适合 SSE 长连接、Webhook 等线程数量多但单线程等待多的场景）；
 * JDK 17 下返回 {@code null}，调用方回退到平台线程池。</p>
 */
public final class ExecutorSupport {

    private ExecutorSupport() {
    }

    /**
     * 创建带命名前缀的虚拟线程执行器（JDK 21+），JDK 17 返回 {@code null}。
     */
    public static ExecutorService newVirtualThreadPerTaskExecutor(String threadNamePrefix) {
        try {
            Class<?> threadClass = Thread.class;
            // Thread.ofVirtual() -> Thread.Builder.OfVirtual
            Object builder = threadClass.getMethod("ofVirtual").invoke(null);
            // .name(prefix + "-", 0L) -> 带序号前缀的命名生成器
            builder = builder.getClass().getMethod("name", String.class, long.class)
                    .invoke(builder, threadNamePrefix + "-", 0L);
            // .factory() -> ThreadFactory
            ThreadFactory factory = (ThreadFactory) builder.getClass().getMethod("factory").invoke(builder);
            // Executors.newThreadPerTaskExecutor(factory)
            return (ExecutorService) Executors.class
                    .getMethod("newThreadPerTaskExecutor", ThreadFactory.class)
                    .invoke(null, factory);
        } catch (ReflectiveOperationException e) {
            return null;
        } catch (RuntimeException e) {
            return null;
        }
    }
}
