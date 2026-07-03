# PROJECT uni_report_guard_mcp

## 프로젝트 목표
1. Agentic Player 10 공모전 수상 MCP 개발
    - Agentic Player 10 공모전 안내: https://b.kakao.com/views/PlayMCP/AGENTIC_PlAYER_10?t_src=developers&t_ch=devtalk
    - **PlayMCP 개발자 안내 notion 문서**: https://app.notion.com/p/PlayMCP-21b9b97b48888093a57cc2d24e53dc60
        - **PlayMCP 서버 개발 가이드**: https://www.notion.so/PlayMCP-2d89b97b4888808a9e1dc17a13e70187
    - PlayMCP 베타 (여러 MCP 서버 큐레이션 리스트): https://playmcp.kakao.com/?page=0

2. 프로젝트 목표: 대학생이 대학생활동안 작성해야 하는 문서(report 류)들에 대한 검수 도우미 MCP 서버
    - MCP 서버 이름: "Report Guard" (한글 / 영어 지원)
    - tools 기능
        1. **글자수/단어수/문장수/문단수 검증** - LLM이 tool calling 시 parameter에 document text 포함하여 MCP 서버로 전달. MCP 서버는 글자수/단어수/문장수/문단수 산출 후 결과값 4개 4개 파라미터로 반환 (결과값 -1이면 산출 불가)
        2. **문서 맞춤법 검사** - LLM이 tool calling 시 parameter에 document text 포함하여 MCP 서버로 전달. MCP 서버는 무상(free-of-charge) 오픈소스 라이브러리/서비스로 맞춤법 검사 로직 구현 (e.g. hanspell 등 — 네이버 맞춤법 검사기를 사용하는 무상·무인증(API key 불필요) 라이브러리; 유상 API는 v1에서 사용하지 않음). 이후 맞춤법이 틀린 문장과 수정 문장을 페어로 파라미터에 넣어서 반환. (맞춤법이 전부 맞는 경우를 따로 정해서 반환)
        3. **문서 출처(Citation) 검사** - LLM이 tool calling 시 parameter에 document 내 모든 citation 제목들, user email(optional) 포함하여 MCP 서버로 전달. MCP 서버는 1. *user email이 없는 경우* -> LLM에게 CITATION_CHECK.md 문서 내용 반환 (CITATION_CHECK.md: 어떻게 Citation 검사를 하는지, 어떤 검색어 조합으로 검색을 해야 하는지, 유저에게 인터넷 공개 정보로만 출처 검사하는 것에 대한 한계 고지 어떻게 하는지, 어떤 형식으로 결과를 반환하는지 등 내용), 이후 LLM이 직접 검색해서(자체 웹서치 기능 사용) 결과를 반환. 2. *user email이 있는 경우* -> crossref.org의 mailto 기능 사용해서 검증 결과 (결과 형식이 어떤지는 crossref 반환 형식 어떤지 따로 확인해서 개발) MCP 서버로 반환 후 MCP서버에서 최종 반환 형식에 맞춰서 반환.
        4. **문서 표절 검사** - LLM이 tool calling 시 parameter에 document text 포함하여 MCP 서버로 전달. MCP 서버는 네이버 검색 API(공용 API 키 사용 예정, 단 키는 코드/로그에 노출하지 않고 환경변수 secret `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`으로만 주입) 사용하여 N문장 단위(쿼리양 조절용으로 향후 조정 가능하게 개발)로 네이버에 쿼리. 반환되는 결과를 가지고 MCP 서버에서 원 문장과 유사도 산출. 특정 threshold 이상의 유사도를 가진 검색 결과 링크만 반환. 또한 이 결과와 함께 LLM에게 PLAGIARISM_CHECK.md 문서 내용 반환 (PLAGIARISM_CHECK.md: 어떻게 plagiarism 검사를 하는지, 어떤 검색어 조합으로 검색을 해야 하는지, 유저에게 인터넷 공개 정보로만 표절 검사하는 것에 대한 한계 고지 어떻게 하는지, 어떤 형식으로 이전 결과와 함께 서칭 결과를 반환하는지 등 내용), 이후 LLM이 직접 검색해서(자체 웹서치 기능 사용) 최종 결과를 반환.
        5. **문서 구조 검사 (구조 추천/개선 등)** - LLM이 tool calling 시 empty parameter로 MCP 서버로 전달. MCP 서버는 LLM에게 GOOD_WRITING.md 문서 내용 반환 (GOOD_WRITING.md: 언어 / 글의 형식과 무관하게 좋은 글의 조건과 여러 형식에 따른 좋은 글의 조건, 그리고 결과 반환 형식이 정의된 문서), 이후 LLM이 직접 GOOD_WRITING.md를 기반으로 document 평가.
        6. **문서 필수 항목 권장 (이름 / 학번 / 소속 등)** - LLM이 tool calling 시 empty parameter로 MCP 서버로 전달. MCP 서버는 LLM에게 TO_HAVE.md 문서 내용 반환 (TO_HAVE.md: 빼먹을 수 있거나 있으면 좋은 정보들 리스트(이름 / 학번 / 소속 / 이메일 / 전화번호 등), 그리고 결과 반환 형식이 정의된 문서), 이후 LLM이 직접 TO_HAVE.md를 기반으로 document 평가.
        7. **1-6 과정 전부 진행** - 1 - 6 과정을 전부 진행, LLM이 최종 결과를 유저에게 반환.
3. 개발 조건: 공모전 제약조건 (MCP 서버 관련 제약조건, 성능 관련 제약조건, 개인정보 관련 제약조건 등 공모전 안내/개발 링크 참조) 고려, MCP 동작 플랫폼(실제 서버를 소비하는 target client app) 고려: ChatGPT for Kakao, OpenClaw. (PlayMCP와 Kakao Tools는 공모전 등록/큐레이션 surface이며 client app이 아니다.) 등