"""Narrative permission / stop discipline generation policy schemas.

NARRATIVE_PERMISSION_STOPPING_FACTORIAL_V1 experiment contracts.

Two independent binary variables, injected as instruction blocks at the tail
of the Writer prompt through the existing generic ``_instruction_block``
override channel.  These schemas describe *what* the policy is; the compiler
in ``app.services.narrative_generation_policy`` decides *what the Writer is
told*.  Neither changes the Planner, the WriterBrief schema, or the frozen
DB prompt v6.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


POLICY_VERSION = "narrative-permission-stop-v1"


class NarrativePermissionPolicy(StrEnum):
    """Information-release permission of the narration (not what the Writer
    backstage knows — what the text may tell the reader)."""

    CURRENT = "CURRENT"
    STRICT_LIMITED = "STRICT_LIMITED"


class StopDisciplinePolicy(StrEnum):
    """Stop discipline: whether the text must end at the first visible fact
    satisfying stop_state."""

    CURRENT = "CURRENT"
    STRICT_STOP = "STRICT_STOP"


class NarrativeGenerationPolicy(BaseModel):
    """One cell of the 2x2 factorial design.  Immutable once constructed."""

    model_config = ConfigDict(frozen=True)

    permission: NarrativePermissionPolicy = NarrativePermissionPolicy.CURRENT
    stop: StopDisciplinePolicy = StopDisciplinePolicy.CURRENT
    policy_version: str = POLICY_VERSION


class CompiledPolicyInstruction(BaseModel):
    """The deterministic compilation product handed to the experiment runner.

    ``instruction_block`` is appended verbatim to the Writer prompt tail via
    the generic ``_instruction_block`` channel.  It is empty for the
    CURRENT+CURRENT group, which receives no policy instruction at all.
    Hashes are sha256 hex digests; ``None`` when the corresponding block is
    empty, so a missing hash can never be mistaken for a real one.
    """

    model_config = ConfigDict(extra="forbid")

    policy: NarrativeGenerationPolicy
    instruction_block: str
    instruction_hash: str | None = Field(default=None, min_length=64, max_length=64)
    permission_instruction_hash: str | None = Field(default=None, min_length=64, max_length=64)
    stop_instruction_hash: str | None = Field(default=None, min_length=64, max_length=64)
    policy_hash: str = Field(min_length=64, max_length=64)
