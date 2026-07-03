# Report Guard (리포트 가드)

A remote **Streamable HTTP MCP server** that helps university students check reports
before submission. Client-agnostic (ChatGPT for Kakao, OpenClaw); registered/curated
via PlayMCP. Server name: **Report Guard**.

## Tools (8)

| Tool | What it does | External calls |
| --- | --- | --- |
| `count_document_units` | character/word/sentence/paragraph counts (deterministic, local) | no |
| `check_document_spelling` | spelling/grammar pairs via a free no-auth speller (hanspell) | yes |
| `check_document_citations` | existence check — Korean → KCI, English → Semantic Scholar (conference/arXiv coverage; DOIs cross-checked against the Crossref registry) then Crossref fallback; unconfirmed items left for the host LLM's own web search | yes |
| `check_document_plagiarism` | bounded Naver web-search similarity risk signals | yes |
| `get_writing_structure_guidance` | writing-structure rubric for the host LLM | no |
| `get_required_fields_guidance` | recommended header-field checklist (privacy-minimizing) | no |
| `get_citation_format_guidance` | correct citation/표기법 rules (APA/IEEE/국내) + in-text↔reference checks for the host LLM | no |
| `run_full_report_check` | composes the above into one compressed summary | yes |

All tools are read-only, non-destructive, idempotent. Responses stay under 24k. Raw
document text, emails, secrets, and upstream bodies are never persisted or logged.

## Architecture

See [`docs/`](./docs) — the build follows `SYSTEM_ARCHITECTURE.md` and
`INTER_MODULE_INTERFACES.md`. Layering:

```
mcp_transport → tool_registry → pipeline_orchestrator → pipelines/* → clients/*
                                                        ↘ result_formatter
shared low-level: config · security · errors · schemas · logging · rate_limit · observability
```

## Local development

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # fill NAVER_CLIENT_ID / NAVER_CLIENT_SECRET for plagiarism
pytest -q                   # run the test suite
report-guard                # serve on http://0.0.0.0:8080  (MCP at /mcp, health at /health)
```

### Environment variables

Required (for plagiarism): `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` — without them
`check_document_plagiarism` returns "평가 불가" (config missing). Optional:
`KCI_API_KEY` (Korea Citation Index Open API key for verifying Korean-journal
citations; without it Korean titles are left "미확인" for the host LLM to verify with
its own web search), `S2_API_KEY` (Semantic Scholar API key — the primary English
citation index works keyless on the shared public pool, but a key gives a dedicated
rate limit; sent only as an `x-api-key` header), `USER_EMAIL` (Crossref polite-pool
contact for the English citation path; verification still works anonymously without
it), and `SPELLCHECK_PROVIDER` (`composite` default; set `mock` for offline).
Secrets are read from the environment only.

`report-guard` auto-loads `.env` from the working directory on startup (existing env
vars are never overridden). Check what the running server actually sees at
`GET /health` → `missing_required_secrets`.

## MCP Inspector

```bash
report-guard &                                   # start the server
npx @modelcontextprotocol/inspector              # connect to http://127.0.0.1:8080/mcp
```

Verify: `initialize` negotiates the protocol, `tools/list` shows 8 tools with
annotations, and each `tools/call` returns a Markdown summary + structured content.

## Deploy (PlayMCP in KC)

Build for **linux/amd64** (arm64 images fail to activate):

```bash
docker build --platform linux/amd64 -t report-guard-mcp .
docker run --platform linux/amd64 -p 8080:8080 \
  -e NAVER_CLIENT_ID=... -e NAVER_CLIENT_SECRET=... \
  -e USER_EMAIL=... -e ALLOWED_ORIGINS=https://your-host report-guard-mcp
```

**Secrets on PlayMCP / KakaoCloud:** PlayMCP builds the image **from the git source**
(Git URL + branch + Dockerfile path + PAT) and provides no runtime env-var injection.
So `.env` is committed to this **private** repo and baked into the image by the
Dockerfile (`COPY .env`); `main()` loads it on startup. This means:

- Keep the repository **private**; scope the PAT to **read-only** with a short expiry.
- Use a **dedicated Naver application** (Search API only) and **rotate the keys**
  regularly — anyone with repo or image access can read them.
- After deploy, hit `GET /health` and confirm `missing_required_secrets` is empty; if
  it lists the Naver keys, `.env` was not picked up.

If you later move to a platform that injects env vars/secrets at runtime, untrack
`.env` (`git rm --cached .env`), re-ignore it in `.gitignore`, and remove `COPY .env`
from the Dockerfile.

Then register the public `/mcp` endpoint in the PlayMCP developer console, confirm
`정보 불러오기` succeeds, test via 임시 등록 + AI 채팅, request review, and set the server
to `전체 공개` after approval. Set `ALLOWED_ORIGINS` in production to enable Origin /
DNS-rebinding protection.

## Documents

1. [Project silhouette](./docs/PROJECT_SILHOUETTE.md)
2. [Development conditions](./docs/DEVELOPMENT_CONDITIONS.md)
3. [System architecture](./docs/SYSTEM_ARCHITECTURE.md)
4. [Inter-module interfaces](./docs/INTER_MODULE_INTERFACES.md)
