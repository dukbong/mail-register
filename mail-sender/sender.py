#!/usr/bin/env python3
"""Precision Email Sender — 목표 시간에 최대한 정밀하게 이메일을 발송한다."""

import argparse
import json
import os
import re
import smtplib
import subprocess
import sys
import time
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

# ── 상수 ──────────────────────────────────────────────
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_CONNECT_TIMEOUT = 5  # 초
SMTP_RETRY_DEADLINE_OFFSET = 10  # T-10초까지만 재시도
MIN_LEAD_TIME = 15  # 최소 15초 전에 실행해야 함


# ── CLI ───────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="정밀 이메일 발송기")
    parser.add_argument("--config", help="JSON config 파일 경로 (다른 인자 대신 사용)")
    parser.add_argument("--time", help="목표 발송 시간 (YYYY-MM-DD HH:MM:SS, 로컬 타임존)")
    parser.add_argument("--to", help="수신자 이메일")
    parser.add_argument("--subject", help="메일 제목")
    parser.add_argument("--body", default="", help="메일 본문")
    parser.add_argument("--attach", nargs="*", default=[], help="첨부파일 경로들")
    parser.add_argument("--dry-run", action="store_true", help="실제 발송 없이 타이밍만 측정")

    args = parser.parse_args()

    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        args.time = cfg['time']
        args.to = cfg['to']
        args.subject = cfg['subject']
        args.body = cfg.get('body', '')
        args.attach = cfg.get('attach', [])
        args.dry_run = args.dry_run or cfg.get('dry_run', False)
    elif not all([args.time, args.to, args.subject]):
        parser.error("--config 또는 --time/--to/--subject 가 필요합니다.")

    return args


# ── 시간 파싱 ─────────────────────────────────────────
def parse_target_time(time_str):
    """목표 시간을 파싱하고 로컬 타임존을 명시적으로 부착."""
    naive_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    local_dt = naive_dt.astimezone()
    return local_dt


# ── 검증 ──────────────────────────────────────────────
def validate_target_time(target_dt):
    remaining = target_dt.timestamp() - time.time()
    if remaining < 0:
        sys.exit("[에러] 목표 시간이 과거입니다.")
    if remaining < MIN_LEAD_TIME:
        sys.exit(f"[에러] 최소 {MIN_LEAD_TIME}초 전에 실행해야 합니다. (현재 {remaining:.0f}초 전)")


def validate_attachments(paths):
    for p in paths:
        if not Path(p).is_file():
            sys.exit(f"[에러] 첨부파일을 찾을 수 없습니다: {p}")


def validate_env():
    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    if not sender or not password:
        sys.exit(
            "[에러] .env 파일에 EMAIL_SENDER, EMAIL_PASSWORD를 설정하세요.\n"
            "       .env.example을 참고하세요.\n"
            "       Gmail App Password: https://myaccount.google.com/apppasswords"
        )
    return sender, password


# ── NTP 동기화 확인 ───────────────────────────────────
def check_clock_sync():
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized"],
            capture_output=True, text=True, timeout=3,
        )
        if "NTPSynchronized=yes" not in result.stdout:
            print("[경고] 시스템 시계가 NTP와 동기화되지 않았습니다.")
            print("       sudo timedatectl set-ntp true 로 활성화하세요.")
    except Exception:
        pass


# ── 메일 조립 ─────────────────────────────────────────
def compose_email(sender, to, subject, body, attachments):
    """MIME 메시지 조립 (첨부파일 포함)."""
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for filepath in attachments:
        path = Path(filepath)
        part = MIMEBase("application", "octet-stream")
        with open(path, "rb") as f:
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", path.name))
        msg.attach(part)

    return msg


# ── SMTP 연결 ─────────────────────────────────────────
def connect_smtp(sender, password):
    """Gmail SMTP 사전 연결 + TLS + 인증."""
    smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_CONNECT_TIMEOUT)
    smtp.ehlo()
    smtp.starttls()
    smtp.ehlo()
    smtp.login(sender, password)
    return smtp


