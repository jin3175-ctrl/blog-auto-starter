# 네이버 블로그 자동 발행 대시보드 (1편 파일럿)

에디 블로그 자동화 스킬이 `~/홈판자료/블로그오토/{YYYYMMDD}/` 에 저장한 원고를 읽어
**본문은 그대로 복붙**하고, **제목만** 지금 네이버 블로그 홈에서 뜨는 인기글 30개의 패턴을
`claude -p`(구독 요금제)로 학습·적용해 새로 만든 뒤, 카드·표·썸네일을 이미지로 정리해
Playwright로 네이버 스마트에디터에 **임시저장(비공개)** 까지 자동화합니다.

## 처리 흐름
1. 원고 `_복붙용.txt` 를 **그대로** 읽음(재작성 없음).
2. `section.blog.naver.com` 인기글 제목 30개 수집 → `claude -p` 로 패턴화 → 이 글에 맞는 **제목 1개 생성**.
   (실패·미로그인 시 manifest 부제로 폴백)
3. 강점카드·표 HTML → PNG 렌더, 썸네일 PNG 사용.
4. 본문 마커 파싱 후 네이버 에디터에 삽입(사진 마커는 자리표시자 유지) → **임시저장**.

## 사전 요구 (중요)

AI 재작성은 `claude -p`(구독 요금제)를 사용합니다. **터미널에서 한 번** 구독 계정으로
CLI 로그인을 해두어야 동작합니다(별도 API 키·과금 없음):

```bash
claude login    # Max/Pro 구독 계정으로 로그인 (최초 1회)
claude -p "테스트" --output-format text   # "Not logged in" 이 안 나오면 준비 완료
```

> 참고: Claude 데스크톱/Cowork 임베드 세션 안에서는 자식 `claude` 프로세스가 로그인 토큰을
> 물려받지 못해 "Not logged in" 이 날 수 있습니다. 이때는 **일반 터미널**에서 `claude login` 후
> `python3 app.py` 를 실행하세요.

## 설치

```bash
cd "클로드 코드 블로그 자동화 웹"
pip3 install -r requirements.txt        # flask (playwright는 이미 설치됨)
python3 -m playwright install chromium  # 최초 1회
```

## 실행

```bash
python3 app.py
# 브라우저에서 http://127.0.0.1:5001 접속
```

1. **네이버 로그인** 버튼 → 뜬 창에서 직접 로그인하면 세션이 `session/naver_state.json` 에 저장됩니다.
2. 1편 카드의 **이 편 처리** → 재작성 → 이미지 렌더 → 네이버 임시저장까지 진행됩니다.
3. 네이버 글 관리에서 **임시저장 글**을 열어 확인 후 직접 발행하세요.

## 매일 자동 실행 (강점인사이트 7시 발행 + 나머지 임시저장)

`run_daily.py` 가 그날 폴더의 글을 분류해 처리합니다:
- **강점인사이트** → 공개 발행 (아침 7시, 이미지 자동 첨부)
- **연예 속 강점(1~8편)** → 임시저장 (`[사진N]`은 방송캡처라 자리표시자 유지)
- **쇼핑커넥트 등** → 임시저장 + 내용에 맞는 Unsplash 이미지 자동 첨부

### 1) 먼저 안전하게 확인 (발행 안 함)
```bash
python3 run_daily.py --dry        # 무엇을 할지 목록만
python3 run_daily.py --draft-all  # 전부 '임시저장'으로 실행(강점인사이트도 공개 안 함)
```
→ 네이버에서 강점인사이트 초안의 이미지·서식을 눈으로 확인한 뒤 다음 단계로.

### 2) 매일 7시 자동 실행 등록 (launchd)
```bash
cp "com.edi.blogauto.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.edi.blogauto.plist
# 해제: launchctl unload ~/Library/LaunchAgents/com.edi.blogauto.plist
```
로그는 `work/run_daily.log` 에 쌓입니다.

### 3) 7시에 맥이 깨어 있어야 함
자동화가 실제 크롬 창을 띄우므로 **맥이 켜져 있고 로그인된 상태**여야 합니다.
- 예약 깨우기(예: 6:58): `sudo pmset repeat wakeorpoweron MTWRFSU 06:58:00`
- 화면 잠자기/자동 로그아웃은 꺼두세요.

### 주의
- **네이버 세션은 며칠~몇 주 뒤 만료**됩니다. 만료되면 대시보드에서 다시 로그인해야 자동 실행이 됩니다.
- 매일 대량 공개 발행은 계정 제재 위험이 있어, **강점인사이트 1편만 자동 발행**하고 나머지는 임시저장→직접 예약발행을 권장합니다.

## 동작 방식 / 결정
- **발행은 임시저장까지만** (공개 발행은 사용자가 직접).
- 연예 본문 `[사진N]` 은 방송 캡처라 자동 다운로드하지 않고 **자리표시자로 본문에 남깁니다**.
  썸네일 PNG · 강점카드 3종 · 표는 이미지로 자동 삽입됩니다.
- AI 재작성은 `claude -p` 서브프로세스 → 구독 요금제 사용(별도 API 키 불필요).

## 파일 구성
| 파일 | 역할 |
|---|---|
| `app.py` | Flask 서버 · 대시보드 · 작업 큐 |
| `pipeline.py` | 1편 처리 파이프라인 |
| `posts.py` | 원고 폴더 스캔 · 편별 에셋 탐색 |
| `claude_cli.py` | `claude -p`(구독) 공용 호출 헬퍼 |
| `naver_titles.py` | 네이버 블로그 홈 인기글 제목 30개 수집 |
| `title_gen.py` | 인기 제목 패턴화 → 제목 1개 생성 |
| `render_assets.py` | HTML 카드/표 → PNG |
| `parse_post.py` | 재작성 원고 → 블록 리스트 |
| `naver.py` | 네이버 로그인·세션저장, 스마트에디터 임시저장 |
| `templates/index.html` | 대시보드 UI |

## 참고 (취약 지점)
네이버 스마트에디터 ONE은 클래스명이 자주 바뀌어 셀렉터가 취약합니다.
`naver.py` 상단의 `SEL_*` 후보 목록에서 실제 화면에 맞게 조정할 수 있습니다.
1차 목표는 제목·본문·인용구·이미지 삽입 후 임시저장이며, 일부 삽입 실패는 로그로 안내됩니다.
