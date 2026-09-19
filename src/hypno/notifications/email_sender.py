from __future__ import annotations

import smtplib
import ssl

from dataclasses import dataclass
from email.message import EmailMessage

from ..config import load_email_config
from ..security import get_email_password


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipients: tuple[str, ...]
    security: str


def load_smtp_config() -> SMTPConfig:
    config = load_email_config()

    password = get_email_password(
        config.username
    )

    return SMTPConfig(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.username,
        password=password,
        sender=config.username,
        recipients=(
            config.recipient,
        ),
        security=config.smtp_security,
    )


def _connect(
    config: SMTPConfig,
):
    context = ssl.create_default_context()

    if config.security == "ssl":
        smtp = smtplib.SMTP_SSL(
            config.host,
            config.port,
            context=context,
            timeout=30,
        )

    else:
        smtp = smtplib.SMTP(
            config.host,
            config.port,
            timeout=30,
        )

        if config.security == "starttls":
            smtp.ehlo()

            smtp.starttls(
                context=context
            )

            smtp.ehlo()

    smtp.login(
        config.username,
        config.password,
    )

    return smtp


def test_email_connection() -> None:
    config = load_smtp_config()

    with _connect(config) as smtp:
        smtp.noop()


def send_email(
    *,
    subject: str,
    text: str,
    html: str,
) -> None:
    config = load_smtp_config()

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = config.sender
    message["To"] = ", ".join(
        config.recipients
    )

    message.set_content(text)

    message.add_alternative(
        html,
        subtype="html",
    )

    with _connect(config) as smtp:
        smtp.send_message(
            message
        )