import time
import json
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

        return LlmResponse(
            text=text,
            input_tokens=len(request.system_prompt + request.user_prompt) // 3,
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
                "scene_goal": goal,
                "location": loc,
                "start_time": "黄昏" if is_twilight else "深夜",
                "characters": chars or [
                    {"name": "主角", "goal": "推进故事", "known": ["当前处境"], "unknown": ["对方身份", "隐藏的真相"], "mistaken_beliefs": ["事情会按预期发展"], "constraints": ["不能暴露意图"]}
                ],
                "pressure": "时间在流逝，黄昏即将结束" if is_twilight else "气氛逐渐紧张",
                "turning_point": "小女孩开口说第一句话" if "老陈" in up else "一个意外的眼神交汇",
                "end_condition": "建立了最初的信任" if "老陈" in up else "雨停了",
                "forbidden": ["不能煽情", "不能用巧合解决冲突"],
            }, ensure_ascii=False)

        # Writer → narrative prose (returns text, not JSON)
        if "小说家" in sp:
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
        if "文学编辑" in sp or "critic" in sp:
            return json.dumps({
                "overall_assessment": "整体氛围营造出色，黄昏光线的描写有质感。但叙事节奏在中段略微松散。",
                "strengths": [
                    {"aspect": "环境描写", "detail": "光线与气味的感官细节丰富，营造了强烈的沉浸感"},
                    {"aspect": "猫的意象", "detail": "阿橘作为情感线索运用得当，动作细节传递了微妙情绪"},
                ],
                "issues": [
                    {"issue_id": "I01", "severity": "low", "issue_type": "pacing", "paragraph_ids": ["P003"], "problem": "老陈内心独白偏长，打断了外部动作流", "revision_goal": "将部分回忆分散到后续对话中自然带出"},
                    {"issue_id": "I02", "severity": "medium", "issue_type": "dialogue", "paragraph_ids": ["P006"], "problem": "'进来坐'三字过于简练，可加一两个小动作丰富层次", "revision_goal": "在'进来坐'之前添加一个小动作，如摘下老花镜或挪开茶杯"},
                    {"issue_id": "I03", "severity": "low", "issue_type": "detail", "paragraph_ids": ["P009"], "problem": "猫的反应过于简单，缺少具体动作细节", "revision_goal": "添加阿橘的嗅觉或声音细节，丰富猫的角色形象"},
                ],
                "decision": "local_revision",
                "protected_strengths": [
                    {"paragraph_ids": ["P001", "P002"], "reason": "黄昏氛围的描写已臻完美，情绪基调准确，不应修改"},
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
            }, ensure_ascii=False)

        # Judge → final verdict
        if "文学评审" in sp or "judge" in sp:
            return json.dumps({
                "decision": "accept_revision",
                "issue_results": [
                    {"issue_id": "I01", "status": "resolved", "action": "keep_revision", "comment": "修订后内心独白更含蓄，不打断叙事流"},
                    {"issue_id": "I02", "status": "resolved", "action": "keep_revision", "comment": "小动作丰富了老陈的形象"},
                    {"issue_id": "I03", "status": "resolved", "action": "keep_revision", "comment": "猫的细节让场景更具温度"},
                ],
                "new_problems": [],
                "final_text": "（合并修订后的完整文本）",
                "quality_score": 8.5,
                "state_patch": {
                    "facts_added": ["老陈的妻子喜欢慢读书"],
                    "relationship_changes": ["老陈与小满的距离缩短了一步"],
                    "unresolved_threads": ["小满的妈妈何时来接她"],
                },
            }, ensure_ascii=False)

        return "这是模拟的章节正文内容。故事从这里开始展开..."
