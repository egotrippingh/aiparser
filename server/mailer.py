"""SMTP delivery of one-use account recovery links."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote


class PasswordMailer:
    def __init__(self, host: str, port: int, sender: str, username: str,
                 password: str, security: str, public_base: str):
        if security not in {"starttls", "ssl"} or not public_base.startswith("https://"):
            raise ValueError("SMTP требует TLS и публичный HTTPS-адрес")
        self.host, self.port, self.sender = host, port, sender
        self.username, self.password = username, password
        self.security, self.public_base = security, public_base.rstrip("/")

    def send_reset(self, email: str, token: str) -> None:
        link = f"{self.public_base}/cabinet/#reset_token={quote(token, safe='')}"
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email
        message["Subject"] = "Восстановление доступа к AI Mentions"
        message.set_content(
            "Чтобы задать новый пароль, откройте ссылку:\n\n"
            f"{link}\n\nСсылка действует 30 минут и подходит для одного использования. "
            "Если вы не запрашивали восстановление, письмо можно игнорировать."
        )
        context = ssl.create_default_context()
        if self.security == "ssl":
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as smtp:
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.starttls(context=context)
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
