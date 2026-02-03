"""
File and request validators
"""

import os
from typing import Optional, Tuple
from fastapi import HTTPException


# Supported file types
SUPPORTED_FILE_TYPES = {
    "md": "text/markdown",
    "txt": "text/plain",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

# File size limits (in bytes)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MIN_FILE_SIZE = 1  # 1 byte (non-empty)

# File name limits
MAX_FILENAME_LENGTH = 255


def validate_file_type(file_type: str) -> None:
    """
    Validate file type is supported

    Args:
        file_type: File extension (e.g., 'md', 'txt', 'pdf', 'docx')

    Raises:
        HTTPException: If file type is not supported
    """
    if not file_type:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10002,
                "message": "文件类型不能为空"
            }
        )

    file_type = file_type.lower().strip('.')

    if file_type not in SUPPORTED_FILE_TYPES:
        supported = ", ".join(SUPPORTED_FILE_TYPES.keys())
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10002,
                "message": f"不支持的文件类型: {file_type}。支持的类型: {supported}"
            }
        )


def validate_file_path(file_path: str) -> None:
    """
    Validate file path exists and is accessible

    Args:
        file_path: Path to the file

    Raises:
        HTTPException: If file doesn't exist or is not accessible
    """
    if not file_path:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10001,
                "message": "文件路径不能为空"
            }
        )

    # Try to resolve relative paths from project root
    if not os.path.isabs(file_path):
        # Try from project root (parent of python-ai)
        # __file__ is python-ai/app/utils/validators.py
        # Go up 4 levels to get to project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        abs_path = os.path.join(project_root, file_path)
        print(f"[Validator] Project root: {project_root}")
        print(f"[Validator] Absolute path: {abs_path}")
        print(f"[Validator] Exists: {os.path.exists(abs_path)}")
        if os.path.exists(abs_path):
            file_path = abs_path
        # Also try from current working directory
        elif os.path.exists(file_path):
            pass  # Use as-is
        else:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": 10001,
                    "message": f"文件不存在: {file_path}"
                }
            )

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail={
                "code": 10001,
                "message": f"文件不存在: {file_path}"
            }
        )

    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10001,
                "message": f"路径不是文件: {file_path}"
            }
        )

    if not os.access(file_path, os.R_OK):
        raise HTTPException(
            status_code=403,
            detail={
                "code": 10001,
                "message": f"文件不可读: {file_path}"
            }
        )


def validate_file_size(file_path: str, max_size: Optional[int] = None) -> None:
    """
    Validate file size is within limits

    Args:
        file_path: Path to the file
        max_size: Maximum allowed size in bytes (default: MAX_FILE_SIZE)

    Raises:
        HTTPException: If file is too large or empty
    """
    max_size = max_size or MAX_FILE_SIZE

    file_size = os.path.getsize(file_path)

    if file_size < MIN_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10003,
                "message": "文件为空"
            }
        )

    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        file_mb = file_size / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10003,
                "message": f"文件过大: {file_mb:.1f}MB，最大允许: {max_mb:.0f}MB"
            }
        )


def validate_filename(filename: Optional[str]) -> None:
    """
    Validate filename length and characters

    Args:
        filename: Original filename

    Raises:
        HTTPException: If filename is invalid
    """
    if not filename:
        return  # Filename is optional

    if len(filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10004,
                "message": f"文件名过长: {len(filename)}字符，最大允许: {MAX_FILENAME_LENGTH}字符"
            }
        )


def validate_document_id(document_id: Optional[str]) -> None:
    """
    Validate document ID

    Args:
        document_id: Document identifier

    Raises:
        HTTPException: If document ID is invalid
    """
    if not document_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10005,
                "message": "文档ID不能为空"
            }
        )

    # Check if it's a valid string (non-empty after stripping)
    if not document_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": 10005,
                "message": "文档ID不能为空"
            }
        )


def validate_file_upload(
    file_path: str,
    file_type: str,
    filename: Optional[str] = None,
    check_size: bool = True
) -> Tuple[str, str]:
    """
    Comprehensive file upload validation

    Args:
        file_path: Path to the file
        file_type: File extension
        filename: Original filename (optional)
        check_size: Whether to check file size

    Returns:
        Tuple of (normalized_file_type, file_path)

    Raises:
        HTTPException: If any validation fails
    """
    # Normalize file type
    file_type = file_type.lower().strip('.')

    # Run all validations
    validate_file_type(file_type)
    validate_file_path(file_path)
    validate_filename(filename)

    if check_size:
        validate_file_size(file_path)

    return file_type, file_path
