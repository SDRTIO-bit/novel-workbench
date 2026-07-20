"""Contract tests for the narrative generation policy compiler.

NARRATIVE_PERMISSION_STOPPING_FACTORIAL_V1: two independent binary variables
(permission x stop) compiled into Writer prompt instruction blocks.
These tests import modules that do not exist yet (Phase 1, tests first).
"""
from app.schemas.narrative_generation_policy import (
    POLICY_VERSION,
    NarrativeGenerationPolicy,
    NarrativePermissionPolicy,
    StopDisciplinePolicy,
)
from app.services.narrative_generation_policy import (
    compile_generation_policy,
    compile_permission_instruction,
    compile_stop_instruction,
)

CURRENT = NarrativePermissionPolicy.CURRENT
LIMITED = NarrativePermissionPolicy.STRICT_LIMITED
STOP_CURRENT = StopDisciplinePolicy.CURRENT
STOP_STRICT = StopDisciplinePolicy.STRICT_STOP


def _policy(permission, stop):
    return NarrativeGenerationPolicy(permission=permission, stop=stop)


def test_group_a_compiles_to_empty_instruction_block():
    compiled = compile_generation_policy(_policy(CURRENT, STOP_CURRENT))
    assert compiled.instruction_block == ""
    assert compiled.instruction_hash is None
    assert compiled.permission_instruction_hash is None
    assert compiled.stop_instruction_hash is None


def test_b_and_c_compile_independent_single_sections():
    b = compile_generation_policy(_policy(LIMITED, STOP_CURRENT))
    c = compile_generation_policy(_policy(CURRENT, STOP_STRICT))
    assert b.instruction_block != ""
    assert c.instruction_block != ""
    assert b.instruction_block != c.instruction_block
    assert b.permission_instruction_hash is not None
    assert b.stop_instruction_hash is None
    assert c.permission_instruction_hash is None
    assert c.stop_instruction_hash is not None


def test_d_is_permission_section_then_stop_section_in_fixed_order():
    b = compile_generation_policy(_policy(LIMITED, STOP_CURRENT))
    c = compile_generation_policy(_policy(CURRENT, STOP_STRICT))
    d = compile_generation_policy(_policy(LIMITED, STOP_STRICT))
    assert d.instruction_block == b.instruction_block + c.instruction_block


def test_section_compilers_accept_enum_directly():
    assert compile_permission_instruction(LIMITED) != ""
    assert compile_permission_instruction(CURRENT) == ""
    assert compile_stop_instruction(STOP_STRICT) != ""
    assert compile_stop_instruction(STOP_CURRENT) == ""


def test_compilation_is_deterministic():
    one = compile_generation_policy(_policy(LIMITED, STOP_STRICT))
    two = compile_generation_policy(_policy(LIMITED, STOP_STRICT))
    assert one.instruction_block == two.instruction_block
    assert one.instruction_hash == two.instruction_hash
    assert one.permission_instruction_hash == two.permission_instruction_hash
    assert one.stop_instruction_hash == two.stop_instruction_hash
    assert one.policy_hash == two.policy_hash


def test_hashes_are_sha256_hex_and_distinct_per_group():
    compiled = {
        group: compile_generation_policy(policy)
        for group, policy in (
            ("A", _policy(CURRENT, STOP_CURRENT)),
            ("B", _policy(LIMITED, STOP_CURRENT)),
            ("C", _policy(CURRENT, STOP_STRICT)),
            ("D", _policy(LIMITED, STOP_STRICT)),
        )
    }
    for group in ("B", "C", "D"):
        h = compiled[group].instruction_hash
        assert isinstance(h, str) and len(h) == 64
        int(h, 16)
    hashes = {compiled[g].instruction_hash for g in ("B", "C", "D")}
    assert len(hashes) == 3
    for group in ("A", "B", "C", "D"):
        ph = compiled[group].policy_hash
        assert isinstance(ph, str) and len(ph) == 64
        int(ph, 16)


def test_policy_version_is_pinned():
    assert POLICY_VERSION == "narrative-permission-stop-v1"
    assert _policy(CURRENT, STOP_CURRENT).policy_version == POLICY_VERSION


def test_instruction_text_invariants():
    b = compile_generation_policy(_policy(LIMITED, STOP_CURRENT))
    c = compile_generation_policy(_policy(CURRENT, STOP_STRICT))
    combined = b.instruction_block + c.instruction_block
    # No first person, no frozen route-system keywords, no pronoun experiment drift
    for banned in (
        "第一人称",
        "A-lite", "A_LITE",
        "C Object", "C_OBJECT",
        "narrative_route", "NARRATIVE_ROUTE",
        "WriterBrief",
    ):
        assert banned not in combined
    # Third-person lock present in the permission section (anti-drift, all
    # groups remain third person; this experiment never introduces 我/他 shifts)
    assert "第三人称" in b.instruction_block
    # Boundary with the frozen v6 section-4 rule must be explicit: planned
    # facts are not weakened; only unconfirmable information stays uncertain
    assert "Planner" in b.instruction_block
    # Additive semantics: restrictions sit on top of the existing rules
    assert "追加" in combined
    # Strict stop names the first-satisfaction discipline
    assert "第一次" in c.instruction_block


def test_policy_dict_serialization_hash_is_stable():
    one = compile_generation_policy(_policy(STOP_STRICT and LIMITED or LIMITED, STOP_STRICT))
    two = compile_generation_policy(
        NarrativeGenerationPolicy.model_validate(
            one.policy.model_dump(mode="json")
        )
    )
    assert one.policy_hash == two.policy_hash
