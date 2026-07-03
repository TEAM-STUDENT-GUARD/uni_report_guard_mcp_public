# DEVELOPMENT_CONDITIONS

Last reviewed: 2026-06-25 (Asia/Seoul)

이 문서는 `Report Guard` MCP 서버 개발자가 반드시 따라야 하는 공모전, PlayMCP, MCP 표준, 성능, 개인정보/보안 제약사항을 정리한 프로젝트 기준 문서이다. LLM 기반 개발자도 이 문서를 구현 판단의 기준으로 사용한다.

공식 문서와 이 문서가 충돌하면 공식 문서가 우선한다. 단, 공식 문서가 더 느슨하게 보이더라도 개인정보, 보안, 저작권, 외부 API 이용 제한은 더 엄격한 쪽을 따른다.

## 1. 공모전 및 제출 조건

### 1.1 공모전 기본 목표

- 목표는 Agentic Player 10 공모전 예선에 제출 가능한 PlayMCP 공개 MCP 서버를 개발하는 것이다.
- 이 프로젝트의 MCP 서버명은 `Report Guard`로 한다. 한국어/영어 사용자를 모두 고려한다.
- 공모전 제출물은 직접 개발한 MCP 서버여야 한다. MCP 서버 자동 생성 제3자 플랫폼에서 생성한 서버는 PlayMCP 정책상 등록이 허용되지 않는다.
- 실제 서버를 소비하는 target client app은 ChatGPT for Kakao와 OpenClaw다. PlayMCP(예선 등록/큐레이션)와 Kakao Tools(본선 Toolbox/Widget)는 공모전 surface이며, 서버는 특정 client에 종속되지 않도록 client-agnostic하게 설계한다.

### 1.2 일정

- 예선 접수 기간: 2026-06-15 ~ 2026-07-14.
- 예선 결과 발표: 2026-07-30.
- 본선 추가 개발 기간: 2026-07-30 ~ 2026-08-27.
- 본선 공개 투표: 2026-08-31 ~ 2026-09-28.
- 최종 심사 및 시상: 2026-10-23, 카카오 AI캠퍼스.
- PlayMCP 심사는 최대 영업일 기준 7일이 걸릴 수 있다. 공모전 마감 직전 심사 요청은 예선 접수 기한 내 승인되지 않을 위험이 있다.

### 1.3 예선 제출 흐름

개발자는 다음 순서를 지켜야 한다.

1. 로컬 환경에서 MCP 서버를 개발하고 테스트한다.
2. PlayMCP in KC를 통해 MCP 서버를 배포하고 Endpoint URL을 발급받는다.
3. PlayMCP 개발자 콘솔에서 새 MCP 서버를 등록한다.
4. `정보 불러오기`가 성공하는지 확인한다. 실패하면 MCP 서버 구현 또는 배포가 잘못된 것이다.
5. 먼저 `임시 등록`으로 저장한다. 최종 제출 전에는 `등록 및 심사 요청`을 누르지 않는다.
6. 임시 등록 상태에서 MCP 상세 미리보기와 PlayMCP AI 채팅으로 충분히 테스트한다.
7. 테스트 완료 후 심사를 요청한다.
8. 심사 승인 후 공개 상태가 기본적으로 `나에게만 공개`가 되므로 반드시 `전체 공개`로 변경한다.
9. 공모전 페이지의 `Player 예선 참여` 비즈폼에서 최종 제출한다.

주의:

- `나에게만 공개` 상태인 MCP는 공모전 접수 대상에서 제외된다.
- 비즈폼 제출은 1회만 가능하다.
- 접수 양식에는 최대 2개의 MCP 서버를 등록할 수 있다.
- 심사 반려 사유는 이메일로 안내되며, 반려 후 수정하여 다시 심사 요청해야 한다.

### 1.4 PlayMCP in KC 사용 조건

