# Report Guard

> 대학생이 리포트를 제출하기 전에 문서의 분량, 구조, 인용, 참고문헌 등을 점검할 수 있도록 돕는 MCP 서비스입니다.

Report Guard는 대학생이 직접 작성한 리포트를 제출 전에 한 번 더 확인할 수 있도록 돕는 **Streamable HTTP 기반 원격 MCP 서버**입니다.

ChatGPT for Kakao, OpenClaw 등 다양한 MCP 클라이언트에서 사용할 수 있으며, PlayMCP를 통해 등록 및 공개됩니다.

* **Service Name:** Report Guard
* **Transport:** Streamable HTTP
* **MCP Endpoint:** `/mcp`
* **Health Check:** `/health`

## Why Report Guard?

리포트를 제출하기 전에는 글자 수와 분량뿐 아니라 문서 구조, 필수 항목, 인용 표기, 참고문헌 등을 다시 확인해야 합니다.

하지만 각 항목을 확인하기 위해 맞춤법 검사기, 학술 검색 서비스, 웹 검색 등을 따로 이용해야 하는 경우가 많습니다.

Report Guard는 이러한 제출 전 점검 과정을 하나의 MCP 서비스에서 수행할 수 있도록 구성했습니다. 리포트를 대신 작성하기보다, 사용자가 직접 작성한 결과물에서 확인이 필요한 부분을 찾고 보완하도록 돕는 것을 목표로 합니다.

## Tools

Report Guard는 총 8개의 MCP Tool을 제공합니다.

| Tool                             | 기능                     | 외부 API |
| -------------------------------- | ---------------------- | :----: |
| `count_document_units`           | 글자, 단어, 문장, 문단 수 계산    |   없음   |
| `check_document_spelling`        | 맞춤법 및 문법 점검            |   사용   |
| `check_document_citations`       | 국내외 참고문헌의 존재 여부 확인     |   사용   |
| `check_document_plagiarism`      | 공개 웹 검색 기반 표절 위험 신호 확인 |   사용   |
| `get_writing_structure_guidance` | 문서 구조 점검 기준 제공         |   없음   |
| `get_required_fields_guidance`   | 리포트 필수 항목 체크리스트 제공     |   없음   |
| `get_citation_format_guidance`   | APA, IEEE, 국내 인용 형식 안내 |   없음   |
| `run_full_report_check`          | 주요 점검 결과를 하나의 요약으로 제공  |   사용   |

### 참고문헌 확인

참고문헌의 언어와 유형에 따라 다음 학술 데이터 소스를 활용합니다.

| 구분            | 활용 데이터 소스                  |
| ------------- | -------------------------- |
| 국내 학술자료       | KCI                        |
| 해외 논문 및 학회 자료 | Semantic Scholar           |
| DOI 및 서지정보    | Crossref                   |
| 확인되지 않은 항목    | 호스트 LLM의 웹 검색을 통한 추가 확인 안내 |

### 표절 위험 신호

네이버 검색 API를 통해 문서의 일부 표현과 유사한 공개 웹 문서를 탐색합니다.

이 기능은 정식 표절 판정을 제공하지 않으며, 사용자가 추가로 확인할 필요가 있는 문장이나 표현을 찾기 위한 사전 점검 기능입니다.

## Design Principles

Report Guard의 모든 Tool은 다음 원칙에 따라 설계했습니다.

* 원본 문서를 수정하지 않는 읽기 전용 작업
* 같은 입력에 대해 동일한 결과를 반환하는 멱등성
* 원문, 이메일, API Key 및 외부 API 응답 본문 미저장
* 검사 결과를 단정하지 않고 추가 확인이 필요한 근거 제공
* 응답 크기를 24KB 이하로 제한
* 사용자의 최종 판단과 수정을 지원하는 방식

## Architecture

세부 설계 문서는 [`docs/`](./docs) 디렉터리에서 확인할 수 있습니다.

```text
mcp_transport
    ↓
tool_registry
    ↓
pipeline_orchestrator
    ↓
pipelines/*
    ↓
clients/*
    ↘
result_formatter
```

공통 모듈은 다음과 같이 구성됩니다.

```text
config
security
errors
schemas
logging
rate_limit
observability
```

## Project Structure

```text
report-guard/
├── docs/
├── src/
│   └── report_guard/
│       ├── clients/
│       ├── pipelines/
│       ├── config.py
│       ├── mcp_transport.py
│       ├── pipeline_orchestrator.py
│       ├── result_formatter.py
│       └── tool_registry.py
├── tests/
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Local Development

### 1. 가상환경 생성

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Windows에서는 다음 명령어를 사용합니다.

```bash
.venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -e ".[dev]"
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일에 필요한 API Key를 입력합니다.

### 4. 테스트 실행

```bash
pytest -q
```

### 5. 서버 실행

```bash
report-guard
```

서버는 기본적으로 다음 주소에서 실행됩니다.

