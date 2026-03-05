# Precision Email Sender

목표 시간에 **최대한 정밀하게** 이메일을 발송하는 CLI 도구.

선착순 마감 환경에서 예약 발송(+0~60초)보다 훨씬 빠르게, 목표 시간 직후 **~1초 이내** 발송.

## 원리

```
일반 발송:  [DNS + TCP + TLS + 인증 + 발송] = 1~3초 (목표 시간 이후)
이 도구:    [DNS + TCP + TLS + 인증 + MAIL FROM + RCPT TO + DATA 354] = 사전 완료
            목표 시간 → [본문 전송] = ~1초
```

SMTP 연결/인증/핸드셰이크를 **목표 시간 전에 미리 완료**하고, 정확한 시간에 본문만 전송.

## 설치

```bash
git clone https://github.com/dukbong/mail-send.git
cd mail-send
pip install -r requirements.txt
```

## 설정

`.env` 파일에 Gmail 인증 정보 입력:

```
EMAIL_SENDER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
```

### Gmail App Password 발급

1. https://myaccount.google.com/security 에서 **2단계 인증** 활성화
2. https://myaccount.google.com/apppasswords 에서 App Password 생성
3. 발급된 16자리 비밀번호를 **공백 없이** `.env`에 입력

## 사용법

```bash
python3 sender.py \
  --time "2026-03-15 13:00:00" \
  --to "recipient@email.com" \
  --subject "대회 참가 신청서" \
  --body "첨부 파일을 확인해주세요." \
  --attach "신청서.pdf" "이력서.xlsx"
```

### 인자

| 인자 | 필수 | 설명 |
|------|------|------|
| `--time` | O | 목표 발송 시간 (YYYY-MM-DD HH:MM:SS, 로컬 타임존) |
| `--to` | O | 수신자 이메일 |
| `--subject` | O | 메일 제목 |
| `--body` | | 메일 본문 (기본값: 빈 문자열) |
| `--attach` | | 첨부파일 경로 (여러 개 가능) |
| `--dry-run` | | 실제 발송 없이 타이밍만 측정 |

### 예시

```bash
# 기본 발송
python3 sender.py \
  --time "2026-03-15 13:00:00" \
  --to "example@email.com" \
  --subject "신청서" \
  --body "첨부 확인 부탁드립니다."

# 첨부파일 포함
python3 sender.py \
  --time "2026-03-15 13:00:00" \
  --to "example@email.com" \
  --subject "신청서" \
  --attach "/path/to/application.pdf"

# 빠른 테스트 (20초 후 발송)
# macOS
python3 sender.py \
  --time "$(date -v+20S '+%Y-%m-%d %H:%M:%S')" \
  --to "your-email@gmail.com" \
  --subject "테스트" \
  --body "테스트입니다."
# Linux
python3 sender.py \
  --time "$(date -d '+20 seconds' '+%Y-%m-%d %H:%M:%S')" \
  --to "your-email@gmail.com" \
  --subject "테스트" \
  --body "테스트입니다."

# 타이밍만 측정 (실제 발송 안 함)
# macOS
python3 sender.py \
  --time "$(date -v+20S '+%Y-%m-%d %H:%M:%S')" \
  --to "your-email@gmail.com" \
  --subject "테스트" \
  --dry-run
# Linux
python3 sender.py \
  --time "$(date -d '+20 seconds' '+%Y-%m-%d %H:%M:%S')" \
  --to "your-email@gmail.com" \
  --subject "테스트" \
  --dry-run
```

## 실행 로그 예시

```
[정보] 목표 시간: 2026-03-15 13:00:00 KST (UTC+0900)
[정보] 수신자: recipient@email.com
[정보] 제목: 대회 참가 신청서
[준비] 메일 조립 완료 (700 bytes)
[Phase 1] 120.0초 대기 중...
[Phase 2] SMTP 연결 시도 (1/3)...
[Phase 2] SMTP 연결 완료!
[Phase 3] MAIL FROM + RCPT TO 사전 전송 완료
[Phase 4] 전송 바이트 준비 완료 (705 bytes)
[Phase 5] 발송 대기 중... 22.5초
[Phase 6] DATA 354 응답 수신 — 서버 대기 중
[Phase 7] Busy-wait 진입...
[완료] 발송 완료! 목표 대비 +1012.3ms
```

## 주의사항

- 최소 **15초 전**에 실행해야 합니다
- 시스템 시계가 **NTP 동기화**되어 있어야 정확합니다
- Gmail **App Password**가 필요합니다 (일반 비밀번호 불가)
