package com.hfusionhub.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.hutool.crypto.digest.BCrypt;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.exception.BusinessException;
import com.hfusionhub.common.limiter.LoginRateLimiter;
import com.hfusionhub.common.utils.JwtUtils;
import com.hfusionhub.dto.AdminPasswordResetDTO;
import com.hfusionhub.dto.UserInfoDTO;
import com.hfusionhub.dto.UserLoginDTO;
import com.hfusionhub.dto.UserRegisterDTO;
import com.hfusionhub.dto.UserUpdateDTO;
import com.hfusionhub.entity.User;
import com.hfusionhub.mapper.TenantMemberMapper;
import com.hfusionhub.mapper.UserMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DuplicateKeyException;

@ExtendWith(MockitoExtension.class)
class UserServiceImplTest {

    @Mock
    private UserMapper userMapper;

    @Mock
    private TenantMemberMapper tenantMemberMapper;

    @Mock
    private JwtUtils jwtUtils;

    @Mock
    private LoginRateLimiter rateLimiter;

    private UserServiceImpl userService;
    private MockedStatic<JwtUtils> jwtUtilsMock;

    @BeforeEach
    void setUp() {
        userService = new UserServiceImpl(userMapper, tenantMemberMapper, jwtUtils, rateLimiter);
        jwtUtilsMock = org.mockito.Mockito.mockStatic(JwtUtils.class);
    }

    @AfterEach
    void tearDown() {
        jwtUtilsMock.close();
    }

    @Test
    void loginRecordsFailureForUnknownUsername() {
        UserLoginDTO login = login("missing", "password");
        when(userMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(null);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.login(login));

        assertEquals(StatusCode.LOGIN_ERROR, error.getCode());
        verify(rateLimiter).recordFailedAttempt("unknown");
    }

    @Test
    void loginRejectsDisabledUserWithoutCheckingPassword() {
        User user = user(1L, "alice");
        user.setStatus(1);
        user.setPassword("not-a-valid-hash");
        when(userMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(user);

        BusinessException error =
                assertThrows(BusinessException.class, () -> userService.login(login("alice", "password")));

        assertEquals(StatusCode.USER_DISABLED, error.getCode());
        verify(rateLimiter, never()).recordFailedAttempt("unknown");
    }

    @Test
    void loginRecordsFailureForWrongPassword() {
        User user = user(1L, "alice");
        user.setPassword(BCrypt.hashpw("correct-password"));
        when(userMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(user);

        BusinessException error =
                assertThrows(BusinessException.class, () -> userService.login(login("alice", "wrong-password")));

        assertEquals(StatusCode.LOGIN_ERROR, error.getCode());
        verify(rateLimiter).recordFailedAttempt("unknown");
    }

    @Test
    void successfulLoginClearsFailuresAndReturnsToken() {
        User user = user(1L, "alice");
        user.setPassword(BCrypt.hashpw("correct-password"));
        when(userMapper.selectOne(any(LambdaQueryWrapper.class))).thenReturn(user);
        jwtUtilsMock.when(JwtUtils::getTokenValue).thenReturn("token-123");

        String token = userService.login(login("alice", "correct-password"));

        assertEquals("token-123", token);
        assertNotNull(user.getLastLoginTime());
        verify(userMapper).updateById(user);
        verify(rateLimiter).recordSuccess("unknown");
        jwtUtilsMock.verify(() -> JwtUtils.login(1L));
    }

    @Test
    void registerRejectsDuplicateUsername() {
        UserRegisterDTO register = register("alice", "alice@example.com");
        when(userMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(1L);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.register(register));

        assertEquals(StatusCode.USER_EXISTS, error.getCode());
        verify(userMapper, never()).insert(any(User.class));
    }

    @Test
    void registerRejectsDuplicateEmail() {
        UserRegisterDTO register = register("alice", "alice@example.com");
        when(userMapper.selectCount(any(LambdaQueryWrapper.class)))
                .thenReturn(0L)
                .thenReturn(1L);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.register(register));

        assertEquals(StatusCode.USER_EXISTS, error.getCode());
        verify(userMapper, never()).insert(any(User.class));
    }

    @Test
    void registerHashesPasswordAndSetsUserDefaults() {
        UserRegisterDTO register = register("alice", "alice@example.com");
        when(userMapper.selectCount(any(LambdaQueryWrapper.class)))
                .thenReturn(0L)
                .thenReturn(0L);
        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);

        UserInfoDTO result = userService.register(register);

        verify(userMapper).insert(captor.capture());
        User inserted = captor.getValue();
        assertEquals("alice", inserted.getUsername());
        assertFalse("secret-123".equals(inserted.getPassword()));
        assertTrue(BCrypt.checkpw("secret-123", inserted.getPassword()));
        assertEquals("pending", inserted.getRole());
        assertEquals(0, inserted.getStatus());
        assertEquals(1L, inserted.getTenantId());
        assertEquals("alice", result.getUsername());
        verify(tenantMemberMapper).insert(any());
    }

    @Test
    void registerNormalisesOptionalFieldsAndDefaultsBlankNickname() {
        UserRegisterDTO register = register("alice", " ALICE@EXAMPLE.COM ");
        register.setNickname("   ");
        register.setPhone(" 13800138000 ");
        when(userMapper.selectCount(any(LambdaQueryWrapper.class)))
                .thenReturn(0L)
                .thenReturn(0L);
        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);

        userService.register(register);

