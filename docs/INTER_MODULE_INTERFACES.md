# INTER_MODULE_INTERFACES

Last reviewed: 2026-06-25 (Asia/Seoul)

이 문서는 `Report Guard`의 모듈 간 interface contract를 정의한다. 구현 언어와 framework는 고정하지 않는다. 아래 type들은 JSON-like pseudo type이며, 실제 구현에서는 선택한 언어의 type/schema/validator로 옮긴다.

상위 기준 문서:

- [`PROJECT_SILHOUETTE.md`](./PROJECT_SILHOUETTE.md)
- [`DEVELOPMENT_CONDITIONS.md`](./DEVELOPMENT_CONDITIONS.md)
- [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md)

## 1. Document Strategy

현재는 interface를 `docs/INTER_MODULE_INTERFACES.md` 한 곳에 둔다.

이유:

- 아직 구현 directory가 없으므로 module별 문서를 흩뿌리면 파일 구조 결정을 앞당기게 된다.
- 병렬 개발자가 같은 contract를 기준으로 작업해야 하므로 중앙 문서가 충돌을 줄인다.
- 코드가 생긴 뒤 module별 README 또는 schema 파일로 분리하더라도 이 문서가 원본 contract 역할을 한다.

분리 규칙:

- 실제 module directory가 생기면 module-local 문서는 이 문서를 요약하거나 구현 상세를 보충할 수 있다.
- module-local 문서가 이 문서와 충돌하면 이 문서가 우선한다.
- interface 변경은 이 문서를 먼저 수정한 뒤 구현에 반영한다.

## 2. Global Interface Rules

### 2.1 Naming and data format

- Public Tool name은 [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md)의 Tool surface를 따른다.
- Public Tool argument/result field는 `snake_case`를 사용한다.
- Internal module field도 기본적으로 `snake_case`를 사용한다.
- MCP protocol wire field는 MCP 스펙의 canonical casing을 그대로 사용한다. 예: `inputSchema`, `outputSchema`, `structuredContent`, `isError`, `readOnlyHint`.
- Time duration은 `*_ms` integer로 표현한다.
- Timestamp가 필요하면 ISO 8601 UTC string을 사용한다.
- URL은 string으로 표현하되 outbound client에서 allowlist와 SSRF 검증을 통과해야 한다.
- Unknown field는 기본적으로 거부한다. 단, `options` object는 명시된 optional field만 허용한다.

### 2.2 Status contract

모든 pipeline과 Tool output은 동일한 status enum을 사용한다.

```text
Status =
  "ok"              // 정상 처리, findings가 있을 수 있음
  "no_findings"     // 정상 처리, 문제 없음
  "partial"         // 일부 module 또는 external call 실패, 사용 가능한 결과 있음
  "invalid_input"   // schema 또는 business validation 실패
  "external_error"  // 외부 API, provider, network 실패
  "internal_error"  // 예상하지 못한 내부 오류
```

### 2.3 Severity and confidence

```text
Severity = "info" | "low" | "medium" | "high"

Confidence =
  "low"     // 후보성 결과, 사용자가 확인 필요
  "medium"  // 근거가 있으나 오탐 가능
  "high"    // 강한 근거
```

Rules:

- `severity`는 사용자에게 우선순위를 알려주기 위한 값이며 학술윤리 최종 판정이 아니다.
- `confidence`는 시스템 판단의 강도를 의미하며 확정 판정으로 표현하지 않는다.

### 2.4 Error code contract

```text
ErrorCode =
  "INVALID_INPUT"
  "DOCUMENT_TOO_LARGE"
  "UNSUPPORTED_LANGUAGE"
  "PROVIDER_TIMEOUT"
  "PROVIDER_UNAVAILABLE"
  "EXTERNAL_RATE_LIMITED"
  "EXTERNAL_QUOTA_EXCEEDED"
  "EXTERNAL_BAD_RESPONSE"
  "CONFIG_MISSING"
  "RESPONSE_TOO_LARGE"
  "INTERNAL_ERROR"
```

Error object:

```text
ModuleError
- code: ErrorCode
- message: safe user-facing string
- retryable: boolean
- module: string
- details: optional object with non-sensitive diagnostic data
```

