---
name: eddie-blog-auto
description: 에디(블로그명 "AI 에디"/ioiykd8599) 네이버 블로그 하루치 자동 생성 스킬(현행 run_ai_daily 시스템). "에디 블로그 자동화 실행", "오늘 블로그 만들어줘", "블로그 5편", "AI 글 만들어줘", "연예 글 만들어줘", "블로그 자동 생성" 등 에디 블로그를 자동 초안 생성→임시저장할 때 사용. 강점코치 옛버전(10편) 아님. 한성협(금사장)·유튜브와 별개.
---

> ★**저장소(2026-08-08)**: `https://github.com/jin3175-ctrl/edi-blog-auto` (private).
> 집 노트북 상시 구동용으로 옮겼다. **새 머신 세팅은 저장소 `CLAUDE.md`의 '새 맥에서 세팅'** 참고
> (네이버 로그인상태유지 ON·IP보안 OFF / `~/홈판자료/.env`의 GEMINI_API_KEY / 제미나이 웹 로그인 /
> launchd 등록 / **두 대 동시 구동 금지**). 스킬은 저장소 `skills/eddie-blog-auto`를 심링크로 설치.
> ★**사진 출처는 세 칸으로 자세히**(2026-08-10): `[사진N - 장면 / 출처: 방송사 '프로그램' 회차(방송일) / 유튜브 검색: 검색어]`.
> 회차·방송일·검색어가 없으면 에디님이 유튜브에서 그 장면을 못 찾는다. LLM이 빠뜨리면
> `gen_celeb_ai._enrich_photo_sources()`가 코드로 채운다(사진마다 다른 검색어).
> ★**연예편 이미지 자동첨부는 껐다**(`gen_celeb_ai.CELEB_AUTO_PHOTOS=False`, 에디님 지시) —
> 캡처·썸네일을 만들지 않고 `[사진N - 장면 / 출처: 프로그램(방송사)]` 마커만 남긴다. 사진은 에디님이 직접 삽입.

# 에디 블로그 자동화 (현행 최종, 2026-08-01)

블로그 "AI 에디"(blog_id `ioiykd8599`)의 하루치 글을 **코드로 직접 생성 → 네이버 임시저장**한다.
브라우저/ChatGPT 왕복 없음. 전부 `~/클로드 코드 블로그 자동화 웹`의 파이썬 파이프라인.
> ★상세 이력·근거(반드시 먼저 읽기): `~/홈판자료/에디AI블로그_핸드오프.md` + `~/홈판자료/블로그정체성_AI실전_확정.md`.
> 옛 v8.4(10편·강점코치·브라우저조작)는 폐기. 이 문서가 현행.

## ★★ 절대 1순위 = 네이버 홈판(홈피드) 노출 → 애드포스트 수익
- 제목·본문·**특히 제목·썸네일·도입부**를 '지금 홈판에 뜨는 것'의 공식으로 만든다(그래야 홈판 뜰 확률↑). → 메모리 [[eddie-blog-homefeed-first]].
- 브랜딩·상품판매·시스템자랑 X. 신뢰(40대 밑바닥→AI 실전 경험)는 주되 홍보 아님.
- 어투 항상 **존댓말**. ★도입부에 인사·자기소개 금지("안녕하세요/에디입니다/여러분"). 첫 줄부터 후킹.

## ★현행 스케줄·발행 정책 (2026-08-10 에디님 결정, 이번 달 애드포스트 100만원 목표)

| | 내용 |
|---|---|
| 배치 | 매일 **01:30** 시작(`com.edi.aiblog`), 편당 20분 간격 → **05:40 전후 종료** |
| 편수 | 하루 **8편** = AI 3 + 쇼핑커넥트 1 + **연예 4** |
| AI·쇼핑 4편 | 자동 **예약 발행**. 시각 = `run_ai_daily.PUBLISH_SLOTS` **09:30·12:10·15:00·20:00**(매일 −20~+30분 지터) |
| 연예 4편 | **임시저장 + 이미지 없음** = **이슈 3 + 정보형 1**(`gen_drama_info.py` — 신작 드라마 등장인물·인물관계도·줄거리 = 검색 재고). 사진은 직접 삽입. 1주일 뒤 편수 판단 |

★**새벽에 발행하지 않는다.** 90만원 벌던 2026-04 발행 시각을 실측하니 10~22시(중심 12~16시)·새벽 0건.
홈피드는 발행 직후 노출이 커서 새벽엔 초기 반응이 안 붙는다. → 생성은 새벽, 발행은 낮.

