"""LLM provider + tier configuration - product scope B.10:

'LLM: provider-agnostic abstraction layer; use a cheaper/smaller model for
routine dialogue turns, a stronger model for clause interpretation and
report generation - research current pricing at build time, this changes
often.'

Provider defaults to Groq (a genuine free tier, no card required) rather
than Anthropic, per an explicit user request to avoid paid API costs during
development. Anthropic remains fully supported - set
FIRE_AGENT_LLM_PROVIDER=anthropic (+ ANTHROPIC_API_KEY) to switch, with no
code changes anywhere else, which is the entire point of the backend
abstraction in app/llm/backends/.

Everything here is read from the environment so a deployer never has to
edit code to change provider or model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

ModelTier = Literal["routine", "reasoning"]

# Groq model IDs current as of this build (see https://console.groq.com/docs/models -
# verify against that page, Groq's free-tier lineup changes over time).
_PROVIDER_DEFAULT_MODELS: dict[str, dict[ModelTier, str]] = {
    "groq": {"routine": "llama-3.1-8b-instant", "reasoning": "llama-3.3-70b-versatile"},
    "anthropic": {"routine": "claude-haiku-4-5", "reasoning": "claude-sonnet-5"},
}


@dataclass(frozen=True)
class LLMConfig:
    provider: str = field(default_factory=lambda: os.environ.get("FIRE_AGENT_LLM_PROVIDER", "groq"))
    _routine_override: str = field(
        default_factory=lambda: os.environ.get("FIRE_AGENT_ROUTINE_MODEL", "")
    )
    _reasoning_override: str = field(
        default_factory=lambda: os.environ.get("FIRE_AGENT_REASONING_MODEL", "")
    )

    def model_for(self, tier: ModelTier) -> str:
        override = self._routine_override if tier == "routine" else self._reasoning_override
        if override:
            return override
        defaults = _PROVIDER_DEFAULT_MODELS.get(self.provider)
        if defaults is None:
            raise ValueError(
                f"Unknown LLM provider '{self.provider}' - no default models registered. "
                f"Known providers: {list(_PROVIDER_DEFAULT_MODELS)}. Set "
                "FIRE_AGENT_ROUTINE_MODEL/FIRE_AGENT_REASONING_MODEL explicitly if you're "
                "adding a new provider's backend."
            )
        return defaults[tier]


DEFAULT_CONFIG = LLMConfig()
