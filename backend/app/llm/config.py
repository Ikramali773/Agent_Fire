"""LLM tier configuration - product scope B.10:

'LLM: provider-agnostic abstraction layer; use a cheaper/smaller model for
routine dialogue turns, a stronger model for clause interpretation and report
generation - research current pricing at build time, this changes often.'

Defaults chosen for this build (2026 Anthropic pricing): Claude Haiku 4.5 for
routine dialogue (field extraction, intent classification - cheap, high
volume) and Claude Sonnet 5 for reasoning (Knowledge Q&A prose, report
narrative). This is a cost/quality tradeoff the product owner should confirm
- bump REASONING_MODEL to claude-opus-5 via env var if higher quality is
worth the ~2.5x cost for this workload.

Both are read from the environment so a deployer never has to edit code to
change models or point at a different Anthropic-compatible base URL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    routine_model: str = os.environ.get("FIRE_AGENT_ROUTINE_MODEL", "claude-haiku-4-5")
    reasoning_model: str = os.environ.get("FIRE_AGENT_REASONING_MODEL", "claude-sonnet-5")


DEFAULT_CONFIG = LLMConfig()
