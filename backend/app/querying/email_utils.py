import os
import smtplib
from email.mime.text import MIMEText

APPROVAL_BASE_URL = os.getenv("APPROVAL_BASE_URL", "http://localhost:8001")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD_AGENTIC")
APPROVER_EMAIL = os.getenv("APPROVER_EMAIL")

async def send_approval_email(session_id: str, total_tokens: int) -> None:
    approve_url = f"{APPROVAL_BASE_URL}/approve?session_id={session_id}&decision=yes"
    deny_url = f"{APPROVAL_BASE_URL}/approve?session_id={session_id}&decision=no"

    body = (
        f"Session '{session_id}' has exceeded the token budget "
        f"(total tokens: {total_tokens}).\n\n"
        f"Approve to continue: {approve_url}\n"
        f"Deny to stop: {deny_url}\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"[Action Needed] Token limit exceeded — session {session_id}"
    msg["From"] = SMTP_USER
    msg["To"] = APPROVER_EMAIL

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [APPROVER_EMAIL], msg.as_string())