- Agentic Player 10 예선 참가를 위해서는 PlayMCP in KC가 제공하는 Endpoint URL로 PlayMCP에 등록해야 한다.
- PlayMCP in KC는 2026-06-15 ~ 2026-07-14 예선 접수 기간에만 MCP 서버 발급이 가능하다.
- PlayMCP in KC는 PlayMCP 회원만 사용할 수 있으며, 계정당 MCP 서버 2대까지 등록할 수 있다.
- PlayMCP in KC 서버는 공모전 참가 목적에 한해 한시적으로 무상 제공된다.
- 발급받은 서버를 공모전 참가 외 용도로 사용하거나 예선에 접수하지 않으면 회수될 수 있다.
- 무상 지원은 공모전 종료 후 일정 기간 유지된 뒤 종료될 수 있으며, 이후 계속 운영하려면 별도 과금 또는 다른 클라우드 이전이 필요할 수 있다.
- Git 소스 배포를 사용할 경우 저장소 루트 또는 지정한 경로에 `Dockerfile`이 있어야 한다.
- 컨테이너 이미지 배포를 사용할 경우 이미지는 `linux/amd64` 아키텍처로 빌드해야 한다. `arm64` 이미지는 서버 활성화 실패 원인이 된다.

### 1.5 심사 및 평가 기준

PlayMCP 및 공모전 심사에서 특히 중요한 기준:

- 창의성: 새로운 아이디어로 문제를 해결하고 파급력을 가지는가.
- 편의성: 적합한 UI/UX를 통해 사용자의 일상에 실질적 가치를 주는가.
- 안정성: 안정적으로 구동되며 정확한 데이터를 제공하고 보안상 문제가 없는가.
- MCP 품질: 안정성, 창의성, 응답 일관성 등 내부 품질 기준에 미달하면 비공개 또는 개선 요청 대상이 될 수 있다.

본선 진출 시 Kakao Tools 공개 및 사용자 투표를 위한 추가 개발은 필수다. Kakao Tools는 PlayMCP보다 더 엄격한 MCP 표준 스펙과 Widget 추가 스펙을 요구할 수 있으므로, 예선 구현도 구조적으로 확장 가능하게 유지한다.

### 1.6 권리, 저작권, 허위 정보

- 제출자는 해당 PlayMCP 서비스의 권리자이거나 적법한 등록/응모 권한을 가져야 한다.
- 서버 개발 및 제공에 사용한 데이터, 코드, 모델, 라이브러리, 문서, 이미지가 제3자의 권리를 침해하지 않아야 한다.
- 허위 정보로 응모하면 PlayMCP 등록 또는 당첨이 취소될 수 있다.
- 공모전 및 이벤트는 카카오 사정에 따라 변경되거나 조기 종료될 수 있다.

## 2. MCP 서버 제약사항

### 2.1 지원 프로토콜 및 전송 방식

- PlayMCP 서버는 MCP 최소 지원 버전 `2025-03-26`, 최대 지원 버전 `2025-11-25` 범위와 호환되어야 한다.
- PlayMCP는 Streamable HTTP 방식만 지원한다.
- stdio-only 서버는 PlayMCP 등록 대상이 아니다.
- Remote MCP 서버만 지원한다. 서버는 공개 URL로 접근 가능한 도메인/Endpoint를 가져야 한다.
- Stateless MCP 서버를 권장한다. 세션이 필요하다면 인증, 만료, 재시도, 스케일아웃을 명확히 설계해야 한다.
- MCP 메시지는 JSON-RPC 2.0 기반이며 UTF-8 인코딩을 지켜야 한다.
- Streamable HTTP 서버는 MCP Endpoint에서 HTTP POST/GET 흐름을 지원해야 한다.

### 2.2 표준 준수 확인

- MCP Inspector로 표준 스펙 준수 여부를 사전 점검해야 한다.
- 활발하게 운영되는 MCP SDK를 사용하거나 참조해야 한다.
- 초기화 단계에서 프로토콜 버전과 capability negotiation을 정상 처리해야 한다.
- 서버는 협상되지 않은 capability를 사용해서는 안 된다.
- PlayMCP는 현재 MCP 스펙의 Resource와 Prompt 정보를 다루지 않는다. Report Guard의 사용자-facing 기능은 Tool 중심으로 설계한다.

### 2.3 인증