## 실행
```bash
cd "/Users/edi/클로드 코드 블로그 자동화 웹"
python3 run_ai_daily.py --ai 3 --shop 1 --celeb 4   # ★현행 하루 8편(2026-08-10)
python3 run_ai_daily.py --dry                       # 미리보기
python3 run_ai_daily.py --gen-only                  # 생성만(발행 X)
python3 run_ai_daily.py --ai 0 --celeb 1            # 연예 1편만 등 편수 조정
python3 gen_shopping.py                             # 쇼핑커넥트 1편만 생성
```
- 자동: `com.edi.aiblog` launchd = **매일 새벽 04:30**, `caffeinate -i python3 run_ai_daily.py --ai 4 --shop 1 --celeb 1 --stagger 1800`.
  로그 `work/ai_daily.log`. Mac은 전원 꽂혀 있으면 안 잠(sleep 0)→정상 실행.
- ★실패 알림(2026-08-01): 세션 만료·부분 실패 시 `_alert()`가 **맥 알림 + 메일**(jin3175@gmail.com, 제이 `blog_report.send_alert` 재사용). 새벽 실행이라 로그만 남기면 아무도 안 본다.
- ★**매일 결산 피드백 메일 = `com.edi.aiblog.report` launchd, 밤 23:30**(2026-08-03 에디님 요청).
  `blog_report.py`(제이 경제 블로그 것을 이식) → 오늘 올린 글·조회수·최근 7일 추이·베스트/워스트 + **LLM 피드백 3줄**(진단/제목에서 배울 점/내일 액션)을 HTML 메일로 jin3175@gmail.com 발송.
  미리보기: `python3 blog_report.py --preview`(메일 안 보내고 /tmp/_blog_report.html 저장). 로그 `work/report.log`.
  ★**조회수는 '관리자 통계 API'에서 가져온다**(2026-08-03 실측). 글 목록 API(`PostTitleListAsync`)의 `readCount`가
  이 블로그에선 **빈 값**이라 전부 0으로 보였다(제이 블로그는 값이 옴 — 블로그 설정 차이). 진짜 수치는:
  · 일간 `https://blog.stat.naver.com/api/blog/daily/cv?timeDimension=DATE&startDate=YYYY-MM-DD&exclude=`
  · 글별 `https://blog.stat.naver.com/api/blog/rank/cvContentPc?...`(title·cv·rank 제공) → `fetch_stats()`.
  ⚠️ 이 API는 **admin.blog.naver.com 쿠키**가 있어야 한다. 없으면 로그인 페이지로 튕긴다 →
  `naver.login_and_save()`가 로그인 직후 통계 페이지를 방문해 그 쿠키까지 저장하도록 해뒀다.
  세션이 만료돼 조회수가 0으로만 보이면 **재로그인**이 답이다.
- 재설치: plist 수정 후 `launchctl bootout gui/$(id -u)/com.edi.aiblog; cp <plist> ~/Library/LaunchAgents/; launchctl bootstrap gui/$(id -u) <plist>; launchctl enable gui/$(id -u)/com.edi.aiblog`.

## 하루 6편 구성 (2026-08-01 확정 — 쇼핑커넥트 편입)
| # | 엔진 | 생성기(모드) | 카테고리 |
|---|---|---|---|
| 01~04 | **AI 홈판 실전** | `gen_ai` (홈판 검증된 주제만) | categorize: 자동화실전/수익화·부업/툴리뷰 |
| 05 | **쇼핑커넥트**(수익) | `gen_shopping` | **AI 에디의 일상**(`CAT_SHOP`) |
| 06 | **연예 90% + AI 10%** 온램프 | `gen_celeb_ai` mode=**celeb_ai10** | 연예이슈강점(`CAT_CELEB`) |
- ★velocity 분산(AI 티 방지): `--stagger 1800`=편당 30분 간격 임시저장. naver 타이핑도 느리게.
- 연예 05: 90% 순수 연예 이슈 + 끝 AI 1문단(가볍게). 제목=순수 연예 홈판 후킹(AI 없음). 1순위 소재 우선. **사망·범죄·비방 제외**(`_BLOCK_RE`).
- (옛 모드 celeb_pure/celeb_story/ai_hook는 코드에 남지만 미사용.)

