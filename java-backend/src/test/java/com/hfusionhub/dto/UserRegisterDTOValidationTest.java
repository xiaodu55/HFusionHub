package com.hfusionhub.dto;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class UserRegisterDTOValidationTest {

    private static ValidatorFactory validatorFactory;
    private static Validator validator;

    @BeforeAll
    static void setUpValidator() {
        validatorFactory = Validation.buildDefaultValidatorFactory();
        validator = validatorFactory.getValidator();
    }

    @AfterAll
    static void closeValidator() {
        validatorFactory.close();
    }

    @Test
    void acceptsACompleteValidRegistration() {
        UserRegisterDTO request = validRequest();

        assertTrue(validator.validate(request).isEmpty());
    }

    @Test
    void rejectsWeakPasswordWithoutLettersAndDigits() {
        UserRegisterDTO request = validRequest();
        request.setPassword("12345678");

        assertFalse(validator.validate(request).isEmpty());
    }

    @Test
    void rejectsUsernameWithUnsupportedCharacters() {
        UserRegisterDTO request = validRequest();
        request.setUsername("alice@example");

        assertFalse(validator.validate(request).isEmpty());
    }

    @Test
    void rejectsMalformedOptionalPhoneNumber() {
        UserRegisterDTO request = validRequest();
        request.setPhone("not-a-phone");

        assertFalse(validator.validate(request).isEmpty());
    }

    private static UserRegisterDTO validRequest() {
        UserRegisterDTO request = new UserRegisterDTO();
        request.setUsername("alice_01");
        request.setPassword("Secret123");
        request.setNickname("Alice");
        request.setEmail("alice@example.com");
        request.setPhone("13800138000");
        return request;
    }
}
