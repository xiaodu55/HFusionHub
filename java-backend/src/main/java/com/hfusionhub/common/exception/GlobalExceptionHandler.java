package com.hfusionhub.common.exception;

import cn.dev33.satoken.exception.NotLoginException;
import cn.dev33.satoken.exception.NotPermissionException;
import cn.dev33.satoken.exception.NotRoleException;
import com.hfusionhub.common.result.R;
import java.util.stream.Collectors;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 全局异常处理器
 *
 * @author HFusionHub Team
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /**
     * 业务异常
     */
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<R<?>> handleBusinessException(BusinessException e) {
        log.warn("业务异常: {}", e.getMessage());
        return ResponseEntity.status(resolveBusinessHttpStatus(e.getCode())).body(R.fail(e.getCode(), e.getMessage()));
    }

    private HttpStatus resolveBusinessHttpStatus(int code) {
        // 标准 HTTP 状态码直接映射
        if (code >= 400 && code < 600) {
            HttpStatus status = HttpStatus.resolve(code);
            if (status != null) {
                return status;
            }
        }
        // 业务层 NOT_FOUND 系列（分块、文档、知识库等）映射为 HTTP 404
        if (isNotFoundCode(code)) {
            return HttpStatus.NOT_FOUND;
        }
        return HttpStatus.BAD_REQUEST;
    }

    /**
     * 判断业务错误码是否对应 HTTP 404 语义。
     * 范围规则：4xxx 系列中个位为 1 的错误码（4001, 4101, 4201...）表示"资源不存在"。
     */
    private boolean isNotFoundCode(int code) {
        return code >= 4000 && code < 5000 && code % 10 == 1;
    }

    /**
     * Sa-Token 未登录异常
     */
    @ExceptionHandler(NotLoginException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public R<?> handleNotLoginException(NotLoginException e) {
        log.warn("用户未登录: {}", e.getMessage());
        return R.fail(401, "用户未登录或登录已过期");
    }

    /**
     * Sa-Token 无权限异常
     */
    @ExceptionHandler(NotPermissionException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public R<?> handleNotPermissionException(NotPermissionException e) {
        log.warn("权限不足: {}", e.getMessage());
        return R.fail(403, "权限不足");
    }

    /**
     * Sa-Token 无角色异常
     */
    @ExceptionHandler(NotRoleException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public R<?> handleNotRoleException(NotRoleException e) {
        log.warn("角色不足: {}", e.getMessage());
        return R.fail(403, "角色权限不足");
    }

    /**
     * 参数校验异常
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public R<?> handleMethodArgumentNotValidException(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining(", "));
        log.warn("参数校验失败: {}", message);
        return R.fail(400, message);
    }

    /**
     * 绑定异常
     */
    @ExceptionHandler(BindException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public R<?> handleBindException(BindException e) {
        String message =
                e.getFieldErrors().stream().map(FieldError::getDefaultMessage).collect(Collectors.joining(", "));
        log.warn("参数绑定失败: {}", message);
        return R.fail(400, message);
    }

    /**
     * 参数非法异常 — 仅返回通用提示，避免泄露内部校验细节
     */
    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public R<?> handleIllegalArgumentException(IllegalArgumentException e) {
        log.warn("参数非法: {}", e.getMessage());
        return R.fail(400, "请求参数不合法，请检查后重试");
    }

    /**
     * 资源不存在异常 — 不存在的请求路径应返回 404 而非 500。
     * <p>Spring 6.1+ 对匹配不到任何 handler/静态资源的路径抛出
     * {@link NoResourceFoundException}；此前被兜底 {@link #handleException}
     * 误归为 500，接口语义不标准且误导排查。404 语义遵循 HTTP 标准：缺失
     * 资源属客户端错误，响应体仍保持统一 R 结构。</p>
     */
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<R<?>> handleNoResourceFoundException(NoResourceFoundException e) {
        log.warn("请求路径不存在: method={} path={}", e.getHttpMethod(), e.getResourcePath());
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(R.fail(404, "请求的资源不存在"));
    }

    /**
     * 请求方法不支持 — 返回 405 而非兜底 500（如旧客户端打到已下线的方法）
     */
    @ExceptionHandler(org.springframework.web.HttpRequestMethodNotSupportedException.class)
    @ResponseStatus(HttpStatus.METHOD_NOT_ALLOWED)
    public R<?> handleMethodNotSupported(org.springframework.web.HttpRequestMethodNotSupportedException e) {
        log.warn("请求方法不支持: {}", e.getMessage());
        return R.fail(405, "请求方法不被支持");
    }

    /**
     * 请求 Content-Type 不支持 — 返回 415 而非兜底 500（如 multipart 端点收到 JSON）
     */
    @ExceptionHandler(org.springframework.web.HttpMediaTypeNotSupportedException.class)
    @ResponseStatus(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
    public R<?> handleMediaTypeNotSupported(org.springframework.web.HttpMediaTypeNotSupportedException e) {
        log.warn("Content-Type 不支持: {}", e.getMessage());
        return R.fail(415, "请求内容类型不被支持");
    }

    /**
     * 运行时异常
     */
    @ExceptionHandler(RuntimeException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public R<?> handleRuntimeException(RuntimeException e) {
        log.error("运行时异常", e);
        return R.fail("系统内部错误");
    }

    /**
     * 其他异常
     */
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public R<?> handleException(Exception e) {
        log.error("未知异常", e);
        return R.fail("系统内部错误");
    }
}
