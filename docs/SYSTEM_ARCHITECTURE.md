# SYSTEM_ARCHITECTURE

Last reviewed: 2026-06-25 (Asia/Seoul)

이 문서는 `Report Guard` MCP 서버의 전체 시스템 아키텍처, Tool pipeline, 외부 연동 경계, 성능/보안 흐름, 병렬 개발용 module-level dependency tree를 정의한다. 구현 언어와 framework는 고정하지 않는다. 구현자는 이 문서를 기준으로 모듈 경계와 개발 순서를 잡되, 세부 문법과 패키지 구조는 선택한 stack에 맞게 옮긴다.

상위 기준 문서:

- [`PROJECT_SILHOUETTE.md`](./PROJECT_SILHOUETTE.md)
- [`DEVELOPMENT_CONDITIONS.md`](./DEVELOPMENT_CONDITIONS.md)

## 1. System Goals

### 1.1 목표

- 대학생이 report류 문서를 제출하기 전에 기본 품질, 출처, 표절 위험, 구조, 필수 항목을 점검할 수 있는 PlayMCP 공개 MCP 서버를 제공한다.
- MCP 서버명은 `Report Guard`로 한다.
- 한국어/영어 문서를 모두 고려한다.
- PlayMCP 예선 제출 조건에 맞는 remote Streamable HTTP MCP 서버로 설계한다.
- Tool 결과는 LLM이 최종 사용자 답변을 만들기 쉬운 정제된 구조와 짧은 Markdown 요약을 함께 제공한다.
- 문서 본문, 이메일, API key, 인증 정보 등 민감 정보는 저장하지 않는다.

### 1.2 비목표

- 학교, 교수자, 학술윤리위원회, 법률 전문가의 최종 판단을 대체하지 않는다.
- 비공개 DB, 학교 내부 제출물, 유료 논문 DB 전체를 검색하지 않는다.
- 표절 회피, 출처 조작, 탐지 우회 방법을 제공하지 않는다.
- PlayMCP가 현재 다루지 않는 MCP Resource/Prompt 기능에 사용자-facing 기능을 의존하지 않는다.
- 구현 언어, web framework, package manager, cloud image registry를 이 문서에서 고정하지 않는다.

## 2. Runtime Context

### 2.1 배포 및 MCP context

- 배포 대상은 PlayMCP in KC에서 발급받은 공개 Endpoint URL이다.
- 등록/큐레이션 surface는 PlayMCP(예선)와 Kakao Tools(본선 Toolbox/Widget)이며, 실제 서버를 소비하는 target client app은 ChatGPT for Kakao와 OpenClaw다. 서버는 특정 client에 종속되지 않는 client-agnostic 설계를 유지한다(host LLM은 ChatGPT/Claude/OpenClaw 모두 가능).
- MCP transport는 Streamable HTTP만 사용한다.
- 서버는 MCP protocol version `2025-03-26` 이상, `2025-11-25` 이하와 호환되어야 한다.
- 서버는 remote public URL에서 동작해야 하며 stdio-only 구현은 허용하지 않는다.
- Stateless 동작을 기본값으로 한다. 세션은 구현하지 않는 것을 원칙으로 하며, 필요 시 인증/만료/스케일아웃 정책을 별도 문서로 승인받는다.
- PlayMCP 심사 전 MCP Inspector, PlayMCP `정보 불러오기`, 임시 등록 후 AI 채팅 테스트를 통과해야 한다.

### 2.2 Tool surface

Report Guard는 7개 Tool을 제공한다.