- 사용자 인증이 필요하지 않은 기능은 인증 없이 동작하도록 단순하게 유지한다.
- 인증이 필요한 경우 PlayMCP 서버 개발 가이드에 따라 OAuth 인증 또는 커스텀 헤더 방식을 지원해야 한다.
- OAuth를 구현하는 경우 MCP Authorization 스펙 및 OAuth 2.1 보안 요구사항을 따른다.
- Access token은 URI query string에 넣지 않는다.
- HTTP 인증 실패는 `401 Unauthorized`로 응답해야 한다.
- 토큰은 MCP 서버를 대상으로 발급된 것인지 검증해야 하며, 목적 외 downstream API 토큰 passthrough는 금지한다.

### 2.4 네트워크 및 HTTP 보안

- Streamable HTTP 구현은 `Origin` 헤더를 검증하여 DNS rebinding 위험을 줄여야 한다.
- 운영 환경에서는 HTTPS를 사용한다.
- 외부 API 호출 URL은 allowlist 또는 엄격한 URL 검증을 적용한다.
- localhost, private IP, link-local, cloud metadata endpoint로 향하는 SSRF성 요청을 허용하지 않는다.
- 리디렉션을 무조건 따라가지 말고, redirect target도 동일하게 검증한다.
- 서버 로그에는 문서 본문, 인증 토큰, API key, 사용자 이메일 등 민감 데이터를 남기지 않는다.

## 3. Tool 구성 제약사항

### 3.1 Tool 개수

- MCP 서버는 최소 1개 이상의 Tool을 포함해야 한다.
- PlayMCP 개발 가이드는 MCP 서버당 Tool 20개 초과를 금지하고, 3~10개를 권장한다.
- Review 정책은 3~20개를 권장하지만, 본 프로젝트는 더 엄격한 3~10개 권장을 따른다.
- `Report Guard`의 계획된 7개 Tool은 허용 범위에 있다.
- 동일 기능의 Tool을 이름, 문구, 출력 형식만 바꾸어 반복 등록해서는 안 된다.
- LLM 자체 웹 검색만으로 충분히 구현 가능한 기능만 제공하는 Tool은 반려될 수 있으므로, 각 Tool은 서버가 제공하는 명확한 계산, 검증, API 연동, 지침 제공 가치를 가져야 한다.

### 3.2 Tool 이름

- Tool name은 1~128자여야 한다.
- 허용 문자는 영어 대소문자, 숫자, underscore `_`, hyphen `-`뿐이다.
- Tool name은 서버 내에서 중복되면 안 된다.
- Tool name은 case-sensitive이다.
- MCP Server Name 또는 Tool Name에 `kakao`를 포함하지 않는다. 대소문자와 위치를 불문하고 사용하지 않는 것을 원칙으로 한다.
- 이름은 간결하고 기능을 대표해야 한다. `AI`, `Bot`, `Service` 같은 중복 키워드는 피한다.

### 3.3 Tool description

- description은 LLM이 기능을 정확히 이해할 수 있도록 구체적으로 작성한다.
- description은 가능하면 영어로 작성하되, 서비스명은 고유명사로 `Report Guard(리포트 가드)`처럼 영문/국문을 병기한다.
- description에는 MCP명 또는 서비스명을 포함해야 한다.
- description은 1,024자 이내로 작성한다.
- 추상적이거나 모호한 이름/설명은 심사 중 수정 요청 대상이 될 수 있다.

### 3.4 필수 property 및 schema

각 Tool은 최소한 다음 property를 포함해야 한다.

- `name`
- `description`
- `inputSchema`
- `annotations`

`annotations`에는 다음 값을 모두 지정해야 한다.

- `title`
- `readOnlyHint`
- `destructiveHint`
- `openWorldHint`
- `idempotentHint`

권장 사항:

- 가능하면 `outputSchema`도 제공하여 구조화된 결과를 검증 가능하게 한다.
- 입력 schema는 필요한 필드만 받도록 좁게 작성한다.
- 빈 입력 Tool도 `type: object`, `properties: {}`, `additionalProperties: false` 형태로 명확히 정의한다.
- Tool 결과는 사람이 읽을 수 있는 Markdown 요약과 기계가 읽을 수 있는 structured result를 함께 고려한다.

