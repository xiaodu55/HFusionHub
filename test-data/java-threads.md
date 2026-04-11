# Java 并发编程指南

## 平台线程（Platform Threads）

Java 平台线程是操作系统线程的 1:1 包装。每个 `java.lang.Thread` 实例对应一个 OS 线程。

### 特点
- 创建成本高（约 1MB 栈空间）
- 上下文切换开销大
- 适合 CPU 密集型任务
- 单机最多支持数千到一万个线程

### 示例代码
```java
Thread thread = new Thread(() -> {
    System.out.println("Platform thread running");
});
thread.start();
```

## 虚拟线程（Virtual Threads）

虚拟线程是 Java 21 正式发布的轻量级并发模型，由 JVM 而非操作系统管理。

### 核心优势
- 创建成本极低（几 KB）
- 支持数百万并发实例
- 阻塞操作自动释放底层平台线程
- 与现有代码完全兼容

### 基础用法
```java
Thread vThread = Thread.startVirtualThread(() -> {
    System.out.println("Hello from virtual thread");
});

// 使用 ExecutorService
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> fetchData());
    executor.submit(() -> processData());
}
```

## 结构化并发（Structured Concurrency）

Java 21 引入 `StructuredTaskScope`，将多个并发任务组织为一个逻辑单元。

```java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    Future<String> user = scope.fork(() -> fetchUser());
    Future<String> order = scope.fork(() -> fetchOrder());
    scope.join().throwIfFailed();
    return user.resultNow() + " - " + order.resultNow();
}
```

## 性能对比

| 指标 | 平台线程 | 虚拟线程 |
|------|---------|---------|
| 创建时间 | ~1ms | ~1μs |
| 内存占用 | ~1MB | ~2KB |
| 最大数量 | ~10,000 | ~1,000,000 |
| 上下文切换 | 内核态 | 用户态 |