```text
MCP:    http://0.0.0.0:8080/mcp
Health: http://0.0.0.0:8080/health
```

## Environment Variables

| 환경 변수                 |  필수 여부  | 설명                              |
| --------------------- | :-----: | ------------------------------- |
| `NAVER_CLIENT_ID`     |    필수   | 네이버 검색 API Client ID            |
| `NAVER_CLIENT_SECRET` |    필수   | 네이버 검색 API Client Secret        |
| `KCI_API_KEY`         |    선택   | 국내 학술자료 확인을 위한 KCI API Key      |
| `S2_API_KEY`          |    선택   | Semantic Scholar 전용 호출 한도 사용    |
| `USER_EMAIL`          |    선택   | Crossref Polite Pool 사용을 위한 연락처 |
| `SPELLCHECK_PROVIDER` |    선택   | 맞춤법 검사 Provider 설정              |
| `ALLOWED_ORIGINS`     | 운영 시 권장 | 허용할 Origin 설정                   |

`SPELLCHECK_PROVIDER`의 기본값은 `composite`입니다. 외부 요청 없이 테스트하려면 `mock`으로 설정할 수 있습니다.

네이버 API Key가 설정되지 않은 경우 `check_document_plagiarism`은 표절 위험을 평가하지 않고 설정 누락 상태를 반환합니다.

서버가 인식한 환경 변수 상태는 다음 경로에서 확인할 수 있습니다.

```text
GET /health
```

응답의 `missing_required_secrets`가 비어 있는지 확인합니다.

## MCP Inspector

서버를 실행합니다.

```bash
report-guard
```

새로운 터미널에서 MCP Inspector를 실행합니다.

```bash
npx @modelcontextprotocol/inspector
```

다음 MCP 주소에 연결합니다.

```text
http://127.0.0.1:8080/mcp
```

아래 항목을 확인합니다.

* `initialize` 요청이 정상적으로 처리되는지
* `tools/list`에서 8개의 Tool이 표시되는지
* `tools/call`이 Markdown 요약과 구조화된 결과를 반환하는지

## Docker

PlayMCP 및 KakaoCloud 환경에서는 `linux/amd64` 이미지가 필요합니다.

### Build

```bash
docker build \
  --platform linux/amd64 \
  -t report-guard-mcp .
```

### Run

```bash
docker run \
  --platform linux/amd64 \
  -p 8080:8080 \
  -e NAVER_CLIENT_ID=... \
  -e NAVER_CLIENT_SECRET=... \
  -e USER_EMAIL=... \
  -e ALLOWED_ORIGINS=https://your-host \
  report-guard-mcp
```

## Deployment

PlayMCP는 Git 저장소와 Dockerfile을 기반으로 이미지를 빌드합니다.

배포 후 다음 항목을 확인합니다.

1. `/health`가 정상적으로 응답하는지 확인합니다.
2. `missing_required_secrets`가 비어 있는지 확인합니다.
3. 공개된 `/mcp` 엔드포인트를 PlayMCP 개발자 콘솔에 등록합니다.
4. `정보 불러오기`를 통해 Tool 목록을 확인합니다.
5. 임시 등록과 AI 채팅을 통해 각 Tool을 테스트합니다.
6. 심사를 요청하고 승인 후 서비스를 `전체 공개`로 전환합니다.

### Secret 관리 주의사항

API Key가 포함된 `.env` 파일은 원칙적으로 Git 저장소와 Docker 이미지에 포함하지 않는 것이 안전합니다.

가능한 경우 배포 플랫폼의 환경 변수 또는 Secret Manager를 통해 주입해야 합니다.

플랫폼 제약으로 인해 이미지 빌드 과정에서 Secret을 포함해야 한다면 다음 조치가 필요합니다.

* 저장소를 비공개로 유지
* 최소 권한의 읽기 전용 PAT 사용
* PAT 만료 기간을 짧게 설정
* 서비스 전용 API Key 사용
* API Key 정기 교체
* 배포 후 Key 노출 여부 확인

런타임 환경 변수 주입이 가능한 플랫폼으로 이전한 뒤에는 다음과 같이 `.env` 추적을 해제해야 합니다.

```bash
git rm --cached .env
```

이후 `.gitignore`에 `.env`를 추가하고 Dockerfile의 `COPY .env` 설정을 제거합니다.

## Documents

| 문서                                                           | 설명            |
| ------------------------------------------------------------ | ------------- |
| [Project Silhouette](./docs/PROJECT_SILHOUETTE.md)           | 프로젝트의 목표와 범위  |
| [Development Conditions](./docs/DEVELOPMENT_CONDITIONS.md)   | 개발 및 운영 조건    |
| [System Architecture](./docs/SYSTEM_ARCHITECTURE.md)         | 전체 시스템 구조     |
| [Inter-module Interfaces](./docs/INTER_MODULE_INTERFACES.md) | 모듈 간 인터페이스 정의 |

