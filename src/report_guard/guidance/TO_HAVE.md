<!--
guidance_id: TO_HAVE
version: 2.0.0
title: 리포트 표지·기본 항목 기준
-->

# 리포트 표지·기본 항목 기준

이 문서는 사용자에게 보여줄 자료가 아니라, 어시스턴트인 당신에게 주는 검사 지시서입니다.
Report Guard 서버는 문서를 검사하지 않았으니, 당신이 아래 항목이 사용자가 제출한 실제
문서에 있는지 직접 확인해야 합니다. 표지 항목은 APA 7판 학생용 표지, 개인정보 항목은
개인정보 보호법을 근거로 합니다.

## Section: 어시스턴트 검사 지시 (먼저 읽기)
checklist:
- 이 항목 목록을 사용자에게 그대로 옮기지 마세요.
- 아래 항목이 실제 문서(주로 표지/머리말)에 있는지 하나씩 확인하세요.
- "포함된 항목"과 "빠졌거나 보완이 필요한 항목"으로 나눠, 문서에서 확인한 실제 값(예: 제목, 작성일)을 함께 제시하세요.
- 개인정보 최소 수집 원칙을 지켜, 과제에 불필요한 개인정보(특히 민감정보/고유식별정보)는 추가를 권하지 마세요.

## Section: 일반적으로 기대되는 항목
checklist:
- 리포트/과제 제목.
- 작성자 이름.
- 과목명 및/또는 과목 코드.
- 담당 교수(지도자) 이름.
- 제출일.
- (형식이 정해진 경우) 페이지 번호.

## Section: 맥락에 따라 넣는 항목 (필요할 때만 권장)
checklist:
- 학번 — 국내 대학에서 흔함. 과목이 요구할 때만 포함.
- 소속(학과, 단과대학) — APA 학생용 표지의 소속(affiliation) 항목에 해당.
- 이메일 — 교수가 요구할 때만 포함.
- 전화번호 — 거의 필요 없음. 명시적으로 요구될 때만.
- 팀/조원 명단 — 조별 과제일 때만.

## Section: 개인정보 최소 수집 (중요)
checklist:
- 과제에 불필요한 개인정보 수집을 권하지 않는다.
- 민감정보·고유식별정보를 표지에 넣도록 권하지 않는다: 주민등록번호, 여권번호, 운전면허번호, 외국인등록번호, 카드·계좌번호 등(개인정보 보호법 제23조 민감정보, 제24조 고유식별정보).
- 사용자가 이런 정보를 넣으려 하면 최소한으로 제한하도록 안내하고 주의를 준다.

## Section: 근거 기준 및 출처
checklist:
- American Psychological Association, "Title page setup" (Student paper), APA Style 7th edition. https://apastyle.apa.org/style-grammar-guidelines/paper-format/title-page
- APA, "Student Title Page Guide" (7th ed. PDF). https://apastyle.apa.org/instructional-aids/student-title-page-guide.pdf
- 개인정보 보호법 제23조(민감정보의 처리 제한), 제24조(고유식별정보의 처리 제한). 국가법령정보센터. https://www.law.go.kr/

## Expected LLM output format
사용자의 실제 문서를 확인한 결과를 다음 형식으로 제시하세요(항목 목록 나열 금지):
- `present`: 문서에서 확인된 항목과 그 실제 값(예: 제목="...", 작성일="...").
- `missing_recommended`: 일반적으로 기대되지만 이 문서에 빠진 것으로 보이는 항목.
- `optional_consider`: 맥락 의존 항목(각각 "~인 경우에만" 단서 포함).
- `privacy_note`: 최소 수집 원칙을 강조하는 한 줄.

## Limitations
- 항목 기대치는 과목, 교수자, 과제 안내에 따라 달라집니다.
- 이는 참고용 가이드이며 공식 제출 요건이 아닙니다.
- APA 표지 기준은 하나의 예시이며, 과제가 다른 양식을 요구하면 그 양식이 우선합니다.
