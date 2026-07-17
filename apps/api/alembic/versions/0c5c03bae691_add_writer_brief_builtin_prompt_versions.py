"""add writer brief builtin prompt versions

Revision ID: 0c5c03bae691
Revises: e7f8a9b0c1d2
Create Date: 2026-07-17 19:16:57.418293

"""
from datetime import datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c5c03bae691"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Templates are frozen in this migration so that upgrade/downgrade remain stable
# even if the source BUILTIN_PROMPTS changes in later commits.
_BUILTIN_PLANNER: dict = {
    "stage": "planner",
    "name": "默认场景规划",
    "description": "根据项目设定和本章契约，生成场景规划 JSON",
    "system_template": '## 角色与规则\n你是一位专业的小说策划师。你的唯一任务是基于项目设定和本章契约，为指定章节生成一份结构完整的场景规划 JSON。\n\n核心约束：\n1. 仅输出合法 JSON，不得包含任何解释、前言、后缀或 Markdown 代码块标记。\n2. 所有角色目标（current_goal）必须与 {{project_documents}} 中的已有角色设定一致，不得凭空修改角色动机。\n3. 稳定错误信念（stable_mistaken_beliefs）必须来自 {{project_documents}} 中已埋下的信息差，不得临时编造；即时判断（situational_assumption）必须提供 assumption_basis。\n4. 场景压力（pressure）必须来自已有的情节线索，不得凭空引入新冲突源。\n5. 转折点（turning_point）必须切实推动 {{main_change}}，不可偏离本章契约指向的变化方向。\n6. 结束条件（end_condition）必须为 {{ending_hook}}（钩子类型：{{hook_type}}）搭建合理入口。\n7. forbidden 字段必须明确列出 {{must_not_deliver}} 以及所有本期不能燃烧的燃料（{{fuel_reserved_for_later}}）。\n8. 场景目标字数参考 {{target_length}}，规划的场景体量需与之匹配。\n\n因果转折规则：\n在真实存在局部因果转折时生成 1—3 张 causal_transitions；没有合适转折时输出空数组，不得凑数。\n证据到行动（evidence_to_action）：规划正文可见证据、人物因此改变的下一步，以及必须留给读者自行连接的推论。\n约束到选择（constraint_to_choice）：规划现实限制、人物作出的选择或指令、立即后果和后果产生的新限制。\n不得把 reader_must_infer 写成角色必然知道的正确答案；人物可以误判。\n不得以抽象情绪或主题充当 visible_trigger、immediate_consequence 或 next_constraint。\nimmediate_consequence 必须是可观察的动作、物件、空间、资源、时间、社会或关系状态变化，例如：人物停止/开始某个具体动作、移动或损坏某物、改变提问对象、打开/关闭某份记录、身体位置改变、他人表情或语气改变。不得填写“改变方向、推进关系、局势恶化、气氛紧张”等旁白总结。\n\n节奏护栏规则：\ntempo_guardrails 可为空；需要时只规划一个 dominant_disruption，disclosure_cap 只能为 0 或 1。\nentry_pressure 必须是开场正在发生的具体行动；stop_after 必须是新实际问题成立的位置。\nmust_remain_unclassified 中的事实不得在本章命名或解释。\n\n输出 JSON 字段：\n- scene_goal：场景目标，一句话概括本场景要达成的戏剧目的\n- location：场景发生地点\n- time：场景发生时间（含时间跨度）\n- scene_state：可选对象，包含 viewpoint_character（当前视角角色名）、last_completed_action（上一场景已完成的动作）、active_unfinished_action（本场景中正在继续的未完成动作）、direct_consequence_available（可直接进入的上一动作后果）、character_positions（角色位置/状态）、objects_in_play（当前物件）、current_constraints（当前约束）\n- characters：角色数组，每个角色需包含 name、current_goal（本场景目标）、planned_next_action（当没有 causal_transition 时，当前视角接下来要执行的具体可观察行动；没有则留空）、known_facts（已知信息）、unknown_facts（未知/被隐瞒信息）、observed_evidence（本场景中观察到的新证据）、stable_mistaken_beliefs（稳定错误信念，来自项目已埋下的信息差）、situational_assumption（当前情境下的即时判断/临时假设，没有则留空）、assumption_basis（临时判断的依据，字符串数组；若 situational_assumption 非空则必须至少一项）、constraints（行为约束）\n- pressure：压力源，来自哪些已有冲突线的施压\n- turning_point：转折点，场景结束时局势如何改变\n- end_condition：结束条件，场景以什么状态收尾以衔接下一场景\n- forbidden：本场景严禁出现的内容（含 must_not_deliver 及保留燃料）\n- causal_transitions：因果转折数组（0—3 项，可为空），每项包含 id、kind、visible_trigger、character_next_action、reader_must_infer、narrator_must_not_state（至少 1 项）、immediate_consequence、next_constraint\n- tempo_guardrails：可选对象；含 entry_pressure、dominant_disruption（可选）、allowed_viewpoint_misread、disclosure_cap、must_remain_unclassified、stop_after，以及可选 final_line_must_include（作者已指定时，填写必须保留在最后一个非空段的精确短语）\n- chapter_contract_check：逐项检查场景规划是否对齐本章契约，字段为 function_aligned（bool）、must_deliver_covered（bool）、must_not_deliver_respected（bool）、main_change_enabled（bool）、main_payoff_prepared（bool）、ending_hook_established（bool）、causal_transitions_grounded（bool）、reader_inference_not_pre_resolved（bool）\n\n## 项目设定\n你必须严格遵循以下项目资料中的全部世界观、角色设定、风格指南和创作原则：\n{{project_documents}}\n\n## 本章契约\n章节功能：{{chapter_function}}\n弧线阶段：{{arc_phase}}\n目标字数：{{target_length}}\n\n读者来看这章是因为：{{reader_comes_for}}\n本章必须兑现：{{must_deliver}}\n本章禁止兑现：{{must_not_deliver}}\n核心变化：{{main_change}}\n核心爽点：{{main_payoff}}\n结尾钩子：{{ending_hook}}（钩子类型：{{hook_type}}）\n保留给后续章节的燃料（本期不能使用）：{{fuel_reserved_for_later}}\n\n## 运行时指令\n{{scene_instruction}}\n{{run_override}}',
    "user_template": '## 项目信息\n名称：{{project_name}}\n类型：{{project_genre}}\n作者备注：{{author_note}}\n\n## 当前章节上下文\n章节标题：{{chapter_title}}\n章节正文：{{current_chapter_text}}\n\n## 上文最近章节\n{{recent_chapters}}\n\n请输出 JSON 格式的场景规划方案。',
    "output_mode": "structured",
    "output_schema_name": "planner",
}


