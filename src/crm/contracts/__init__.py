"""Pydantic CRM contract boundary; no runtime JSON schema definitions."""

from .registry import CONTRACT_MODELS, model_for
from .validation import DomainValidationError, normalized_create, normalized_patch, validate_payload

__all__ = [
    "CONTRACT_MODELS",
    "DomainValidationError",
    "model_for",
    "normalized_create",
    "normalized_patch",
    "validate_payload",
]
