import os,smtplib
from email.message import EmailMessage
def build_draft(job,profile,cv_path,cover_path=None):
 return {"subject":f"Application: {job['title']} — {profile['name']}","body":f"Dear Hiring Team,\n\nPlease find attached my application for {job['title']}.\n\nKind regards,\n{profile['name']}","attachments":[x for x in [cv_path,cover_path] if x]}
def send(message:EmailMessage):
 if os.getenv("EMAIL_AUTO_SEND","false").lower()!="true": raise PermissionError("EMAIL_AUTO_SEND is not enabled")
 with smtplib.SMTP(os.environ["SMTP_HOST"],int(os.getenv("SMTP_PORT","587"))) as s: s.starttls(); s.login(os.environ["SMTP_USERNAME"],os.environ["SMTP_PASSWORD"]); s.send_message(message)
