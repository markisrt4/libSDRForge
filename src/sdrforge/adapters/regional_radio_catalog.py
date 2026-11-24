# SPDX-License-Identifier: MIT
"""Opt-in regional catalog overlay, independent of any particular host app."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from sdrforge.adapters.factory_radio_catalog import load_factory_radio_catalog
from sdrforge.adapters.orc_radio_import import ImportedRadioData, import_orc_radio_data
from sdrforge.controllers.radio_catalog import RadioCatalog
from sdrforge.interfaces.radio_catalog_if import RadioPreset


def _overlay(
    catalog: RadioCatalog,
    factory: tuple[RadioPreset, ...],
    imported: ImportedRadioData,
) -> tuple[RadioCatalog, tuple[RadioPreset, ...]]:
    external = {profile.key: profile for profile in imported.catalog.profiles()}
    profiles = {profile.key: profile for profile in catalog.profiles()}
    profiles.update(external)
    presets = tuple(p for p in factory if p.profile_key not in external)
    presets += imported.factory_presets
    return RadioCatalog(tuple(profiles[key] for key in sorted(profiles))), presets


def load_radio_catalog(
    *, radio_root: Path | None = None, locale: str | None = None
) -> tuple[RadioCatalog, tuple[RadioPreset, ...]]:
    """Load factory defaults, packaged region, then optional external overrides.

    User presets are deliberately not imported or modified.
    """
    catalog, factory = load_factory_radio_catalog()
    if locale is not None:
        if not locale or Path(locale).name != locale or locale in {".", ".."}:
            raise ValueError("locale must be a single directory name")
        root = Path(str(files("sdrforge").joinpath("data/regions")))
        if (root / locale).is_dir():
            catalog, factory = _overlay(
                catalog, factory, import_orc_radio_data(root, locale=locale)
            )
        elif radio_root is None:
            raise ValueError(f"Unknown packaged locale {locale}; radio_root required")
    if radio_root is not None:
        catalog, factory = _overlay(
            catalog, factory, import_orc_radio_data(radio_root, locale=locale)
        )
    return catalog, factory