| Public Tool name | Tool 역할 | Pipeline module | 핵심 책임 |
| --- | --- | --- | --- |
| `count_document_units` | 글자수/단어수/문장수/문단수 검사 | `pipelines/counts` | 문서 통계 산출 |
| `check_document_spelling` | 문서 맞춤법 검사 | `pipelines/spellcheck` | 맞춤법 오류와 수정 제안 생성 |
| `check_document_citations` | 문서 출처(Citation) 검사 | `pipelines/citation` | citation 제목 검증, KCI/Semantic Scholar/Crossref 연동, 검색 지침 반환 |
| `check_document_plagiarism` | 문서 표절 검사 | `pipelines/plagiarism` | Naver Search API 질의, 유사도 산출, 공개 검색 한계 고지 |
| `get_writing_structure_guidance` | 문서 구조 검사 (구조 추천/개선) | `pipelines/writing_structure` | `GOOD_WRITING.md` 기반 평가 지침 반환 |
| `get_required_fields_guidance` | 문서 필수 항목 권장 | `pipelines/required_fields` | `TO_HAVE.md` 기반 필수/권장 항목 점검 지침 반환 |
| `run_full_report_check` | 전체 검사 | `pipelines/full_check` | 위 6개 pipeline을 조합하고 24k 이하 요약 반환 |

Public Tool name은 위 표를 따른다. 모든 이름은 `[A-Za-z0-9_-]`, 1~128자, 중복 없음, `kakao` 미포함 조건을 만족한다. Tool description에는 `Report Guard(리포트 가드)` 서비스명을 포함한다.

## 3. Core Architecture

### 3.1 Layer overview

```text
Client apps (MCP hosts): ChatGPT for Kakao / OpenClaw
        |   (registered & curated via PlayMCP 예선 / Kakao Tools 본선)
        v
Streamable HTTP MCP endpoint
        |
        v
mcp_transport
        |
        v
tool_registry + schema validation
        |
        v
pipeline_orchestrator
        |
        +--> pipelines/counts
        +--> pipelines/spellcheck
        +--> pipelines/citation
        +--> pipelines/plagiarism
        +--> pipelines/writing_structure
        +--> pipelines/required_fields
        +--> pipelines/full_check
        |
        v
result_formatter
        |
        v
MCP Tool response: TextContent + structured result
```

Cross-cutting modules wrap or support the flow without owning feature logic:

- `config`: environment variables, limits, feature flags.
- `schemas`: shared input/output contracts and validators.
- `errors`: normalized error and partial-result model.
- `security`: input sanitization, secret redaction, SSRF-safe URL policy.
- `logging`: redacted operational logs only.
- `rate_limit`: per-client or per-process invocation guard.
- `observability`: latency, count, error-class metrics without document body.

### 3.2 Module responsibilities

| Module | Responsibility | Must not do |
| --- | --- | --- |
| `mcp_transport` | Streamable HTTP MCP lifecycle, JSON-RPC mapping, Tool call envelope handling | Feature-specific analysis, external API calls |
| `tool_registry` | Expose Tool metadata, input schema, annotations, output schema references | Own business logic or call external clients |
| `pipeline_orchestrator` | Route validated Tool calls to the correct pipeline, enforce timeout budget, collect partial results | Parse MCP protocol details |
| `pipelines/*` | Feature-specific document checks | Store raw document text |
| `clients/*` | Isolated outbound API access with timeout, quota, retry/backoff policy | Depend on MCP transport or orchestrator |
| `guidance_provider` | Load static guidance docs such as `CITATION_CHECK.md` | Mutate guidance at runtime |
| `result_formatter` | Compress findings, normalize status, enforce response size | Perform feature analysis |

## 4. Request and Response Pipeline

### 4.1 Common request flow

Every Tool call follows this sequence.

1. `mcp_transport` receives a Streamable HTTP MCP `tools/call` request.
2. `tool_registry` resolves the Tool and validates `inputSchema`.
3. `security` redacts secrets, rejects unsafe inputs, and applies size limits.
4. `rate_limit` checks invocation policy.
5. `pipeline_orchestrator` starts a per-call timeout budget.
6. The selected `pipelines/*` module runs with transient in-memory input only.
7. External clients are called only through `clients/*` boundaries.
8. Pipeline returns normalized findings, limitations, and next actions.
9. `result_formatter` compresses output below 24k and produces MCP-compatible content.
10. `mcp_transport` returns TextContent plus structured result where supported.