Rules:

- `message`와 `details`에는 원문 document text, API key, token, raw headers, raw stack trace를 넣지 않는다.
- External API raw response body는 `details`에 넣지 않는다. 필요한 경우 `status_code`, `provider`, `retry_after_ms` 정도만 둔다.

## 3. Shared Core Types

### 3.1 Request context

`RequestContext`는 MCP transport가 생성하고 pipeline_orchestrator 이하로 전달한다.

```text
RequestContext
- request_id: string
- tool_name: string
- deadline_ms: integer
- received_at: ISO timestamp
- language_hint: optional "ko" | "en" | "auto"
- caller: optional object
  - kind: optional string
  - display_name: optional string
```

Rules:

- `request_id`는 로그 상관관계용이며 개인정보를 포함하지 않는다.
- `caller`는 PlayMCP 또는 host가 제공한 비민감 정보만 담는다.
- module은 `deadline_ms`를 초과할 가능성이 있으면 partial result를 선호한다.

### 3.2 Normalized Tool result

모든 pipeline은 `PipelineResult`를 반환하고, `result_formatter`가 MCP Tool response로 변환한다.

```text
PipelineResult
- status: Status
- summary: string
- findings: list<Finding>
- metrics: optional object
- limitations: list<string>
- next_actions: list<string>
- links: list<LinkResult>
- partial_failures: list<ModuleError>
```

```text
Finding
- id: string
- category: string
- severity: Severity
- confidence: Confidence
- title: string
- message: string
- evidence: list<Evidence>
- suggestion: optional string
```

```text
Evidence
- kind: "text_span" | "citation" | "external_match" | "metric" | "guidance"
- excerpt: optional string
- location: optional TextLocation
- source: optional string
- score: optional number
```

```text
TextLocation
- paragraph_index: optional integer
- sentence_index: optional integer
- start_offset: optional integer
- end_offset: optional integer
```

```text
LinkResult
- title: string
- url: string
- source: optional string
- confidence: optional Confidence
```

Rules:

- `excerpt`는 짧은 증거 snippet만 허용한다. 원문 전체 또는 긴 문단을 넣지 않는다.
- `id`는 response 내에서만 stable하면 된다. 영구 저장 identifier가 아니다.
- `links`는 외부 검증 결과 또는 참고 링크만 담는다.

### 3.3 MCP Tool response boundary

`mcp_transport`가 최종 반환하는 MCP response는 다음 논리 구조를 가져야 한다.

```text
McpToolResponse
- content: list<TextContent>
- structuredContent: optional PipelineResult
- isError: boolean
```

Rules:

- `content[0].text`는 사용자가 읽을 수 있는 Markdown 요약이다.
- 가능하면 `structuredContent`에 `PipelineResult`를 둔다.
- Tool execution error는 MCP protocol error가 아니라 `isError: true` Tool result로 반환한다.
- unknown tool, malformed JSON-RPC, invalid protocol state는 MCP protocol error로 반환한다.

## 4. Public Tool Interfaces

### 4.1 `count_document_units`

Input:

```text
CountDocumentUnitsInput
- document_text: string
- language: optional "ko" | "en" | "auto"
- options: optional object
  - include_spaces: optional boolean
```

Output metrics:

```text
CountMetrics
- character_count: integer
- word_count: integer
- sentence_count: integer
- paragraph_count: integer
- character_count_includes_spaces: boolean
- calculation_notes: list<string>
```

Rules:

- 산출 불가 항목은 `-1`로 반환하고 `calculation_notes`에 이유를 넣는다.
- 정상 산출 시 `status`는 `ok`다.
- 문제 발견형 Tool이 아니므로 `findings`는 비워도 된다.

### 4.2 `check_document_spelling`

Input:

```text
CheckDocumentSpellingInput
- document_text: string
- language: optional "ko" | "en" | "auto"
- options: optional object
  - max_findings: optional integer
```

Finding category:

```text
SpellingFinding extends Finding
- category: "spelling"
- evidence.kind: "text_span"
- suggestion: corrected sentence or phrase
```

