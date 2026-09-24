"""Persistence conflicts surfaced as domain-safe API errors."""


class ResourceNotFound(RuntimeError):
    pass


class ResourceConflict(RuntimeError):
    pass
