package com.hfusionhub.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.result.R;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.entity.SystemNotice;
import com.hfusionhub.mapper.SystemNoticeMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * Notification endpoints — user notifications and unread count.
 *
 * <p>Admin endpoints (publish / list-all / delete) complete the notification
 * bell loop: admins publish system notices, users see them in the bell popup
 * and mark them as read.</p>
 */
@RestController
@RequestMapping("/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private static final List<String> ALLOWED_LEVELS = List.of("info", "warning", "error");
    private static final List<String> ALLOWED_SCOPES = List.of("all", "admin", "user");

    private final SystemNoticeMapper noticeMapper;
    private final JdbcTemplate jdbcTemplate;
    private final com.hfusionhub.service.AuditLogService auditLogService;

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

    // ── Admin: publish / manage system notices ──────────────────────────

    @GetMapping("/admin")
    @SaCheckRole("admin")
    public R<List<SystemNotice>> adminList() {
        return R.ok(noticeMapper.selectList(
            new LambdaQueryWrapper<SystemNotice>()
                .orderByDesc(SystemNotice::getCreatedAt)
        ));
    }

    @PostMapping("/admin")
    @SaCheckRole("admin")
    public R<SystemNotice> adminCreate(@RequestBody SystemNotice notice) {
        String level = notice.getLevel() == null ? "info" : notice.getLevel().toLowerCase();
        String scope = notice.getScope() == null ? "all" : notice.getScope().toLowerCase();
        if (!ALLOWED_LEVELS.contains(level)) {
            return R.fail("level 仅允许 info / warning / error");
        }
        if (!ALLOWED_SCOPES.contains(scope)) {
            return R.fail("scope 仅允许 all / admin / user");
        }
        if (notice.getTitle() == null || notice.getTitle().isBlank()) {
            return R.fail("公告标题不能为空");
        }
        notice.setId(null);
        notice.setLevel(level);
        notice.setScope(scope);
        notice.setPublisher(JwtUtils.getCurrentUserId().toString());
        if (notice.getExpiresAt() != null && notice.getExpiresAt().isBefore(LocalDateTime.now())) {
            return R.fail("过期时间不能早于当前时间");
        }
        noticeMapper.insert(notice);
        auditLogService.record("notice.create", "system_notice", String.valueOf(notice.getId()),
                "发布公告: " + notice.getTitle());
        return R.ok("公告已发布", notice);
    }

    @DeleteMapping("/admin/{noticeId}")
    @SaCheckRole("admin")
    public R<Void> adminDelete(@PathVariable Long noticeId) {
        noticeMapper.deleteById(noticeId);
        jdbcTemplate.update("DELETE FROM notice_recipient WHERE notice_id = ?", noticeId);
        auditLogService.record("notice.delete", "system_notice", String.valueOf(noticeId), "删除公告");
        return R.ok("公告已删除", null);
    }
}