### 4.2 Common input shape

This is a behavior-level contract, not a language-specific type.

```text
ToolInput
- document_text: optional string
- citation_titles: optional list of strings
- user_email: optional string
- language: optional "ko" | "en" | "auto"
- options:
  - include_spaces: optional boolean
  - sentence_chunk_size: optional integer
  - similarity_threshold: optional number
  - max_queries: optional integer
  - max_results: optional integer
```

Rules:

- Tool-specific schemas must accept only fields that Tool needs.
- `document_text` is required for counts, spell-check, plagiarism, and full-check.
- `citation_titles` is required for standalone citation check. In full-check, `citation_titles` is optional; if absent, citation check is skipped and reported in `skipped_pipelines`.
- `user_email` is optional and used only for Crossref `mailto`.
- Empty-input Tools for writing structure and required fields must still define an explicit empty object schema.

### 4.3 Common output shape

```text
ToolOutput
- status: "ok" | "partial" | "no_findings" | "invalid_input" | "external_error" | "internal_error"
- summary: short user-facing Markdown summary
- findings: list of normalized finding objects
- metrics: optional structured counts or timings
- limitations: list of user-visible limitations
- next_actions: list of safe improvement steps
- links: optional list of source/result URLs
- partial_failures: optional list of failed sub-pipelines or external calls
```

Rules:

- `status` must be normalized across all pipelines.
- Raw upstream API responses are never returned.
- Raw document text is never echoed back in full.
- Response must stay under 24k.
- Error output must not include stack traces, secrets, internal network names, or raw request headers.

## 5. Feature Pipelines

### 5.1 `pipelines/counts`

Input:

- `document_text`
- optional `language`
- optional `include_spaces`

Flow:

1. Normalize line endings and Unicode whitespace.
2. Use `text/segmentation` to compute paragraph, sentence, word, and character boundaries.
3. Return four counts: character count, word count, sentence count, paragraph count.
4. Return `-1` for a count only when the specific count cannot be computed, with reason.

Dependencies:

- `text/segmentation`
- `schemas`
- `errors`
- `result_formatter`

No external API calls.

### 5.2 `pipelines/spellcheck`

Input:

- `document_text`
- optional `language`

Flow:

1. Segment document into bounded units.
2. Call the v1 `providers/spellcheck` implementation (a free-of-charge local library or a free no-auth online service such as hanspell) through a provider interface.
3. Convert provider-specific output into pairs of original sentence and suggested correction.
4. Mark provider uncertainty for names, citations, domain terms, and quoted text.
5. Return `no_findings` when no spelling issue is detected.

Dependencies:

- `text/segmentation`
- `providers/spellcheck`
- `schemas`
- `errors`
- `result_formatter`

Provider constraints:

- Provider must be legally usable.
- Provider must be free of charge for v1 (no paid API or paid quota). A free local library or a free no-auth online service (e.g. hanspell) is allowed.
- If the provider makes external calls, its adapter must apply timeout, UTF-8 encoding, outbound URL allowlist/SSRF checks, and normalized error classes (same outbound-safety rules as `clients/*`), send only minimal text units, disclose the external transmission, and the Tool is `openWorldHint: true`. A fully local provider performs no external call and is `openWorldHint: false`.
- An online scraping-based provider (e.g. hanspell) may be unstable; on failure return a no-result/`partial`/`external_error` state instead of crashing.
- Provider must not persist document text.
- Provider timeout must fit inside the 3,000ms p99 requirement or return partial results.

### 5.3 `pipelines/citation`

Input:

- `citation_titles`
- optional `user_email`
- optional `max_results`

Flow (email-independent; per-title language routing, lookups run concurrently):

1. Validate and normalize citation titles; extract a bare DOI and a clean title
   from each raw reference string.
