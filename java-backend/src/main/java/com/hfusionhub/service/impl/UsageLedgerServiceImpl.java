package com.hfusionhub.service.impl;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.config.QuotaProperties;
import com.hfusionhub.entity.Tenant;
import com.hfusionhub.entity.TenantQuota;
import com.hfusionhub.entity.UsageCounter;
import com.hfusionhub.entity.UsageEvent;
import com.hfusionhub.entity.UsageReservation;
import com.hfusionhub.mapper.TenantMapper;
import com.hfusionhub.mapper.TenantQuotaMapper;
import com.hfusionhub.mapper.UsageCounterMapper;
import com.hfusionhub.mapper.UsageEventMapper;
import com.hfusionhub.mapper.UsageReservationMapper;
import com.hfusionhub.quota.UsageMeter;
import com.hfusionhub.service.UsageLedgerService;
import com.hfusionhub.tenant.TenantContext;
import java.time.LocalDate;
import java.time.ZoneOffset;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 用量账本服务实现
 *
 * <p><b>预占</b>（单事务）：
 * 1. 先插入 usage_reservation（唯一键 (tenant_id, meter, request_id) 是幂等门）；
 *    并发重复由唯一键拦截，插入失败的线程直接幂等返回，绝不动计数器；
 * 2. 再条件 UPDATE usage_counter 原子预占，超限时 affected rows = 0 → 抛 QUOTA_EXCEEDED，
 *    整个事务（含刚插入的预占行）回滚；
 * 3. 写 usage_event RESERVE 账本。
 *
 * <p><b>终态转换</b>：settle/release 一律以 usage_reservation.state 为权威，
 * 经 {@code state='RESERVED'} 条件 UPDATE 独占转换到 COMMITTED / RELEASED 之一，
 * 二次调用按新状态幂等返回或拒绝，reserved 永不为负。结算量封顶为预占上界，
 * 且结算/退回都作用于预占所在 window_key（跨 UTC 零点不串天）。</p>
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UsageLedgerServiceImpl implements UsageLedgerService {

    public static final String OP_RESERVE = "RESERVE";
    public static final String OP_COMMIT = "COMMIT";
    public static final String OP_RELEASE = "RELEASE";

    private final UsageEventMapper usageEventMapper;
    private final UsageCounterMapper usageCounterMapper;
    private final UsageReservationMapper usageReservationMapper;
    private final TenantQuotaMapper tenantQuotaMapper;
    private final TenantMapper tenantMapper;
    private final QuotaProperties quotaProperties;

    @Override
    @Transactional
    public void reserve(UsageMeter meter, String requestId, long amount, String refType, String refId) {
        if (amount <= 0) {
            return;
        }
        Long tenantId = TenantContext.requireTenantId();
        String windowKey = windowKey();

        // 幂等快速路径：预占已存在则直接返回（不动计数器）
        if (usageReservationMapper.selectByKey(tenantId, meter.getCode(), requestId) != null) {
            log.debug("Idempotent reserve skipped: tenant={} requestId={}", tenantId, requestId);
            return;
        }

        // 幂等权威门：先插预占行，唯一键拦截并发重复
        UsageReservation reservation = new UsageReservation();
        reservation.setTenantId(tenantId);
        reservation.setMeter(meter.getCode());
        reservation.setRequestId(requestId);
        reservation.setWindowKey(windowKey);
        reservation.setReservedAmount(amount);
        reservation.setActualAmount(0L);
        reservation.setState(UsageReservation.STATE_RESERVED);
        reservation.setRefType(refType);
        reservation.setRefId(refId);
        try {
            usageReservationMapper.insert(reservation);
        } catch (DuplicateKeyException e) {
            log.debug("Concurrent duplicate reserve ignored: tenant={} requestId={}", tenantId, requestId);
            return;
        }

        // 原子预占：committed + reserved + amount <= limit 才成功
        long limit = effectiveDailyLimit(tenantId, meter);
        ensureCounterRow(tenantId, meter, windowKey);
        int updated = usageCounterMapper.tryReserve(tenantId, meter.getCode(), windowKey, amount, limit);
        if (updated == 0) {
            throw new BusinessException(StatusCode.QUOTA_EXCEEDED, "今日用量已达上限（" + limit + "），请明天再试或联系管理员提升配额");
        }
        insertEvent(tenantId, meter.getCode(), OP_RESERVE, requestId, windowKey, amount, refType, refId);
        log.info(
                "Usage reserved: tenant={} meter={} requestId={} amount={} limit={}",
                tenantId,
                meter.getCode(),
                requestId,
                amount,
                limit);
    }

    @Override
    @Transactional
    public void settle(UsageMeter meter, String requestId, long actualAmount, String refType, String refId) {
        Long tenantId = TenantContext.requireTenantId();
        UsageReservation reservation = usageReservationMapper.selectByKey(tenantId, meter.getCode(), requestId);
        if (reservation == null) {
            log.debug("Settle skipped: no reservation tenant={} requestId={}", tenantId, requestId);
            return;
        }
        if (UsageReservation.STATE_COMMITTED.equals(reservation.getState())) {
            log.debug("Idempotent commit skipped: tenant={} requestId={}", tenantId, requestId);
            return;
        }
        if (UsageReservation.STATE_RELEASED.equals(reservation.getState())) {
            log.warn(
                    "Invalid settle after release: tenant={} requestId={} — reservation already released",
                    tenantId,
                    requestId);
            return;
        }

        // 独占转换 RESERVED → COMMITTED；0 行说明并发线程已先行转换
        int transitioned =
                usageReservationMapper.tryCommit(tenantId, meter.getCode(), requestId, Math.max(actualAmount, 0));
        if (transitioned == 0) {
            UsageReservation current = usageReservationMapper.selectByKey(tenantId, meter.getCode(), requestId);
            if (current != null && UsageReservation.STATE_COMMITTED.equals(current.getState())) {
                return;
            }
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "并发预占终态转换失败，请重试 requestId=" + requestId);
        }

        // 结算量封顶为预占上界；作用于预占所在窗口
        long reservedAmount = reservation.getReservedAmount();
        long charge = Math.min(Math.max(actualAmount, 0), reservedAmount);
        ensureCounterRow(tenantId, meter, reservation.getWindowKey());
        usageCounterMapper.settle(tenantId, meter.getCode(), reservation.getWindowKey(), charge, reservedAmount);
        insertEvent(
                tenantId, meter.getCode(), OP_COMMIT, requestId, reservation.getWindowKey(), charge, refType, refId);
        log.info(
                "Usage settled: tenant={} meter={} requestId={} actual={} reserved={}",
                tenantId,
                meter.getCode(),
                requestId,
                charge,
                reservedAmount);
    }

    @Override
    @Transactional
    public void release(UsageMeter meter, String requestId) {
        Long tenantId = TenantContext.requireTenantId();
        UsageReservation reservation = usageReservationMapper.selectByKey(tenantId, meter.getCode(), requestId);
        if (reservation == null) {
            log.debug("Release skipped: no reservation tenant={} requestId={}", tenantId, requestId);
            return;
        }
        if (UsageReservation.STATE_RELEASED.equals(reservation.getState())) {
            log.debug("Idempotent release skipped: tenant={} requestId={}", tenantId, requestId);
            return;
        }
        if (UsageReservation.STATE_COMMITTED.equals(reservation.getState())) {
            log.warn(
                    "Invalid release after commit: tenant={} requestId={} — reservation already committed",
                    tenantId,
                    requestId);
            return;
        }

        // 独占转换 RESERVED → RELEASED
        int transitioned = usageReservationMapper.tryRelease(tenantId, meter.getCode(), requestId);
        if (transitioned == 0) {
            UsageReservation current = usageReservationMapper.selectByKey(tenantId, meter.getCode(), requestId);
            if (current != null && UsageReservation.STATE_RELEASED.equals(current.getState())) {
                return;
            }
            throw new BusinessException(StatusCode.INTERNAL_ERROR, "并发预占终态转换失败，请重试 requestId=" + requestId);
        }

        long reservedAmount = reservation.getReservedAmount();
        ensureCounterRow(tenantId, meter, reservation.getWindowKey());
        usageCounterMapper.release(tenantId, meter.getCode(), reservation.getWindowKey(), reservedAmount);
        insertEvent(
                tenantId,
                meter.getCode(),
                OP_RELEASE,
                requestId,
                reservation.getWindowKey(),
                reservedAmount,
                reservation.getRefType(),
                reservation.getRefId());
        log.info(
                "Usage released: tenant={} meter={} requestId={} amount={}",
                tenantId,
                meter.getCode(),
                requestId,
                reservedAmount);
    }

    @Override
    public long currentCommitted(UsageMeter meter) {
        UsageCounter counter = currentCounter(meter);
        return counter != null ? counter.getCommitted() : 0L;
    }

    @Override
    public long currentReserved(UsageMeter meter) {
        UsageCounter counter = currentCounter(meter);
        return counter != null ? counter.getReserved() : 0L;
    }

    @Override
    public long currentUsage(UsageMeter meter) {
        return currentCommitted(meter) + currentReserved(meter);
    }

    @Override
    public long effectiveDailyLimit(UsageMeter meter) {
        return effectiveDailyLimit(TenantContext.requireTenantId(), meter);
    }

    @Override
    public long effectiveDailyLimit(Long tenantId, UsageMeter meter) {
        TenantQuota quota = tenantQuotaMapper.selectByTenantAndMeter(tenantId, meter.getCode());
        if (quota != null && quota.getDailyLimit() != null) {
            return Math.max(quota.getDailyLimit(), 0);
        }
        Tenant tenant = tenantMapper.selectById(tenantId);
        String plan = tenant != null && tenant.getPlanTier() != null ? tenant.getPlanTier() : "free";
        return quotaProperties.defaultLimit(plan, meter.getCode());
    }

    private UsageCounter currentCounter(UsageMeter meter) {
        return usageCounterMapper.selectByKey(TenantContext.requireTenantId(), meter.getCode(), windowKey());
    }

    private void ensureCounterRow(Long tenantId, UsageMeter meter, String windowKey) {
        if (usageCounterMapper.selectByKey(tenantId, meter.getCode(), windowKey) != null) {
            return;
        }
        UsageCounter counter = new UsageCounter();
        counter.setTenantId(tenantId);
        counter.setMeter(meter.getCode());
        counter.setWindowKey(windowKey);
        counter.setReserved(0L);
        counter.setCommitted(0L);
        try {
            usageCounterMapper.insert(counter);
        } catch (DuplicateKeyException e) {
            // 并发插入，行已存在，忽略
        }
    }

    private void insertEvent(
            Long tenantId,
            String meterCode,
            String operation,
            String requestId,
            String windowKey,
            long amount,
            String refType,
            String refId) {
        UsageEvent event = new UsageEvent();
        event.setTenantId(tenantId);
        event.setMeter(meterCode);
        event.setOperation(operation);
        event.setRequestId(requestId);
        event.setWindowKey(windowKey);
        event.setAmount(amount);
        event.setRefType(refType);
        event.setRefId(refId);
        try {
            usageEventMapper.insert(event);
        } catch (DuplicateKeyException e) {
            // 唯一键 (tenant_id, meter, request_id, operation) 冲突 = 并发重复操作，整体回滚本事务
            throw e;
        }
    }

    private String windowKey() {
        return LocalDate.now(ZoneOffset.UTC).toString();
    }
}