Metrics:

```text
SpellcheckMetrics
- checked_units: integer
- issue_count: integer
- provider_name: string
- provider_timed_out: boolean
```

Rules:

- v1 uses a free-of-charge spell-check provider: either a free local library or a free no-auth online service such as hanspell. Paid APIs or paid quotas are out of v1 scope. See `providers/spellcheck` (§6.3) for external-call handling.
- 오류가 없으면 `status: "no_findings"`를 반환한다.
- provider timeout 후 일부 결과가 있으면 `status: "partial"`이다.
- 맞춤법 제안은 문맥상 오탐 가능성을 `limitations`에 포함한다.

### 4.3 `check_document_citations`

Input:

```text
CheckDocumentCitationsInput
- citation_titles: list<string>
- user_email: optional string
- options: optional object
  - max_results: optional integer
```

Finding category:

```text
CitationFinding extends Finding
- category: "citation"
- evidence.kind: "citation" | "external_match"
- matched_work: optional CrossrefWorkSummary
```

```text
CrossrefWorkSummary
- title: string
- doi: optional string
- publisher: optional string
- publication_year: optional integer
- authors: list<string>
- url: optional string
- match_score: optional number
- cited_by_count: optional integer
```

Rules:

- 언어별 라우팅: 한국어 제목 → `clients/kci`, DOI가 있는 영어 항목 → `clients/crossref` DOI 조회, DOI 없는 영어 제목 → `clients/semantic_scholar` 우선 조회 후 미확정 시 `clients/crossref` 제목 검색으로 폴백한다.
- `user_email`은 선택 입력이며 `clients/crossref`의 `mailto`(polite pool)에만 전달한다. 이메일이 없어도 검증은 동일하게 동작한다.
- 어느 DB에서도 확정되지 않으면 `no_findings`가 아니라 `ok` 또는 `partial`로 "미확인" finding을 반환하고, 호스트 LLM의 자체 웹 검색 2차 확인을 위해 `CITATION_CHECK` 가이드를 함께 첨부한다. "확인 실패"는 "문제 없음"과 다르다.
- metadata 한계를 `limitations`에 반드시 포함한다.

### 4.4 `check_document_plagiarism`

Input:

```text
CheckDocumentPlagiarismInput
- document_text: string
- language: optional "ko" | "en" | "auto"
- options: optional object
  - sentence_chunk_size: optional integer
  - similarity_threshold: optional number
  - max_queries: optional integer
  - max_results: optional integer
```

Finding category:

```text
PlagiarismFinding extends Finding
- category: "plagiarism_risk"
- evidence.kind: "external_match"
- matched_url: string
- similarity_score: number
- query_index: integer
```

Metrics:

```text
PlagiarismMetrics
- query_count: integer
- result_count: integer
- suspect_match_count: integer
- threshold: number
- naver_rate_limited: boolean
```

Rules:

- threshold 이상 결과가 없으면 `status: "no_findings"`다.
- Naver timeout 또는 quota 문제로 일부만 검색되면 `status: "partial"`이다.
- 공개 검색 기반 한계를 `limitations`에 반드시 포함한다.
- 표절 회피 방법을 `next_actions`에 넣지 않는다.

### 4.5 `get_writing_structure_guidance`

Input:

```text
GetWritingStructureGuidanceInput
{} // additionalProperties: false
```

Output:

```text
GuidanceResult extends PipelineResult
- status: Status                  // 정상 로드 시 "ok"
- summary: string
- findings: list<Finding>         // guidance Tool은 보통 빈 리스트
- metrics: optional object
- limitations: list<string>
- next_actions: list<string>
- links: list<LinkResult>
- partial_failures: list<ModuleError>
- guidance_id: "GOOD_WRITING"
- guidance_version: string
- sections: list<GuidanceSection>
- expected_llm_output_format: string
```

```text
GuidanceSection
- title: string
- body: string
- checklist: list<string>
```

Rules:

