package com.hfusionhub.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.SystemNotice;
import com.hfusionhub.mapper.SystemNoticeMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Notification endpoints — user notifications and unread count.
 */
@RestController
@RequestMapping("/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final SystemNoticeMapper noticeMapper;
    private final JdbcTemplate jdbcTemplate;

    @GetMapping
    public R<List<SystemNotice>> listMine() {
        Long userId = JwtUtils.getCurrentUserId();
        // Select notices that don't have a read recipient entry for this user yet
        String sql = """
            SELECT sn.* FROM system_notice sn
            WHERE (sn.scope = 'all' OR sn.scope = 'admin')
            AND (sn.expires_at IS NULL OR sn.expires_at > NOW())
            ORDER BY sn.created_at DESC
            LIMIT 20
            """;
        List<SystemNotice> notices = jdbcTemplate.query(sql, (rs, rowNum) -> {
            SystemNotice n = new SystemNotice();
            n.setId(rs.getLong("id"));
            n.setTitle(rs.getString("title"));
            n.setContent(rs.getString("content"));
            n.setLevel(rs.getString("level"));
            n.setPublisher(rs.getString("publisher"));
            n.setCreatedAt(rs.getTimestamp("created_at").toLocalDateTime());
            return n;
        });
        return R.ok(notices);
    }

    @GetMapping("/unread-count")
    public R<Map<String, Integer>> unreadCount() {
        Long userId = JwtUtils.getCurrentUserId();
        int count = jdbcTemplate.queryForObject("""
            SELECT COUNT(*) FROM system_notice sn
            WHERE (sn.scope = 'all' OR sn.scope = 'admin')
            AND (sn.expires_at IS NULL OR sn.expires_at > NOW())
            AND sn.id NOT IN (
                SELECT nr.notice_id FROM notice_recipient nr WHERE nr.user_id = ?
            )
            """, Integer.class, userId);
        return R.ok(Map.of("count", count));
    }

    @PostMapping("/{noticeId}/read")
    public R<Void> markRead(@PathVariable Long noticeId) {
        Long userId = JwtUtils.getCurrentUserId();
        jdbcTemplate.update("""
            INSERT IGNORE INTO notice_recipient (notice_id, user_id, is_read, read_at)
            VALUES (?, ?, 1, NOW())
            """, noticeId, userId);
        return R.ok();
    }
}
