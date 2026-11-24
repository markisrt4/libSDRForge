# SPDX-License-Identifier: MIT
"""!
@brief Hardware-independent REST routing for radio profiles and user presets.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sdrforge.controllers.radio_catalog import PresetService
from sdrforge.interfaces.radio_catalog_if import RadioCatalogIf, RadioMode, RadioPreset


class RadioApi:
    """!
    @brief Pure request dispatcher; no HTTP server or SDR device dependencies.
    """

    def __init__(
        self,
        catalog: RadioCatalogIf,
        presets: PresetService,
        *,
        factory_presets: tuple[RadioPreset, ...] = (),
    ) -> None:
        """!
        @brief Bind radio catalog and preset services.
        @param self The current instance.
        @param catalog Canonical radio catalog.
        @param presets User preset service.
        @param factory_presets Immutable factory presets.
        """
        self.catalog = catalog
        self.presets = presets
        self.factory_presets = factory_presets

    def dispatch(
        self, method: str, target: str, body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        """!
        @brief Dispatch a radio catalog or preset request.
        @param self The current instance.
        @param method HTTP request method.
        @param target Request path and optional query string.
        @param body Optional decoded JSON request body.
        @return HTTP status and response payload.
        """
        url = urlsplit(target)
        path = url.path
        query = parse_qs(url.query)
        segments = path.strip("/").split("/")
        try:
            if method == "GET" and path == "/v1/radio/profiles":
                return 200, {"profiles": [asdict(p) for p in self.catalog.profiles()]}
            if (
                method == "GET"
                and len(segments) == 4
                and segments[:3] == ["v1", "radio", "profiles"]
            ):
                return 200, {"profile": asdict(self.catalog.profile(segments[3]))}
            if method == "GET" and path == "/v1/radio/presets":
                profile_key = query.get("profile_key", [None])[0]
                owner = query.get("owner", [None])[0]
                factory = (
                    p
                    for p in self.factory_presets
                    if (profile_key is None or p.profile_key == profile_key)
                    and (owner is None or owner == "factory")
                )
                user = self.presets.list_presets(profile_key=profile_key, owner=owner)
                return 200, {"presets": [asdict(p) for p in (*factory, *user)]}
            if method == "POST" and path == "/v1/radio/presets":
                if body is None:
                    raise ValueError("JSON body required")
                mode = body.get("mode")
                parsed_mode = None
                if mode is not None:
                    if not isinstance(mode, dict):
                        raise ValueError("mode must be an object")
                    parsed_mode = RadioMode(**mode)
                preset = self.presets.save(
                    profile_key=body["profile_key"],
                    label=body["label"],
                    frequency_hz=body["frequency_hz"],
                    mode=parsed_mode,
                    owner=body.get("owner", "default"),
                )
                return 201, {"preset": asdict(preset)}
            if len(segments) == 4 and segments[:3] == ["v1", "radio", "presets"]:
                preset_id = segments[3]
                if body is None:
                    raise ValueError("JSON body required")
                owner = body.get("owner", "default")
                existing = next(
                    (
                        p
                        for p in self.presets.list_presets(owner=owner)
                        if p.id == preset_id
                    ),
                    None,
                )
                if existing is None:
                    return 404, {"error": "preset_not_found"}
                if method == "DELETE":
                    self.presets.delete(preset_id, owner=owner)
                    return 200, {"ok": True}
                if method == "PATCH":
                    mode = body.get("mode")
                    if mode is not None and not isinstance(mode, dict):
                        raise ValueError("mode must be an object")
                    updated = RadioPreset(
                        id=existing.id,
                        profile_key=body.get("profile_key", existing.profile_key),
                        label=body.get("label", existing.label),
                        frequency_hz=body.get("frequency_hz", existing.frequency_hz),
                        mode=RadioMode(**mode) if mode is not None else existing.mode,
                        owner=existing.owner,
                        origin=existing.origin,
                    )
                    return 200, {"preset": asdict(self.presets.update(updated))}
            return 404, {"error": "not_found"}
        except (KeyError, TypeError, ValueError) as exc:
            return 400, {"error": str(exc)}