# ── 정밀 타이밍 엔진 ──────────────────────────────────
def precision_send(sender, password, to, msg_str, target_ts, dry_run=False):
    """SMTP 연결 → 정밀 대기 → 발송을 일원화."""

    # Phase 1: Coarse sleep (T-30초 전까지)
    now = time.time()
    if target_ts - now > 35:
        sleep_duration = target_ts - now - 30
        print(f"[Phase 1] {sleep_duration:.1f}초 대기 중...")
        time.sleep(sleep_duration)

    # Phase 2: SMTP 연결 (T-30초 부근, 실패 시 T-10초까지 재시도)
    smtp = None
    retry_deadline = target_ts - SMTP_RETRY_DEADLINE_OFFSET
    for attempt in range(3):
        try:
            print(f"[Phase 2] SMTP 연결 시도 ({attempt + 1}/3)...")
            smtp = connect_smtp(sender, password)
            print("[Phase 2] SMTP 연결 완료!")
            break
        except Exception as e:
            if time.time() >= retry_deadline:
                raise RuntimeError(f"SMTP 연결 실패, 재시도 시간 초과 (T-{SMTP_RETRY_DEADLINE_OFFSET}초): {e}")
            print(f"[Phase 2] 연결 실패 ({e}), 2초 후 재시도...")
            time.sleep(2)
    if smtp is None:
        raise RuntimeError("SMTP 연결 실패 (3회 재시도 소진)")

    try:
        # Phase 3: MAIL FROM + RCPT TO 사전 전송
        smtp.mail(sender)
        code, rcpt_msg = smtp.rcpt(to)
        if code != 250:
            raise smtplib.SMTPRecipientsRefused({to: (code, rcpt_msg)})
        print("[Phase 3] MAIL FROM + RCPT TO 사전 전송 완료")

        # Phase 4: 메일 본문 바이트 사전 준비 (smtp.data() 내부 로직 재현)
        raw = msg_str.encode("ascii", errors="surrogateescape")
        raw = re.sub(br"(?m)^\.", b"..", raw)  # period stuffing (RFC 5321)
        if raw[-2:] != b"\r\n":
            raw = raw + b"\r\n"
        raw = raw + b".\r\n"
        print(f"[Phase 4] 전송 바이트 준비 완료 ({len(raw):,} bytes)")

        # Phase 5: Fine sleep (T-5초까지)
        now = time.time()
        remaining = target_ts - now
        if remaining > 5:
            print(f"[Phase 5] 발송 대기 중... {remaining - 5:.1f}초")
            time.sleep(remaining - 5)

        # Phase 6: DATA 명령 사전 전송 → 354 응답 수신
        smtp.putcmd("data")
        code, data_msg = smtp.getreply()
        if code != 354:
            raise smtplib.SMTPDataError(code, data_msg)
        print("[Phase 6] DATA 354 응답 수신 — 서버 대기 중")

        # Phase 7: Busy-wait (최대 정밀도)
        print("[Phase 7] Busy-wait 진입...")
        while time.time() < target_ts:
            pass

        # Phase 8: 본문 바이트 즉시 전송!
        if dry_run:
            send_time = time.time()
            print("[DRY-RUN] send() 호출 시점 (실제 발송 안 함)")
        else:
            try:
                smtp.send(raw)
                code, reply_msg = smtp.getreply()
                send_time = time.time()
                if code != 250:
                    raise smtplib.SMTPDataError(code, reply_msg)
            except smtplib.SMTPException as e:
                send_time = time.time()
                offset_ms = (send_time - target_ts) * 1000
                sys.exit(f"[실패] 발송 실패 (목표 대비 +{offset_ms:.1f}ms): {e}")

        offset_ms = (send_time - target_ts) * 1000
        print(f"[완료] 발송 완료! 목표 대비 +{offset_ms:.1f}ms")
        return send_time

    finally:
        smtp.quit()


# ── 메인 ──────────────────────────────────────────────
def main():
    args = parse_args()

    # 0. 시스템 시계 NTP 동기화 확인
    check_clock_sync()

    # 1. 입력 검증 (환경 변수 불필요한 검증 먼저)
    target_dt = parse_target_time(args.time)
    validate_target_time(target_dt)
    validate_attachments(args.attach)

    # 2. 환경 변수 로드
    load_dotenv(Path(__file__).parent / ".env")
    sender, password = validate_env()

    # 3. 타임존 정보 로깅
    tz_name = target_dt.strftime("%Z")
    tz_offset = target_dt.strftime("%z")
    print(f"[정보] 목표 시간: {target_dt.strftime('%Y-%m-%d %H:%M:%S')} {tz_name} (UTC{tz_offset})")
    print(f"[정보] 수신자: {args.to}")
    print(f"[정보] 제목: {args.subject}")
    if args.attach:
        print(f"[정보] 첨부파일: {', '.join(args.attach)}")
    if args.dry_run:
        print("[정보] DRY-RUN 모드 (실제 발송 안 함)")

    # 4. 메일 조립 + 사전 직렬화
    msg = compose_email(sender, args.to, args.subject, args.body, args.attach)
    msg_str = msg.as_string()
    print(f"[준비] 메일 조립 완료 ({len(msg_str):,} bytes)")

    # 5. 정밀 엔진에 제어권 이양
    precision_send(sender, password, args.to, msg_str, target_dt.timestamp(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