### 3.5 Tool 응답

- Tool response가 24k를 초과하면 PlayMCP에서 에러 처리될 수 있으므로 모든 응답은 24k 미만이어야 한다.
- API 원본 응답을 그대로 반환하지 않는다. 불필요한 필드를 제거하고 Report Guard의 반환 형식으로 정제한다.
- 오류 발생 시 raw stack trace, secret, 내부 URL을 반환하지 않는다.
- Tool execution error는 사용자가 이해 가능한 메시지와 재시도 가능 여부를 포함한다.
- 필요한 경우 결과에 outbound link를 포함할 수 있으나, 상업적 링크, 구매 유도, 리워드 제공 등 과도한 상업 행위는 금지한다.
- 응답에 비속어, 정치적 선동, 성적 내용, 일반 사회 통념에 위배되는 내용, 악성 파일 다운로드 유도는 포함하지 않는다.

## 4. Report Guard 기능별 개발 조건

### 4.1 공통 원칙

- Report Guard는 대학생의 report류 문서 검수 도우미다. 법률, 학칙, 학술윤리 최종 판단 기관처럼 행동하지 않는다.
- 모든 결과는 "검수 보조"이며, 확정 판정이 필요한 경우 학교/수업/지도교수/공식 학술윤리 기준을 확인하도록 안내한다.
- 한국어와 영어 문서를 모두 고려하되, 언어 감지 실패 시 명시적으로 불확실성을 반환한다.
- 문서 본문은 처리 후 저장하지 않는다.
- 검색/API 기반 기능은 공개 인터넷 또는 외부 API에서 확인 가능한 범위만 다룬다.

### 4.2 글자수/단어수/문장수/문단수 검증

- 서버 내부에서 결정적으로 계산한다.
- 결과는 character count, word count, sentence count, paragraph count를 구조화해 반환한다.
- 특정 항목 산출이 불가능하면 해당 값은 `-1`로 반환하고 이유를 함께 제공한다.
- 계산 기준은 문서화한다. 예: 공백 포함/제외 여부, 문장 구분자 기준, 문단 구분자 기준.

### 4.3 맞춤법 검사

- v1 맞춤법 검사는 무상(free-of-charge) provider만 사용한다. 유상 API나 유료 quota가 필요한 서비스는 v1 범위 밖이다.
- 무상 조건을 충족하면 (a) 로컬/offline 오픈소스 라이브러리, 또는 (b) 무상·무인증 온라인 서비스(e.g. hanspell — 네이버 맞춤법 검사기 사용, API key 불필요) 중에서 선택할 수 있다.
- 온라인/외부 호출 provider를 사용하는 경우 connect/read timeout, UTF-8 인코딩, outbound URL allowlist/SSRF 검증, 오류 정규화를 적용하고, 검사 대상 텍스트 일부가 외부 서비스로 전송됨을 §6.3에 따라 고지하며, 해당 Tool의 `openWorldHint`를 `true`로 둔다. 완전 로컬 provider면 외부 전송이 없고 `openWorldHint`는 `false`다.
- hanspell처럼 비공식 스크레이핑 기반 서비스는 가용성이 보장되지 않으므로(엔드포인트 변경/차단 가능) provider timeout과 검사 불가(no-result/partial) fallback을 설계한다.
- 라이브러리/서비스의 라이선스와 유지보수·가용성 상태를 확인한 뒤 채택한다.
- 잘못된 문장과 수정 제안을 pair로 반환한다.
- 오류가 없으면 "검출된 맞춤법 오류 없음" 상태를 별도로 반환한다.
- 맞춤법 결과는 제안이며, 문맥상 허용 가능한 고유명사/전문용어/인용문은 오탐 가능성을 표시한다.

### 4.4 출처(Citation) 검사

