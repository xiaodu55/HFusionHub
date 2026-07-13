package com.hfusionhub.common.lock;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.concurrent.TimeUnit;
import org.aspectj.lang.ProceedingJoinPoint;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

@ExtendWith(MockitoExtension.class)
class SchedulerLockAspectTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ValueOperations<String, String> valueOperations;

    @Mock
    private ProceedingJoinPoint joinPoint;

    private SchedulerLockAspect aspect;

    @BeforeEach
    void setUp() {
        aspect = new SchedulerLockAspect(redisTemplate);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    @Test
    void runsTaskWhenLockAcquiredAndReleases() throws Throwable {
        when(valueOperations.setIfAbsent(anyString(), anyString(), anyLong(), any(TimeUnit.class)))
                .thenReturn(true);
        when(joinPoint.proceed()).thenReturn(42);

        Object result = aspect.around(joinPoint, lock("test"));

        assertThat(result).isEqualTo(42);
        verify(joinPoint).proceed();
        verify(redisTemplate).execute(any(), anyList(), any());
    }

    @Test
    void skipsExecutionWhenLockHeldElsewhere() throws Throwable {
        when(valueOperations.setIfAbsent(anyString(), anyString(), anyLong(), any(TimeUnit.class)))
                .thenReturn(false);

        Object result = aspect.around(joinPoint, lock("test"));

        assertThat(result).isNull();
        verify(joinPoint, never()).proceed();
    }

    @Test
    void failsClosedByDefaultWhenRedisUnavailable() throws Throwable {
        when(valueOperations.setIfAbsent(anyString(), anyString(), anyLong(), any(TimeUnit.class)))
                .thenThrow(new RuntimeException("connection refused"));

        Object result = aspect.around(joinPoint, lock("test"));

        // 默认 fail-closed：Redis 故障时跳过本次调度，等待下一周期补偿
        assertThat(result).isNull();
        verify(joinPoint, never()).proceed();
    }

    @Test
    void failsOpenWhenExplicitlyConfigured() throws Throwable {
        org.springframework.test.util.ReflectionTestUtils.setField(aspect, "failOpen", true);
        when(valueOperations.setIfAbsent(anyString(), anyString(), anyLong(), any(TimeUnit.class)))
                .thenThrow(new RuntimeException("connection refused"));
        when(joinPoint.proceed()).thenReturn("ran");

        Object result = aspect.around(joinPoint, lock("test"));

        // 显式 fail-open=true 时保留历史行为：无锁执行
        assertThat(result).isEqualTo("ran");
        verify(joinPoint).proceed();
    }

    @Test
    void releasesLockEvenWhenTaskThrows() throws Throwable {
        when(valueOperations.setIfAbsent(anyString(), anyString(), anyLong(), any(TimeUnit.class)))
                .thenReturn(true);
        when(joinPoint.proceed()).thenThrow(new IllegalStateException("boom"));

        assertThatThrownBy(() -> aspect.around(joinPoint, lock("test")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("boom");
        verify(redisTemplate).execute(any(), anyList(), any());
    }

    private SchedulerLock lock(String name) {
        return new SchedulerLock() {
            @Override
            public Class<? extends java.lang.annotation.Annotation> annotationType() {
                return SchedulerLock.class;
            }

            @Override
            public String value() {
                return name;
            }

            @Override
            public long ttlSeconds() {
                return 300;
            }
        };
    }
}
