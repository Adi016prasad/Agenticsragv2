"""
Lightweight test script to verify Gmail SMTP credentials and 1-click email rendering
without calling any expensive LLM agents.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()


def test_smtp_send():
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD_AGENTIC")
    approver_email = os.getenv("APPROVER_EMAIL")
    base_url = os.getenv("APPROVAL_BASE_URL", "http://localhost:8001")

    print("==================================================")
    print("📧 SMTP EMAIL DISPATCH TEST")
    print("==================================================")
    print(f"SMTP Host:      {smtp_host}")
    print(f"SMTP Port:      {smtp_port}")
    print(f"Sender Email:   {smtp_user}")
    print(f"Receiver Email: {approver_email}")
    print(f"Base URL:       {base_url}")
    print("==================================================\n")

    if not all([smtp_host, smtp_user, smtp_password, approver_email]):
        print("❌ Error: Missing SMTP environment variables in your .env file.")
        return

    proposal_id = "prop_2d51aa51e8"
    approve_url = f"{base_url}/optimization/approve?proposal_id={proposal_id}&decision=approve"
    reject_url = f"{base_url}/optimization/approve?proposal_id={proposal_id}&decision=reject"

    executive_summary = (
        "• Prompt Caching hit rate dropped to 2.7%\n"
        "• Semantic agent token usage spiked to 4,572 tokens.\n"
        "• Hybrid agent satisfaction is low (48.5%)."
    )

    action_plan = (
        "1. Switch model from 120B to GPT OSS Safeguard 20B (Saves 65% cost).\n"
        "2. Restructure templates to enable prefix caching."
    )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #2b5797;">🧪 SMTP test Connection Successful!</h2>
            <p><strong>Proposal ID:</strong> <code>{proposal_id}</code></p>
            <hr style="border: none; border-top: 1px solid #eee;">
            
            <h3>📊 Executive Summary</h3>
            <div style="background-color: #f9f9f9; padding: 12px; border-radius: 6px;">
                <pre style="white-space: pre-wrap; font-family: inherit; margin: 0;">{executive_summary}</pre>
            </div>

            <h3>🎯 Proposed Action Plan</h3>
            <div style="background-color: #f0f7ff; padding: 12px; border-radius: 6px; border-left: 4px solid #0078d4;">
                <pre style="white-space: pre-wrap; font-family: inherit; margin: 0;">{action_plan}</pre>
            </div>

            <div style="margin-top: 30px; text-align: center;">
                <a href="{approve_url}" style="background-color: #107c41; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin-right: 15px; display: inline-block;">
                    ✅ Approve & Deploy
                </a>
                <a href="{reject_url}" style="background-color: #d83b01; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                    ❌ Reject Proposal
                </a>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🧪 [SMTP TEST] Connection & Rendering Test: {proposal_id}"
    msg["From"] = smtp_user
    msg["To"] = approver_email

    msg.attach(MIMEText(html_body, "html"))

    try:
        print("Connecting to SMTP server...")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            print("Logging in with credentials...")
            server.login(smtp_user, smtp_password)
            print("Sending email...")
            server.sendmail(smtp_user, [approver_email], msg.as_string())
        print("\n🎉 SUCCESS! Test email has been sent successfully to your inbox.")
    except Exception as exc:
        print(f"\n❌ FAILED: {exc}")


if __name__ == "__main__":
    test_smtp_send()