- 이 Tool은 문서 본문을 받지 않는다.
- Host LLM이 이미 가진 document text에 rubric을 적용하도록 지침을 제공한다.
- `GOOD_WRITING.md`가 없거나 로드 실패하면 `internal_error` 또는 `partial`을 반환한다.
- `GuidanceResult`는 `PipelineResult`를 만족하므로 `run_full_report_check`의 `sub_results`에 그대로 포함된다.

### 4.6 `get_required_fields_guidance`

Input:

```text
GetRequiredFieldsGuidanceInput
{} // additionalProperties: false
```

Output:

```text
GuidanceResult extends PipelineResult
- status: Status                  // 정상 로드 시 "ok"
- summary: string
- findings: list<Finding>         // guidance Tool은 보통 빈 리스트
- metrics: optional object
- limitations: list<string>
- next_actions: list<string>
- links: list<LinkResult>
- partial_failures: list<ModuleError>
- guidance_id: "TO_HAVE"
- guidance_version: string
- sections: list<GuidanceSection>
- expected_llm_output_format: string
```

Rules:

- 이 Tool은 문서 본문을 받지 않는다.
- 이름, 학번, 소속, 이메일, 전화번호 등은 report 맥락에 따라 권장 여부가 달라진다.
- 개인정보 최소화 원칙을 guidance에 포함한다.
- `GuidanceResult`는 `PipelineResult`를 만족하므로 `run_full_report_check`의 `sub_results`에 그대로 포함된다.

### 4.7 `run_full_report_check`

Input:

```text
RunFullReportCheckInput
- document_text: string
- citation_titles: optional list<string>
- user_email: optional string
- language: optional "ko" | "en" | "auto"
- options: optional object
  - include_spaces: optional boolean
  - sentence_chunk_size: optional integer
  - similarity_threshold: optional number
  - max_queries: optional integer
  - max_results: optional integer
  - max_findings_per_pipeline: optional integer
```

Output:

```text
FullCheckResult extends PipelineResult
- metrics: object
  - completed_pipelines: list<string>
  - skipped_pipelines: list<string>
  - timed_out_pipelines: list<string>
  - total_findings: integer
- sub_results: optional object
  - counts: optional PipelineResult
  - spellcheck: optional PipelineResult
  - citation: optional PipelineResult
  - plagiarism: optional PipelineResult
  - writing_structure: optional PipelineResult
  - required_fields: optional PipelineResult
```

Rules:

- `sub_results`는 내부/structured output용이다. Markdown summary에는 압축된 top findings만 포함한다.
- `citation_titles`가 없으면 citation pipeline을 실행하지 않고 `metrics.skipped_pipelines`에 `citation`을 포함한다.
- citation이 skipped된 경우 `limitations`에 citation 검사가 입력 부족으로 생략되었음을 포함한다.
- 일부 pipeline 실패 시 `status: "partial"`이다.
- `writing_structure`와 `required_fields`는 guidance pipeline 결과로 포함한다.
- 전체 응답은 반드시 24k 미만이어야 한다.

## 5. Internal Module Interfaces

### 5.1 `mcp_transport`

Consumes:

```text
ToolRegistry.resolve(tool_name) -> ToolDefinition | ModuleError
PipelineOrchestrator.execute(tool_name, arguments, context) -> PipelineResult
ResultFormatter.to_mcp_response(result) -> McpToolResponse
```

Provides:

```text
handle_initialize(request) -> initialize response
handle_tools_list(request) -> list<ToolDefinition>
handle_tools_call(request) -> McpToolResponse or protocol error
handle_health(request) -> health response
```

Rules:

- `mcp_transport`는 Tool별 business validation을 하지 않는다.
- JSON-RPC protocol error와 Tool execution error를 구분한다.
- stdout/response body에는 valid MCP message만 반환한다.

### 5.2 `tool_registry`

Type:

```text
ToolDefinition
- name: string
- title: string
- description: string
- inputSchema: object
- outputSchema: optional object
- annotations:
  - title: string
  - readOnlyHint: boolean
  - destructiveHint: boolean
  - openWorldHint: boolean
  - idempotentHint: boolean
```

Provides:

```text
list_tools() -> list<ToolDefinition>
resolve(tool_name) -> ToolDefinition | ModuleError
validate_input(tool_name, arguments) -> ValidatedInput | ModuleError
```

