"""Closed contact social-profile contract shared by create, patch, and merge."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator


class SocialLinks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linkedin: HttpUrl | None = None
    x: HttpUrl | None = None
    facebook: HttpUrl | None = None
    instagram: HttpUrl | None = None
    threads: HttpUrl | None = None
    bluesky: HttpUrl | None = None
    mastodon: HttpUrl | None = None
    tiktok: HttpUrl | None = None
    youtube: HttpUrl | None = None
    snapchat: HttpUrl | None = None
    pinterest: HttpUrl | None = None
    reddit: HttpUrl | None = None
    github: HttpUrl | None = None
    gitlab: HttpUrl | None = None
    telegram: HttpUrl | None = None
    discord: HttpUrl | None = None
    whatsapp: HttpUrl | None = None
    wechat: HttpUrl | None = None
    line: HttpUrl | None = None


class SocialLinksPatch(SocialLinks):
    @model_validator(mode="after")
    def has_changes(self) -> SocialLinksPatch:
        if not self.model_fields_set:
            raise ValueError("At least one social platform must change")
        return self
