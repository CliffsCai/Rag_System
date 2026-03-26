# -*- coding: utf-8 -*-
"""
统一业务异常体系
service 层抛出这些异常，API 层和全局 handler 统一映射到 HTTP 状态码
"""


class AppError(Exception):
    """所有业务异常的基类"""
    status_code: int = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message


class NotFoundError(AppError):
    """资源不存在 → 404"""
    status_code = 404


class ValidationError(AppError):
    """参数/业务校验失败 → 400"""
    status_code = 400


class ForbiddenError(AppError):
    """权限不足 → 403"""
    status_code = 403


class ConflictError(AppError):
    """资源冲突（如重复创建）→ 409"""
    status_code = 409


class ExternalServiceError(AppError):
    """外部服务调用失败（ADB / OSS / LLM）→ 502"""
    status_code = 502