        verify(userMapper).insert(captor.capture());
        assertEquals("alice", captor.getValue().getNickname());
        assertEquals("alice@example.com", captor.getValue().getEmail());
        assertEquals("13800138000", captor.getValue().getPhone());
    }

    @Test
    void registerConvertsConcurrentUniqueConstraintViolationToUserExists() {
        UserRegisterDTO register = register("alice", "alice@example.com");
        when(userMapper.selectCount(any(LambdaQueryWrapper.class)))
                .thenReturn(0L)
                .thenReturn(0L);
        doThrow(new DuplicateKeyException("duplicate username"))
                .when(userMapper)
                .insert(any(User.class));

        BusinessException error = assertThrows(BusinessException.class, () -> userService.register(register));

        assertEquals(StatusCode.USER_EXISTS, error.getCode());
    }

    @Test
    void ordinaryUserCannotReadAnotherUser() {
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        jwtUtilsMock.when(() -> JwtUtils.hasRole("admin")).thenReturn(false);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.getUserById(2L));

        assertEquals(StatusCode.FORBIDDEN, error.getCode());
        verify(userMapper, never()).selectById(2L);
    }

    @Test
    void administratorCanReadAnotherUser() {
        User target = user(2L, "bob");
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        jwtUtilsMock.when(() -> JwtUtils.hasRole("admin")).thenReturn(true);
        when(userMapper.selectById(2L)).thenReturn(target);

        UserInfoDTO result = userService.getUserById(2L);

        assertEquals(2L, result.getId());
        assertEquals("bob", result.getUsername());
    }

    @Test
    void administratorCanAssignBuilderRole() {
        User target = user(2L, "bob");
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        when(userMapper.selectById(2L)).thenReturn(target);

        UserInfoDTO result = userService.updateUserRole(2L, "builder");

        assertEquals("builder", result.getRole());
        assertEquals("builder", target.getRole());
        assertFalse(Boolean.TRUE.equals(target.getPlatformAdmin()));
        verify(userMapper).updateById(target);
    }

    @Test
    void administratorCannotGrantSuperAdminRole() {
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.updateUserRole(2L, "admin"));

        assertEquals(StatusCode.BAD_REQUEST, error.getCode());
        verify(userMapper, never()).selectById(2L);
    }

    @Test
    void administratorCannotDemoteOwnAccount() {
        User current = user(1L, "admin");
        current.setRole("admin");
        current.setPlatformAdmin(true);
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        when(userMapper.selectById(1L)).thenReturn(current);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.updateUserRole(1L, "user"));

        assertEquals(StatusCode.BAD_REQUEST, error.getCode());
        verify(userMapper, never()).updateById(current);
    }

    @Test
    void updateRejectsEmailOwnedByAnotherUser() {
        User current = user(1L, "alice");
        UserUpdateDTO update = new UserUpdateDTO();
        update.setEmail("used@example.com");
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        when(userMapper.selectById(1L)).thenReturn(current);
        when(userMapper.selectCount(any(LambdaQueryWrapper.class))).thenReturn(1L);

        BusinessException error = assertThrows(BusinessException.class, () -> userService.updateUser(update));

        assertEquals(StatusCode.USER_EXISTS, error.getCode());
        verify(userMapper, never()).updateById(current);
    }

    @Test
    void adminResetHashesTemporaryPassword() {
        User target = user(2L, "bob");
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        when(userMapper.selectById(2L)).thenReturn(target);
        AdminPasswordResetDTO dto = new AdminPasswordResetDTO();
        dto.setNewPassword("temp-pass-123");
        ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);

        UserInfoDTO result = userService.resetUserPassword(2L, dto);

        assertEquals(2L, result.getId());
        verify(userMapper).updateById(captor.capture());
        assertTrue(BCrypt.checkpw("temp-pass-123", captor.getValue().getPassword()));
    }

    @Test
    void adminResetRejectsSelfReset() {
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        AdminPasswordResetDTO dto = new AdminPasswordResetDTO();
        dto.setNewPassword("temp-pass-123");

        BusinessException error = assertThrows(BusinessException.class, () -> userService.resetUserPassword(1L, dto));

        assertEquals(StatusCode.BAD_REQUEST, error.getCode());
        verify(userMapper, never()).updateById(any(User.class));
    }

    @Test
    void adminResetRejectsMissingUser() {
        jwtUtilsMock.when(JwtUtils::getCurrentUserId).thenReturn(1L);
        when(userMapper.selectById(404L)).thenReturn(null);
        AdminPasswordResetDTO dto = new AdminPasswordResetDTO();
        dto.setNewPassword("temp-pass-123");

        BusinessException error = assertThrows(BusinessException.class, () -> userService.resetUserPassword(404L, dto));

        assertEquals(StatusCode.NOT_FOUND, error.getCode());
        verify(userMapper, never()).updateById(any(User.class));
    }

    private UserLoginDTO login(String username, String password) {
        UserLoginDTO login = new UserLoginDTO();
        login.setUsername(username);
        login.setPassword(password);
        return login;
    }

    private UserRegisterDTO register(String username, String email) {
        UserRegisterDTO register = new UserRegisterDTO();
        register.setUsername(username);
        register.setPassword("secret-123");
        register.setNickname("Alice");
        register.setEmail(email);
        register.setPhone("13800138000");
        return register;
    }

    private User user(Long id, String username) {
        User user = new User();
        user.setId(id);
        user.setUsername(username);
        user.setNickname(username);
        user.setEmail(username + "@example.com");
        user.setRole("user");
        user.setStatus(0);
        return user;
    }
}
