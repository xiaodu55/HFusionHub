package com.hfusionhub.service.impl;

import com.hfusionhub.dto.AgentStatusEventDTO;
import com.hfusionhub.entity.AgentStatusEvent;
import com.hfusionhub.mapper.AgentStatusEventMapper;
import com.hfusionhub.service.AgentStatusEventService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Agent 状态事件服务实现
 *
 * @author HFusionHub Team
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentStatusEventServiceImpl implements AgentStatusEventService {

    private final AgentStatusEventMapper statusEventMapper;

    @Value("${agent.status-event.retention-days:7}")
    private int retentionDays;

    @Override
    @Transactional(propagation = Propagation.REQUIRED)
    public void record(Long taskId, Long runId, String eventType, String status,
                       Map<String, Object> payload) {
        AgentStatusEvent event = new AgentStatusEvent();
        event.setTaskId(taskId);
        event.setRunId(runId);
        event.setEventType(eventType);
        event.setStatus(status);
        event.setPayload(payload);
        statusEventMapper.insert(event);
    }

    @Override
    public List<AgentStatusEventDTO> listEvents(Long taskId, Long sinceId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 200));
        List<AgentStatusEvent> events = statusEventMapper.selectAfter(taskId, sinceId, safeLimit);
        return events.stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    @Override
    public AgentStatusEventDTO getLatestEvent(Long taskId) {
        AgentStatusEvent event = statusEventMapper.selectLatestByTaskId(taskId);
        return event != null ? toDTO(event) : null;
    }

    @Override
    public int cleanupEvents() {
        LocalDateTime cutoff = LocalDateTime.now().minusDays(retentionDays);
        int deleted = statusEventMapper.deleteOlderThan(cutoff);
        if (deleted > 0) {
            log.info("Cleaned up {} agent status events older than {} days", deleted, retentionDays);
        }
        return deleted;
    }

    private AgentStatusEventDTO toDTO(AgentStatusEvent event) {
        return AgentStatusEventDTO.builder()
                .id(event.getId())
                .taskId(event.getTaskId())
                .runId(event.getRunId())
                .eventType(event.getEventType())
                .status(event.getStatus())
                .payload(event.getPayload())
                .createdAt(event.getCreatedAt())
                .build();
    }
}