## 홈판 공식 파이프라인 (자동, 1회 수집해 공유)
1. `gen_ai.collect_live_context`: **전체 홈판(dir=0)** 위너 제목·썸네일 → 제목공식·썸네일공식 / AI본문공식=dir=30. (연예본문공식=dir=12 `collect_celeb_body_formula`)
2. AI 주제: `gen_ai.derive_topics` — dir=0+dir30에서 **'홈판 뜰' 주제만**(니치·전문 API/벤치마크 탈락). 소재뱅크는 폴백. 이력 `work/ai_topics_used.json`.
3. 연예 소재: `build_pure_pool`=랭킹+1순위 소재 능동 뉴스검색(`fetch_news_search`). url없으면 스니펫 소재.
4. 본문: 홈판 공식대로. 인사 도입 자동 제거(`pipeline._strip_greeting_intro`).
5. 제목: 홈판 공식, `_clean_title`(라벨 제거). 연예=나vs연예인 비교/자랑 금지.
6. 썸네일: `gemini_thumb`(홈판 썸네일 공식 ref_formula). 실패 시 텍스트 폴백. (Gemini 429=일일한도 폴백)
7. **연예 사진(2026-08-02 전면 개편 — 에디님 지시)**: `[사진N]` 자리에 **실제 방송 캡처를 자동 삽입**(옛 '직접 삽입' 방침 폐기).
   · 확보: `celeb_video.fetch_multi(want=13)` = 유튜브 영상 **여러 개의 여러 시점을 Playwright 스크린샷** + Gemini 비전으로 본인 얼굴 검증(실측 13/13 성공, 영상 10개 순회). 부족하면 `celeb_image`(영상 썸네일)로 보충 — 썸네일은 채널로고·자막이 박혀 화질이 덜 좋으니 영상 캡처가 1순위.
   · 삽입: `pipeline._fill_celeb_captures`가 `{no}_*_연예캡처N.(png|jpg)`를 번호순으로 꽂는다. 캡처가 모자라면 남는 자리는 자리표시자 유지(없는 사진 지어내지 않음).
   · **썸네일 = 방송 캡처 1번 그대로**(텍스트 얹기 없음). ★제미나이 생성 썸네일은 쓰지 않는다 — 실존 인물이 아닌 **'가짜 부부' 이미지가 대표사진으로 올라간 사고**(08-02). 캡처가 하나도 없을 때만 옛 생성 방식 폴백.
   · **유튜브 채널 CTA는 연예편에서 제거**(`pipeline._strip_youtube_cta`). 연예 글은 순수 홈판 트래픽용. AI·쇼핑편은 유지.
8. 카테고리 자동선택 + AI활용 표기 토글 + `pipeline.process_post(publish=False)`=임시저장.

## 쇼핑커넥트 (05번, 2026-08-01 편입 — 애드포스트 위 커미션 수익)
- `gen_shopping.py`: 시의성 소비재 선정(최근 30일 중복 회피 `recent_products`+`_FAMILY_WORDS`) → 구매가이드 본문 → `[표]` + **`[커넥트 - 제품]`** 마커.
- 업로드 시 `parse_post.RE_CONNECT`가 connect 블록으로 파싱 → `naver._insert_shopping_connect`가 툴바 쇼핑커넥트→검색→**관련도 1위 상품카드** 자동 삽입. 실패해도 날텍스트로 새지 않음(메모만 남음).
- ★**심리 설득 공식**(조회수 상위 쇼핑글 리서치로 도출, BODY_PROMPT에 주입): 손실회피("안 씌우면 후회하는 이유")·페인포인트 공감 도입·**선택 단순화**("이 세 가지만 보면 5분이면 끝")·구체 수치/평수별 표·"이것만은 피하세요"·완독 유도.
  **절대 금지**: 가짜 할인·기간한정·품절임박 등 지어낸 긴급성, 미검증 제품 사용후기, 허위 스펙.
- 카테고리는 새로 만들지 않고 기존 **`AI 에디의 일상`** 사용(에디님 지정).

## 이미지 — 웹 구독으로 뽑는다(API 과금 X, 2026-08-01)
- `web_image.make(설명, 저장경로)` = **제미나이 → (실패/한도) → ChatGPT** 폴백 체인. 둘 다 유료 구독 활용.
- 실측 함정: 제미나이는 headless OK지만 **fetch(blob:)이 CORS로 막혀** 엘리먼트 스크린샷으로 받음 → 겹친 UI를 `_trim_ui()`로 크롭. ChatGPT는 **Cloudflare 봇검증 때문에 headless 불가**(창 모드), 이미지 URL이 `backend-api/estuary/content`이고 **사이드바 앱 아이콘(Canva)이 같은 크기로 잡히므로** 대화영역+가로세로비≥1.2로 걸러야 함. 상세 [[eddie-blog-celeb-photos]].
- ⏳ 아직 `image_finder`에 배선 전 — 실제 글에 물리려면 그 작업 필요.