- 입력은 문서 내 citation 제목 목록과 선택적 사용자 이메일이다.
- 사용자 이메일이 없는 경우, 서버는 `CITATION_CHECK.md`에 정의될 검색 지침과 반환 형식을 Tool 응답으로 제공하여 LLM이 공개 웹 검색을 수행할 수 있게 한다.
- 사용자 이메일이 있는 경우, Crossref REST API 요청에 `mailto`를 사용해 polite pool 방식으로 질의한다.
- 이메일은 Crossref `mailto` 목적 외로 저장하거나 재사용하지 않는다.
- Crossref는 학술 metadata 검증에 유용하지만 모든 출처를 포괄하지 않는다. 비학술 웹페이지, 수업자료, 보고서, 뉴스, 도서 일부는 Crossref에서 확인되지 않을 수 있음을 결과에 명시한다.
- Crossref 응답은 title, DOI, publisher, publication year, authors, URL 등 필요한 필드만 정제해 반환한다.
- 동일/유사 제목 후보가 여러 개면 match_score(매칭 신뢰도)와 불확실성을 표시한다.

### 4.5 표절 검사

- Naver Search API를 사용하는 경우 client id/secret은 환경변수로만 주입하고 코드/로그/응답에 노출하지 않는다.
- Naver Search API는 일일 호출 한도 25,000회를 전제로 설계한다. Tool 호출당 query 수를 제한한다.
- query는 UTF-8로 인코딩한다.
- 검색 endpoint는 목적에 맞게 `webkr` 또는 필요한 검색 카테고리를 선택한다.
- 검색 결과 `display`는 최대 100, `start`는 최대 1000 범위를 넘지 않는다.
- 원문 문장을 N문장 단위로 쿼리하되, N과 threshold는 설정 가능하게 둔다.
- 원문과 검색 결과 snippet/title/link의 유사도를 산출하고 threshold 이상인 결과 링크만 반환한다.
- 공개 검색 결과 기반 표절 검사는 완전한 표절 판정이 아니다. 비공개 자료, 유료 DB, 학교 내부 제출물, 이미지/PDF 내 텍스트, 검색엔진 미색인 자료는 검출하지 못할 수 있음을 고지한다.
- `PLAGIARISM_CHECK.md`에 정의될 지침과 함께 LLM의 추가 공개 웹 검색을 유도할 수 있으나, 전체 응답은 24k 제한을 넘지 않아야 한다.

### 4.6 문서 구조 검사

- 서버는 `GOOD_WRITING.md`에 정의될 좋은 글 조건, 문서 구조 평가 기준, 반환 형식을 Tool 응답으로 제공한다.
- PlayMCP가 Resource/Prompt를 다루지 않으므로 `GOOD_WRITING.md`는 Tool 결과 또는 서버 내부 정적 텍스트로 제공한다.
- LLM이 문서 본문을 평가할 때 사용할 수 있도록 명확하고 짧은 rubric 형태로 유지한다.

### 4.7 필수 항목 권장

- 서버는 `TO_HAVE.md`에 정의될 필수/권장 항목 기준과 반환 형식을 Tool 응답으로 제공한다.
- 이름, 학번, 소속, 이메일, 전화번호 등은 "있으면 좋은 항목"일 수 있으나 모든 report에 항상 필요한 것은 아니다.
- 개인정보 최소 수집 원칙에 따라 문서 목적상 불필요한 개인정보를 추가하라고 강요하지 않는다.

### 4.8 전체 검사 Tool

- 전체 검사 Tool은 1~6 과정을 실행하거나 실행 지침을 결합해 최종 요약을 반환한다. 단, citation 제목처럼 특정 하위 검사에 필요한 입력이 없으면 해당 하위 검사는 건너뛰고 그 사실을 결과의 limitation/skipped pipeline에 명시한다.
- 외부 API 호출이 포함된 검사는 timeout budget을 넘기면 부분 결과와 `partial` 상태를 반환한다.
- 전체 결과는 24k 미만이어야 하며, 세부 항목은 요약/상위 N개/링크 중심으로 제한한다.

## 5. 성능 및 안정성 제약사항

### 5.1 PlayMCP 성능 기준

- Tool 응답속도는 평균 100ms 이내를 목표로 해야 한다.
- p99 응답속도는 3,000ms 이내가 필수다.
- 응답이 지나치게 느리거나 timeout이 자주 발생하면 심사 반려 사유가 될 수 있다.
- 과도한 리디렉션, 크롤링 지연, 불필요한 외부 호출은 성능 저하로 반려될 수 있다.

