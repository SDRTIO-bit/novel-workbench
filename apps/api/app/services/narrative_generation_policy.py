"""Compile narrative generation policies into Writer prompt instruction blocks.

Deterministic pure functions: the same policy always compiles to the same
instruction text and the same hashes.  GenerationService never sees the rule
content — the experiment runner passes the compiled block through the
existing generic ``_instruction_block`` / ``_instruction_hash`` override
channel, exactly like the (now frozen) narrative-route system did.

The two sections are independent: the permission section exists iff the
policy's permission is STRICT_LIMITED, the stop section iff stop is
STRICT_STOP.  The combined block is always permission-then-stop.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.narrative_generation_policy import (
    CompiledPolicyInstruction,
    NarrativeGenerationPolicy,
    NarrativePermissionPolicy,
    StopDisciplinePolicy,
)


# ── Instruction sections (verbatim experiment contracts) ─────────────
#
# Both are additive restrictions on top of the frozen DB writer prompt v6.
# They introduce no first person, no route modes, no Planner/WriterBrief
# schema changes, and no story-goal changes.

STRICT_LIMITED_INSTRUCTION = (
    "\n\n## 叙述权限（在既有规则之上追加的限制）\n"
    "本篇使用第三人称，并严格限定为单一视角人物（viewpoint_character）的限知叙述。\n"
    "一、全文只有视角人物可以出现内心、记忆、判断、感觉；不得切入第二个人物的内心或真实动机。\n"
    "二、正文只允许直接陈述：视角人物看见或听见的内容、其身体感受、其记忆、"
    "其判断猜测与误判，以及其能够确认的已发生事实。\n"
    "三、其他人物只能通过可见动作、可听语言、停顿、视线、姿势、物件操作，"
    "以及对现场状态的可见改变来呈现；不得把其他人物的心理、真实意图或正确解释作为事实宣布。\n"
    "四、视角人物无法确认时，正文必须保持不确定（他没听清、她分辨不出、他以为、她猜、"
    "看起来像、可能）；不得在下一句公布正确答案。\n"
    "五、禁止以下叙述功能：「他不知道的是……」「其实她早就……」「实际上对方只是……」；"
    "同时解释两个人物的真实心理；宣布所有旁观者共同感受到某种气氛；"
    "宣布人物关系已经发生变化；直接总结事件的主题或意义；"
    "用视角人物尚无法确认的信息纠正其判断。\n"
    "六、本限制不弱化 Planner 已确定的现场事实：要求发生的事件仍须实际发生；"
    "受限制的只是叙述者向读者释放信息的范围。"
)

STRICT_STOP_INSTRUCTION = (
    "\n\n## 停止纪律（在既有规则之上追加的限制）\n"
    "一、正文第一次出现满足 stop_state 的可见事实时，立即结束全文。\n"
    "二、该事实成立之后，不得再写：对刚才动作的解释；双方再次确认；"
    "人物心理变化的回顾；关系或意义总结；环境余韵；同一物件的再次描写；"
    "新的停顿或对视；「他没有走」「她也没有退开」一类第二确认；"
    "旁白对局面变化的宣布。\n"
    "三、允许停止在：一个物件被放回、一个人改变方向、一句话获得回应、"
    "一个请求被接受或拒绝、一项现场状态被改变、一个新限制变得可见。\n"
    "四、不得为满足字数继续生成；正文长度以实际停点为准。"
)


# ── Stable hashing ────────────────────────────────────────────────────


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_dict(data: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


# ── Section compilers ────────────────────────────────────────────────


def compile_permission_instruction(
    policy: NarrativeGenerationPolicy | NarrativePermissionPolicy,
) -> str:
    """The STRICT_LIMITED permission section, or "" for CURRENT."""
    permission = (
        policy.permission
        if isinstance(policy, NarrativeGenerationPolicy)
        else policy
    )
    if permission is NarrativePermissionPolicy.STRICT_LIMITED:
        return STRICT_LIMITED_INSTRUCTION
    return ""


def compile_stop_instruction(
    policy: NarrativeGenerationPolicy | StopDisciplinePolicy,
) -> str:
    """The STRICT_STOP discipline section, or "" for CURRENT."""
    stop = (
        policy.stop
        if isinstance(policy, NarrativeGenerationPolicy)
        else policy
    )
    if stop is StopDisciplinePolicy.STRICT_STOP:
        return STRICT_STOP_INSTRUCTION
    return ""


# ── Main entry point ──────────────────────────────────────────────────


def compile_generation_policy(policy: NarrativeGenerationPolicy) -> CompiledPolicyInstruction:
    """Compile one factorial cell into its Writer-prompt instruction block.

    The block is permission-section then stop-section, in fixed order; the
    CURRENT+CURRENT cell compiles to an empty block with ``None`` hashes.
    """
    permission_block = compile_permission_instruction(policy)
    stop_block = compile_stop_instruction(policy)
    block = permission_block + stop_block
    return CompiledPolicyInstruction(
        policy=policy,
        instruction_block=block,
        instruction_hash=_hash_text(block) if block else None,
        permission_instruction_hash=(
            _hash_text(permission_block) if permission_block else None
        ),
        stop_instruction_hash=(
            _hash_text(stop_block) if stop_block else None
        ),
        policy_hash=_hash_dict(policy.model_dump(mode="json")),
    )