Rules:

- 모든 Tool은 `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`를 기본으로 한다.
- 외부 검색/API를 사용하는 citation, plagiarism, full-check(`run_full_report_check`) Tool은 `openWorldHint: true`다.
- `count_document_units`와 guidance-only Tool(`get_writing_structure_guidance`, `get_required_fields_guidance`)은 외부 호출이 없으므로 `openWorldHint: false`다.
- `check_document_spelling`의 `openWorldHint`는 shipped provider에 따른다: 온라인 무상 서비스(e.g. hanspell) 사용 시 `true`, 완전 로컬 라이브러리 사용 시 `false`. v1 기본 계획(hanspell)에서는 `true`다.

### 5.3 `pipeline_orchestrator`

Provides:

```text
execute(tool_name, validated_input, context) -> PipelineResult
execute_full_check(input, context) -> FullCheckResult
```

Rules:

- Tool name과 pipeline mapping은 고정 table로 관리한다.
- timeout budget을 pipeline에 전달한다.
- pipeline exception은 잡아서 `ModuleError`로 변환한다.
- `full_check`는 feature pipeline public interface만 호출한다.

### 5.4 `result_formatter`

Provides:

```text
format_markdown(result, budget_chars) -> string
compress_result(result, budget_chars) -> PipelineResult
to_mcp_response(result) -> McpToolResponse
```

Rules:

- summary, status, limitations, next_actions는 가능한 한 보존한다.
- response size가 커지면 low-confidence detail, duplicate links, lower-severity findings 순서로 줄인다.
- raw document text를 복원할 수 있을 정도의 긴 excerpt를 출력하지 않는다.

### 5.5 `config`

Provides:

```text
get_required_secret(name) -> string | ModuleError
get_optional_secret(name) -> optional string
get_limit(name) -> number
get_feature_flag(name) -> boolean
```

Required keys:

```text
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
```

Optional keys:

```text
DEFAULT_LANGUAGE
MAX_DOCUMENT_CHARS
MAX_TOOL_RESPONSE_CHARS
DEFAULT_TIMEOUT_MS
NAVER_MAX_QUERIES
NAVER_SIMILARITY_THRESHOLD
```

Rules:

- secret 값은 `logging` 또는 Tool response로 전달하지 않는다.
- missing required secret은 `CONFIG_MISSING`으로 반환한다.

### 5.6 `security`

Provides:

```text
validate_document_size(document_text) -> ok | ModuleError
sanitize_user_text(text) -> string
redact_sensitive(value) -> string
validate_email_for_mailto(user_email) -> ok | ModuleError
validate_outbound_url(url, policy_name) -> ok | ModuleError
```

Rules:

- email validation은 Crossref `mailto`에 적합한지 확인하는 수준이다.
- outbound URL validation은 private IP, localhost, link-local, cloud metadata endpoint를 차단한다.
- sanitizer는 의미 있는 문서 내용을 임의로 바꾸지 않는다. logging/redaction 경계에서만 민감정보를 제거한다.

### 5.7 `logging` and `observability`

Provides:

```text
log_event(level, event_name, fields) -> void
record_metric(metric_name, value, tags) -> void
start_timer(name, tags) -> TimerHandle
```

Allowed log fields:

```text
request_id
tool_name
status
error_code
duration_ms
document_length
pipeline_name
provider_name
http_status
retryable
```

Forbidden log fields:

```text
document_text
citation_titles
user_email
NAVER_CLIENT_SECRET
OAuth token
raw external response body
raw request headers
```

### 5.8 `rate_limit`

Provides:

```text
check_request(context, cost) -> ok | ModuleError
estimate_cost(tool_name, input) -> integer
```

Rules:

- plagiarism and full-check have higher cost than counts/guidance Tools.
- quota protection must happen before external API calls.
- rate limit errors return `external_error` only if upstream quota caused the limit; local policy limits return `invalid_input` or safe Tool error with retry guidance.

## 6. Text and Analysis Module Interfaces

### 6.1 `text/segmentation`

Provides:

```text
detect_language(document_text, hint) -> "ko" | "en" | "mixed" | "unknown"
split_paragraphs(document_text) -> list<TextUnit>
split_sentences(document_text, language) -> list<TextUnit>
split_words(document_text, language) -> list<TextUnit>
count_characters(document_text, include_spaces) -> integer
```

```text
TextUnit
- text: string
- index: integer
- location: TextLocation
```

Rules:

- Segmentation must preserve offsets against normalized text.
- Mixed Korean/English text must not fail solely because language is mixed.

### 6.2 `text/chunker`

Provides:

```text
build_sentence_chunks(sentences, sentence_chunk_size, max_queries) -> list<QueryChunk>
```

```text
QueryChunk
- query_text: string
- index: integer
- sentence_indexes: list<integer>
- location: optional TextLocation
```

Rules:

- Query chunks must be bounded by `max_queries`.
- Query text must be short enough for Naver Search API query usage.
- Chunks must avoid sending the entire document as one query.

### 6.3 `providers/spellcheck`

Provides:

```text
check_text(units, language, deadline_ms) -> SpellcheckProviderResult
```

```text
SpellcheckProviderResult
- status: Status
- provider_name: string
- corrections: list<SpellcheckCorrection>
- errors: list<ModuleError>
```

```text
SpellcheckCorrection
- original: string
- corrected: string
- message: optional string
- location: optional TextLocation
- confidence: Confidence
```

Rules:

- v1 provider must be free of charge (no paid API or paid quota). A free local library or a free no-auth online service (e.g. hanspell) is allowed.
- If the provider makes external network calls, the adapter must apply connect/read timeout, UTF-8 encoding, outbound URL allowlist/SSRF checks, and normalized error classes, and must not leak raw upstream payloads — the same outbound-safety rules as `clients/*`. It sends only the needed text units (not the whole document at once), and that external transmission is disclosed.
- An online scraping-based service (e.g. hanspell) may be unstable; on failure return `PROVIDER_UNAVAILABLE`/`PROVIDER_TIMEOUT` with a no-result/`partial` state rather than crashing.
- Provider adapter owns conversion from provider-specific output.
- Provider adapter must not leak provider raw payload.
- Provider adapter must support test double implementation.

### 6.4 `citation/parser`

Provides:

```text
normalize_titles(citation_titles) -> list<CitationQuery>
```

```text
CitationQuery
- original_title: string
- normalized_title: string
- index: integer
```

Rules:

- Empty titles are invalid input.
- Duplicate normalized titles should be deduplicated for external calls but mapped back to original indexes.

### 6.5 `similarity/scorer`

Provides:

```text
score_match(source_text, candidate_text) -> number
filter_matches(matches, threshold) -> list<ScoredMatch>
```

```text
ScoredMatch
- source_index: integer
- candidate_title: string
- candidate_snippet: string
- candidate_url: string
- score: number
```

Rules:

- Score range is `0.0` to `1.0`.
- Scores are similarity indicators, not final plagiarism proof.

## 7. External Client Interfaces

### 7.1 `clients/crossref`

Input:

```text
CrossrefSearchRequest
- query_title: string
- mailto: optional string
- rows: integer
- deadline_ms: integer
```

Output:

```text
CrossrefSearchResponse
- status: Status
- works: list<CrossrefWorkSummary>
- errors: list<ModuleError>
- http_status: optional integer
```

Rules:

- Base URL is fixed to Crossref API host.
- `mailto` is included only when the user supplied `user_email` (or `USER_EMAIL` env); queries still run anonymously without it.
- Client must apply timeout and normalize 429/5xx/network failures.
- Client must not depend on `pipelines/citation`.

### 7.1b `clients/semantic_scholar`

Input: `match_title(title, deadline_ms)` — a single best-title-match lookup against
the Semantic Scholar Graph API (`/graph/v1/paper/search/match`).

Output:

```text
S2MatchResponse
- status: Status
- paper: optional S2Paper (title, year, venue, citation_count, doi, arxiv_id, url, authors)
- errors: list<ModuleError>
- http_status: optional integer
```

Rules:

