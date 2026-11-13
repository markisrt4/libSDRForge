# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Standalone RDS receiver chain, independent of FM audio playback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np

from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.protocols.rds.rds_biphase_decoder import RdsBiphaseDecoder
from sdrforge.protocols.rds.rds_block_sync import RdsBlockSynchronizer, RdsGroup
from sdrforge.protocols.rds.rds_carrier_recovery import RdsCarrierRecovery
from sdrforge.protocols.rds.rds_metadata_decoder import RdsMetadata, RdsMetadataDecoder
from sdrforge.protocols.rds.rds_persistent_sync import RdsPersistentSynchronizer
from sdrforge.protocols.rds.rds_subcarrier_extractor import RdsSubcarrierExtractor
from sdrforge.protocols.rds.rds_symbol_timing_recovery import RdsSymbolTimingRecovery
from sdrforge.protocols.rds.rds_soft_confirmation import RdsSoftConfirmation, ConfirmedRdsFragment, ExperimentalRadioText


@dataclass(frozen=True)
class RdsReceiverStatus:
    metadata: RdsMetadata
    groups_found: int
    invalid_pairs: int
    carrier_offset_hz: float
    half_bit_samples_per_symbol: float
    locked_pair_phase: int | None
    phase_groups_found: tuple[int, int]
    sync_confidence: int
    selected_invalid_pairs: int
    selected_total_pairs: int
    selected_invalid_pair_fraction: float | None
    selected_recent_invalid_pair_fraction: float | None
    selected_recent_pair_count: int
    phase_recent_invalid_pair_fraction: tuple[float | None, float | None]
    rds_baseband_rms: float
    rds_band_excess_db: float | None
    persistent_sync_enabled: bool = False
    clean_blocks: int = 0
    missing_blocks: int = 0
    partial_groups: int = 0
    loss_events: int = 0
    phase_framing_diagnostics: tuple[dict[str, Any], dict[str, Any]] | None = None


