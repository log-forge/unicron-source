"""Pydantic schemas for AI enrichment settings API."""

from typing import Optional

from pydantic import BaseModel, Field


class AISettingsResponse(BaseModel):
    """Response schema for AI settings -- effective values after merge.

    All fields are non-optional because the response always contains
    the effective value (DB override merged with env-var default).
    """

    ai_enabled: bool = Field(description="Whether AI enrichment is enabled")
    ollama_url: str = Field(description="Ollama API URL")
    ollama_model: str = Field(description="Ollama model name")
    ai_timeout: int = Field(description="AI request timeout in seconds")
    ai_cache_ttl: int = Field(description="AI cache TTL in seconds")
    ai_default_preprompt: str = Field(description="Default AI preprompt text")
    has_overrides: bool = Field(
        description="Whether any DB override exists for this organization"
    )


class AISettingsUpdate(BaseModel):
    """Request schema for updating AI settings.

    All fields are optional -- only non-None fields will be persisted
    as overrides. Fields left as None retain their current value.
    """

    ai_enabled: Optional[bool] = Field(
        default=None, description="Whether AI enrichment is enabled"
    )
    ollama_url: Optional[str] = Field(
        default=None, description="Ollama API URL"
    )
    ollama_model: Optional[str] = Field(
        default=None, description="Ollama model name"
    )
    ai_timeout: Optional[int] = Field(
        default=None, description="AI request timeout in seconds"
    )
    ai_cache_ttl: Optional[int] = Field(
        default=None, description="AI cache TTL in seconds"
    )
    ai_default_preprompt: Optional[str] = Field(
        default=None, description="Default AI preprompt text"
    )


__all__ = ["AISettingsResponse", "AISettingsUpdate"]
