from app.tgbreak.models import CoreProfile, ImportedPreset


# These identifiers come from the audited local preset. Names are intentionally
# absent from the persisted profile so renamed or duplicated labels do not alter
# an existing user's switches.
CORE_ENABLED_IDENTIFIERS = {
    "5fde60e9-5a2d-4105-8123-39b5266cf7a8",  # COT Chinese head
    "d9e9a9f2-aeab-466b-9ec3-60929d6d13ed",  # basic thinking
    "6505cfc4-07b7-4479-95cc-96ba600a1779",  # anti-omniscience (first)
    "4a976cf4-1650-4f89-934e-5074d3397785",  # anti-omniscience (second)
    "13876bd9-3354-487b-96b8-72455c7bf7e9",  # personality reshaping
    "0b635214-1e8e-448f-a81b-f13fde6642fa",  # COT ending
    "e986219b-f8ca-4645-8c53-3b53bb5c0393",  # format stabilizer
    "4a66903a-d4cc-4764-b9db-8930a35c63a7",  # assistant tail
    "chatHistory",  # Chat History marker
    "74ef906f-026a-42ca-a843-dbbe8c03b7fb",  # medium word-count module
    "fefd1cdf-2f88-43b3-a9d5-f2cc0c007d8f",  # general writing-style module
    "66a00901-29fe-4324-8170-c36a1879baca",  # metaphor optimization
}

CORE_DISABLED_IDENTIFIERS = {
    "0a52ffaf-6924-4dfd-8627-b169bbfab627",  # alternate Japanese light-novel style
    "f57ada5f-4999-426b-b260-f9c0aa0b9ead",  # W2G action options
    "c88d5afd-a53e-4551-bc32-c4238a6a70b9",  # catsay
    "8f08aead-45e9-4243-8e7c-0fe35650b0fd",  # CEstuff
    "4e3334f8-2e70-49c0-821b-a287589976d2",  # summary
    "7f8e2f80-df37-4c2d-9709-0e2a70aca440",  # time and place
    "5799c512-a207-4a07-b4a8-07ab8cb7c3d2",  # variable card updates
    "4daea251-b2a0-4047-b54c-93d744e500fd",  # NSFW variation
    "6d06ac3b-dd8d-437f-9ebf-b918a5b6d098",  # large summary assistant
}


def build_tgbreak_core_profile(preset: ImportedPreset) -> CoreProfile:
    present = {entry.identifier for entry in preset.entries}
    overrides: dict[str, dict[str, bool]] = {}
    for identifier in CORE_ENABLED_IDENTIFIERS:
        if identifier in present:
            overrides[identifier] = {"enabled": True}
    for identifier in CORE_DISABLED_IDENTIFIERS:
        if identifier in present:
            overrides[identifier] = {"enabled": False}
    return CoreProfile(
        source_preset_id=preset.preset_id,
        source_sha256=preset.source_sha256,
        entry_overrides=overrides,
    )
