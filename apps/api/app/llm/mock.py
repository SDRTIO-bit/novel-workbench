import time
import json
import re
from app.llm.base import BaseLlmClient, LlmRequest, LlmResponse, LlmError

MOCK_MODE_NORMAL = "normal"
MOCK_MODE_TIMEOUT = "timeout"
MOCK_MODE_INVALID_JSON = "invalid_json"
MOCK_MODE_RATE_LIMIT = "rate_limit"


class MockClient(BaseLlmClient):
    def __init__(self, mode: str = MOCK_MODE_NORMAL, delay_ms: int = 50):
        self.mode = mode
        self.delay_ms = delay_ms

    async def complete(self, request: LlmRequest) -> LlmResponse:
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000)

        if self.mode == MOCK_MODE_TIMEOUT:
            raise LlmError("LLM_TIMEOUT", "模拟超时", 502)
        if self.mode == MOCK_MODE_RATE_LIMIT:
            raise LlmError("LLM_RATE_LIMIT", "模拟频率限制", 502)

        text = self._build_response(request)

        if self.mode == MOCK_MODE_INVALID_JSON:
            text = "这不是有效的 JSON { broken"

        input_text = "".join(
            message.get("content", "") for message in (request.messages or [])
        ) or (request.system_prompt + request.user_prompt)
        return LlmResponse(
            text=text,
            input_tokens=len(input_text) // 3,
            output_tokens=len(text) // 3,
            latency_ms=self.delay_ms,
            provider_request_id="mock-request-001",
        )

    def _build_response(self, request: LlmRequest) -> str:
        sp = request.system_prompt.lower()
        up = request.user_prompt.lower()

        # ── Stage detection via system_prompt role markers ONLY ──
        # Using sp avoids cross-contamination from prior-stage outputs
        # injected into the user_prompt via {{variables}}.
        # Content extraction (chars, places) uses `up` (user prompt).

        # Planner → scene plan JSON
        if "小说策划师" in sp or "场景规划师" in sp or ("小说规划" in sp and "plan" in sp):
            chars = []
            loc = "未指定地点"
            goal = "完成本章叙事目标"
            if "老陈" in up or "书店" in up:
                loc = "老街时光书屋"
                goal = "让老陈与小女孩小满建立信任"
                chars = [
                    {"name": "老陈", "goal": "安抚迷路的孩子，守护书店的宁静", "known": ["书店是避风港", "阿橘每天黄昏准时来"], "unknown": ["小女孩为什么哭", "她家在哪里"], "mistaken_beliefs": ["一个人的生活不需要改变"], "constraints": ["不擅言辞", "不能离开书店"]},
                    {"name": "小满", "goal": "找到回家的路，表达内心的不安", "known": ["放学后走散了", "书店看起来很温暖"], "unknown": ["老陈是谁", "妈妈什么时候来接我"], "mistaken_beliefs": ["大人都不理解小孩"], "constraints": ["年纪小，表达能力有限"]},
                ]
            elif "林远" in up or "雨夜" in up or "公交站" in up:
                loc = "深夜城郊公交站"
                goal = "两个陌生人在雨夜公交站产生微妙共鸣"
                chars = [
                    {"name": "林远", "goal": "结束漫长加班，回家", "known": ["今天加班到深夜", "秋雨来得突然"], "unknown": ["站台上的女子是谁", "这场邂逅会改变什么"], "mistaken_beliefs": ["城市里人与人注定擦肩而过"], "constraints": ["性格内向，不善主动搭话"]},
                    {"name": "苏念", "goal": "等待末班车，保持自己的节奏", "known": ["花店刚打烊", "喜欢下雨的夜晚"], "unknown": ["身边的陌生人在想什么"], "mistaken_beliefs": ["浪漫只存在于电影里"], "constraints": ["独立惯了，不习惯依靠别人"]},
                ]

            is_twilight = "黄昏" in up or "黄昏" in sp
            return json.dumps({
                "planner_contract_version": 2,
                "scene_goal": goal,
                "location": loc,
                "time": "黄昏" if is_twilight else "深夜",
                "scene_state": {
                    "last_completed_action": "场景开始前的状态",
                    "present_characters": [c["name"] for c in (chars or [{"name": "主角"}])],
                    "visible_facts": ["场景中的可见事实"],
                    "available_objects": ["场景中的可用物件"],
                    "unresolved_problem": "未解决的问题",
                    "already_existing_constraints": ["已有的限制条件"],
                },
                "concrete_problem": "角色在本场景中需要面对的具体问题",
                "characters": chars or [
                    {"name": "主角", "goal": "推进故事", "known": ["当前处境"], "unknown": ["对方身份", "隐藏的真相"], "mistaken_beliefs": ["事情会按预期发展"], "constraints": ["不能暴露意图"]}
                ],
                "pressure": "时间在流逝，黄昏即将结束" if is_twilight else "气氛逐渐紧张",
                "turning_point": "小女孩开口说第一句话" if "老陈" in up else "一个意外的眼神交汇",
                "end_condition": "建立了最初的信任" if "老陈" in up else "雨停了",
                "forbidden": ["不能煽情", "不能用巧合解决冲突"],
                "causal_transitions": [
                    {
                        "id": "CT01",
                        "kind": "evidence_to_action",
                        "visible_trigger": "书店铜铃响起，门口出现一个红着眼眶的小女孩",
                        "character_interpretation": "老陈看出女孩需要安全感",
                        "character_next_action": "老陈用最平常的语气请她进来坐",
                        "rejected_alternative": "直接询问女孩为什么哭",
                        "reader_must_infer": "老陈选择用日常感而非直接询问来安抚",
                        "narrator_must_not_state": ["老陈判断女孩需要安全感", "这是最好的处理方式"],
                        "immediate_consequence": "女孩跨过门槛，阿橘走到她脚边坐下",
                        "counterfactual_without_action": "如果老陈不邀请，女孩会继续站在门外",
                        "consequence_would_still_happen": False,
                        "state_delta": {"before": "女孩站在门外犹豫", "after": "女孩进入书店坐下"},
                        "cost_or_commitment": "老陈打破了自己不干涉他人事务的习惯",
                        "next_constraint": "老陈还不知道女孩为什么哭以及她从哪里来",
                    }
                ],
                "tempo_guardrails": {
                    "entry_pressure": "铜铃响起，女孩出现在门口",
                    "dominant_pressure": {"kind": "social_friction", "description": "陌生人之间的信任建立"},
                    "allowed_viewpoint_misread": "女孩可能误以为老陈不关心她",
                    "disclosure_cap": 1,
                    "must_remain_unclassified": ["女孩哭的真正原因"],
                    "stop_state": {
                        "type": "relationship_shift",
                        "visible_fact": "女孩坐在书店里",
                        "what_is_now_different": "从陌生人变成了暂时的庇护关系",
                        "must_not_append": "不得解释女孩为什么哭",
                    },
                },
                "chapter_contract_check": {
                    "function_aligned": True,
                    "must_deliver_covered": True,
                    "must_not_deliver_respected": True,
                    "main_change_enabled": True,
                    "main_payoff_prepared": True,
                    "ending_hook_established": True,
                    "causal_transitions_grounded": True,
                    "reader_inference_not_pre_resolved": True,
                    "scene_state_reconstructed": True,
                    "information_sources_legal": True,
                    "character_choice_is_real": True,
                    "consequence_is_counterfactual": True,
                    "state_delta_is_nonempty": True,
                    "next_constraint_is_new": True,
                    "stop_state_is_visible": True,
                    "stop_state_changes_future_actions": True,
                },
            }, ensure_ascii=False)

        # Writer → narrative prose (returns text, not JSON)
        if "小说家" in sp or "小说写作者" in sp:
            if "老陈" in up or "书店" in up or "黄昏" in up:
                return """黄昏的光从梧桐叶的缝隙里漏进来，在书店的木地板上画出一块块金色的光斑。

老陈坐在柜台后面，手里的《浮生六记》已经翻到卷三。这本书他读过不下十遍，每回翻到沈复写芸娘那一段，他总会停下来，目光越过老花镜的上沿，望向窗外。窗台上，橘猫阿橘正用尾巴有节奏地轻轻敲着玻璃，那是它每天的黄昏仪式——准时得像教堂的钟。

书店里弥漫着旧纸和樟脑的味道。这些书，有些比老陈还老，它们的书脊已经褪色，但每一本都被他修整得整整齐齐。书架的第三排左侧，有他给妻子留的位置——那几本她最爱读的散文集，五年来没有人动过。

门上的铜铃突然响了。

老陈抬起头。门口的光线里站着一个小小的身影——一个背书包的女孩，头发有点乱，眼眶红红的。她没有走进来，只是站在门槛上，一只手紧紧攥着书包带子，另一只手揉着眼睛。

阿橘的尾巴停了。它转过头，用琥珀色的眼睛打量着这个闯入者。

老陈没有站起来。他把书轻轻合上，推到一边，然后用最平常的语气说了三个字——

"进来坐。"

女孩犹豫了一下，跨过了门槛。书店的木门在她身后慢慢合上，铜铃又响了一声。黄昏的光继续在地板上移动，像是在丈量时间的流速。

阿橘从窗台上跳下来，悄无声息地走到女孩脚边，坐了下来。"""

            return """雨是从九点四十分开始下的。林远走出写字楼旋转门的时候，第一滴雨正好落在他的手背上，凉得他一激灵。

他看了看天——云层压得很低，路灯的光在雨雾里化成一团团模糊的光晕。末班车还要二十分钟。他叹了口气，把工牌塞进裤兜，朝街角的公交站跑去。

公交站的雨棚只有半边，靠左的位置已经被人占了。林远缩着脖子站在右边，雨水顺着棚沿滚下来，在他脚边溅成细碎的水花。他这才注意到身边站着一个年轻的女子。

她撑着一把透明雨伞，伞面上的水珠在路灯下折射出细碎的光。她穿一件米色风衣，右手撑伞，左手拿着一盆用旧报纸包着的小盆栽——看不出是什么植物，只有两片叶子从报纸的破口里探出来。

雨声很大，但公交站很小。他们之间不到一米。

林远能闻到她身上淡淡的花香，混合着雨水和初秋夜晚特有的清冷气息。不是香水，倒像是花店里整天待着的那种味道——植物的、泥土的、潮湿的味道。

他注意到她握着伞柄的手指很细，指甲剪得很短，左手食指上贴着一张卡通创可贴。大概是整理花枝的时候被刺扎到了。

她似乎感觉到了他的目光，微微侧过头。林远赶紧收回视线，假装在看站牌上的线路图——其实那些线路他闭着眼睛都能背出来。

雨越下越大。末班车还没来。

她忽然笑了一下，声音轻得几乎被雨声盖住："你也觉得这雨一时半会儿停不了？"

林远愣了一下，才反应过来她是在跟他说话。"""

        # Critic → diagnostic report
        if "文学编辑" in sp or "critic" in sp or "合同核验员" in sp:
            if "planner_contract_validation_version" in sp:
                first_quote = (
                    "黄昏的光从梧桐叶的缝隙里漏进来"
                    if "黄昏的光从梧桐叶的缝隙里漏进来" in up
                    else "雨是从九点四十分开始下的"
                )
                return json.dumps({
                    "planner_contract_validation_version": 1,
                    "overall_assessment": "Writer 基本执行了 Planner 合同，但部分字段存在缩水或缺失。",
                    "stop_state": {
                        "visible_fact": {
                            "status": "present",
                            "evidence": [{
                                "paragraph_id": "P001",
                                "quote": first_quote,
                                "explanation": "正文给出了可见的停点事实。",
                            }],
                            "explanation": "停点事实完整存在。",
                        },
                        "must_not_append": {
                            "status": "present",
                            "evidence": [{
                                "paragraph_id": "P001",
                                "quote": first_quote,
                                "explanation": "正文没有追加禁止内容。",
                            }],
                            "explanation": "停点后未追加禁止内容。",
                        },
                    },
                    "transitions": [{
                        "transition_id": "CT01",
                        "visible_trigger": {
                            "status": "present",
                            "evidence": [{
                                "paragraph_id": "P001",
                                "quote": first_quote,
                                "explanation": "正文给出了可见触发。",
                            }],
                            "explanation": "触发完整存在。",
                        },
                        "rejected_alternative": {
                            "status": "missing",
                            "evidence": [],
                            "explanation": "正文中没有呈现被拒绝的替代方案。",
                        },
                        "character_next_action": {
                            "status": "present",
                            "evidence": [{
                                "paragraph_id": "P001",
                                "quote": first_quote,
                                "explanation": "正文给出了人物下一步行动。",
                            }],
                            "explanation": "行动完整存在。",
                        },
                        "cost_or_commitment": {
                            "status": "partial",
                            "evidence": [{
                                "paragraph_id": "P001",
                                "quote": first_quote,
                                "explanation": "正文暗示了代价但未明确呈现。",
                            }],
                            "explanation": "代价部分存在，需要更具体的呈现。",
                        },
                        "immediate_consequence": {
                            "status": "present",
                            "evidence": [{
                                "paragraph_id": "P001",
                                "quote": first_quote,
                                "explanation": "正文给出了直接后果。",
                            }],
                            "explanation": "后果完整存在。",
                        },
                        "next_constraint": {
                            "status": "missing",
                            "evidence": [],
                            "explanation": "正文中没有呈现选择后形成的新行动限制。",
                        },
                    }],
                    "general_findings": [],
                    "strength_candidates": [],
                    "issues": [
                        {
                            "issue_id": "I01",
                            "severity": "high",
                            "issue_type": "contract_not_delivered",
                            "paragraph_ids": ["P001"],
                            "problem": "被拒绝的替代方案缺失：正文中没有呈现被拒绝的替代方案",
                            "revision_goal": "在正文中呈现被拒绝的替代方案，使其具体可执行",
                            "recommended_operation": "tighten",
                        },
                        {
                            "issue_id": "I02",
                            "severity": "medium",
                            "issue_type": "contract_not_delivered",
                            "paragraph_ids": ["P001"],
                            "problem": "代价或承诺缩水：正文暗示了代价但未明确呈现",
                            "revision_goal": "用具体行动呈现代价或承诺",
                            "recommended_operation": "causalize",
                        },
                        {
                            "issue_id": "I03",
                            "severity": "high",
                            "issue_type": "contract_not_delivered",
                            "paragraph_ids": ["P001"],
                            "problem": "新行动限制缺失：正文中没有呈现选择后形成的新行动限制",
                            "revision_goal": "在正文中呈现选择后形成的新行动限制",
                            "recommended_operation": "causalize",
                        },
                    ],
                }, ensure_ascii=False)
            if "critic_evidence_contract_version" in sp:
                first_quote = (
                    "黄昏的光从梧桐叶的缝隙里漏进来"
                    if "黄昏的光从梧桐叶的缝隙里漏进来" in up
                    else "雨是从九点四十分开始下的"
                )
                return json.dumps({
                    "critic_evidence_contract_version": 1,
                    "overall_assessment": "编号正文在停点后仍继续，选择重量未完整落地。",
                    "stop_audit": {
                        "visible_fact_found": True,
                        "first_satisfied_paragraph_id": "P001",
                        "quote": first_quote,
                        "explanation": "该可见画面可作为停点事实的落点。",
                    },
                    "inference_findings": [],
                    "transition_audits": [{
                        "transition_id": "CT01",
                        "trigger": {"visible": True, "evidence": [{
                            "paragraph_id": "P001", "quote": first_quote,
                            "explanation": "正文给出了可见触发。",
                        }], "explanation": "触发可见。"},
                        "next_action": {"visible": True, "evidence": [{
                            "paragraph_id": "P001", "quote": first_quote,
                            "explanation": "正文有后续变化。",
                        }], "explanation": "行动可见。"},
                        "immediate_consequence": {"visible": True, "evidence": [{
                            "paragraph_id": "P001", "quote": first_quote,
                            "explanation": "正文有即时可见结果。",
                        }], "explanation": "后果可见。"},
                        "rejected_alternative": {"visible": False, "evidence": [], "explanation": "没有可验证的替代路线。"},
                        "cost_or_commitment": {"visible": False, "evidence": [], "explanation": "没有可验证的具体代价。"},
                        "next_constraint": {"visible": False, "evidence": [], "explanation": "没有可验证的新限制。"},
                        "reader_inference_withheld": True,
                        "forbidden_explanation_evidence": [],
                    }],
                    "general_findings": [],
                    "strength_candidates": [],
                    "chapter_contract_observations": {
                        "chapter_function_delivered": True, "must_deliver_satisfied": True,
                        "must_not_deliver_respected": True, "main_change_advanced": True,
                        "main_payoff_delivered": True, "ending_hook_set": True,
                        "fuel_reserved": True, "target_length_met": True,
                    },
                    "tempo_observations": {
                        "starts_in_motion": True, "disruption_interrupts_action": True,
                        "viewpoint_misread_is_actionable": True, "disclosure_cap_respected": True,
                        "unclassified_facts_preserved": True, "formulaic_completion_risk": "low",
                    },
                }, ensure_ascii=False)
            return json.dumps({
                "critic_contract_version": 2,
                "overall_assessment": "结尾已经形成可见变化，但停点之后仍追加说明；人物选择的代价也需要在正文中落地。",
                "strengths": [
                    {"aspect": "场景细节", "detail": "黄昏光线与书店气味建立了具体空间感"},
                    {"aspect": "人物互动", "detail": "女孩进门前的迟疑保留了关系尚未稳定的张力"},
                ],
                "issues": [
                    {"issue_id": "I01", "severity": "high", "issue_type": "stop_state_overrun", "paragraph_ids": ["P010"], "problem": "停点的可见事实成立后又追加行动和情绪说明", "revision_goal": "在停点成立处收束，删去其后的附加说明", "recommended_operation": "tighten"},
                    {"issue_id": "I02", "severity": "medium", "issue_type": "inference_overexplained", "paragraph_ids": ["P008"], "problem": "叙述直接替读者解释人物犹豫的意义", "revision_goal": "保留动作与对话，让读者自行推断", "recommended_operation": "withhold_inference"},
                    {"issue_id": "I03", "severity": "medium", "issue_type": "choice_cost_missing", "paragraph_ids": ["P006", "P012"], "problem": "人物做出选择后没有呈现放弃退路或承担代价", "revision_goal": "用具体行动呈现被放弃的替代方案和新约束", "recommended_operation": "causalize"},
                ],
                "decision": "local_revision",
                "chapter_contract_check": {
                    "chapter_function_delivered": True,
                    "must_deliver_satisfied": True,
                    "must_not_deliver_respected": True,
                    "main_change_advanced": True,
                    "main_payoff_delivered": True,
                    "ending_hook_set": True,
                    "fuel_reserved": True,
                    "target_length_met": True,
                },
                "protected_strengths": [
                    {"paragraph_ids": ["P002"], "reason": "黄昏氛围的描写具体且服务于人物行动，不应为了压缩而删去", "strength_type": "scene_specific_detail"},
                    {"paragraph_ids": ["P005"], "reason": "女孩进门前的停顿留下了读者可参与的推断空间", "strength_type": "reader_inference_gap"},
                ],
                "causal_transition_check": [
                    {
                        "transition_id": "CT01",
                        "trigger_visible": True,
                        "next_action_changed": True,
                        "reader_inference_withheld": True,
                        "forbidden_explanation_found": [],
                        "consequence_visible": True,
                        "next_constraint_preserved": True,
                        "paragraph_ids": [21, 22, 23, 24, 25],
                        "result": "pass",
                        "comment": "编号并列出现后，人物直接改变提问，叙述者没有解释编号关系。"
                    }
                ],
                "tempo_profile_check": {
                    "starts_in_motion": True,
                    "disruption_interrupts_action": True,
                    "viewpoint_misread_is_actionable": True,
                    "disclosure_cap_respected": True,
                    "unclassified_facts_preserved": True,
                    "ending_stops_without_summary": False,
                    "formulaic_completion_risk": "low",
                },
                "stop_state_audit": {
                    "visible_fact_found": True,
                    "first_satisfied_paragraph_id": "P009",
                    "paragraphs_after_stop": ["P010"],
                    "post_stop_new_action_found": True,
                    "post_stop_emotional_summary_found": True,
                    "issue_id": "I01",
                },
                "inference_audit": {
                    "overexplained": True,
                    "paragraph_ids": ["P008"],
                    "quoted_phrases": ["她终于明白了老陈的善意"],
                    "issue_id": "I02",
                },
                "choice_realization_check": [
                    {
                        "transition_id": "CT01",
                        "rejected_alternative_visible": False,
                        "cost_or_commitment_visible": False,
                        "next_constraint_visible": True,
                        "paragraph_ids": ["P006", "P012"],
                        "rejected_alternative_evidence": [],
                        "cost_or_commitment_evidence": [],
                        "next_constraint_evidence": [
                            {
                                "paragraph_id": "P012",
                                "quote": "女孩停在门内，没有立刻走向柜台。",
                                "explanation": "进入书店后，她仍受不主动接近柜台的行动限制。",
                            }
                        ],
                        "issue_id": "I03",
                        "comment": "选择被写出，但放弃的退路和由此产生的责任尚不可见。",
                    }
                ],
            }, ensure_ascii=False)

        # Reviser → targeted fixes
        if "文字修订师" in sp or "reviser" in sp:
            return json.dumps({
                "patches": [
                    {"issue_id": "I01", "operation": "replace", "target_paragraph_ids": ["P003"], "replacement": "老陈把书翻到夹着书签的那一页，却没有继续读。他想起妻子以前总说，一本书读得越慢，里面的世界就越长。窗台上的阿橘还在敲尾巴。他摘下老花镜，用袖口擦了擦镜片。"},
                    {"issue_id": "I02", "operation": "insert_after", "target_paragraph_ids": ["P005"], "replacement": "他摘下老花镜搁在书页上，顺手把桌上那杯已经凉透的茶往旁边挪了挪。"},
                    {"issue_id": "I03", "operation": "insert_after", "target_paragraph_ids": ["P009"], "replacement": "阿橘凑近女孩的球鞋闻了闻，然后抬起头，发出一声很轻的'喵'——像是在打招呼，又像是在替老陈说那句他没有说出口的话。"},
                ],
                "revised_text": "黄昏的光从梧桐叶的缝隙里漏进来...(修订后的完整文本)...",
                "unchanged_ratio": 0.88,
                "introduced_facts": [],
                "contract_verification": {
                    "chapter_function_preserved": True,
                    "must_deliver_preserved": True,
                    "must_not_deliver_respected": True,
                    "main_change_preserved": True,
                    "main_payoff_preserved": True,
                    "ending_hook_preserved": True,
                    "fuel_remains_reserved": True,
                },
            }, ensure_ascii=False)

        # Judge → final verdict
        if "文学评审" in sp or "judge" in sp:
            selected_markers = re.findall(
                r"SELECTED_ISSUES_JSON=(.*?)-->", request.user_prompt, re.DOTALL
            )
            selected_marker = selected_markers[-1] if selected_markers else ""
            selected_issue_ids = re.findall(
                r'"issue_id"\s*:\s*"([^"]+)"', selected_marker
            )
            if not selected_issue_ids:
                selected_issue_ids = ["I01"]
            issue_results = [
                {
                    "issue_id": issue_id,
                    "status": "resolved",
                    "action": "keep_revision",
                    "comment": "模拟修订已处理该选定问题",
                }
                for issue_id in selected_issue_ids
            ]
            return json.dumps({
                "decision": "accept_revision",
                "issue_results": issue_results,
                "new_problems": [],
                "final_text": "（合并修订后的完整文本）",
                "quality_score": 85,
                "revision_became_cleaner_but_flatter": False,
                "author_intent_preserved": True,
                "chapter_contract_completed": True,
                "main_payoff_preserved": True,
                "state_patch": {
                    "facts_added": ["老陈的妻子喜欢慢读书"],
                    "relationships_changed": ["老陈与小满的距离缩短了一步"],
                    "threads_carry_forward": ["小满的妈妈何时来接她"],
                },
                "reader_inference_preserved": True,
                "decision_consequence_preserved": True,
                "narrator_management_reduced": True,
                "necessary_information_lost": False,
                "causal_transition_results": [
                    {
                        "transition_id": "CT01",
                        "original_status": "pass",
                        "revision_status": "pass",
                        "preferred_version": "revision",
                        "comment": "修订丰富了细节，因果链推理空间未受破坏。"
                    }
                ],
            }, ensure_ascii=False)

        return "这是模拟的章节正文内容。故事从这里开始展开..."