class RdsReceiverController:
    """Process 240 kSPS FM multiplex (or channelized IQ) into RDS groups.

    In automatic mode both half-bit pair phases run independently. The first
    CRC-validated group acquires lock; the alternate phase stays active so
    the receiver can reacquire after a sustained lack of valid groups.
    Real-world RDS BER remains a future validation gate.
    Use process_multiplex when another consumer already demodulates FM to
    avoid duplicating the FM discriminator.
    """

    def __init__(self, *, pair_phase: int | None = None,
                 loss_timeout_bits: int = 2080,
                 ps_repetitions: int = 2,
                 persistent_sync: bool = False,
                 experimental_soft_pairs: bool = False) -> None:
        if pair_phase not in (None, 0, 1):
            raise ValueError('pair_phase must be None, 0 or 1')
        if loss_timeout_bits < 104:
            raise ValueError('loss_timeout_bits must be at least 104')
        self._persistent_sync_enabled = bool(persistent_sync)
        self._pair_phase = pair_phase
        self._experimental_soft_pairs = bool(experimental_soft_pairs)
        self._loss_timeout_bits = loss_timeout_bits
        self._fm = FmMultiplexDiscriminator()
        self._extractor = RdsSubcarrierExtractor()
        self._carrier = RdsCarrierRecovery()
        self._timing = RdsSymbolTimingRecovery(symbol_rate_hz=2375.0)
        self._biphases = [RdsBiphaseDecoder(pair_phase=i) for i in (0, 1)]
        self._block_candidates: list[RdsPersistentSynchronizer | RdsBlockSynchronizer] = ([RdsPersistentSynchronizer() for _ in (0, 1)]
                                  if persistent_sync else
                                  [RdsBlockSynchronizer() for _ in (0, 1)])
        # Isolated diagnostic path; never feeds trusted metadata or TMC.
        self._soft_biphases = ([RdsBiphaseDecoder(pair_phase=i, experimental_soft_pairs=True)
                                for i in (0, 1)] if experimental_soft_pairs else [])
        self._soft_blocks = ([RdsBlockSynchronizer() for _ in (0, 1)]
                             if experimental_soft_pairs else [])
        self._soft_last_groups: list[RdsGroup] = []
        self._soft_confirmers = ([RdsSoftConfirmation() for _ in (0, 1)]
                                 if experimental_soft_pairs else [])
        self._soft_confirmed: list[ConfirmedRdsFragment] = []
        self._biphase = self._biphases[pair_phase or 0]
        self._blocks = self._block_candidates[pair_phase or 0]
        self._locked_pair_phase = pair_phase
        self._bits_since_group = 0
        self._metadata = RdsMetadataDecoder(ps_repetitions=ps_repetitions)
        self._sync_confidence = 0
        self._rds_baseband_rms = 0.0
        self._rds_band_excess_db: float | None = None
        self._diagnostic_blocks = 0

    def reset(self, *, preserve_metadata: bool = False) -> None:
        self._fm.reset()
        self._extractor.reset()
        self._carrier.reset()
        self._timing.reset()
        for stage in self._biphases:
            stage.reset()
        for stage in self._soft_biphases:
            stage.reset()
        for stage in self._soft_blocks:
            stage.reset()
        self._soft_last_groups = []
        self._soft_confirmed = []
        for confirmer in self._soft_confirmers:
            confirmer.reset()
        for block_synchronizer in self._block_candidates:
            block_synchronizer.reset()
        if preserve_metadata:
            self._metadata.lose_sync()
        else:
            self._metadata.reset()
        self._locked_pair_phase = self._pair_phase
        self._bits_since_group = 0
        self._sync_confidence = 0

    def _persistent_candidates(self) -> tuple[RdsPersistentSynchronizer, RdsPersistentSynchronizer]:
        return (
            cast(RdsPersistentSynchronizer, self._block_candidates[0]),
            cast(RdsPersistentSynchronizer, self._block_candidates[1]),
        )

    def _framing_diagnostics(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not self._persistent_sync_enabled:
            return None

        def describe(stage: RdsPersistentSynchronizer) -> dict[str, Any]:
            return {
                "locked": stage.locked,
                "last_alignment": stage.last_alignment,
                "last_pi": f"0x{stage.last_pi:04X}" if stage.last_pi is not None else None,
                "acquisitions": list(stage.acquisition_events),
                "loss_positions": list(stage.loss_positions),
                "aligned_blocks": dict(stage.aligned_block_counts),
                "partial_groups": stage.partial_groups,
                "clean_blocks": stage.clean_blocks,
                "missing_blocks": stage.missing_blocks,
            }

        first, second = self._persistent_candidates()
        return describe(first), describe(second)

    @property
    def status(self) -> RdsReceiverStatus:
        return RdsReceiverStatus(
            metadata=self._metadata.metadata,
            groups_found=self._blocks.groups_found if self._locked_pair_phase is not None else 0,
            invalid_pairs=sum(stage.invalid_pairs for stage in self._biphases) if self._pair_phase is None else self._biphase.invalid_pairs,
            carrier_offset_hz=self._carrier.frequency_offset_hz,
            half_bit_samples_per_symbol=self._timing.samples_per_symbol,
            locked_pair_phase=self._locked_pair_phase,
            phase_groups_found=(self._block_candidates[0].groups_found,
                                self._block_candidates[1].groups_found),
            sync_confidence=(cast(RdsPersistentSynchronizer, self._blocks).sync_confidence if self._persistent_sync_enabled
                             and self._locked_pair_phase is not None else self._sync_confidence),
            selected_invalid_pairs=(self._biphases[self._locked_pair_phase].invalid_pairs
                                    if self._locked_pair_phase is not None else 0),
            selected_total_pairs=(self._biphases[self._locked_pair_phase].total_pairs
                                 if self._locked_pair_phase is not None else 0),
            selected_invalid_pair_fraction=(
                self._biphases[self._locked_pair_phase].invalid_pairs /
                self._biphases[self._locked_pair_phase].total_pairs
                if self._locked_pair_phase is not None and
                self._biphases[self._locked_pair_phase].total_pairs else None),
            selected_recent_invalid_pair_fraction=(
                self._biphases[self._locked_pair_phase].recent_invalid_pair_fraction
                if self._locked_pair_phase is not None else None),
            phase_recent_invalid_pair_fraction=(self._biphases[0].recent_invalid_pair_fraction,
                                                self._biphases[1].recent_invalid_pair_fraction),
            rds_baseband_rms=self._rds_baseband_rms,
            rds_band_excess_db=self._rds_band_excess_db,
            persistent_sync_enabled=self._persistent_sync_enabled,
            clean_blocks=getattr(self._blocks, 'clean_blocks', 0),
            missing_blocks=getattr(self._blocks, 'missing_blocks', 0),
            partial_groups=getattr(self._blocks, 'partial_groups', 0),
            loss_events=getattr(self._blocks, 'loss_events', 0),
            phase_framing_diagnostics=self._framing_diagnostics(),
            selected_recent_pair_count=(
                self._biphases[self._locked_pair_phase].recent_pair_count
                if self._locked_pair_phase is not None else 0),
        )

    def process_iq(self, iq: np.ndarray) -> list[RdsGroup]:
        """Accept complex FM channel IQ sampled at 240 kSPS."""
        return self.process_multiplex(self._fm.process(iq))

    def process_multiplex(self, multiplex: np.ndarray) -> list[RdsGroup]:
        """Accept real FM multiplex sampled at 240 kSPS."""
        # Periodic spectrum check, kept off the audio-critical path on most blocks.
        # This is an RDS-band energy contrast, not a calibrated SNR or proof of RDS.
        self._diagnostic_blocks += 1
        if self._diagnostic_blocks % 10 == 1 and len(multiplex) >= 8192:
            segment = np.asarray(multiplex[:8192], dtype=np.float64)
            spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment)))) ** 2
            frequencies = np.fft.rfftfreq(len(segment), 1 / 240_000)
            target = (frequencies >= 55_000) & (frequencies <= 59_000)
            reference = ((frequencies >= 49_000) & (frequencies <= 53_000)) | (
                (frequencies >= 62_000) & (frequencies <= 66_000))
            target_power = float(np.mean(spectrum[target]))
            reference_power = float(np.mean(spectrum[reference]))
            self._rds_band_excess_db = float(10 * np.log10(
                max(target_power, 1e-20) / max(reference_power, 1e-20)))
        baseband = self._extractor.process(multiplex)
        if len(baseband):
            self._rds_baseband_rms = float(np.sqrt(np.mean(np.abs(baseband.astype(np.complex128)) ** 2)))
        corrected = self._carrier.process(baseband)
        halves = self._timing.process(corrected)
        return self.process_half_bits(halves)

    @property
    def experimental_soft_last_groups(self) -> tuple[RdsGroup, ...]:
        """Speculative groups from the last chunk, not trusted metadata."""
        return tuple(self._soft_last_groups)

    @property
    def experimental_radio_text(self) -> tuple[ExperimentalRadioText, ...]:
        """Per-phase provisional previews; never trusted station metadata."""
        return tuple(confirmer.radio_text for confirmer in self._soft_confirmers)

    @property
    def experimental_confirmed_fragments(self) -> tuple[ConfirmedRdsFragment, ...]:
        """Newly corroborated experimental fragments, never trusted metadata."""
        return tuple(self._soft_confirmed)

    def process_half_bits(self, halves: np.ndarray) -> list[RdsGroup]:
        """Feed recovered half-bit symbols, including for hardware-free tests."""
        candidates = []
        self._soft_last_groups = []
        self._soft_confirmed = []
        phases = (self._pair_phase,) if self._pair_phase is not None else (0, 1)
        for phase in phases:
            bits, valid = self._biphases[phase].process(halves)
            groups = self._block_candidates[phase].process(bits, valid)
            candidates.append((phase, len(bits), groups))
            if self._experimental_soft_pairs:
                soft_bits, soft_valid = self._soft_biphases[phase].process(halves)
                speculative = self._soft_blocks[phase].process(
                    soft_bits, soft_valid,
                    self._soft_biphases[phase].last_uncertain_mask)
                self._soft_last_groups.extend(speculative)
                for candidate in speculative:
                    if candidate.start_bit is None:
                        continue
                    confirmed = self._soft_confirmers[phase].observe(
                        candidate, start_bit=candidate.start_bit,
                        uncertain_bits=candidate.uncertain_bits)
                    if confirmed is not None:
                        self._soft_confirmed.append(confirmed)
        if self._pair_phase is None:
            current = next((item for item in candidates
                            if item[0] == self._locked_pair_phase), None)
            if current is not None and self._persistent_sync_enabled and not cast(RdsPersistentSynchronizer, self._block_candidates[current[0]]).locked:
                self._locked_pair_phase = None
                self._metadata.lose_sync()
                current = None
            if current is not None and current[2]:
                self._bits_since_group = 0
                self._sync_confidence = min(10, self._sync_confidence + len(current[2]))
            elif self._locked_pair_phase is not None and not self._persistent_sync_enabled:
                self._bits_since_group += current[1] if current else 0
                if self._bits_since_group >= self._loss_timeout_bits:
                    self._sync_confidence = max(0, self._sync_confidence - 1)
                    self._bits_since_group = 0
                    if self._sync_confidence == 0:
                        self._locked_pair_phase = None
                        self._metadata.lose_sync()
            if self._locked_pair_phase is None:
                winners = ([item for item in candidates if cast(RdsPersistentSynchronizer, self._block_candidates[item[0]]).locked]
                           if self._persistent_sync_enabled else
                           [item for item in candidates if item[2]])
                if winners:
                    winner = max(winners, key=lambda item: len(item[2]))
                    self._locked_pair_phase = winner[0]
                    self._biphase = self._biphases[winner[0]]
                    self._blocks = self._block_candidates[winner[0]]
                    self._bits_since_group = 0
                    self._sync_confidence = max(1, min(10, len(winner[2])))
        selected = next((groups for phase, _, groups in candidates
                         if phase == self._locked_pair_phase), [])
        for group in selected:
            self._metadata.process(group)
        return selected