## 로그인 세션 — 한 번 로그인하면 자동 (에디님 방침 [[edi-login-sessions]])
- 저장 위치 `session/`: `naver_state.json`(네이버, 7/12분이 3주+ 유지) · `gemini_profile` · `chatgpt_profile`(실제 Chrome 프로필).
- 새 서비스도 **세션 저장·재사용** 구조로 만들 것. 비번은 에디님이 직접 입력.
- 제미나이 `login()`은 비로그인 상태에서도 입력창이 보여 조기 저장되는 함정 있음 → 로그인 버튼 사라짐까지 확인하도록 수정됨. 안 되면 **제이 프로필 복사**가 확실(`cp -R '/Users/edi/경제이슈 블로그 자동화/session/gemini_profile' session/`).

## 연예 1순위 소재 (`gen_celeb_ai.PRIORITY_SUBJECTS`, 최고 조회수)
나는솔로·나솔사계·이혼숙려캠프·이호선 교수·오은영 교수. 랭킹에 없어도 능동 검색으로 후보 풀에 들어감.

## 절대 원칙
- **완전 무인 공개발행 금지** — 임시저장까지만. 발행은 에디님이 검토(연예 사진 삽입·인사줄 확인) 후 직접.
- 과장·가짜수치 금지. 연예 사진 저작권은 에디님 판단(방송 출처 정확 표기).
- 옛 셀럽 카테고리 `연예이슈강점`은 삭제 X(조회수 바닥, 점진 대체). 새 이름 원하면 `run_ai_daily.CAT_CELEB` 한 줄 교체.

## 주요 파일 (`~/클로드 코드 블로그 자동화 웹`)
`run_ai_daily.py`(오케스트레이터·stagger·categorize·CAT_SHOP·_alert) · `gen_ai.py`(AI·collect_live_context·derive_topics·EDI_STORY) · `gen_celeb_ai.py`(연예·celeb_ai10·build_pure_pool·PRIORITY_SUBJECTS·_BLOCK_RE) · **`gen_shopping.py`**(쇼핑커넥트·심리공식) · **`web_image.py`**(제미나이→ChatGPT 웹 이미지·make/login/login-gpt) · **`celeb_video.py`**(유튜브 프레임 Playwright 캡처·fetch_multi·Gemini 얼굴검증) · `gemini_thumb.py`(썸네일·extract_thumb_formula) · `youtube_thumb.py` · `celeb_image.py`(유튜브 썸네일 다운·키리스 검색) · `celeb_sources.py`(스크래핑·fetch_news_search) · `pipeline.py`(조립·_strip_greeting_intro·_GREET_RE) · `parse_post.py`(마커→블록·RE_CONNECT) · `naver.py`(임시저장·카테고리·AI표기·_insert_shopping_connect) · `formula.py` · `com.edi.aiblog.plist`(4:30 스케줄).
소재뱅크(폴백) `~/홈판자료/AI실전_소재뱅크30.md` · 출력 `~/홈판자료/블로그오토/gen_YYYYMMDD/`.

## 2026-08-02 저녁 에디님 피드백 반영 (내일부터 적용 — 결과 확인 필요)
1. **본문 이미지가 매번 같았다**(KORTRIJK 돌표지판·ChatGPT 화면 반복) — `web_image`를 만들어놓고 **`_attach_stock_images`에 배선하지 않아** Unsplash 스톡만 쓰고 있었다. → **웹 구독 생성(제미나이→ChatGPT)이 1순위**, Unsplash/Gemini API는 폴백.
2. **`[요약 3줄]` 같은 편집 라벨이 본문에 노출** → 원고 로드 시 `^\[라벨\]$` 줄 제거(단 `[사진N]`·`[표]`·`[커넥트]`는 보존).
3. **목차 4번만 인용구가 안 걸림** — `_apply_orphan_subheads`의 **22자 제한**에 23자가 걸려 탈락. → **32자로 완화** + 장식기호(◆▶■) 자동 제거.
4. **"에디 채널 이야기 넣지 말라니까"** — 유튜브 CTA를 연예편만 빼고 AI·쇼핑편엔 썸네일까지 붙이고 있었다. → **전 글에서 제거**(프롬프트 + `_strip_youtube_cta` 백스톱). **`@출처` 줄도 제거**(연예편만 방송 출처 유지).
5. **연예 사진 1·2·3번, 4·5·6번이 거의 같음** — 한 영상에서 여러 시점을 연달아 뽑아서. → **영상당 최대 2장**(`per_video`), 시점 3개로 축소, 순회 영상 20개로 확대.
6. **AI 활용 토글이 안 켜짐**(로그는 ON) — `already-on` 오판정. → 클릭 후 **상태 재확인**, 꺼져 있으면 재시도.
7. **쇼핑 썸네일에 제품 사진이 없음**(텍스트만) → 제품 사진을 웹 구독으로 생성 → 문구 합성(`photo_thumb.make_face`), 실패 시 사진만/텍스트형 폴백.
8. **빈 인용박스 '내용을 입력하세요' 45곳** — LLM이 넣은 **제로폭 공백(U+200B)** 줄이 `strip()`에 안 지워져 소주제로 오인. → 원고 로드 시 제거 + 판정에서도 무시.
9. **AI편이 `celeb`으로 오분류** — `posts.category()`의 기본값이 celeb이라 연예 전용 처리가 AI편에도 걸렸다. → `_ai.flag`로 **`ai`** 구분 추가.

