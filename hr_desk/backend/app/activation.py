"""Send a short-lived account activation link to a work mailbox."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit


def public_origin() -> str:
    return os.environ.get("HR_DESK_PUBLIC_ORIGIN", "").strip().rstrip("/")


def allows_local_password_setup() -> bool:
    origin = urlsplit(public_origin())
    return origin.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1"}


def accepts_employee_email(email: str) -> bool:
    if allows_local_password_setup():
        return email.endswith("@stylo.example")
    domain = os.environ.get("HR_DESK_EMPLOYEE_DOMAIN", "").strip().lower()
    return not domain or email.rsplit("@", 1)[-1] == domain


def validate_deployment(dsn: str) -> None:
    from psycopg.conninfo import conninfo_to_dict

    origin = urlsplit(public_origin())
    db = conninfo_to_dict(dsn)
    if origin.path or origin.query or origin.fragment or origin.username or not origin.hostname:
        raise RuntimeError("Set HR_DESK_PUBLIC_ORIGIN to the app's origin.")
    if allows_local_password_setup():
        if (db.get("dbname") != "hr_desk" or db.get("port") != "5433"
                or db.get("host") not in {"localhost", "127.0.0.1"}):
            raise RuntimeError("Local password setup requires the local hr_desk database on port 5433.")
    else:
        if origin.scheme != "https":
            raise RuntimeError("Company deployments require an HTTPS origin.")
        domain = os.environ.get("HR_DESK_EMPLOYEE_DOMAIN", "").strip().lower()
        if (not domain or domain.endswith(".example") or not os.environ.get("HR_DESK_SMTP_HOST")
                or not os.environ.get("HR_DESK_SMTP_FROM")):
            raise RuntimeError("Set the company employee domain, SMTP host, and sender address.")


def send_activation(email: str, token: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Set up your Stylo HR Desk account"
    message["To"] = email
    message["From"] = os.environ["HR_DESK_SMTP_FROM"]
    message.set_content(
        "Open this link to choose your HR Desk password. It expires in 30 minutes.\n\n"
        f"{public_origin()}/sign-up#{token}\n\n"
        "If you did not ask for this email, you can ignore it.\n"
    )
    host = os.environ.get("HR_DESK_SMTP_HOST", "")
    if not host:
        raise RuntimeError("Configure company SMTP before inviting employees.")
    port = int(os.environ.get("HR_DESK_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=5) as server:
        server.starttls(context=ssl.create_default_context())
        username = os.environ.get("HR_DESK_SMTP_USER")
        if username:
            server.login(username, os.environ["HR_DESK_SMTP_PASSWORD"])
        server.send_message(message)
