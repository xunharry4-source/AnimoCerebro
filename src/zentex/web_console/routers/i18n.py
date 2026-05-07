"""Web API for G27 locale-aware messages."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from zentex.core.i18n import I18nCatalogError, I18nLocaleError, available_locales, default_locale, translate

router = APIRouter(prefix="/i18n", tags=["i18n"])


class TranslationRequest(BaseModel):
    """Translation request payload."""

    model_config = ConfigDict(extra="forbid")

    message_key: str = Field(min_length=1)
    locale: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


@router.get("/config")
def get_i18n_config() -> dict[str, object]:
    """Return configured UI/API language settings."""

    try:
        return {
            "language": default_locale(),
            "supported_languages": available_locales(),
            "fallback_language": "zh-CN",
        }
    except I18nLocaleError as exc:
        raise HTTPException(status_code=500, detail={"error": "invalid_i18n_config", "message": str(exc)}) from exc


@router.get("/locales")
def get_locales() -> dict[str, list[str]]:
    """Return supported locales."""

    return {"locales": available_locales()}


@router.post("/translate")
def translate_message(payload: TranslationRequest) -> dict[str, str]:
    """Translate one message key using the strict catalog."""

    try:
        result = translate(payload.message_key, locale=payload.locale, params=payload.params)
    except I18nLocaleError as exc:
        raise HTTPException(status_code=400, detail={"error": "unsupported_locale", "message": str(exc)}) from exc
    except I18nCatalogError as exc:
        raise HTTPException(status_code=404, detail={"error": "missing_catalog_entry", "message": str(exc)}) from exc
    return {"locale": result.locale, "message_key": result.message_key, "message": result.message}


@router.get("/messages/{message_key}")
def get_message(
    message_key: str,
    locale: str | None = Query(default=None),
    status: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
) -> dict[str, str]:
    """Translate one message key through query parameters."""

    params = {key: value for key, value in {"status": status, "event_id": event_id}.items() if value is not None}
    try:
        result = translate(message_key, locale=locale, params=params)
    except I18nLocaleError as exc:
        raise HTTPException(status_code=400, detail={"error": "unsupported_locale", "message": str(exc)}) from exc
    except I18nCatalogError as exc:
        raise HTTPException(status_code=404, detail={"error": "missing_catalog_entry", "message": str(exc)}) from exc
    return {"locale": result.locale, "message_key": result.message_key, "message": result.message}