2. Korean title → `clients/kci` (KCI, Korea Citation Index). Exact normalized-title
   match → "KCI 확인됨"; close match → "유사 후보"; miss → "미확인" for the host LLM
   to verify with its own web search.
3. English title with a DOI → `clients/crossref` `/works/{doi}` (authoritative).
4. English title without a DOI → `clients/semantic_scholar` best-title-match first
   (covers NeurIPS/CVPR/arXiv works Crossref indexes poorly). When the matched
   record carries a DOI, it is cross-checked against `clients/crossref`'s registry
   (best-effort) so the confirmation rests on the official DOI registry, not just
   the aggregator. On an S2 miss or error, fall back to `clients/crossref` title
   search; when several Crossref records share the exact title, confirm only a
   citation-count-dominant record.
5. Normalize candidate works into title, DOI, publisher, year, authors, URL, and
   `match_score` (the score that feeds the finding's `confidence`).
6. Return confirmed/candidate/unconfirmed findings, uncertainty, safe next actions,
   and the `CITATION_CHECK.md` guidance so the host LLM can second-pass the
   unconfirmed items.

Dependencies:

- `citation/parser`
- `clients/kci`
- `clients/semantic_scholar`
- `clients/crossref`
- `guidance_provider`
- `result_formatter`
- `schemas`
- `errors`

Privacy:

- `user_email` is optional; it only upgrades Crossref to the polite pool (`mailto`).
- Email and citation titles are not logged in raw form.

### 5.4 `pipelines/plagiarism`

Input:

- `document_text`
- optional `sentence_chunk_size`
- optional `similarity_threshold`
- optional `max_queries`
- optional `max_results`

Flow:

1. Segment document into sentence chunks.
2. Select bounded query chunks under `max_queries`.
3. Query `clients/naver_search` using configured endpoint and UTF-8 query encoding.
4. Compare original chunks with result title/snippet/link metadata using `similarity/scorer`.
5. Return only results above threshold.
6. Include `PLAGIARISM_CHECK.md` guidance for host LLM follow-up search.
7. State limitations: public web only, no private DB, no school submissions, no unindexed files.

Dependencies:

- `text/chunker`
- `clients/naver_search`
- `similarity/scorer`
- `guidance_provider`
- `result_formatter`
- `schemas`
- `errors`

External limits:

- Naver credentials come from environment only.
- Tool call must cap query count to protect quota and latency.
- 429, quota exhaustion, timeout, and 5xx return `partial` or `external_error`, not process failure.

### 5.5 `pipelines/writing_structure`

Input:

- empty object for guidance-only mode.

Flow:

1. Load `GOOD_WRITING.md` through `guidance_provider` (`guidance_id: GOOD_WRITING`).
2. Return concise rubric, evaluation dimensions, result format, and limitations.
3. Host LLM uses this guidance to evaluate the document text it already has.

Dependencies:

- `guidance_provider`
- `result_formatter`
- `schemas`
- `errors`

No external API calls.

### 5.6 `pipelines/required_fields`

Input:

- empty object for guidance-only mode.

Flow:

1. Load `TO_HAVE.md` through `guidance_provider` (`guidance_id: TO_HAVE`).
2. Return field checklist and result format.
3. Make clear that name, student ID, affiliation, email, and phone are context-dependent and must not be over-collected.

Dependencies:

- `guidance_provider`
- `result_formatter`
- `schemas`
- `errors`

No external API calls.

### 5.7 `pipelines/full_check`

Input:

- `document_text`
- optional `citation_titles`
- optional `user_email`
- optional pipeline options

Flow:

1. Run `counts` first because it is deterministic and cheap.
2. Run `spellcheck`, `plagiarism`, `writing_structure`, and `required_fields` under the remaining timeout budget.
3. Run `citation` only when `citation_titles` is provided.
4. If `citation_titles` is absent, skip `citation`, record `citation` in `skipped_pipelines`, and add a limitation explaining citation checking was skipped.
5. Prefer local deterministic results when external calls are slow or unavailable.
6. Collect partial failures rather than failing the whole Tool.
7. Treat `writing_structure` and `required_fields` as guidance payloads for the host LLM, not as server-side document evaluation results.
8. Compress output to summary, top findings, top suspect links, limitations, and next actions.
9. Return `partial` if any sub-pipeline times out or external APIs fail.

Dependencies:

- Stable interfaces of the six feature pipelines only.
- `result_formatter`
- `schemas`
- `errors`

Constraint:

- `full_check` must not reach into sub-pipeline internals. Each feature pipeline remains independently testable and replaceable.

## 6. Module-Level Dependency Tree

This tree is the source of truth for parallel development ownership. Dependencies point downward. A module may depend only on modules listed under it or on standard/runtime libraries.

```text
app_server
├── config
├── security
├── logging
├── rate_limit
├── observability
├── mcp_transport
│   ├── tool_registry
│   │   ├── tools/definitions
│   │   └── schemas/validators
│   └── schemas
└── pipeline_orchestrator
    ├── schemas
    ├── errors
    ├── result_formatter
    ├── pipelines/counts
    │   ├── text/segmentation
    │   ├── schemas
    │   ├── errors
    │   └── result_formatter
    ├── pipelines/spellcheck
    │   ├── text/segmentation
    │   ├── providers/spellcheck
    │   ├── schemas
    │   ├── errors
    │   └── result_formatter
    ├── pipelines/citation
    │   ├── citation/parser
    │   ├── clients/crossref
    │   │   ├── config
    │   │   ├── security
    │   │   ├── errors
    │   │   └── logging
    │   ├── guidance_provider
    │   ├── schemas
    │   ├── errors
    │   └── result_formatter
    ├── pipelines/plagiarism
    │   ├── text/chunker
    │   ├── clients/naver_search
    │   │   ├── config
    │   │   ├── security
    │   │   ├── errors
    │   │   └── logging
    │   ├── similarity/scorer
    │   ├── guidance_provider
    │   ├── schemas
    │   ├── errors
    │   └── result_formatter
    ├── pipelines/writing_structure
    │   ├── guidance_provider
    │   ├── schemas
    │   ├── errors
    │   └── result_formatter
    ├── pipelines/required_fields
    │   ├── guidance_provider
    │   ├── schemas
    │   ├── errors
    │   └── result_formatter
    └── pipelines/full_check
        ├── pipelines/counts interface
        ├── pipelines/spellcheck interface
        ├── pipelines/citation interface
        ├── pipelines/plagiarism interface
        ├── pipelines/writing_structure interface
        ├── pipelines/required_fields interface
        ├── schemas
        ├── errors
        └── result_formatter
```

### 6.1 Dependency rules

- `mcp_transport` depends on `tool_registry` and shared `schemas` only.
- `tool_registry` depends on Tool definitions and schema validators only.
- `pipelines/counts` depends only on text segmentation utilities plus shared schema/error/formatting contracts.
- `pipelines/spellcheck` depends on text segmentation plus spell-check provider interface. If the v1 `providers/spellcheck` adapter makes external calls (e.g. hanspell), that adapter additionally depends on `config`, `security`, `errors`, and `logging` for outbound safety, mirroring `clients/*`.
- `pipelines/citation` depends on citation parser, Crossref client, the shared `guidance_provider`, shared contracts, and result formatter.
- `pipelines/plagiarism` depends on text chunker, Naver Search client, similarity scorer, the shared `guidance_provider`, shared contracts, and result formatter.
- `pipelines/writing_structure` depends on the shared `guidance_provider` (`GOOD_WRITING`) and formatter.
- `pipelines/required_fields` depends on the shared `guidance_provider` (`TO_HAVE`) and formatter.
- `pipelines/full_check` depends on all six feature pipelines through stable interfaces only.
- `clients/crossref` and `clients/naver_search` must not depend on MCP transport, Tool registry, pipeline orchestrator, or feature pipelines.
- `security`, `config`, `errors`, `logging`, `rate_limit`, and `schemas` are low-level modules and must not depend on feature pipelines.

### 6.2 No-cycle policy

Forbidden dependency examples:

- `clients/naver_search` -> `pipelines/plagiarism`
- `clients/crossref` -> `pipelines/citation`
- `result_formatter` -> any `pipelines/*`
- `schemas` -> `tool_registry`
- `tool_registry` -> `pipeline_orchestrator`
- Any feature pipeline -> `pipelines/full_check`

## 7. Data, Privacy, and Security Flow

### 7.1 Document data lifecycle

```text
User document text
  -> host LLM
  -> MCP Tool input
  -> in-memory pipeline processing
  -> summarized findings
  -> Tool response
  -> discarded
```

Rules:

- Raw document text is never stored.
- Raw document text is never logged.
- Raw document text is never sent to Crossref, Semantic Scholar, or KCI.
- Naver Search receives only bounded query chunks required for plagiarism search.
- Crossref receives citation titles and optional `mailto` only; Semantic Scholar and
  KCI receive citation titles only (Semantic Scholar is keyless).
- An online spell-check provider, if selected for v1 (e.g. hanspell), receives only the text units needed for spell checking; send minimal fragments and disclose the transmission. A fully local provider sends nothing externally.
- Guidance-only Tools do not need document text.

### 7.2 Secrets

- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, OAuth secrets, registry credentials, and Git PAT values are loaded by `config`.
- Secrets are passed only to the specific outbound client that needs them.
- `security` and `logging` must redact secrets before any log or error result leaves the process.
- Secrets must not appear in Tool output, metrics labels, exceptions, Docker layers, or docs examples.

### 7.3 External request safety

- External clients use fixed base URLs or strict allowlists.
- Redirects are validated before following.
- Private IP, loopback, link-local, and cloud metadata addresses are blocked unless explicitly allowed for local development tooling outside production.
- All external calls have connect/read timeouts and normalized error classes.

## 8. Performance and Failure Policy

### 8.1 Budget

- Target average Tool response: 100ms.
- Required p99 Tool response: 3,000ms.
- Maximum Tool response size: under 24k.
- Full-check must reserve budget for formatting and result compression.

Suggested budget split for full-check:

| Stage | Budget guidance |
| --- | --- |
| Counts | deterministic, run immediately |
| Spell-check | bounded by sentence count or provider timeout |
| Citation | bounded by citation count and `max_results` |
| Plagiarism | bounded by `max_queries`, `max_results`, and Naver timeout |
| Guidance pipelines | static load, should be near-instant |
| Formatting | final compression before timeout |

### 8.2 Partial result behavior

- A single failed external API call must not crash the server.
- If one sub-pipeline fails in full-check, return `partial` with completed results.
- If all sub-pipelines fail due to invalid input, return `invalid_input`.
- If an external service times out, return `external_error` for that pipeline and include safe retry guidance.
- If response size approaches 24k, `result_formatter` drops lower-priority details before summary, status, limitations, and next actions.

## 9. Parallel Development Workstreams

### 9.1 Transport and Tool contract

Owns:

- `app_server`
- `mcp_transport`
- `tool_registry`
- `tools/definitions`
- `schemas/validators`

Deliverables:

- Streamable HTTP MCP endpoint.
- Seven Tool metadata definitions with required annotations.
- Input validation and normalized Tool output contract.
- MCP Inspector readiness.

Can proceed before feature pipelines are complete by using stub pipeline interfaces.

### 9.2 Text segmentation and counts

Owns:

- `text/segmentation`
- `text/chunker`
- `pipelines/counts`

Deliverables:

- Korean/English-aware paragraph, sentence, word, and character counting.
- Configurable chunking for plagiarism queries.
- Deterministic fixtures for whitespace, punctuation, mixed-language text.

No external dependency.

### 9.3 Spell-check provider

Owns:

- `providers/spellcheck`
- `pipelines/spellcheck`

Deliverables:

- Provider abstraction.
- Provider-specific adapter.
- Normalized error/correction pair output.
- Timeout and no-findings behavior.

Can use mock provider until final library/API is selected.

### 9.4 Citation and Crossref

Owns:

- `citation/parser`
- `clients/crossref`
- `CITATION_CHECK.md` (guidance content; loaded via shared `guidance_provider`)
- `pipelines/citation`

Deliverables:

- Citation title normalization.
- Crossref polite-pool query with optional `mailto`.
- Candidate matching and confidence.
- `CITATION_CHECK.md` guidance integration.

Must coordinate with security workstream for email redaction and outbound allowlist.

### 9.5 Plagiarism, Naver Search, and similarity

Owns:

- `clients/naver_search`
- `similarity/scorer`
- `PLAGIARISM_CHECK.md` (guidance content; loaded via shared `guidance_provider`)
- `pipelines/plagiarism`

Deliverables:

- Naver Search API wrapper with quota/error handling.
- Query chunk selection.
- Similarity scoring and threshold filtering.
- `PLAGIARISM_CHECK.md` guidance integration.

Must coordinate with text segmentation for chunking rules.

### 9.6 Static guidance and qualitative rubrics

Owns:

- `guidance_provider` (shared loader for all guidance docs: `CITATION_CHECK.md`, `PLAGIARISM_CHECK.md`, `GOOD_WRITING.md`, `TO_HAVE.md`)
- `pipelines/writing_structure`
- `pipelines/required_fields`
- static docs `GOOD_WRITING.md`, `TO_HAVE.md`

Deliverables:

- Compact guidance text for host LLM.
- Output format expectations.
- Privacy-aware required-field checklist.

No external dependency.

### 9.7 Full-check orchestration and compression

Owns:

- `pipeline_orchestrator`
- `pipelines/full_check`
- `result_formatter`

Deliverables:

- Stable pipeline interface composition.
- Timeout and partial-result handling.
- Response size enforcement below 24k.
- Consolidated summary and next actions.

Can proceed once each feature pipeline exposes stubs matching the common output shape.

### 9.8 Test, CI, and deployment packaging

Owns:

- Test fixtures.
- MCP Inspector workflow.
- Dockerfile and deployment docs.
- `linux/amd64` image verification.

Deliverables:

- Unit tests for low-level modules.
- Contract tests for all seven Tool schemas.
- Mocked external API tests for Crossref and Naver.
- Full-check partial-failure tests.
- Deployment checklist aligned with PlayMCP in KC.

## 10. Acceptance Criteria

The architecture is implementation-ready when:

- All seven Tool roles from `PROJECT_SILHOUETTE.md` map to one public Tool name and one pipeline module.
- Every external integration has a client boundary, timeout behavior, error policy, and privacy note.
- `DEVELOPMENT_CONDITIONS.md` constraints are reflected: Streamable HTTP, remote endpoint, Tool count, schema/annotations, 24k response limit, 3,000ms p99, no raw document logging.
- The dependency tree has no required cycles.
- A developer can implement any feature pipeline without importing MCP transport or another feature pipeline, except `full_check` through stable interfaces.
- A reviewer can trace PlayMCP constraints back to explicit architecture decisions.

## Sources

- [`PROJECT_SILHOUETTE.md`](./PROJECT_SILHOUETTE.md)
- [`DEVELOPMENT_CONDITIONS.md`](./DEVELOPMENT_CONDITIONS.md)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18)
- [MCP Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP Streamable HTTP Transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [MCP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [Naver Search API - 웹문서](https://developers.naver.com/docs/serviceapi/search/web/web.md)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
