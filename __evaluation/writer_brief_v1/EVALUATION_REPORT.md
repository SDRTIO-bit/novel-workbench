# WRITER_BRIEF_AB_TEST_V1 Evaluation Report

## Execution

Cases stopped before model invocation: CASE-001, CASE-002, CASE-003, CASE-004.

The frozen Compiler was audited without modification. It has no declared active-project-facts cap and does not emit explicit unknown_information, current_assumption, or assumption_basis fields. These violate the preflight contract for every case. No vNext Writer call, blind comparison, or contract comparison was performed; no Planner or later-stage call occurred.

| Case | Planner Candidate | Baseline Writer Candidate | vNext Writer Candidate | Brief characters | Writer tokens / latency | Anonymous mapping | Status |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| CASE-001 | d9d44c85-72dd-4766-a007-1f64adb867c3 | ee2c90be-a734-4a76-a119-92a5139f470e | — | 1848 | — | — | stopped_preflight |
| CASE-002 | ab3461b9-d2d0-42a0-b594-237432670478 | ac5f95e7-aebc-442b-9c0c-3a3ab5e8f88c | — | 1528 | — | — | stopped_preflight |
| CASE-003 | ea5a7149-2c4e-4525-b83b-f8de428dcdee | 82c12b37-e209-4043-a44d-d0394c3e2984 | — | 1411 | — | — | stopped_preflight |
| CASE-004 | 8ca4df8f-2d8a-43bf-98f2-27a6c86a3484 | 74e31b42-c427-4228-a4b5-6971f38fe087 | — | 1432 | — | — | stopped_preflight |

No anonymous mapping exists because a blind pair is only valid after both permitted Writer texts exist.

## Preflight failures

| Case | Failed condition |
| --- | --- |
| CASE-001 | WRITER_BRIEF_FACT_CAP_UNDEFINED; WRITER_BRIEF_REQUIRED_FIELD_MISSING:unknown_information; WRITER_BRIEF_REQUIRED_FIELD_MISSING:current_assumption; WRITER_BRIEF_REQUIRED_FIELD_MISSING:assumption_basis |
| CASE-002 | WRITER_BRIEF_FACT_CAP_UNDEFINED; WRITER_BRIEF_REQUIRED_FIELD_MISSING:unknown_information; WRITER_BRIEF_REQUIRED_FIELD_MISSING:current_assumption; WRITER_BRIEF_REQUIRED_FIELD_MISSING:assumption_basis |
| CASE-003 | WRITER_BRIEF_FACT_CAP_UNDEFINED; WRITER_BRIEF_REQUIRED_FIELD_MISSING:unknown_information; WRITER_BRIEF_REQUIRED_FIELD_MISSING:current_assumption; WRITER_BRIEF_REQUIRED_FIELD_MISSING:assumption_basis |
| CASE-004 | WRITER_BRIEF_FACT_CAP_UNDEFINED; WRITER_BRIEF_REQUIRED_FIELD_MISSING:unknown_information; WRITER_BRIEF_REQUIRED_FIELD_MISSING:current_assumption; WRITER_BRIEF_REQUIRED_FIELD_MISSING:assumption_basis |

## Overall decision

**NOT PASSED — engineering preflight failed.** The primary, blind, and safety thresholds cannot be evaluated because the required WriterBrief input contract was not satisfied.

## Evidence supports

The current implementation deterministically omits full Planner JSON and keeps the WriterBrief at the end of the Writer prompt. It does not yet provide all fields required by this frozen A/B protocol.

## Evidence does not support

It does not support either adopting or rejecting WriterBrief as the default based on prose quality or Planner-contract performance: no permitted Writer comparison was run.