- Base URL is fixed to the Semantic Scholar API host. Works keyless (shared public
  pool); an optional `S2_API_KEY` is sent only as an `x-api-key` header (never in
  the URL, never logged) for a dedicated rate limit.
- A 404 means "no title match" and is returned as OK with `paper=None` — not an error.
- Request starts are paced (~1s apart) across threads because the keyless pool
  rejects concurrent bursts with 429.
- Primary route for English titles without a DOI; the citation pipeline confirms
  only on exact normalized-title match. A matched record carrying a DOI is
  cross-checked against Crossref (the DOI registry) best-effort; on an S2 miss or
  error the pipeline silently falls back to the Crossref title search.
- Client must apply timeout, normalize 429/5xx/network failures, and must not depend
  on `pipelines/citation`.

### 7.2 `clients/naver_search`

Input:

```text
NaverSearchRequest
- query: string
- display: integer
- start: integer
- sort: optional string
- endpoint: "webkr" | "blog"
- deadline_ms: integer
```

Output:

```text
NaverSearchResponse
- status: Status
- items: list<NaverSearchItem>
- errors: list<ModuleError>
- http_status: optional integer
- rate_limited: boolean
```

```text
NaverSearchItem
- title: string
- link: string
- description: string
- source: optional string
- post_date: optional string
```

Rules:

- `display` must not exceed 100.
- `start` must not exceed 1000.
- Query must be UTF-8 encoded for request transmission.
- `X-Naver-Client-Id` and `X-Naver-Client-Secret` come from `config`.
- Client must not depend on `pipelines/plagiarism`.

## 8. Guidance Provider Interfaces

### 8.1 Common guidance provider

이 모듈은 `SYSTEM_ARCHITECTURE.md`의 `guidance_provider`이며, 네 guidance 문서(`CITATION_CHECK`, `PLAGIARISM_CHECK`, `GOOD_WRITING`, `TO_HAVE`)를 모두 로드하는 단일 provider다. 기능별 `guidance/*` 모듈로 분리하지 않는다.

Provides:

```text
load_guidance(guidance_id) -> GuidanceDocument | ModuleError
```

```text
GuidanceDocument
- guidance_id: "CITATION_CHECK" | "PLAGIARISM_CHECK" | "GOOD_WRITING" | "TO_HAVE"
- version: string
- title: string
- sections: list<GuidanceSection>
- expected_llm_output_format: string
- limitations: list<string>
```

Rules:

- Guidance should be loaded from local static docs or embedded static text.
- Missing guidance is an internal configuration error.
- Guidance content must be concise enough to fit Tool response budget.

## 9. Test Contracts

### 9.1 Contract tests

Each public Tool must have tests for:

- schema accepts valid minimal input.
- schema rejects unknown fields.
- schema rejects missing required fields.
- output has valid `status`, `summary`, `findings`, `limitations`, `next_actions`.
- output stays under configured response size budget.

### 9.2 Module boundary tests

- `mcp_transport` can list all seven Tool definitions without importing feature internals.
- `tool_registry` annotations include title, readOnlyHint, destructiveHint, openWorldHint, idempotentHint.
- `clients/crossref` and `clients/naver_search` can be tested with mocked HTTP and no pipeline imports.
- `pipelines/full_check` can run against stub implementations of all six feature pipelines.
- `result_formatter` can compress oversized synthetic results without dropping status or limitations.

### 9.3 Privacy tests

- Logs do not contain document text.
- Logs do not contain user email.
- Logs do not contain API secrets.
- Error output does not contain stack trace or raw external response.
- Naver client receives query chunks, not whole document, for plagiarism pipeline.
- If an online spell-check provider is used, it receives only spell-check text units (not the whole document at once), and document text is not logged.

## 10. Change Control

Interface changes are breaking when they:

- rename public Tool names.
- remove a field from public Tool input or output.
- change `Status`, `ErrorCode`, `Severity`, or `Confidence` semantics.
- change module dependency direction.
- allow raw document text or secrets to cross a boundary previously marked safe.

Breaking changes require updates to:

- this document.
- `SYSTEM_ARCHITECTURE.md` if module boundaries change.
- Tool schema contract tests.
- affected module-local docs, once they exist.
