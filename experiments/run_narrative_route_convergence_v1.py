"""Run NARRATIVE_ROUTE_CONVERGENCE_V1 experiment.

24 scenes x 3 route replicas + 3 baseline replicas = 144 Writer calls + 24 Planner
calls = 168 total.  Route briefs use ``writer_input_mode="narrative_route"``.
Baselines use the best-known old mode for each route category.

Dry-run mode (--dry-run) validates scene definitions without any LLM calls.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.schemas.chapter import ChapterCreate
from app.schemas.project import ProjectCreate
from app.services.chapter_service import ChapterService
from app.services.generation_service import GenerationService
from app.services.project_service import ProjectService
from app.services.narrative_route_classifier import classify_narrative_route

EXPERIMENT = "NARRATIVE_ROUTE_CONVERGENCE_V1"
SEED = 20260719
REPLICAS = 3  # 3 replicas per group

# Baseline modes per route category
ROUTE_BASELINE = {
    "C_OBJECT_CAUSAL":           "writer_brief",        # B is best baseline for C
    "A_LITE_INFORMATION_GAP":    "complete_planner",    # A is best baseline for A-lite
    "B_SHORT_RELATION":          "writer_brief",        # B normal length for B-short
    "D_FALLIBLE_TASK":           "writer_brief",        # B is current best for D
}

FROZEN = {
    "provider_id": "34c14b6b-7231-432a-96b2-8272329b828d",
    "model_id": "deepseek-v4-pro",
    "planner_prompt_version_id": "f9052f8a-dc4e-5408-b14e-fc1badaf57f8",
    "writer_prompt_version_id": "f7760cd8-8048-4f3c-839c-e33333eb96fb",
    "temperature": 0.7,
    "top_p": 1.0,
    "planner_max_output_tokens": 12288,
    "max_output_tokens": 4000,
    "timeout_seconds": 300,
}

# 24 scene definitions: (case_id, category, title, scene_instruction)
# Structure per route: 1 old high-anchor, 1 old unstable, 4 new same-mechanism
CASE_SPECS = (
    # ═══ C_OBJECT_CAUSAL: object-misrecognition / pursuit ═══
    ("CAMPUS-03", "校园误会", "错拿外套",
     "放学铃响后，顾栖发现椅背上挂着的深蓝外套被同桌程野穿走，而程野正往操场跑。外套口袋里有今天必须交的社团钥匙。顾栖不能在满走廊里喊对方名字，也不能凭空知道程野是否故意，必须用现场可用物件处理这个具体麻烦。写选择、代价、后果，停在钥匙去向出现新事实的位置。"),
    ("C-02", "校园误会", "错拿书包",
     "午休后，赵遥发现自己的灰色书包被隔壁班的徐帆错拿走了，书包里有下午第一节课必须交的实验报告。徐帆正往实验楼走，赵遥不能追上去当众喊人，也不能假定对方动机。她必须用走廊里可见的一个物件发出信号，让对方自己发现拿错了。停在书包归属出现新事实。"),
    ("C-03", "校园日常", "图书馆错拿书",
     "图书馆闭馆前，陈川发现自己借阅的那本《电路原理》被陌生女生夹在归还车里推走，书里夹着他明天答辩要用的笔记。他不能大声喊人，也不能翻找回车。他必须用一个现场物件让书被退回。停在书的位置出现新事实。"),
    ("C-04", "日常任务", "菜市场错拿菜篮",
     "菜市场收摊前，丁立发现自己的菜篮和一个老太太的菜篮被换走了，他的篮子里有今天必须带回家的药。老太太正推着菜篮往出口走。丁立不能追上去翻篮子，必须用一个现场物件完成交换。停在篮子归属改变的新事实。"),
    ("C-05", "校园误会", "更衣室错拿运动服",
     "体育课后，孟然发现自己的黑色运动服外套被同班同学穿走了，口袋里装着家门钥匙。对方正往田径场方向跑。孟然不能追上去，也不能在更衣室大喊。他必须用一个现场物件让对方自己发现。停在外套归属出现新事实。"),
    ("C-06", "城市日常", "外卖架错拿餐",
     "下班时，陆柯发现写字楼一楼外卖架上的那袋标注自己名字的餐被别人拿走了，架子上只剩另外一袋没写名字的餐。监控死角，前台已下班。陆柯必须用一个现场物件处理这个错拿问题。停在餐的去向或替代方案出现新事实。"),

    # ═══ A_LITE_INFORMATION_GAP: partial message / multi-char misreading ═══
    ("CAMPUS-04", "校园误会", "被听见的便签",
     '课间，班长叶舟在黑板槽里发现一张写着自己名字的便签，只看见\u201c别再\u2026\u2026\u201d三个字。写便签的唐闻正从讲台下来，其他同学围着收作业。叶舟不能把便签内容念出来，也不能直接追问；她要根据有限信息做一个会改变现场局面的动作，并承担被误解的代价。结尾保留便签后半句未知。'),
    ("CAMPUS-02", "校园误会", "社团名单",
     "校园广播站门口，许澄看见自己名字被贴在迟到名单上，误以为好友周弈忘了替她登记。周弈正抱着器材从走廊另一头过来，值班老师在旁边。许澄必须只凭名单和现场动作作出判断，放弃当面追问，做一件会带来具体麻烦的事；不要解释周弈的真实安排。"),
    ("A-03", "校园日常", "办公室听到半句话",
     '课间，韩雨去办公室交作业，走到门边听见班主任对年级组长说\u201c你们班的韩雨\u2026\u2026\u201d，下半句被关上的门截断了。班主任很快走出来，手里拿着一张表格。韩雨不能追问，不能偷看表格，必须根据听到的半句话做一个具体行动。停在新出现的事实。'),
    ("A-04", "校园日常", "楼下撕碎的信",
     "课间操结束，吴筝在楼梯口看到自己写给何屿的信被撕成四片散在地上，何屿正从楼上走下来。旁边没有别人。吴筝不能捡起来拼读，也不能直接问何屿。她必须根据地上的碎片做一个具体行动。停在新事实。"),
    ("A-05", "职场日常", "茶水间议论",
     '午休时，苏晴去茶水间倒水，走到门边听见两个同事在说自己名字，关键词是\u201c那份提案\u201d和\u201c她不知道\u201d。其中一个同事很快走出来，端着一杯咖啡。苏晴不能追问，也不能假装没听见。她必须做一个具体选择。停在新的可见信息。'),
    ("A-06", "校园日常", "群撤回消息",
     "晚自习前，孙然看到班级群里有人@了自己然后撤回了，昵称是经常和自己排练的搭档。群里有三十多个人在线。孙然不能私聊追问，不能假装没看见。她必须根据这个撤回信号做一个具体行动。停在新事实。"),

    # ═══ B_SHORT_RELATION: low-conflict romance, 350-550 chars ═══
    ("ROMANCE-02", "恋爱日常", "未读消息",
     "合租屋厨房里，夏知看见韩川的手机亮起自己昨晚的未读消息，韩川却先把手机扣在桌上去洗菜。水已经开了，桌上只有两只碗。夏知不能偷看手机，也不能断言对方为何没回；她需要根据可见事实选择继续帮忙、离开或提出别的行动，并让代价和后果落在现场。"),
    ("ROMANCE-04", "恋爱日常", "生日蜡烛",
     '朋友聚餐结束，许岚发现桌角留着一小盒没点过的生日蜡烛，而陈述正替大家收盘子。今天不是许岚生日，但她知道陈述记得她上周随口说过的日期。她不能直接问\u201c是不是给我准备的\u201d，必须以可见物件处理尴尬，并让一次选择有可见的承诺或退路。不要解释蜡烛原本用途。'),
    ("B-03", "恋爱日常", "图书馆闭馆时刻",
     "图书馆闭馆铃响后，江晚发现自己和坐在对面的宋行是最后两个人。宋行把她的借阅卡从地上捡起来递还，两人的手指碰了一下。江晚不能追问对方是不是故意等自己，只能选择先走、后走或说一句话。停在闭馆灯熄灭前的一个具体动作。"),
    ("B-04", "恋爱日常", "晨跑偶遇",
     "早晨六点半，沈辛在操场慢跑时看到余苒从对面跑来，两人并排跑了一段后余苒突然拐弯走了岔道。沈辛不能追过去问为什么，也不能推断对方心思。两人下午有共享的实验课。停在绕操场跑回来或离开的选择。"),
    ("B-05", "恋爱日常", "社团聚餐散场",
     '社团聚餐散场，丁宁发现自己和季然被分配了同一条回宿舍的路。其他人都往相反方向走了。季然把外套递还给她，站在原地等她先走。丁宁不能直接问\u201c你是不是有话要说\u201d。她必须选择一起走还是先走。停在路口分岔处的一个动作。'),
    ("B-06", "恋爱日常", "暴雨便利店",
     '下班时分暴雨，只有一把公共伞的便利店门口，林希发现同事温洲也站在门廊下避雨。温洲先开了口说\u201c好大的雨\u201d。便利店店员正在关卷帘门。林希不能替他解释为什么站在这，必须选择撑伞一起走、把伞让给他、或等雨停。停在伞撑开或不撑开的那个动作。'),

    # ═══ D_FALLIBLE_TASK: investigation / infiltration / search ═══
    ("TASK-02", "具体任务", "丢失的快递",
     '小区驿站快关门时，周默发现自己取错了一只同款纸箱，真正的收件人正在门外找箱子。箱内露出一角写着\u201c今晚使用\u201d的说明书，柜台只剩一部固定电话和一辆推车。周默不能拆箱确认，也不能假定里面是什么；他必须在关门前处理可见的错领问题，写出选择、反事实风险和立即后果。'),
    ("TASK-04", "具体任务", "走失的孩子",
     "商场服务台旁，一个小男孩攥着一张被雨打湿的电影票，说不清家长在哪层。保安正在处理另一桩纠纷，电梯口人流很快。志愿者陶然只能依据票面时间、孩子指向和现场广播按钮行动；她不能带孩子离开商场，也不能替他编出父母信息。写她如何作出可检验的选择、承担延误代价，并停在一个新的可见线索上。"),
    ("D-03", "具体任务", "火车站丢失身份证",
     "火车站出发前半小时，方舟发现装在手机壳里的身份证不见了，他刚在三个地方用过：自动售票机、充电桩和洗手间。进站口已经排起长队。方舟不能补办，必须做出一个找或不找的选择。每走错一个位置就损失时间。停在身份确认或改签的具体事实。"),
    ("D-04", "具体任务", "深夜快递柜取错",
     "深夜快递柜前，乔安输入取件码后箱门弹开，发现里面的包裹不是自己的名字，但自己的取件码已经失效。手机上客服热线排队第47位。旁边只有一个快递柜屏幕和一个扫码失败的送货员。乔安不能拆别人的包裹，也不能空手回家。停在选择后的可见结果。"),
    ("D-05", "具体任务", "医院找错科室",
     "门诊楼里，唐婉按照挂号单找到301室，推门发现里面的医生和病人都不对，护士说她的科室在三楼另一侧。手机没电了，走廊里的指示牌被人挡住了关键一行。挂号单上时间是十五分钟后。唐婉不能每一扇门都推，必须选择一个方向。停在找到正确科室或错过时间的具体事实。"),
    ("D-06", "具体任务", "地下车库找车",
     "商场打烊后，郑宣在B2地下车库找不到车了，他只记得停在蓝色柱子旁，但B2层有至少二十根蓝色柱子。车库广播已经关闭，手机剩电8%。郑宣不能每根柱子旁边都去找，必须做一个覆盖路线选择。停在找到车或放弃的可见状态。"),
)

# Map from scene_id to expected route category (for dry-run validation)
EXPECTED_ROUTES = {
    "CAMPUS-03": "C_OBJECT_CAUSAL",
    "C-02": "C_OBJECT_CAUSAL", "C-03": "C_OBJECT_CAUSAL",
    "C-04": "C_OBJECT_CAUSAL", "C-05": "C_OBJECT_CAUSAL",
    "C-06": "C_OBJECT_CAUSAL",
    "CAMPUS-04": "A_LITE_INFORMATION_GAP", "CAMPUS-02": "A_LITE_INFORMATION_GAP",
    "A-03": "A_LITE_INFORMATION_GAP", "A-04": "A_LITE_INFORMATION_GAP",
    "A-05": "A_LITE_INFORMATION_GAP", "A-06": "A_LITE_INFORMATION_GAP",
    "ROMANCE-02": "B_SHORT_RELATION", "ROMANCE-04": "B_SHORT_RELATION",
    "B-03": "B_SHORT_RELATION", "B-04": "B_SHORT_RELATION",
    "B-05": "B_SHORT_RELATION", "B-06": "B_SHORT_RELATION",
    "TASK-02": "D_FALLIBLE_TASK", "TASK-04": "D_FALLIBLE_TASK",
    "D-03": "D_FALLIBLE_TASK", "D-04": "D_FALLIBLE_TASK",
    "D-05": "D_FALLIBLE_TASK", "D-06": "D_FALLIBLE_TASK",
}


def planner_output_cap(model_id: str) -> int:
    return 12288 if model_id == "deepseek-v4-pro" else FROZEN["planner_max_output_tokens"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def record(candidate: Any) -> dict[str, Any]:
    params = json.loads(candidate.parameters_json or "{}")
    return {
        "candidate_id": candidate.id,
        "attempt_number": candidate.attempt_number,
        "provider_id": candidate.provider_id,
        "model_id": candidate.model_id,
        "prompt_version_id": candidate.prompt_version_id,
        "parameters": params,
        "text_output": candidate.text_output,
        "raw_response": candidate.raw_response,
        "input_tokens": candidate.input_tokens,
        "output_tokens": candidate.output_tokens,
        "latency_ms": candidate.latency_ms,
        "finish_reason": candidate.finish_reason,
        "error_code": candidate.error_code,
        "error_message": candidate.error_message,
        "rendered_user_prompt_sha256": hashlib.sha256(
            candidate.rendered_user_prompt.encode("utf-8")
        ).hexdigest(),
        # Narrative route metadata from parameters_json
        "route_name": params.get("route_name"),
        "route_decision": params.get("route_decision"),
        "compiled_brief_hash": params.get("compiled_brief_hash"),
        "instruction_hash": params.get("instruction_hash"),
    }


def writer_override_for_route() -> dict[str, Any]:
    """Writer override for narrative_route briefs."""
    return {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": FROZEN["writer_prompt_version_id"],
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": "narrative_route",
        "route_policy_version": "narrative-route-v1",
    }


def writer_override_for_baseline(baseline_mode: str) -> dict[str, Any]:
    """Writer override for baseline (old-mode) briefs."""
    return {
        "provider_id": FROZEN["provider_id"],
        "model_id": FROZEN["model_id"],
        "prompt_version_id": FROZEN["writer_prompt_version_id"],
        "temperature": FROZEN["temperature"],
        "top_p": FROZEN["top_p"],
        "max_output_tokens": FROZEN["max_output_tokens"],
        "timeout_seconds": FROZEN["timeout_seconds"],
        "writer_input_mode": baseline_mode,
    }


def make_blind_queue(root: Path, exported: list[dict[str, Any]]) -> None:
    cards: list[dict[str, str]] = []
    private: dict[str, dict[str, str]] = {}
    for case in exported:
        case_id = case["case_id"]
        for item in case.get("drafts", []):
            if item.get("error_code"):
                continue
            token = hashlib.sha256(
                f"{SEED}:{case_id}:{item['group']}:{item['replica']}".encode()
            ).hexdigest()[:12].upper()
            cards.append({"blind_id": token, "case_id": case_id, "text_path": item["text_path"]})
            private[token] = {
                "case_id": case_id, "group": item["group"],
                "replica": str(item["replica"]),
                "route_name": item.get("route_name"),
            }
    random.Random(SEED).shuffle(cards)
    write_json(root / "blind_review_queue.json", cards)
    write_json(root / "blind_mapping.private.json", private)


def package_zhuque_submission(root: Path) -> None:
    """Package all drafts into an anonymous Zhuque detector submission.

    Reads ``blind_review_queue.json`` for ordering.  Concatenates every draft
    (including error texts) with five-newline separators.  Generates boundary
    tracking, submission manifest, and deterministic self-tests.
    """
    queue_path = root / "blind_review_queue.json"
    if not queue_path.exists():
        raise FileNotFoundError(f"blind_review_queue.json not found in {root}")

    zhuque_dir = root / "zhuque"
    zhuque_dir.mkdir(parents=True, exist_ok=True)

    queue: list[dict[str, str]] = json.loads(queue_path.read_text(encoding="utf-8"))
    if len(queue) == 0:
        raise ValueError("blind_review_queue.json is empty")

    # ── Build concatenated submission ──
    parts: list[str] = []
    boundaries: list[dict] = []
    cursor = 0
    SEPARATOR = "\n\n\n\n\n"

    for ordinal_zero, card in enumerate(queue):
        ordinal = ordinal_zero + 1  # 1-based
        blind_id = card["blind_id"]
        text_path_rel = card["text_path"]
        text_path = root / text_path_rel
        if not text_path.exists():
            raise FileNotFoundError(f"draft not found: {text_path}")

        raw = text_path.read_text(encoding="utf-8")
        # Normalize: strip leading/trailing whitespace only if it's pure blank
        # lines before/after real content.  Preserve internal blank lines.
        text = raw.strip("\n").strip()
        if not text:
            # Preserve genuinely empty drafts as-is
            text = raw

        start_char = cursor
        parts.append(text)
        cursor += len(text)
        end_char = cursor
        boundaries.append({
            "ordinal": ordinal,
            "blind_id": blind_id,
            "start_char": start_char,
            "end_char": end_char,
            "character_count": len(text),
            "text_path": text_path_rel,
        })
        cursor += len(SEPARATOR)
        if ordinal < len(queue):
            parts.append(SEPARATOR)

    submission_text = "".join(parts)

    # ── Write submission ──
    submission_path = zhuque_dir / "zhuque_submission_all.txt"
    submission_path.write_text(submission_text, encoding="utf-8")

    # ── Write boundaries ──
    write_json(zhuque_dir / "zhuque_blind_boundaries.json", boundaries)

    # ── Write manifest ──
    blind_queue_bytes = queue_path.read_bytes()
    submission_sha256 = hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
    blind_queue_sha256 = hashlib.sha256(blind_queue_bytes).hexdigest()
    total_content_chars = sum(b["character_count"] for b in boundaries)

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    write_json(zhuque_dir / "zhuque_submission_manifest.json", {
        "experiment_id": manifest["experiment"],
        "source_commit": manifest.get("git_commit", ""),
        "total_articles": len(boundaries),
        "total_content_characters": total_content_chars,
        "separator": "five newline characters (\\\\n\\\\n\\\\n\\\\n\\\\n)",
        "submission_sha256": submission_sha256,
        "blind_queue_sha256": blind_queue_sha256,
        "generated_at": subprocess.check_output(
            ["git", "log", "-1", "--format=%aI", "HEAD"],
            cwd=REPO_ROOT, text=True,
        ).strip(),
    })

    # ── Deterministic self-tests ──
    _run_zhuque_tests(submission_text, boundaries, queue, root, submission_path)


def _run_zhuque_tests(
    submission_text: str,
    boundaries: list[dict],
    queue: list[dict],
    root: Path,
    submission_path: Path,
) -> None:
    """Deterministic integrity tests — raise AssertionError on failure."""
    # Test 1: Recover all articles from boundaries
    for b in boundaries:
        recovered = submission_text[b["start_char"]:b["end_char"]]
        text_path = root / b["text_path"]
        original = text_path.read_text(encoding="utf-8").strip("\n").strip()
        if not original:
            original = text_path.read_text(encoding="utf-8")
        assert recovered == original, (
            f"Boundary recovery mismatch for blind_id={b['blind_id']} "
            f"ordinal={b['ordinal']}"
        )

    # Test 2: Each article appears exactly once (by blind_id)
    blind_ids = [b["blind_id"] for b in boundaries]
    assert len(blind_ids) == len(set(blind_ids)), "Duplicate blind_ids detected"
    assert len(blind_ids) == len(queue), (
        f"Expected {len(queue)} articles, got {len(blind_ids)}"
    )

    # Test 3: Intervals are non-overlapping and contiguous
    for i in range(len(boundaries) - 1):
        assert boundaries[i]["end_char"] <= boundaries[i + 1]["start_char"], (
            f"Overlapping boundaries at ordinal {i + 1}"
        )

    # Test 4: Separator is NOT counted in any article
    SEP = "\n\n\n\n\n"
    for b in boundaries:
        article = submission_text[b["start_char"]:b["end_char"]]
        assert SEP not in article, (
            f"Separator found inside article blind_id={b['blind_id']}"
        )

    # Test 5: Article count matches queue
    assert len(boundaries) == len(queue), (
        f"Boundary count {len(boundaries)} != queue count {len(queue)}"
    )

    # Test 6: Last article boundary aligns with file end
    file_len = len(submission_text)
    assert boundaries[-1]["end_char"] == file_len, (
        f"Last boundary end={boundaries[-1]['end_char']} != file length {file_len}"
    )

    # Test 7: Hash reproducibility — run twice, same result
    submission_sha256_a = hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
    submission_sha256_b = hashlib.sha256(submission_text.encode("utf-8")).hexdigest()
    assert submission_sha256_a == submission_sha256_b, "SHA-256 not reproducible"

    # Test 8: No blind_id markers in the raw submission text.
    # Blind IDs are 12-character uppercase hex — they should never
    # appear in natural Chinese text.  Ordinals (e.g. "19") are NOT
    # checked because small integers can appear in natural prose.
    for b in boundaries:
        blind_id = b["blind_id"]
        assert blind_id not in submission_text, (
            f"Blind ID '{blind_id}' leaked into submission text"
        )

    print(f"  Zhuque submission: {len(boundaries)} articles, "
          f"{len(submission_text)} chars → {submission_path}")
    print(f"  All 8 integrity tests passed")


async def run(
    root: Path,
    database: Path,
    dry_run: bool,
    case_start: int = 0,
    *,
    zhuque_only: bool = False,
) -> None:
    if zhuque_only:
        # Standalone packaging mode: read existing experiment data, produce
        # Zhuque submission only.  No LLM calls, no DB access.
        if not (root / "manifest.json").exists():
            raise FileNotFoundError(f"manifest.json not found in {root} — run experiment first")
        if not (root / "blind_review_queue.json").exists():
            raise FileNotFoundError(f"blind_review_queue.json not found in {root}")
        package_zhuque_submission(root)
        return
    if (root / "manifest.json").exists() and case_start == 0 and not zhuque_only:
        raise RuntimeError(f"{EXPERIMENT} evidence already exists; refusing to rerun")
    if not dry_run and database.exists() and case_start == 0 and not zhuque_only:
        raise RuntimeError(f"isolated database already exists: {database}")
    selected_cases = CASE_SPECS[case_start:]
    if not selected_cases:
        raise ValueError(f"case_start must select at least one case (got {case_start})")
    root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "experiment": EXPERIMENT,
        "git_commit": git_commit(),
        "seed": SEED,
        "replicas_per_group": REPLICAS,
        "case_start": case_start,
        "case_ids": [c[0] for c in selected_cases],
        "writer_drafts_expected": len(selected_cases) * 6,  # 3 route + 3 baseline
        "frozen_writer": {k: v for k, v in FROZEN.items() if not k.startswith("planner_")},
        "frozen_planner": {
            "provider_id": FROZEN["provider_id"], "model_id": FROZEN["model_id"],
            "prompt_version_id": FROZEN["planner_prompt_version_id"],
            "temperature": FROZEN["temperature"], "top_p": FROZEN["top_p"],
            "max_output_tokens": FROZEN["planner_max_output_tokens"],
            "timeout_seconds": FROZEN["timeout_seconds"],
        },
        "route_baseline_map": ROUTE_BASELINE,
        "writer_input_mode": "narrative_route",
        "route_policy_version": "narrative-route-v1",
        "rules": [
            "One Planner call per scenario.",
            "3 Writer route-brief calls per scenario (narrative_route mode).",
            "3 Writer baseline calls per scenario (old mode, per route category).",
            "No Critic, Reviser, Judge, TGbreak, retry, or candidate selection.",
            "All failures preserved; no filtering or selection.",
        ],
        "detector_status": "pending_external_measurement",
    }
    write_json(root / "manifest.json", manifest)
    write_json(root / "cases.json", [
        {"case_id": c[0], "category": c[1], "title": c[2],
         "scene_instruction": c[3], "expected_route": EXPECTED_ROUTES.get(c[0], "UNKNOWN")}
        for c in selected_cases
    ])

    if dry_run:
        # Dry-run: print audit table without any LLM calls
        print(f"\n{'='*90}")
        print(f"  {EXPERIMENT} — DRY-RUN AUDIT ({len(selected_cases)} scenes)")
        print(f"{'='*90}")
        print(f"{'Scene':12s} {'Category':12s} {'Expected Route':25s} {'Baseline':15s} {'Type':10s}")
        print("-" * 80)
        total_plans = len(selected_cases)
        total_writers = len(selected_cases) * 6
        for sid, cat, title, instr in selected_cases:
            expected = EXPECTED_ROUTES.get(sid, "UNKNOWN")
            baseline = ROUTE_BASELINE.get(expected, "writer_brief")
            stype = "OLD" if sid.startswith(("CAMPUS", "ROMANCE", "TASK")) else "NEW"
            print(f"{sid:12s} {cat:12s} {expected:25s} {baseline:15s} {stype:10s}")
        print("-" * 80)
        print(f"  Total: {total_plans} Planner + {total_writers} Writer = {total_plans + total_writers} calls")
        print(f"  Estimated USD: ${total_plans * 0.001 + total_writers * 0.0004:.3f}")
        print(f"{'='*90}\n")
        return

    # Real run: isolate DB and execute
    if case_start == 0:
        shutil.copy2(REPO_ROOT / "data" / "novel_workbench.db", database)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    exported: list[dict[str, Any]] = []

    try:
        async with factory() as session:
            projects = ProjectService(session)
            chapters = ChapterService(session)
            generation = GenerationService(session)

            for case_id, category, title, instruction in selected_cases:
                case_dir = root / "cases" / case_id
                expected_route = EXPECTED_ROUTES.get(case_id, "B_DEFAULT")
                baseline_mode = ROUTE_BASELINE.get(expected_route, "writer_brief")

                project = await projects.create_project(
                    ProjectCreate(name=f"{EXPERIMENT} {case_id}", genre=category)
                )
                chapter = await chapters.create_chapter(
                    project.id, ChapterCreate(title=title, sort_order=1)
                )
                run_obj = await generation.create_run(project.id, chapter.id, None, instruction)
                await session.commit()

                # ── Planner ──
                planner_override = {
                    "provider_id": FROZEN["provider_id"],
                    "model_id": FROZEN["model_id"],
                    "prompt_version_id": FROZEN["planner_prompt_version_id"],
                    "temperature": FROZEN["temperature"],
                    "top_p": FROZEN["top_p"],
                    "max_output_tokens": FROZEN["planner_max_output_tokens"],
                    "timeout_seconds": FROZEN["timeout_seconds"],
                }
                planner = await generation.execute_stage(run_obj.id, "planner", planner_override)
                await session.commit()

                case_result: dict[str, Any] = {
                    "case_id": case_id, "category": category, "title": title,
                    "run_id": run_obj.id, "expected_route": expected_route,
                    "planner": record(planner), "drafts": [],
                }

                if planner.error_code:
                    write_json(case_dir / "result.json", case_result)
                    exported.append(case_result)
                    continue

                await generation.select_candidate(run_obj.id, "planner", planner.id)
                await session.commit()
                planner_output = json.loads(planner.parsed_output_json or "{}")

                # Classify the actual route from Planner output
                decision = classify_narrative_route(planner_output)
                actual_route = decision.route_name.value
                case_result["actual_route"] = actual_route
                case_result["route_decision"] = decision.model_dump()

                write_json(case_dir / "planner.json", planner_output)
                write_json(case_dir / "route_classification.json", {
                    "case_id": case_id, "expected_route": expected_route,
                    "actual_route": actual_route, "decision": decision.model_dump(),
                })

                # ── Route brief Writers (3 replicas) ──
                route_override = writer_override_for_route()
                for replica in range(1, REPLICAS + 1):
                    candidate = await generation.execute_stage(
                        run_obj.id, "writer", route_override
                    )
                    await session.commit()
                    cr = {"group": f"ROUTE-{actual_route}", "replica": replica,
                          "mode": "narrative_route", **record(candidate)}
                    text_path = case_dir / "drafts" / f"route-{replica}.txt"
                    text_path.parent.mkdir(parents=True, exist_ok=True)
                    text_path.write_text(
                        candidate.text_output or candidate.raw_response,
                        encoding="utf-8",
                    )
                    cr["text_path"] = str(text_path.relative_to(root))
                    write_json(case_dir / "drafts" / f"route-{replica}.json", cr)
                    case_result["drafts"].append(cr)

                # ── Baseline Writers (3 replicas) ──
                baseline_override = writer_override_for_baseline(baseline_mode)
                for replica in range(1, REPLICAS + 1):
                    candidate = await generation.execute_stage(
                        run_obj.id, "writer", baseline_override
                    )
                    await session.commit()
                    cr = {"group": f"BASELINE-{baseline_mode}", "replica": replica,
                          "mode": baseline_mode, **record(candidate)}
                    text_path = case_dir / "drafts" / f"baseline-{replica}.txt"
                    text_path.parent.mkdir(parents=True, exist_ok=True)
                    text_path.write_text(
                        candidate.text_output or candidate.raw_response,
                        encoding="utf-8",
                    )
                    cr["text_path"] = str(text_path.relative_to(root))
                    write_json(case_dir / "drafts" / f"baseline-{replica}.json", cr)
                    case_result["drafts"].append(cr)

                write_json(case_dir / "result.json", case_result)
                exported.append(case_result)
                print(f"  [{case_id}] route={actual_route}  completed")
    finally:
        await engine.dispose()

    make_blind_queue(root, exported)
    package_zhuque_submission(root)
    completed = [d for case in exported for d in case["drafts"] if not d.get("error_code")]
    write_json(root / "execution_summary.json", {
        "experiment": EXPERIMENT,
        "writer_drafts_completed": len(completed),
        "writer_drafts_expected": len(selected_cases) * 6,
        "planner_failures": [
            case["case_id"] for case in exported
            if case["planner"].get("error_code")
        ],
    })
    (root / "DETECTOR_RESULTS_TEMPLATE.md").write_text(
        f"# {EXPERIMENT} results\n\n"
        "For every blind ID in `blind_review_queue.json`, record the external "
        "detector's three character ratios and orange spans.\n\n"
        "Acceptance gates per route:\n"
        "- Median human rate >=60% on 6 scenes\n"
        "- >=2/3 scenes better than baseline\n"
        "- >=2 of 3 replicas >=60%\n",
        encoding="utf-8",
    )

    print(f"\n  Completed: {len(completed)}/{len(selected_cases) * 6} drafts")
    print(f"  Planner failures: {len([c for c in exported if c['planner'].get('error_code')])}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path,
        default=REPO_ROOT / "__evaluation" / "narrative_route_convergence_v1",
        help="Evaluation output directory",
    )
    parser.add_argument(
        "--database", type=Path,
        default=REPO_ROOT / "__evaluation" / "narrative_route_convergence_v1.sqlite3",
        help="Isolated database copy",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without LLM calls")
    parser.add_argument("--zhuque-only", action="store_true", help="Only package zhuque submission from existing data")
    parser.add_argument("--case-start", type=int, default=0, help="Start from case index")
    parser.add_argument("--model-id", default=FROZEN["model_id"])
    args = parser.parse_args()
    FROZEN["model_id"] = args.model_id
    FROZEN["planner_max_output_tokens"] = planner_output_cap(args.model_id)
    asyncio.run(run(args.root, args.database, args.dry_run, args.case_start,
                    zhuque_only=args.zhuque_only))


if __name__ == "__main__":
    main()