### 5.2 외부 호출 budget

- 외부 API를 사용하는 Tool은 전체 처리 시간을 3초 안에 끝내도록 설계한다.
- Naver/Crossref 호출은 connect/read timeout을 명시적으로 둔다.
- 네트워크 실패, 429, 5xx, quota 초과는 정상 오류 상태로 처리하고 서버 전체 장애로 전파하지 않는다.
- 동일 citation/title/query 반복 호출은 짧은 TTL cache를 고려한다.
- 전체 검사 Tool은 외부 호출 수를 제한하고, 시간이 부족하면 로컬 검사 결과를 우선 반환한다.

### 5.3 응답 크기 및 품질

- 모든 Tool 응답은 24k 미만이어야 한다.
- 장문 문서 입력에서도 결과는 요약, count, 상위 issue, 상위 suspect links 중심으로 제한한다.
- 원문 전체를 결과에 다시 포함하지 않는다.
- 중복 결과를 병합한다.
- confidence, limitation, next action을 일관된 형식으로 제공한다.

### 5.4 운영 안정성

- 서버는 cold start, dependency import, 외부 API DNS 지연을 고려해 시작 시간을 줄인다.
- health check 또는 기본 endpoint를 운영상 확인 가능하게 둔다.
- 예외는 Tool 단위로 격리한다. 하나의 검사 실패가 서버 전체 프로세스를 죽이면 안 된다.
- rate limiting을 적용해 악의적 또는 실수성 반복 호출을 완화한다.
- PlayMCP 심사 전 MCP Inspector, 로컬 테스트, PlayMCP 임시 등록 테스트를 모두 통과해야 한다.

## 6. 개인정보, 보안, 윤리 제약사항

### 6.1 개인정보 최소화

- Tool 기능과 무관한 개인정보를 수집하거나 요구하지 않는다.
- 반드시 필요한 경우를 제외하고 사용자의 인증 정보나 민감 정보를 외부로 전송하지 않는다.
- OAuth, token, key로 획득한 인증 정보는 Tool 사용 목적 외에 사용하지 않는다.
- 다음 정보를 요구하거나 response로 전송하는 기능은 만들지 않는다.
  - 주민등록번호
  - 운전면허번호
  - 여권번호
  - 외국인등록번호
  - 카드번호
  - 계좌번호

### 6.2 문서 본문 처리

- 사용자가 제공한 문서 본문은 검수 목적의 일시 처리 데이터로 취급한다.
- 문서 본문을 영구 저장하지 않는다.
- 로그에는 원문, citation 전체 목록, 이메일, 이름/학번 등 개인정보를 남기지 않는다.
- 오류 분석이 필요하면 document length, language, anonymized error code 정도만 남긴다.

### 6.3 외부 전송 고지

- Citation 검사에서 Crossref를 사용할 수 있음을 명시한다.
- 표절 검사에서 Naver Search API 및 공개 웹 검색을 사용할 수 있음을 명시한다.
- 맞춤법 검사가 온라인 provider(e.g. hanspell, 네이버 맞춤법 검사기)를 사용하는 경우 검사 대상 텍스트 일부가 해당 외부 서비스로 전송됨을 명시한다. 완전 로컬 provider면 외부 전송이 없다.
- 외부 API로 전송되는 데이터는 최소화한다. 전체 문서를 보내지 말고 필요한 query fragment/title만 보낸다.

### 6.4 Secret 관리

- Naver client id/secret, OAuth client secret, registry password, Git PAT 등은 환경변수나 배포 플랫폼 secret으로만 관리한다.
- secret을 repository, Docker image layer, log, Tool response, error message에 노출하지 않는다.
- private Git/PAT 또는 private registry credential은 최소 권한으로 발급하고 회전 가능해야 한다.

### 6.5 안전한 결과 생성

- Report Guard는 표절 회피, 출처 조작, 탐지 우회 방법을 제공하지 않는다.
- 표절 또는 citation 문제가 발견되면 수정 방향은 인용 보강, 원문 재작성, 출처 명확화, 담당자 확인 등 정직한 개선으로 제한한다.
- 사용자가 민감정보 추가를 요청하더라도 문서 목적상 불필요하면 최소화 원칙을 안내한다.

