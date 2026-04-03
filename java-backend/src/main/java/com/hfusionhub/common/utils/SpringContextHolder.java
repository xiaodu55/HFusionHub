package com.hfusionhub.common.utils;

import org.springframework.beans.BeansException;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Component;

/**
 * Spring ApplicationContext holder for static bean access.
 * Used by classes like JwtUtils that are instantiated outside Spring's DI container
 * (e.g., Sa-Token's StpInterface) but need access to Spring-managed beans.
 *
 * @author HFusionHub Team
 */
@Component
public class SpringContextHolder implements ApplicationContextAware {

    private static ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) throws BeansException {
        SpringContextHolder.context = applicationContext;
    }

    public static <T> T getBean(Class<T> beanClass) {
        if (context == null) {
            throw new IllegalStateException("ApplicationContext not initialized");
        }
        return context.getBean(beanClass);
    }

    public static <T> T getBean(String name, Class<T> beanClass) {
        if (context == null) {
            throw new IllegalStateException("ApplicationContext not initialized");
        }
        return context.getBean(name, beanClass);
    }
}
