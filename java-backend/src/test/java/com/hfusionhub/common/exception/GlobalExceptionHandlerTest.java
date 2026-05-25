package com.hfusionhub.common.exception;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.hfusionhub.common.constant.StatusCode;
import com.hfusionhub.common.result.R;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.resource.NoResourceFoundException;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Test
    void mapsDefaultBusinessExceptionToBadRequest() {
        ResponseEntity<R<?>> response = handler.handleBusinessException(new BusinessException("bad input"));

        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(StatusCode.BAD_REQUEST, response.getBody().getCode());
    }

    @Test
    void mapsHttpBusinessCodeToMatchingStatus() {
        ResponseEntity<R<?>> response =
                handler.handleBusinessException(new BusinessException(StatusCode.TOO_MANY_REQUESTS, "too many"));

        assertEquals(HttpStatus.TOO_MANY_REQUESTS, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(StatusCode.TOO_MANY_REQUESTS, response.getBody().getCode());
    }

    @Test
    void mapsDomainBusinessCodeToBadRequest() {
        ResponseEntity<R<?>> response =
                handler.handleBusinessException(new BusinessException(StatusCode.LOGIN_ERROR, "invalid credentials"));

        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(StatusCode.LOGIN_ERROR, response.getBody().getCode());
    }

    @Test
    void mapsNoResourceFoundExceptionTo404() {
        ResponseEntity<R<?>> response = handler.handleNoResourceFoundException(
                new NoResourceFoundException(HttpMethod.GET, "/api/does-not-exist"));

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(404, response.getBody().getCode());
        assertNotNull(response.getBody().getMessage());
    }
}
