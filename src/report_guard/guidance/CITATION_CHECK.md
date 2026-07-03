<!--
guidance_id: CITATION_CHECK
version: 2.2.0
title: 참고문헌 존재 확인 후속 가이드
-->

# 참고문헌 존재 확인 후속 가이드

Report Guard는 각 참고문헌을 언어에 따라 학술 DB로만 1차 조회합니다: 한국어 논문은
KCI(한국학술지인용색인), 영어 논문은 Semantic Scholar(학회 논문·arXiv 포함)와 Crossref.
서버는 공개 웹을 검색하지 않으므로, 이 학술 DB들에서 확정되지 않은 항목은 "미확인"으로
남습니다. 이 문서는 사용자에게 그대로
보여줄 자료가 아니라, 어시스턴트인 당신에게 주는 지시서입니다. 함께 반환된 자동 검사
결과(확인됨/유사 후보/미확인)를 사용자에게 정리해 제시하고, 웹 검색이 가능하다면 아래
방법으로 당신이 직접 웹서치로 후속 검증까지 수행하세요. 검색으로 안 나온다고 해서 존재하지
않는 것은 아닙니다.

## Section: 어시스턴트 작업 지시 (먼저 읽기)
checklist:
- 이 가이드 원문을 사용자에게 그대로 나열하지 마세요.
- 함께 반환된 각 참고문헌의 자동 판정(확인됨/유사 후보/미확인)을 사용자에게 정리해 보여주세요.
- 서버는 KCI(한국어)·Semantic Scholar/Crossref(영어)까지만 조회하고 웹 검색은 하지 않습니다. 웹 검색 도구를 쓸 수 있다면, "미확인"과 "유사 후보" 항목을 당신의 웹서치로 직접 2차 검증하세요(확인됨 항목도 여력이 되면 교차 확인).
- 각 항목을 confirmed(신뢰할 수 있는 출처로 확인) / likely / unconfirmed로 다시 판정하고, 찾은 출처 URL을 제시하세요.
- 한국 논문은 KCI·RISS·DBpia·국립중앙도서관, 해외 논문은 Semantic Scholar·Crossref·DOI 리졸버·Google Scholar·출판사 페이지에서 확인하세요.
- 공개 검색만으로는 모든 출처를 확인할 수 없다는 한계를 함께 고지하세요.

## Section: 각 참고문헌 확인 방법
checklist:
- 제목을 큰따옴표로 정확히 묶어 먼저 검색한다.
- 일치가 없으면 제목에 제1저자 성 또는 발행연도를 더해 검색한다.
- 학술 자료는 "doi", 학술지명, 출판사 같은 단어를 함께 넣는다.
- 신뢰도 높은 출처를 우선한다: 출판사 페이지, DOI 리졸버(doi.org), Google Scholar, 도서관 목록, 기관 공식 페이지.
- 국내 논문은 KCI, RISS, DBpia, 국립중앙도서관에서 확인한다.
- 낮은 품질의 단일 일치는 미확인으로 취급한다.

## Section: 시도할 검색 쿼리 조합
checklist:
- "<정확한 제목>"
- <제목> <제1저자 성>
- <제목> <발행연도>
- <제목> doi
- <제목의 특징적 구절> 학술지 OR 학회

## Section: 결과 분류 방법
checklist:
- `confirmed`: 제목(및 아는 경우 저자·연도)이 일치하는 신뢰할 수 있는 출처를 찾음.
- `likely`: 그럴듯하지만 일부 정보가 다르거나 출처가 약함.
- `unconfirmed`: 신뢰할 수 있는 공개 출처를 찾지 못함.
- 공개 검색만으로 참고문헌을 "조작됨"이라고 단정하지 않는다.

## Section: 근거 기준 및 출처
checklist:
- Crossref REST API — 학술 메타데이터·DOI. https://www.crossref.org/
- Semantic Scholar — 학회 논문·arXiv 포함 학술 검색. https://www.semanticscholar.org/
- International DOI Foundation, DOI 리졸버. https://www.doi.org/
- 한국학술지인용색인(KCI). https://www.kci.go.kr/
- 한국교육학술정보원 RISS. https://www.riss.kr/
- American Psychological Association, "How do I cite ... / verifying sources", APA Style. https://apastyle.apa.org/

## Expected LLM output format
각 참고문헌 제목별로 다음을 반환하세요:
- `title`: 제목
- `status`: confirmed | likely | unconfirmed
- `best_source_url`: 찾은 경우 가장 신뢰할 수 있는 출처 URL
- `notes`: 근거(저자·연도 불일치, 약한 출처 등 간단히)
그다음 전체 결과를 한 줄로 요약하세요.

## Limitations
- 공개 웹 검색으로 모든 출처를 확인할 수는 없습니다: 비학술 웹페이지, 강의 자료, 내부 보고서, 뉴스, 일부 도서는 찾지 못할 수 있습니다.
- 공개 일치가 없다고 해서 출처가 가짜라는 뜻은 아닙니다. 오프라인·유료·미색인 자료일 수 있습니다.
- 이는 검증 보조 도구이며 연구윤리 판정이 아닙니다.