## 2026-08-02에 고친 것 (재발 감시)
1. **네이버 세션 만료로 0/6 전멸** — `is_logged_in()`이 파일 존재만 봐서 만료된 쿠키도 True였고, 실패 메시지도 '에디터 셀렉터 조정 필요'로 잘못 떠 진단이 헷갈렸다. → **`naver.session_alive()`** 신설(실제로 네이버에 물어봄) + `run_ai_daily`가 **생성 전에** 검사·알림·중단.
2. **가짜 필명 자동 생성** — "안녕하세요~ 햄찡이에요 🐹"(08-02), "정리해 드리는 엘라입니다"(08-01). 원인: **연예 프롬프트에 인사 금지 규칙이 아예 없었음**(AI편엔 있었음). → 프롬프트에 ★★★도입부 절대 규칙 신설(**없는 사람 이름 지어내기 금지**, 필자는 '에디' 하나, 홈판 위너처럼 첫 문장부터 사건·대사로) + `_strip_greeting_intro`를 **도입부 8줄**까지 훑고 `~이에요/예요`·이모지 변형까지 잡도록 확장.
3. **연예 사진·썸네일** — 위 '연예 사진' 항목 참고(자동 삽입 + 캡처 썸네일 + 유튜브 CTA 제거).

## 2026-08-01에 고친 버그 (재발 감시 대상)
1. **제목 오염** — LLM 설명문("…5개 서로 다른 구조로 뽑았습니다")이 제목으로 업로드됨. `gen_ai`/`gen_celeb_ai` 제목 필터에 프리앰블 토큰 추가.
2. **인사·자기소개 도입** — 프롬프트로 금지해도 LLM이 종종 붙임. 생성단계(`gen_ai`·`gen_celeb_ai`·`gen_shopping` 모두) + 업로드 백스톱(`pipeline._GREET_RE`) **이중** 제거. 연예편은 **없는 페르소나를 지어냄**("여러분의 연예 이슈, 정리해 드리는 엘라입니다") → `_GREET_RE`에 `~해 드리는 OO입니다`·`블로거 OO입니다` 패턴 추가.
3. **스크래핑 타임아웃** — `networkidle` 대기가 네이버에선 안 끝나 쇼핑 생성이 통째로 죽음 → `celeb_sources.py` 전부 `domcontentloaded`로 전환 + `gen_shopping` 폴백.

## ★ 미완/다음 작업 (새 창에서 이어갈 것)
- **연예 사진 10~13장 자동**(에디님 요청): 현재 2장·수동 자리표시자 → `celeb_video.fetch_multi(want=13)`로 유튜브 여러 영상 캡처, **썸네일도 연예인 사진(텍스트 없이)**, 본문 `[사진N]` 자동 삽입. 캡처 모듈은 이식·검증 완료(오은영 3/3). 인스타 캡처는 그다음(로그인·안티봇).
- **`image_finder`에 `web_image` 배선** — 본문 이미지를 웹 구독으로(위 참고).
- **연예편 표 버그**: 본문이 `[표1 - 제목]`+마크다운 파이프를 뱉어 파서에 안 걸림 → 날텍스트로 샘. `[표]`로 정규화 필요. (AI·쇼핑편은 정상)
- `gen_shopping`이 옛 강점코치 `EDDIE_PROFILE` 주입 → "저도 장사해본 적" 억지 경험. 'AI 에디' 브랜드로 교체 검토.
- 연예↔AI 내부링크(A): 순수 연예글 끝에 AI글 링크로 유입(blog_related.py) — 논의만.
- **8/2 04:30 첫 쇼핑커넥트 실전 점검**: 커넥트 카드가 실제 붙었는지(`쇼핑커넥트 상품 삽입 → 링크제품` 로그). 실패면 `_insert_shopping_connect` 셀렉터 수정.
