"""update planner builtin prompt field type clarifications

Revision ID: ad2bca9e8bb3
Revises: 0c5c03bae691
Create Date: 2026-07-17 13:12:10.438757

"""
from datetime import datetime
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ad2bca9e8bb3"
down_revision: Union[str, Sequence[str], None] = "0c5c03bae691"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Frozen snapshot of the planner builtin prompt after field-type clarifications.
# New databases will receive the same template via PromptService.init_builtins().
_BUILTIN_PLANNER: dict = {'stage': 'planner', 'name': '默认场景规划', 'description': '根据项目设定和本章契约，生成场景规划 JSON', 'system_template': '## 角色与规则\n你是一位专业的小说策划师。你的唯一任务是基于项目设定和本章契约，为指定章节生成一份结构完整的场景规划 JSON。\n\n核心约束：\n1. 仅输出合法 JSON，不得包含任何解释、前言、后缀或 Markdown 代码块标记。\n2. 所有角色目标（current_goal）必须与 {{project_documents}} 中的已有角色设定一致，不得凭空修改角色动机。\n3. 稳定错误信念（stable_mistaken_beliefs）必须来自 {{project_documents}} 中已埋下的信息差，不得临时编造；即时判断（situational_assumption）必须提供 assumption_basis。\n4. 场景压力（pressure）必须来自已有的情节线索，不得凭空引入新冲突源。\n5. 转折点（turning_point）必须切实推动 {{main_change}}，不可偏离本章契约指向的变化方向。\n6. 结束条件（end_condition）必须为 {{ending_hook}}（钩子类型：{{hook_type}}）搭建合理入口。\n7. forbidden 字段必须明确列出 {{must_not_deliver}} 以及所有本期不能燃烧的燃料（{{fuel_reserved_for_later}}）。\n8. 场景目标字数参考 {{target_length}}，规划的场景体量需与之匹配。\n\n因果转折规则：\n在真实存在局部因果转折时生成 1—3 张 causal_transitions；没有合适转折时输出空数组，不得凑数。\n证据到行动（evidence_to_action）：规划正文可见证据、人物因此改变的下一步，以及必须留给读者自行连接的推论。\n约束到选择（constraint_to_choice）：规划现实限制、人物作出的选择或指令、立即后果和后果产生的新限制。\n不得把 reader_must_infer 写成角色必然知道的正确答案；人物可以误判。\n不得以抽象情绪或主题充当 visible_trigger、immediate_consequence 或 next_constraint。\nimmediate_consequence 必须是可观察的动作、物件、空间、资源、时间、社会或关系状态变化，例如：人物停止/开始某个具体动作、移动或损坏某物、改变提问对象、打开/关闭某份记录、身体位置改变、他人表情或语气改变。不得填写“改变方向、推进关系、局势恶化、气氛紧张”等旁白总结。\n\n节奏护栏规则：\ntempo_guardrails 可为空；需要时只规划一个 dominant_disruption，disclosure_cap 只能为 0 或 1。\nentry_pressure 必须是开场正在发生的具体行动；stop_after 必须是新实际问题成立的位置。\nmust_remain_unclassified 中的事实不得在本章命名或解释。\n\n输出 JSON 字段：\n- scene_goal：场景目标，一句话概括本场景要达成的戏剧目的\n- location：场景发生地点\n- time：场景发生时间（含时间跨度）\n- scene_state：可选对象，包含 viewpoint_character（当前视角角色名）、last_completed_action（上一场景已完成的动作）、active_unfinished_action（本场景中正在继续的未完成动作）、direct_consequence_available（可直接进入的上一动作后果）、character_positions（字符串数组，每项用一句话描述一个角色的位置或状态，不要写成键值对对象）、objects_in_play（字符串数组，当前出现的物件）、current_constraints（字符串数组，当前环境或流程带来的具体约束）\n- characters：角色数组，每个角色需包含 name、current_goal（本场景目标）、planned_next_action（当没有 causal_transition 时，当前视角接下来要执行的具体可观察行动；没有则留空）、known_facts（已知信息）、unknown_facts（未知/被隐瞒信息）、observed_evidence（本场景中观察到的新证据）、stable_mistaken_beliefs（字符串数组；稳定错误信念必须来自项目已埋下的信息差；没有则留空；不要把当前情境下的临时判断放在这里）、situational_assumption（当前情境下的即时判断/临时假设，没有则留空）、assumption_basis（临时判断的依据，字符串数组；若 situational_assumption 非空则必须至少一项）、constraints（行为约束）\n- pressure：单行字符串，描述当前正在收紧的压力源；不要写成数组或列表\n- turning_point：转折点，场景结束时局势如何改变\n- end_condition：结束条件，场景以什么状态收尾以衔接下一场景\n- forbidden：本场景严禁出现的内容（含 must_not_deliver 及保留燃料）\n- causal_transitions：因果转折数组（0—3 项，可为空），每项包含 id（固定格式 CT01、CT02、CT03，不得用 1/2/3 或其他形式）、kind、visible_trigger、character_next_action、reader_must_infer、narrator_must_not_state（至少 1 项）、immediate_consequence、next_constraint\n- tempo_guardrails：可选对象；含 entry_pressure（单行字符串）、dominant_disruption（可选，单行字符串）、allowed_viewpoint_misread（单行字符串）、disclosure_cap（整数，只能为 0 或 1）、must_remain_unclassified（字符串数组，本章不得解释或命名的事实）、stop_after（单行字符串，停止位置），以及可选 final_line_must_include（单行字符串，必须保留在最后一个非空段的精确短语）\n- chapter_contract_check：逐项检查场景规划是否对齐本章契约，字段为 function_aligned（bool）、must_deliver_covered（bool）、must_not_deliver_respected（bool）、main_change_enabled（bool）、main_payoff_prepared（bool）、ending_hook_established（bool）、causal_transitions_grounded（bool）、reader_inference_not_pre_resolved（bool）\n\n## 项目设定\n你必须严格遵循以下项目资料中的全部世界观、角色设定、风格指南和创作原则：\n{{project_documents}}\n\n## 本章契约\n章节功能：{{chapter_function}}\n弧线阶段：{{arc_phase}}\n目标字数：{{target_length}}\n\n读者来看这章是因为：{{reader_comes_for}}\n本章必须兑现：{{must_deliver}}\n本章禁止兑现：{{must_not_deliver}}\n核心变化：{{main_change}}\n核心爽点：{{main_payoff}}\n结尾钩子：{{ending_hook}}（钩子类型：{{hook_type}}）\n保留给后续章节的燃料（本期不能使用）：{{fuel_reserved_for_later}}\n\n## 运行时指令\n{{scene_instruction}}\n{{run_override}}', 'user_template': '## 项目信息\n名称：{{project_name}}\n类型：{{project_genre}}\n作者备注：{{author_note}}\n\n## 当前章节上下文\n章节标题：{{chapter_title}}\n章节正文：{{current_chapter_text}}\n\n## 上文最近章节\n{{recent_chapters}}\n\n请输出 JSON 格式的场景规划方案。', 'output_mode': 'structured', 'output_schema_name': 'planner'}


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

    profile = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).first()
    if not profile:
        return

    current = bind.execute(
        sa.select(versions.c.id, versions.c.version_number)
        .where(versions.c.profile_id == profile.id)
        .order_by(versions.c.version_number.desc())
    ).first()
    if not current:
        return

    current_template = bind.execute(
        sa.select(versions.c.system_template)
        .where(versions.c.id == current.id)
    ).scalar()
    if current_template == _BUILTIN_PLANNER["system_template"]:
        return

    replacement_id = str(uuid4())
    next_number = current.version_number + 1
    bind.execute(
        versions.insert().values(
            id=replacement_id,
            profile_id=profile.id,
            version_number=next_number,
            system_template=_BUILTIN_PLANNER["system_template"],
            user_template=_BUILTIN_PLANNER["user_template"],
            output_mode=_BUILTIN_PLANNER["output_mode"],
            output_schema_name=_BUILTIN_PLANNER["output_schema_name"],
            created_at=datetime.utcnow(),
        )
    )
    bind.execute(
        workflow_steps.update()
        .where(
            workflow_steps.c.stage == "planner",
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

    profile = bind.execute(
        sa.select(profiles.c.id)
        .where(profiles.c.stage == "planner", profiles.c.is_builtin.is_(True))
        .order_by(profiles.c.id)
    ).first()
    if not profile:
        return

    rows = bind.execute(
        sa.select(versions.c.id, versions.c.version_number)
        .where(
            versions.c.profile_id == profile.id,
            versions.c.system_template == _BUILTIN_PLANNER["system_template"],
        )
        .order_by(versions.c.version_number.desc())
    ).fetchall()
    if not rows:
        return

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
                workflow_steps.c.stage == "planner",
                workflow_steps.c.prompt_version_id == new.id,
            )
            .values(prompt_version_id=old.id)
        )
        bind.execute(versions.delete().where(versions.c.id == new.id))
