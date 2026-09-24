"""Explicit, typed resource routes grouped by CRM domain."""

from fastapi import APIRouter

from . import activity, companies, contacts, deals, notes, pipelines, tags, tasks

router = APIRouter()
for resource_router in (
    companies.router,
    contacts.router,
    deals.router,
    tasks.router,
    notes.router,
    tags.router,
    activity.router,
    pipelines.router,
):
    router.include_router(resource_router)