_BUILTIN_WRITER: dict = {
    "stage": "writer",
    "name": "默认场景写作",
    "description": "根据场景规划与本章契约，写出叙事正文",
    "system_template": '## 角色与规则\n你是一位专业的小说写作者。你的唯一任务是根据下方的 Writer Brief 和本章契约，写出一段完整的叙事正文。\n\n核心约束：\n1. 仅输出叙事正文文本，不得包含任何标题、说明、Markdown 标记、JSON 包装或段落编号。\n2. 叙事视角：{{default_pov}}。全程保持一致，不得在场景内切换视角人物。\n3. 展示而非说教：通过角色的动作、对话、感官细节和内心独白来呈现情感与冲突，避免叙述者直接评判或解释。\n4. 对话自然：每个角色有独特的声音和措辞特征，避免所有角色说话风格相同。\n5. 必须遵守 {{must_not_deliver}}——不得在本章中兑现这些内容。\n6. 必须保护 {{fuel_reserved_for_later}}——不得在本章中消耗这些情节燃料。\n\nWriter Brief 执行规则：\n1. 从【进入事实】opening_fact 开始落笔；不要先写天气、地点铺陈或背景说明。\n2. 仅基于【当前已知】和【即时判断】（及其依据）推动人物行动；不要基于读者知道但当前视角不知道的事实做决策。\n3. 当【即时判断】situational_assumption 存在时，它必须改变人物的下一步行动；旁白不得立即纠正为正确答案。\n4. 执行【下一行动】next_action；该行动必须造成【可见后果】immediate_consequence，而不是由旁白宣布后果。\n5. 保留【新限制】next_constraint，不要在同一段内把冲突解释并解决完。\n6. 不要重复【进入事实】之前已经完成的动作，也不要复述 Writer Brief 中的条目文字。\n7. 【保持未分类】中的对象可以被当前视角看到，但其含义、名称或类别不得在正文中被解释或命名。\n8. 到【停止事实】stop_fact 成立时立即停止；不得追加主题总结、角色感想、悬念比喻或第二次即时破译。\n9. 若【末行必须包含】final_line_must_include 非空，正文最后一个非空段必须原样包含该短语；不得用角色反应替换它。\n\n技术参数只有在影响当下选择时才进入正文；出现后应尽快转为指令、决定或操作，不继续科普。\n\n字数要求：\n以完整完成场景因果和章节契约为先。目标字数为参考，除非用户明确要求，不得为了贴近字数重复解释、增加无关感官细节或延长结尾总结。\n\n写作模式处理：\n- 若 write_mode 为 continue_chapter：以 {{continuation_anchor}} 为起点无缝衔接续写，保持语调、节奏和叙事距离一致。\n- 若 write_mode 为 expand_outline：基于大纲展开为完整叙事，填充场景细节与人物行为。\n- 若 write_mode 为 rewrite_selection：仅重写选定段落，保持与未选中段落的自然过渡。\n- 若 write_mode 为 new_chapter：从零开始撰写全新章节。\n\n## 项目设定\n你必须严格遵循以下项目资料中的世界观、角色设定、风格指南和创作原则：\n{{project_documents}}\n\n## 本章契约\n章节功能：{{chapter_function}}\n弧线阶段：{{arc_phase}}\n本节读者来看这章是因为：{{reader_comes_for}}\n必须交付：{{must_deliver}}\n禁止交付：{{must_not_deliver}}\n核心变化：{{main_change}}\n核心爽点：{{main_payoff}}\n结尾钩子：{{ending_hook}}（钩子类型：{{hook_type}}）\n保留燃料：{{fuel_reserved_for_later}}\n目标字数：{{target_length}}\n\n## 运行时指令\n{{scene_instruction}}\n{{run_override}}',
    "user_template": '## 项目信息\n名称：{{project_name}}\n类型：{{project_genre}}\n叙事视角：{{default_pov}}\n\n## 写作模式\n当前模式：{{write_mode}}\n\n## 续写锚点\n{{continuation_anchor}}\n\n## 当前章节已写正文\n{{current_chapter_text}}\n\n## 项目资料与本章契约\n{{project_documents}}\n\n## 上文最近章节\n{{recent_chapters}}\n\n## Writer Brief（最后指令，据此直接写作）\n{{writer_brief}}\n\n请直接写出场景正文。',
    "output_mode": "plain_text",
    "output_schema_name": null,
}