## 7. 구현 및 배포 체크리스트

개발 완료 전 반드시 확인한다.

- [ ] MCP 프로토콜 버전 `2025-03-26` 이상, `2025-11-25` 이하 호환.
- [ ] Streamable HTTP remote endpoint 제공.
- [ ] MCP Inspector 통과.
- [ ] PlayMCP `정보 불러오기` 성공.
- [ ] Tool 개수 3~10 범위.
- [ ] 모든 Tool name이 1~128자, `[A-Za-z0-9_-]` 규칙 충족.
- [ ] `kakao` 문자열이 server/tool name에 없음.
- [ ] 모든 Tool에 `name`, `description`, `inputSchema`, `annotations` 포함.
- [ ] `annotations`의 `title`, `readOnlyHint`, `destructiveHint`, `openWorldHint`, `idempotentHint` 지정.
- [ ] Tool description 1,024자 이하, 기능/서비스명 명확.
- [ ] Tool response 24k 미만.
- [ ] 평균 응답 100ms 목표, p99 3,000ms 이하 검증.
- [ ] 외부 API timeout, retry/backoff, quota handling 구현.
- [ ] 원문/개인정보/secret 미로깅.
- [ ] Naver/Crossref key와 email 처리 방식 검증.
- [ ] Docker image가 `linux/amd64`로 빌드됨.
- [ ] PlayMCP 임시 등록 후 AI 채팅에서 실제 Tool call 테스트 완료.
- [ ] 심사 승인 후 공개 상태를 `전체 공개`로 변경.

## 8. 확인 필요 항목

다음 항목은 구현 또는 제출 직전에 다시 확인한다.

- PlayMCP/공모전/Notion 문서가 변경되었는지.
- Kakao Tools 본선용 Widget 추가 스펙 및 더 엄격한 MCP 요구사항.
- 선택할 맞춤법 라이브러리/서비스의 무상(free-of-charge) 여부, 라이선스, 유지보수·가용성 상태, 외부 전송 여부(§4.3/§6.3).
- Naver Search API 실제 계정 quota와 운영 정책.
- Crossref 응답 schema 변경 여부.

## Sources

- [PROJECT_SILHOUETTE.md](./PROJECT_SILHOUETTE.md)
- [AGENTIC PLAYER 10 공모전 안내](https://b.kakao.com/views/PlayMCP/AGENTIC_PlAYER_10?t_src=developers&t_ch=devtalk)
- [PlayMCP 개발자 안내 Notion](https://app.notion.com/p/PlayMCP-21b9b97b48888093a57cc2d24e53dc60)
- [PlayMCP 서버 개발가이드](https://app.notion.com/p/PlayMCP-2d89b97b4888808a9e1dc17a13e70187)
- [MCP 심사 정책](https://app.notion.com/p/MCP-21b9b97b48888024922ec3dfcacf97e5)
- [Agentic Player 10 공모전 참가를 위한 가이드](https://app.notion.com/p/3749b97b4888803bb90bef3ddbcfbcfb)
- [Agentic Player 10 공모전 참가 방법](https://app.notion.com/p/Agentic-Player-10-3749b97b4888806b8564ee264e2fafde)
- [[필독] 공모전 참가 유의사항](https://app.notion.com/p/3749b97b488880a58d90ff614ea361d4)
- [Git 소스로 MCP 서버 등록하기](https://app.notion.com/p/Git-MCP-3749b97b4888809d8f07eb0f008a252c)
- [컨테이너 이미지로 MCP 서버 등록하기](https://app.notion.com/p/MCP-3749b97b488880a18f73f5871a314a98)
- [MCP Specification 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)
- [MCP Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP Streamable HTTP Transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [MCP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [Naver Search API - 웹문서](https://developers.naver.com/docs/serviceapi/search/web/web.md)
- [Naver Search API - 블로그](https://developers.naver.com/docs/serviceapi/search/blog/blog.md)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Crossref REST API Tips](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)
