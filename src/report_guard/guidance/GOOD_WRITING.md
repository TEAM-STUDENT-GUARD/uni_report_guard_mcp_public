<!--
guidance_id: GOOD_WRITING
version: 2.0.0
title: 리포트 글 구조 평가 기준
-->

# 리포트 글 구조 평가 기준

이 문서는 사용자에게 보여줄 자료가 아니라, 어시스턴트인 당신에게 주는 검사 지시서입니다.
Report Guard 서버는 문서를 검사하지 않았으니, 당신이 아래 기준으로 사용자가 제출한 실제
문서를 직접 평가해야 합니다. 항목은 학술 글쓰기 통념과 아래 출처(IMRaD, Purdue OWL, APA)를
근거로 합니다.

## Section: 어시스턴트 검사 지시 (먼저 읽기)
checklist:
- 이 내용을 사용자에게 그대로 옮기거나 "이런 것을 점검하세요"라고 되돌려주지 마세요.
- 아래 기준을 사용자가 방금 제출한 실제 문서에 하나씩 적용하세요.
- 각 기준마다 충족 / 부분 충족 / 미충족을 판정하고, 판단 근거로 문서의 실제 문장이나 문단(짧게 인용)을 제시하세요.
- 문서에 없는 내용을 지어내지 말고, 확인한 사실만 쓰세요.
- 마지막에 우선순위 상위 3개 개선안을 문서에 맞게 구체적으로 제안하세요.

## Section: 핵심 품질 (문서 유형·언어 무관)
checklist:
- 글 앞부분에 논지(thesis)나 목적이 분명히 제시되어 있는가.
- 각 문단이 하나의 중심 생각을 담고 그 논지를 뒷받침하는가.
- 논리적 흐름: 주장이 순서대로 배열되고 연결어로 이어지는가.
- 주장을 근거가 뒷받침하며, 필요한 곳에 출처가 표시되어 있는가.
- 결론은 새 주장을 덧붙이지 않고 핵심 결과를 정리하는가.
- 용어가 일관되고 핵심 용어가 정의되어 있는가.
- 군더더기 없이 간결한가.

## Section: 문서 유형별 구조
checklist:
- 학술 에세이: 서론(논지) → 본론(절마다 하나의 주장) → 결론.
- 실험·실습 보고서: IMRaD 구조 — 서론(Introduction) → 방법(Methods) → 결과(Results) → 논의(Discussion) → 결론.
- 문헌 고찰: 범위 설정 → 주제별 정리 → 종합 → 미해결 과제 → 결론.
- 성찰·저널: 맥락 → 관찰 → 분석 → 시사점.
- 제안서: 문제 → 목표 → 접근 방법 → 일정 → 기대 효과.

## Section: IMRaD 구조와 분량 배분 참고
checklist:
- 초록(Abstract)은 IMRaD의 축약본으로, 방법·결과·시사점을 요약한다.
- 서론 약 10~15%, 방법 약 20~30%, 결과 약 20~25%, 논의 약 25~30%를 대략적 참고치로 본다(과제 성격에 따라 조정).
- 서론은 배경 → 문제 → 목적/연구질문 순으로 좁혀 간다.
- 논의는 결과의 의미, 한계, 후속 과제를 다룬다.

## Section: 한국어·영어 문체 고려
checklist:
- 한국어 학술 문체: 문어체(서술체) 어미(예: -다/-이다)를 일관되게 쓰고 구어체 혼용을 피한다.
- 영어 학술 문체: 시제 일관, 축약형 지양, 능동태 선호.
- 공통: 문단 길이의 균형을 맞추고, 의도가 아니라면 한 문장짜리 문단을 피한다.

## Section: 근거 기준 및 출처
checklist:
- Purdue Online Writing Lab(OWL), "Organization and Structure" 및 "Reports, Proposals, and Technical Papers". https://owl.purdue.edu/owl/
- Sollaci, L. B., & Pereira, M. G. (2004). The introduction, methods, results, and discussion (IMRAD) structure: a fifty-year survey. Journal of the Medical Library Association, 92(3), 364-371. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC442179/
- American Psychological Association. (2020). Publication Manual of the American Psychological Association (7th ed.). https://apastyle.apa.org/
- Booth, W. C., Colomb, G. G., Williams, J. M., et al. (2016). The Craft of Research (4th ed.). University of Chicago Press.

## Expected LLM output format
사용자의 실제 문서를 검사한 결과를 다음 형식으로 제시하세요(가이드 원문 나열 금지):
- `overall`: 이 문서의 구조에 대한 한두 문장 총평.
- `structure_map`: 이 문서가 실제로 어떤 구성(예: 초록 → 서론 → … → 결론 → 참고문헌)을 따르는지 요약.
- `strengths`: 이 문서의 강점 목록(각 항목에 문서 근거를 짧게 인용).
- `issues`: 이 문서의 문제 목록(각각 위치 힌트 + 문서 근거 + 수정 방향).
- `priority_fixes`: 이 문서에 대한 우선순위 상위 3개 개선안.

## Limitations
- 이는 글쓰기 보조 기준이지 공식 채점 기준이 아닙니다.
- 최종 구조 기대치는 과목, 교수자, 과제 안내에 따라 달라집니다.
- 분량 배분 수치는 IMRaD 관행에 따른 대략적 참고치이며 규정이 아닙니다.
