# Mail Register

> 이메일 한 통으로 대회 신청을 자동화하는 시스템

선착순 대회 신청에서 1~2초 차이로 탈락하는 문제를 해결합니다.
이메일을 보내면 n8n이 자동으로 감지하고, 지정된 시간에 정밀 발송합니다.

## 동작 흐름

```
Gmail로 대회 정보 전송
        │
        ▼
n8n이 1분마다 메일 감지 (Gmail Trigger)
        │
        ▼
본문 파싱 → 수신자, 제목, 시간, 본문, 첨부파일 추출
        │
        ▼
목표 시간 5분 전까지 대기 (Wait Node)
        │
        ▼
Python 정밀 발송 엔진 실행 (sender.py)
  - SMTP 연결/인증을 사전 완료
  - DATA 명령까지 미리 전송
  - 목표 시간에 본문만 즉시 전송
        │
        ▼
성공/실패 알림 메일 수신
```

## 정밀 발송 원리

```
일반 발송:  목표 시간 → [DNS + TCP + TLS + 인증 + 발송] = 1~3초 지연
이 시스템:  [DNS + TCP + TLS + 인증 + MAIL FROM + RCPT TO + DATA 354] = 사전 완료
           목표 시간 → [본문 전송] = ~1ms 지연
```

SMTP 프로토콜의 단계를 분리하여, 네트워크 지연이 발생하는 모든 과정을 목표 시간 전에 완료합니다.

## 기술 스택

| 기술 | 용도 |
|------|------|
| **Docker** | n8n + Python 환경을 단일 컨테이너로 패키징 |
| **n8n** | Gmail 감지 → 파싱 → 스케줄링 → 알림 워크플로우 |
| **Python** | SMTP 정밀 타이밍 제어 (busy-wait + DATA 사전 전송) |
| **Gmail API** | OAuth2 기반 메일 트리거 및 알림 발송 |

## 워크플로우

<img width="1044" height="356" alt="image" src="https://github.com/user-attachments/assets/480530e9-e84c-440c-8109-e19737dbd9ff" />

| 노드 | 역할 |
|------|------|
| Gmail Trigger | 1분마다 특정 제목의 메일 감지 |
| Parse Email | 본문 파싱 + 첨부파일 저장 + config JSON 생성 |
| Mark as Read | 처리된 메일 읽음 처리 (중복 방지) |
| Has Error? | 파싱 에러 분기 → 에러 시 알림 발송 |
| Wait Until T-5min | 목표 시간 5분 전까지 대기 |
| Run sender.py | 정밀 타이밍 이메일 발송 |
| Send OK? | 발송 결과에 따라 성공/실패 알림 |

## 이메일 형식

```
제목: 대회신청

본문:
수신자: competition@example.com
제목: 제5회 OO대회 참가 신청
시간: 2026/03/23 09:00
본문: 참가 신청합니다.

+ 첨부파일 (선택)
```

## 빠른 시작

```bash
git clone https://github.com/dukbong/mail-register.git
cd mail-register
```

### 1. 환경 변수 설정

```bash
cp mail-sender/.env.example mail-sender/.env
# .env 파일에 Gmail 인증 정보 입력
```

### 2. Docker 빌드 및 실행

```bash
docker compose build
docker compose up -d
```

### 3. n8n 설정

1. `http://localhost:5678` 접속
2. Gmail OAuth2 Credential 설정
3. 워크플로우 생성 (위 노드 구조 참고)
4. 워크플로우 Publish

## 프로젝트 구조

```
mail-register/
├── Dockerfile              # n8n + Python3 멀티스테이지 빌드
├── docker-compose.yml      # 컨테이너 구성
├── mail-sender/
│   ├── sender.py           # 정밀 타이밍 이메일 발송 엔진
│   ├── requirements.txt
│   └── .env.example
└── shared/                 # 런타임 데이터 (gitignore)
    ├── attachments/        # 첨부파일 임시 저장
    └── jobs/               # 발송 config JSON
```

## 라즈베리파이 이전

폴더 그대로 복사 후 `docker compose up -d` — ARM 이미지는 Docker가 자동 빌드합니다.
