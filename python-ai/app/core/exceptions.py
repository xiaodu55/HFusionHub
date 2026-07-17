"""
Custom exceptions for HFusionHub Python AI Engine
"""

from typing import Any


class HFusionHubException(Exception):
    """Base exception for HFusionHub"""

    def __init__(
        self,
        message: str,
        code: int = 500,
        details: Any | None = None
    ):
        self.message = message
        self.code = code
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        result = {
            "code": self.code,
            "message": self.message
        }
        if self.details:
            result["details"] = self.details
        return result


class ValidationException(HFusionHubException):
    """Validation error (400)"""

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(message, code=400, details=details)


class FileNotFoundException(HFusionHubException):
    """File not found (404)"""

    def __init__(self, file_path: str):
        super().__init__(f"文件不存在: {file_path}", code=404)


class FileTypeException(HFusionHubException):
    """Unsupported file type (400)"""

    def __init__(self, file_type: str, supported_types: list):
        supported = ", ".join(supported_types)
        super().__init__(
            f"不支持的文件类型: {file_type}。支持的类型: {supported}",
            code=400
        )


class FileSizeException(HFusionHubException):
    """File too large (400)"""

    def __init__(self, file_size: int, max_size: int):
        file_mb = file_size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        super().__init__(
            f"文件过大: {file_mb:.1f}MB，最大允许: {max_mb:.0f}MB",
            code=400
        )


class ParsingException(HFusionHubException):
    """Document parsing error (500)"""

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(f"文档解析失败: {message}", code=500, details=details)


class VectorizationException(HFusionHubException):
    """Vectorization error (500)"""

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(f"向量化失败: {message}", code=500, details=details)


class EmbeddingException(HFusionHubException):
    """Embedding generation error (500)"""

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(f"Embedding生成失败: {message}", code=500, details=details)


class MilvusException(HFusionHubException):
    """Milvus operation error (500)"""

    def __init__(self, message: str, details: Any | None = None):
        super().__init__(f"向量数据库操作失败: {message}", code=500, details=details)


class CallbackException(HFusionHubException):
    """Callback notification error (500)"""

    def __init__(self, callback_url: str, message: str):
        super().__init__(
            f"回调通知失败: {callback_url} - {message}",
            code=500
        )


class ExternalServiceException(HFusionHubException):
    """External service error (502)"""

    def __init__(self, service: str, message: str):
        super().__init__(
            f"外部服务调用失败: {service} - {message}",
            code=502
        )