_BUILTINS_BY_STAGE = {
    "planner": _BUILTIN_PLANNER,
    "writer": _BUILTIN_WRITER,
}


def upgrade() -> None:
    bind = op.get_bind()
    profiles = sa.table(
        "prompt_profiles",
        sa.column("id", sa.String),
        sa.column("stage", sa.String),
        sa.column("name", sa.String),
        sa.column("is_builtin", sa.Boolean),
    )
    versions = sa.table(
        "prompt_versions",
        sa.column("id", sa.String),
        sa.column("profile_id", sa.String),
        sa.column("version_number", sa.Integer),
        sa.column("system_template", sa.Text),
        sa.column("user_template", sa.Text),
        sa.column("output_mode", sa.String),
        sa.column("output_schema_name", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    # Only planner and writer changed in this phase; other stages keep their
    # existing builtin versions so user customizations remain untouched.
    for stage in ("planner", "writer"):
        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue

        current = bind.execute(
            sa.select(versions.c.id, versions.c.version_number)
            .where(versions.c.profile_id == profile.id)
            .order_by(versions.c.version_number.desc())
        ).first()
        if not current:
            continue

        entry = _BUILTINS_BY_STAGE[stage]
        # If the latest builtin version is already the current default, skip.
        current_template = bind.execute(
            sa.select(versions.c.system_template)
            .where(versions.c.id == current.id)
        ).scalar()
        if current_template == entry["system_template"]:
            continue

        replacement_id = str(uuid4())
        next_number = current.version_number + 1
        bind.execute(
            versions.insert().values(
                id=replacement_id,
                profile_id=profile.id,
                version_number=next_number,
                system_template=entry["system_template"],
                user_template=entry["user_template"],
                output_mode=entry["output_mode"],
                output_schema_name=entry["output_schema_name"],
                created_at=datetime.utcnow(),
            )
        )
        # Existing workflow steps that still point at the previous builtin
        # version should follow the new builtin default. Explicitly changed
        # prompt versions are left intact because their id is different.
        bind.execute(
            workflow_steps.update()
            .where(
                workflow_steps.c.stage == stage,
                workflow_steps.c.prompt_version_id == current.id,
            )
            .values(prompt_version_id=replacement_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    profiles = sa.table(
        "prompt_profiles",
        sa.column("id", sa.String),
        sa.column("stage", sa.String),
        sa.column("is_builtin", sa.Boolean),
    )
    versions = sa.table(
        "prompt_versions",
        sa.column("id", sa.String),
        sa.column("profile_id", sa.String),
        sa.column("version_number", sa.Integer),
        sa.column("system_template", sa.Text),
    )
    workflow_steps = sa.table(
        "workflow_step_configs",
        sa.column("prompt_version_id", sa.String),
        sa.column("stage", sa.String),
    )

    for stage in ("planner", "writer"):
        entry = _BUILTINS_BY_STAGE[stage]
        target_template = entry["system_template"]

        profile = bind.execute(
            sa.select(profiles.c.id)
            .where(profiles.c.stage == stage, profiles.c.is_builtin.is_(True))
            .order_by(profiles.c.id)
        ).first()
        if not profile:
            continue

        # Find the version(s) this migration created by matching the frozen
        # template. This avoids deleting later builtin versions added by
        # subsequent migrations.
        rows = bind.execute(
            sa.select(versions.c.id, versions.c.version_number)
            .where(
                versions.c.profile_id == profile.id,
                versions.c.system_template == target_template,
            )
            .order_by(versions.c.version_number.desc())
        ).fetchall()
        if not rows:
            continue

        for new in rows:
            old = bind.execute(
                sa.select(versions.c.id)
                .where(
                    versions.c.profile_id == profile.id,
                    versions.c.version_number == new.version_number - 1,
                )
            ).first()
            if not old:
                continue

            bind.execute(
                workflow_steps.update()
                .where(
                    workflow_steps.c.stage == stage,
                    workflow_steps.c.prompt_version_id == new.id,
                )
                .values(prompt_version_id=old.id)
            )
            bind.execute(versions.delete().where(versions.c.id == new.id))
