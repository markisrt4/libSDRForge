# SPDX-License-Identifier: MIT
"""Opt-in regional catalog overlay, independent of any particular host app."""
from __future__ import annotations

from pathlib import Path

from sdrforge.adapters.factory_radio_catalog import load_factory_radio_catalog
from sdrforge.adapters.orc_radio_import import import_orc_radio_data
from sdrforge.controllers.radio_catalog import RadioCatalog
from sdrforge.interfaces.radio_catalog_if import RadioPreset


def load_radio_catalog(
    *, radio_root: Path | None = None, locale: str | None = None,
) -> tuple[RadioCatalog, tuple[RadioPreset, ...]]:
    """Combine packaged profiles with an optional external regional catalog.

    External profiles override matching packaged profiles and their factory
    presets. Profiles absent from the external catalog remain available.
    User presets are deliberately not imported or modified.
    """
    catalog, factory = load_factory_radio_catalog()
    if radio_root is None:
        if locale is not None:
            raise ValueError("radio_root is required when locale is specified")
        return catalog, factory
    imported = import_orc_radio_data(Path(radio_root), locale=locale)
    external = {profile.key: profile for profile in imported.catalog.profiles()}
    profiles = {profile.key: profile for profile in catalog.profiles()}
    profiles.update(external)
    presets = tuple(p for p in factory if p.profile_key not in external)
    presets += imported.factory_presets
    return RadioCatalog(tuple(profiles[key] for key in sorted(profiles))), presets
