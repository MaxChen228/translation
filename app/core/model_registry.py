"""Central registry for Gemini model metadata and helpers.

This module consolidates canonical model ids, friendly aliases, and pricing
information so other parts of the backend no longer need to maintain their own
hard-coded allow-lists.  Later steps can extend the registry with model-specific
config defaults or deprecation flags.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple


@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing a single Gemini model option."""

    canonical_name: str
    aliases: Tuple[str, ...] = ()
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
    deprecated: bool = False

    @property
    def name(self) -> str:
        """Return the canonical identifier used for bookkeeping."""
        return self.canonical_name

    def all_names(self) -> Tuple[str, ...]:
        """Return every identifier that should resolve to this model."""
        if not self.aliases:
            return (self.canonical_name,)
        return (self.canonical_name, *self.aliases)


@dataclass(frozen=True)
class ResolvedModel:
    """A resolved model capturing both the request string and registry entry."""

    request_name: str
    info: ModelInfo

    @property
    def name(self) -> str:
        """Return the identifier that should be sent to the LLM provider."""
        return self.request_name

    @property
    def canonical_name(self) -> str:
        return self.info.canonical_name


# Pricing numbers sourced from Google Gemini public pricing (2025-02).
_MODEL_REGISTRY: Dict[str, ModelInfo] = {
    "gemini-2.5-flash": ModelInfo(
        canonical_name="gemini-2.5-flash",
        aliases=(
            "gemini-flash-latest",
            "gemini-2.5-flash-preview-09-2025",
            "gemini-default",
            "gemini-alt",
        ),
        input_price_per_million=0.30,
        output_price_per_million=2.50,
    ),
    "gemini-2.5-flash-lite": ModelInfo(
        canonical_name="gemini-2.5-flash-lite",
        aliases=(
            "gemini-flash-lite-latest",
            "gemini-2.5-flash-lite-preview-09-2025",
        ),
        input_price_per_million=0.10,
        output_price_per_million=0.40,
    ),
    "gemini-2.5-pro": ModelInfo(
        canonical_name="gemini-2.5-pro",
        input_price_per_million=1.25,
        output_price_per_million=10.00,
    ),
    "alpha": ModelInfo(
        canonical_name="alpha",
        input_price_per_million=None,
        output_price_per_million=None,
        deprecated=True,
    ),
    "beta": ModelInfo(
        canonical_name="beta",
        input_price_per_million=None,
        output_price_per_million=None,
        deprecated=True,
    ),
}

_DEFAULT_MODEL = "gemini-2.5-flash-preview-09-2025"

# Build a reverse lookup for aliases so we can resolve quickly.
_ALIAS_INDEX: Dict[str, str] = {}
for info in _MODEL_REGISTRY.values():
    for name in info.all_names():
        _ALIAS_INDEX[name] = info.canonical_name


def allowed_model_names(include_deprecated: bool = False) -> Iterable[str]:
    """Yield all known model identifiers, aliases included."""
    for info in _MODEL_REGISTRY.values():
        if info.deprecated and not include_deprecated:
            continue
        for name in info.all_names():
            yield name


def default_model() -> str:
    """Return the default model identifier for the backend."""
    return _DEFAULT_MODEL


def get_model_info(name: str) -> Optional[ModelInfo]:
    """Return registry metadata for the provided model/alias name."""
    normalized = (name or "").strip()
    if not normalized:
        return None
    canonical = _ALIAS_INDEX.get(normalized)
    if canonical is None:
        return None
    return _MODEL_REGISTRY.get(canonical)


def _error_payload(invalid: str) -> str:
    return json.dumps(
        {
            "invalid_model": invalid,
            "allowed": sorted(allowed_model_names(include_deprecated=True)),
        },
        ensure_ascii=False,
    )


def resolve_model_name(name: str, *, include_deprecated: bool = False) -> ResolvedModel:
    """Resolve a model identifier or alias to a registry entry.

    Raises ValueError with a structured payload if the model is unknown.
    """
    normalized = (name or "").strip()
    if not normalized:
        raise ValueError(_error_payload(normalized))

    info = get_model_info(normalized)
    if info is None:
        raise ValueError(_error_payload(normalized))
    if info.deprecated and not include_deprecated:
        raise ValueError(_error_payload(normalized))
    return ResolvedModel(request_name=normalized, info=info)


def pricing_for_model(name: str) -> Tuple[float, float]:
    """Return input/output USD pricing for the given model if known."""
    info = get_model_info(name)
    if info is None:
        return (0.0, 0.0)
    return (
        float(info.input_price_per_million or 0.0),
        float(info.output_price_per_million or 0.0),
    )


def allowed_models(custom_allowlist: Optional[Iterable[str]] = None) -> set[str]:
    """Return the set of allowed model identifiers.

    When a custom allow-list is supplied (e.g. from configuration), we intersect
    it with the registry so that typos or unknown models are filtered out early.
    """
    if custom_allowlist is None:
        return set(allowed_model_names())

    allowed: set[str] = set()
    for name in custom_allowlist:
        info = get_model_info(name)
        if info is None:
            continue
        allowed.update(info.all_names())
    return allowed
