"""Generate rendered Writer prompts for five fixed scenes.

This script is a manual verification helper. It compiles deterministic
Writer Briefs from fixed PlannerOutput-like inputs and renders the current
built-in Writer system/user prompts, saving them under
`data/writer_prompt_samples/` for inspection.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "apps" / "api"
OUTPUT_DIR = REPO_ROOT / "data" / "writer_prompt_samples"

sys.path.insert(0, str(API_ROOT))

from app.llm.output_contracts import PlannerOutput, validate_planner_output
from app.prompts.writer_brief import compile_writer_brief, format_writer_brief
from app.prompts.defaults import BUILTIN_PROMPTS
from app.prompts.renderer import render

WRITER_PROMPT = next(p for p in BUILTIN_PROMPTS if p["stage"] == "writer")

SCENES: list[dict] = [
    {
        "name": "01_evidence_to_action_hangar",
        "planner": {
            "scene_goal": "陆衡在机库发现异常编号，推动调查转向",
            "location": "地下机库",
            "time": "换班前二十分钟",
            "characters": [
                {
                    "name": "陆衡",
                    "current_goal": "查明冷却管异响来源",
                    "known_facts": ["工单编号 GR-0713", "冷却管昨夜有异响", "压力表读数偏高"],
                    "unknown_facts": ["敲击声来源", "编号与许明远的关系"],
                    "observed_evidence": ["接线盒里出现 GR-0713 铭牌"],
                    "stable_mistaken_beliefs": ["阀门只是松了"],
                    "situational_assumption": "阀门松了导致压力偏高",
                    "assumption_basis": ["压力表读数偏高", "昨夜大风"],
                    "constraints": ["不能暴露未来工单"],
                }
            ],
            "scene_state": {
                "viewpoint_character": "陆衡",
                "last_completed_action": "放下扳手",
                "active_unfinished_action": "检查阀门",
                "direct_consequence_available": "工具落地后，敲击声突然停止",
                "character_positions": ["陆衡在冷却管旁"],
                "objects_in_play": ["压力表", "扳手", "接线盒"],
                "current_constraints": ["不能暴露未来工单"],
            },
            "pressure": "即将交班，值班日志不能再拖延",
            "turning_point": "敲击声再次出现，且来自接线盒方向",
            "end_condition": "陆衡切断外门电源",
            "forbidden": ["揭晓发送者", "直接说明编号含义"],
            "causal_transitions": [
                {
                    "id": "CT01",
                    "kind": "evidence_to_action",
                    "visible_trigger": "接线盒里出现 GR-0713",
                    "character_next_action": "陆衡询问许栀父亲的名字",
                    "reader_must_infer": "编号与许明远有关",
                    "narrator_must_not_state": ["两个编号一致", "许明远就是发送者"],
                    "immediate_consequence": "陆衡改变调查方向，从机械故障转向人事档案",
                    "next_constraint": "他不能透露未来工单的存在",
                }
            ],
            "chapter_contract_check": {},
            "tempo_guardrails": {
                "entry_pressure": "林隅正把熄火的探测车拖回仓库。",
                "dominant_disruption": "冷却管里传出敲击声。",
                "allowed_viewpoint_misread": "他以为压力阀松了。",
                "disclosure_cap": 1,
                "must_remain_unclassified": ["敲击声来源"],
                "stop_after": "他切断外门电源。",
                "final_line_must_include": "身份验证通过",
            },
        },
    },
    {
        "name": "02_constraint_to_choice_rescue",
        "planner": {
            "scene_goal": "周漾在缆绳断裂前被迫作出救援选择",
            "location": "悬崖外侧维修平台",
            "time": "暴风夜，凌晨两点",
            "characters": [
                {
                    "name": "周漾",
                    "current_goal": "把受伤工友拉回平台",
                    "known_facts": ["缆绳承重只剩三十秒", "工友腿部被卡住", "风暴正在加剧"],
                    "unknown_facts": ["备用锚点是否牢固"],
                    "observed_evidence": ["缆绳纤维一根根崩断"],
                    "stable_mistaken_beliefs": ["再撑一下就能解开卡扣"],
                    "situational_assumption": "必须优先保住上方平台",
                    "assumption_basis": ["平台一旦倾斜两人都会坠崖"],
                    "constraints": ["不能抛下工友单独逃生"],
                }
            ],
            "scene_state": {
                "viewpoint_character": "周漾",
                "last_completed_action": "把安全绳系在工友腰间",
                "active_unfinished_action": "尝试解开被卡住的腿",
                "direct_consequence_available": "第一根缆绳突然崩断，平台剧烈晃动",
                "character_positions": ["周漾半跪在平台边缘", "工友悬在平台外"],
                "objects_in_play": ["安全绳", "断裂的缆绳", "卡扣"],
                "current_constraints": ["不能抛下工友"],
            },
            "pressure": "风暴和重力同时作用，缆绳正在断裂",
            "turning_point": "周漾决定割断主缆，让平台先复位",
            "end_condition": "工友被甩回内侧，周漾失去平衡挂在安全绳上",
            "forbidden": ["工友当场死亡", "平台完全坍塌"],
            "causal_transitions": [
                {
                    "id": "CT01",
                    "kind": "constraint_to_choice",
                    "visible_trigger": "第二根缆绳开始发出金属撕裂声",
                    "character_next_action": "周漾割断主缆让平台复位",
                    "reader_must_infer": "只有牺牲稳定才能换取两人同时生还的可能",
                    "narrator_must_not_state": ["这是唯一正确的救援方案"],
                    "immediate_consequence": "平台猛然回摆，工友被甩回内侧",
                    "next_constraint": "周漾自己被抛向空中，仅靠安全绳悬挂",
                }
            ],
            "chapter_contract_check": {},
            "tempo_guardrails": {
                "entry_pressure": "周漾已经解开了半个卡扣。",
                "dominant_disruption": "缆绳在风暴中一根根崩断。",
                "allowed_viewpoint_misread": "他以为还能再撑三十秒。",
                "disclosure_cap": 0,
                "must_remain_unclassified": ["备用锚点是否牢固"],
                "stop_after": "周漾单手挂在安全绳上，平台在他脚下摇晃。",
            },
        },
    },
    {
        "name": "03_ordinary_conversation_cafe",
        "planner": {
            "scene_goal": "两位老同学在咖啡馆寒暄，交换近况",
            "location": "街角咖啡馆",
            "time": "周六下午三点",
            "characters": [
                {
                    "name": "沈明",
                    "current_goal": "了解老同学近况",
                    "known_facts": ["对方上个月换了工作", "两人三年未见"],
                    "unknown_facts": [],
                    "observed_evidence": [],
                    "stable_mistaken_beliefs": [],
                    "situational_assumption": "",
                    "assumption_basis": [],
                    "constraints": [],
                }
            ],
            "scene_state": {
                "viewpoint_character": "沈明",
                "last_completed_action": "推开咖啡馆门",
                "active_unfinished_action": "",
                "direct_consequence_available": "",
                "character_positions": ["沈明坐在靠窗位置"],
                "objects_in_play": ["两杯咖啡", "旧照片"],
                "current_constraints": [],
            },
            "pressure": "",
            "turning_point": "对方提到下周要出国",
            "end_condition": "沈明把旧照片递过去",
            "forbidden": ["揭晓隐藏身份", "引入悬疑阴谋"],
            "causal_transitions": [],
            "chapter_contract_check": {},
            "tempo_guardrails": {
                "entry_pressure": "沈明推开咖啡馆门，风铃响了一声。",
                "dominant_disruption": "",
                "allowed_viewpoint_misread": "",
                "disclosure_cap": 0,
                "must_remain_unclassified": [],
                "stop_after": "沈明把那张旧照片推到桌面中央。",
            },
        },
    },
    {
        "name": "04_identity_verification_checkpoint",
        "planner": {
            "scene_goal": "苏璃通过哨卡身份验证，同时隐藏真实意图",
            "location": "城门外哨卡",
            "time": "黄昏，换岗前",
            "characters": [
                {
                    "name": "苏璃",
                    "current_goal": "顺利进城不引起怀疑",
                    "known_facts": ["伪造路引上的印章", "守军换岗时间"],
                    "unknown_facts": ["守军是否接到画像通缉"],
                    "observed_evidence": ["士兵在核对一叠新到的画像"],
                    "stable_mistaken_beliefs": ["自己的伪装足够普通"],
                    "situational_assumption": "士兵还没认出她",
                    "assumption_basis": ["士兵仍在闲聊", "她排在队伍末尾"],
                    "constraints": ["不能主动暴露武艺"],
                }
            ],
            "scene_state": {
                "viewpoint_character": "苏璃",
                "last_completed_action": "把路引递出",
                "active_unfinished_action": "等待士兵核对",
                "direct_consequence_available": "士兵抬头看了她一眼",
                "character_positions": ["苏璃站在哨卡木栅前"],
                "objects_in_play": ["伪造路引", "画像", "马缰绳"],
                "current_constraints": ["不能主动暴露武艺"],
            },
            "pressure": "换岗前的士兵态度最松懈也最难预测",
            "turning_point": "士兵把路引递回，没有比对画像",
            "end_condition": "苏璃接过路引，牵着马走入城门",
            "forbidden": ["主动动手", "揭示真实身份"],
            "causal_transitions": [
                {
                    "id": "CT01",
                    "kind": "evidence_to_action",
                    "visible_trigger": "士兵把路引递回并摆了摆手",
                    "character_next_action": "苏璃低头接过路引，牵马入城",
                    "reader_must_infer": "士兵没有把她和通缉画像对上",
                    "narrator_must_not_state": ["她其实已经被放过"],
                    "immediate_consequence": "城门在她身后缓缓关闭",
                    "next_constraint": "她必须立刻消失在人群中",
                }
            ],
            "chapter_contract_check": {},
            "tempo_guardrails": {
                "entry_pressure": "苏璃把伪造路引递到士兵手中。",
                "dominant_disruption": "",
                "allowed_viewpoint_misread": "她以为自己的伪装足够普通。",
                "disclosure_cap": 1,
                "must_remain_unclassified": ["通缉画像的内容"],
                "stop_after": "苏璃牵着马走入城门阴影。",
                "final_line_must_include": "身份验证通过",
            },
        },
    },
    {
        "name": "05_old_friend_assumption",
        "planner": {
            "scene_goal": "林知微发现旧友隐瞒一件事，但选择不点破",
            "location": "旧友公寓客厅",
            "time": "雨夜，晚饭后",
            "characters": [
                {
                    "name": "林知微",
                    "current_goal": "确认旧友是否需要帮助",
                    "known_facts": ["对方辞了稳定工作", "客厅多了行李箱"],
                    "unknown_facts": ["旧友要去哪里", "为什么隐瞒家人"],
                    "observed_evidence": ["沙发靠垫下露出一张车票"],
                    "stable_mistaken_beliefs": ["旧友一向冲动"],
                    "situational_assumption": "旧友准备不辞而别",
                    "assumption_basis": ["行李箱半开着", "车票日期是明天"],
                    "constraints": ["不能替对方做决定"],
                }
            ],
            "scene_state": {
                "viewpoint_character": "林知微",
                "last_completed_action": "把茶杯放到茶几上",
                "active_unfinished_action": "",
                "direct_consequence_available": "她的目光扫到沙发靠垫下的车票",
                "character_positions": ["林知微坐在沙发上", "旧友背对她整理书架"],
                "objects_in_play": ["茶杯", "半开的行李箱", "车票"],
                "current_constraints": ["不能替对方做决定"],
            },
            "pressure": "旧友明显在回避关键问题",
            "turning_point": "林知微决定假装没看见车票",
            "end_condition": "林知微起身告辞，把疑问留在门后",
            "forbidden": ["当场揭穿", "改变旧友决定"],
            "causal_transitions": [
                {
                    "id": "CT01",
                    "kind": "constraint_to_choice",
                    "visible_trigger": "旧友把行李箱推回卧室，装作若无其事",
                    "character_next_action": "林知微起身告辞，没有提起车票",
                    "reader_must_infer": "林知微选择尊重对方的沉默",
                    "narrator_must_not_state": ["她知道旧友明天就要离开"],
                    "immediate_consequence": "门在两人之间轻轻合上",
                    "next_constraint": "林知微必须在门外决定下一步",
                }
            ],
            "chapter_contract_check": {},
            "tempo_guardrails": {
                "entry_pressure": "林知微把茶杯放到茶几上，水已经凉了。",
                "dominant_disruption": "旧友把半开的行李箱匆匆推回卧室。",
                "allowed_viewpoint_misread": "她觉得旧友又在逃避。",
                "disclosure_cap": 1,
                "must_remain_unclassified": ["车票目的地"],
                "stop_after": "林知微把门带上，走廊灯闪了一下。",
            },
        },
    },
]

COMMON_VARIABLES = {
    "project_name": "《锈蚀工单》",
    "project_genre": "悬疑科幻",
    "author_note": "保持克制、具象的工业风格，避免旁白解释。",
    "default_pov": "第三人称有限视角，跟随当前视角角色",
    "chapter_title": "第七章：边界测试",
    "current_chapter_text": "",
    "recent_chapters": "",
    "project_documents": (
        "## 世界观\n近未来矿业卫星，资源枯竭导致维修站废弃。\n\n"
        "## 角色\n陆衡：前工程师，沉默寡言，习惯靠证据说话。\n"
        "周漾：救援队员，行动优先，内心有未愈合的愧疚。\n"
        "苏璃：流亡者，精于伪装，信任成本极高。\n"
        "林知微：心理咨询师，擅长保留边界。\n"
        "沈明：普通上班族，生活流观察者。\n"
    ),
    "chapter_function": "推进主线调查并铺垫下一章危机",
    "arc_phase": "上升冲突",
    "reader_comes_for": "看主角如何在信息不完整时作出关键判断",
    "must_deliver": "一个可见证据、一个改变行动的误判、一个未解悬念",
    "must_not_deliver": "幕后黑手的真实身份、世界观核心设定的完整解释",
    "main_change": "主角从被动调查转向主动追踪",
    "main_payoff": "读者意识到编号背后连着更大的图谋",
    "ending_hook": "身份验证通过的瞬间，系统显示了一条未授权访问记录",
    "hook_type": "信息缺口",
    "fuel_reserved_for_later": "GR-0713 的真实发送者、卫星坠毁真相",
    "target_length": "2500",
    "scene_instruction": "",
    "run_override": "",
    "write_mode": "new_chapter",
    "continuation_anchor": "",
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for scene in SCENES:
        name = scene["name"]
        planner_output = validate_planner_output(scene["planner"])
        writer_brief = compile_writer_brief(planner_output)

        variables = dict(COMMON_VARIABLES)
        variables["writer_brief"] = format_writer_brief(writer_brief)

        system_prompt = render(WRITER_PROMPT["system_template"], variables, strict=True)
        user_prompt = render(WRITER_PROMPT["user_template"], variables, strict=True)

        payload = {
            "scene_name": name,
            "writer_brief": writer_brief.model_dump(),
            "rendered_system_prompt": system_prompt,
            "rendered_user_prompt": user_prompt,
        }

        out_path = OUTPUT_DIR / f"{name}.json"
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote {out_path}")

    print(f"\nDone. Samples are in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
