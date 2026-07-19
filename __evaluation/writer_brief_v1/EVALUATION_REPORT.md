# WRITER_BRIEF_AB_TEST_V1 Evaluation Report

## Scope and frozen conditions

This compares the saved historical baseline Writer candidate (full Planner JSON
input) with one new Writer candidate produced from the same saved Planner
candidate through the deterministic WriterBriefCompiler. All calls used the
saved Writer PromptVersion, provider/model, temperature, top_p, output limit,
and timeout. Planner, Critic, Reviser, Judge, TGbreak, retry, and candidate
selection were not called. The four new candidates live only in the isolated
experiment database.

The earlier `WRITER_BRIEF_AB_TEST_V1_PRECHECK_FAILED` record was an
engineering-precheck failure, not a prose result: it asked for the
noncanonical `unknown_information` name and required conditional assumption
fields to be nonempty. This run uses the canonical `unknown_facts` contract
and its shared compiler/preflight validator.

## Preflight

`WRITER_BRIEF_PRECHECK_4_OF_4_PASSED`.

Each brief has the canonical fields, excludes Planner-only fields, appears at
the end of the Writer user prompt, and has zero active-project facts (within
the five-fact cap).

| Case | Planner Candidate | Baseline Writer | vNext Writer | Brief chars / est. tokens | Preflight |
| --- | --- | --- | --- | ---: | --- |
| CASE-001 | d9d44c85-72dd-4766-a007-1f64adb867c3 | ee2c90be-a734-4a76-a119-92a5139f470e | 37600094-3ae6-4443-aff3-290238446594 | 1,035 / 259 | pass |
| CASE-002 | ab3461b9-d2d0-42a0-b594-237432670478 | ac5f95e7-aebc-442b-9c0c-3a3ab5e8f88c | 59977758-c54a-4bb4-9f7b-be8043474f5b | 872 / 218 | pass |
| CASE-003 | ea5a7149-2c4e-4525-b83b-f8de428dcdee | 82c12b37-e209-4043-a44d-d0394c3e2984 | 2b58454a-9865-4c10-8c27-e1c096726cce | 812 / 203 | pass |
| CASE-004 | 8ca4df8f-2d8a-43bf-98f2-27a6c86a3484 | 74e31b42-c427-4228-a4b5-6971f38fe087 | 9ff06242-d78d-4836-b9ec-e8f2706a3a0e | 831 / 208 | pass |

## Blind evaluation

Blind decisions were completed from `blind_pair.json` before opening each
private source mapping. After that mapping: CASE-001 B = vNext,
CASE-002 A = vNext, CASE-003 B = vNext, and CASE-004 A = vNext.

| Case | Blind preference | vNext result | Main evidence |
| --- | --- | --- | --- |
| CASE-001 | B | win | B reaches the planned physical stop: “鼻尖碰到了女孩的手背……手没有缩回去”; A only says “几乎要碰到”. |
| CASE-002 | B | loss | B avoids A's unplanned morning-report and spare-button additions while preserving the same visible resolution. |
| CASE-003 | B | win | B stops at “她握着钥匙站在走廊里，顾言已经不见了”; A continues into speculation after that point. |
| CASE-004 | A | win | A holds on the teacher's parent demand and Zhao leaving; B introduces an unplanned mother/sister obligation and continues past the stop. |

Blind threshold: **pass** — vNext wins 3/4 and loses 1/4.

## Planner-contract audit

`missing` and `contradicted` are counted as key errors; `partial` is retained
as an audit finding rather than counted as a key error.

| Case | Baseline key errors | vNext key errors | Better contract execution |
| --- | ---: | ---: | --- |
| CASE-001 | 2 | 1 | vNext |
| CASE-002 | 0 | 0 | tie |
| CASE-003 | 2 | 0 | vNext |
| CASE-004 | 1 | 0 | vNext |

Primary threshold: **pass** — vNext has fewer key Planner-contract errors in
3/4 cases. Full per-text, sentence-cited audits are in `results/CASE-001.json`
through `results/CASE-004.json`.

## Safety audit

- Important Planner-external facts in vNext: 0/4.
- vNext stop fact accurate: 4/4.
- CASE-002's vNext adds a duty/report and spare-button detail; CASE-004's
  baseline adds a mother/sister obligation. These are recorded in the result
  evidence and do not count against vNext's safety gate.

Safety threshold: **pass**.

## Tokens and latency

| Case | Baseline input / output / latency | vNext input / output / latency |
| --- | --- | --- |
| CASE-001 | 3,033 / 467 / 10,373 ms | 1,413 / 520 / 11,839 ms |
| CASE-002 | 2,515 / 436 / 8,673 ms | 1,270 / 523 / 13,171 ms |
| CASE-003 | 2,275 / 580 / 9,784 ms | 1,209 / 560 / 11,523 ms |
| CASE-004 | 2,439 / 811 / 13,078 ms | 1,209 / 607 / 14,291 ms |
| Total | 10,262 / 2,294 / 41,908 ms | 5,101 / 2,210 / 50,824 ms |

The vNext inputs are lower in all four cases. This four-call sample does not
show a latency improvement.

## Overall decision

**PASSED.** The predeclared primary, blind, and safety gates all pass for the
four frozen cases.

## Evidence supports

On these four saved Planner outputs and fixed Writer settings, the canonical
deterministic WriterBrief can reduce input size and meet the frozen Writer
quality/contract gates without reintroducing full Planner JSON.

## Evidence does not support

This does not establish performance outside these four cases, establish a
latency benefit, or establish any claim about Critic, Reviser, Judge, or the
full five-stage pipeline; those stages were intentionally absent from this
experiment.
