"""Error types the API maps to HTTP responses. Messages are plain text and safe to show users."""
from rest_framework.views import exception_handler as drf_handler
from rest_framework.response import Response

from .domain import DomainError


class Forbidden(Exception):
    """The user's role or institution does not allow this action."""


class NotFound(Exception):
    pass


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response({'code': 'rule_violation', 'message': str(exc), 'fields': {}}, status=400)
    if isinstance(exc, Forbidden):
        return Response({'code': 'forbidden', 'message': str(exc), 'fields': {}}, status=403)
    if isinstance(exc, NotFound):
        return Response({'code': 'not_found', 'message': 'Record not found.', 'fields': {}}, status=404)
    response = drf_handler(exc, context)
    if response is not None:
        detail = response.data
        message = detail.get('detail') if isinstance(detail, dict) and 'detail' in detail else 'Please check the highlighted fields.'
        code = getattr(exc, 'default_code', 'error')
        fields = detail if isinstance(detail, dict) and 'detail' not in detail else {}
        response.data = {'code': code, 'message': str(message), 'fields': fields}
    return response
