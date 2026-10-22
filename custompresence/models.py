"""Validated controls for the fields supported by Discord's desktop RPC."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from .images import normalize_image_url


INVITE_FIELDS = {"join", "spectate", "match"}


def public_url(value):
    if not value:
        return value
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("Enter a valid public HTTPS link.") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a public HTTPS link.")
    return value


class ActivityButton(BaseModel):
    label: str = Field(min_length=1, max_length=32)
    url: str = Field(max_length=512)

    @field_validator("label", "url", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        if not value:
            raise ValueError("A button needs a link.")
        return public_url(value)


class Activity(BaseModel):
    activity_type: Literal["playing", "listening", "watching", "competing"] = "playing"
    image_mode: Literal["upload", "link"] = "upload"
    image: str = Field(default="", max_length=2048)
    name: str = Field(default="", max_length=128)
    details: str = Field(default="", max_length=128)
    state: str = Field(default="", max_length=128)
    details_url: str = Field(default="", max_length=512)
    state_url: str = Field(default="", max_length=512)
    status_display_type: Literal["name", "details", "state"] = "name"
    large_text: str = Field(default="", max_length=128)
    large_url: str = Field(default="", max_length=512)
    small_image: str = Field(default="", max_length=2048)
    small_image_mode: Literal["upload", "link"] = "link"
    small_text: str = Field(default="", max_length=128)
    small_url: str = Field(default="", max_length=512)
    start: int | None = Field(default=None, ge=1, le=253402300799)
    end: int | None = Field(default=None, ge=1, le=253402300799)
    party_id: str = Field(default="", max_length=128)
    party_current: int | None = Field(default=None, ge=1, le=2147483647)
    party_max: int | None = Field(default=None, ge=1, le=2147483647)
    join: str = Field(default="", max_length=128)
    spectate: str = Field(default="", max_length=128)
    match: str = Field(default="", max_length=128)
    buttons: list[ActivityButton] = Field(default_factory=list, max_length=2)
    instance: bool = True

    @field_validator("*", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("details", "state", "join", "spectate", "match")
    @classmethod
    def minimum_text(cls, value):
        if value and len(value) < 2:
            raise ValueError("Use at least two characters, or leave this field empty.")
        return value

    @field_validator("image", "small_image")
    @classmethod
    def valid_image(cls, value):
        if value and not value.startswith("https://"):
            if not all(c.isalnum() or c in "_-" for c in value):
                raise ValueError("Use a public HTTPS image link or an uploaded asset key.")
            return value
        return normalize_image_url(value) if value else value

    @field_validator("details_url", "state_url", "large_url", "small_url")
    @classmethod
    def valid_url(cls, value):
        return public_url(value)

    @model_validator(mode="after")
    def consistent_fields(self):
        if (self.party_current is None) != (self.party_max is None):
            raise ValueError("Enter both the current and maximum party size.")
        if self.party_current is not None and self.party_current > self.party_max:
            raise ValueError("Current party size cannot exceed the maximum.")
        if self.start and self.end and self.end <= self.start:
            raise ValueError("The end time must be after the start time.")
        status_text = self.presence_state if self.status_display_type == "state" else getattr(self, self.status_display_type)
        if self.status_display_type != "name" and not status_text:
            raise ValueError("Add text for the selected status display field.")
        return self

    @property
    def presence_state(self):
        if self.party_current is None:
            return self.state
        state = self.state or "In a party"
        # Other activity layouts may omit Discord's native party badge.
        if self.activity_type != "playing":
            suffix = f" ({self.party_current} of {self.party_max})"
            if len((state + suffix).encode("utf-16-le")) > 256:
                budget = (127 - len(suffix)) * 2
                state = state.encode("utf-16-le")[:budget].decode("utf-16-le", errors="ignore").rstrip() + "…"
            state += suffix
        return state

    def rpc_fields(self):
        result = {key: getattr(self, key) or None for key in (
            "details", "state", "details_url", "state_url", "large_text", "large_url",
            "small_image", "small_text", "small_url", "party_id", "join", "spectate", "match",
        )}
        # Discord rejects an empty name; a single space preserves the user's blank activity.
        result.update(name=self.name or " ", state=self.presence_state or None,
                      large_image=self.image or None, start=self.start, end=self.end,
                      instance=self.instance, buttons=[button.model_dump() for button in self.buttons] or None,
                      party_size=[self.party_current, self.party_max] if self.party_current is not None else None)
        return result
