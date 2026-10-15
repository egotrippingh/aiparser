"""TLS SMTP delivery of account recovery and balance notifications."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import quote


class MailDeliveryError(Exception):
    def __init__(self, *, uncertain: bool):
        super().__init__("SMTP acceptance unknown" if uncertain else "SMTP did not accept message")
        self.uncertain = uncertain


def rubles(amount_kopeks: int) -> str:
    whole, cents = divmod(amount_kopeks, 100)
    return f"{whole:,}".replace(",", " ") + f",{cents:02d} ₽"


def topup_message(sender: str, public_base: str, email: str, order_id: str,
                  amount_kopeks: int, balance_kopeks: int) -> EmailMessage:
    values = {"amount": rubles(amount_kopeks), "balance": rubles(balance_kopeks),
              "cabinet_url": f"{public_base.rstrip('/')}/cabinet/#/topup"}
    templates = Path(__file__).with_name("email_templates")
    message = EmailMessage()
    message["From"], message["To"] = sender, email
    message["Subject"] = f"Баланс AIRate пополнен на {values['amount']}"
    message["Reply-To"] = "support@airate.tech"
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = f"<topup.{order_id}@airate.tech>"
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(Template((templates / "topup.txt").read_text(encoding="utf-8")).substitute(values))
    message.add_alternative(Template((templates / "topup.html").read_text(encoding="utf-8")).substitute(
        {key: escape(value, quote=True) for key, value in values.items()}), subtype="html")
    message.get_payload()[-1].add_related((templates / "airate.png").read_bytes(),
        maintype="image", subtype="png", cid="<airate-logo>", disposition="inline")
    return message


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
        message["Subject"] = "Восстановление доступа к AIRate"
        message.set_content(
            "Чтобы задать новый пароль, откройте ссылку:\n\n"
            f"{link}\n\nСсылка действует 30 минут и подходит для одного использования. "
            "Если вы не запрашивали восстановление, письмо можно игнорировать."
        )
        self._send(message)

    def send_topup(self, email: str, order_id: str, amount_kopeks: int, balance_kopeks: int) -> None:
        self._send(topup_message(self.sender, self.public_base, email, order_id,
                                 amount_kopeks, balance_kopeks))

    def send_verification(self, email: str, code: str) -> None:
        templates = Path(__file__).with_name("email_templates")
        message = EmailMessage()
        message["From"], message["To"] = self.sender, email
        message["Subject"] = "Код подтверждения почты AIRate"
        message["Reply-To"] = "support@airate.tech"
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message["Message-ID"] = make_msgid(domain="airate.tech")
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(Template((templates / "verification-code.txt").read_text(encoding="utf-8")).substitute(code=code))
        message.add_alternative(Template((templates / "verification-code.html").read_text(encoding="utf-8"))
                                .substitute(code=escape(code)), subtype="html")
        message.get_payload()[-1].add_related((templates / "airate.png").read_bytes(),
            maintype="image", subtype="png", cid="<airate-logo>", disposition="inline")
        self._send(message)

    def _send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        started = accepted = False
        try:
            smtp_client = (smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15)
                           if self.security == "ssl" else smtplib.SMTP(self.host, self.port, timeout=15))
            with smtp_client as smtp:
                if self.security == "starttls":
                    smtp.starttls(context=context)
                if self.username:
                    smtp.login(self.username, self.password)
                started = True
                smtp.send_message(message)
                accepted = True
        except (OSError, smtplib.SMTPException) as exc:
            if accepted:
                return  # QUIT failure cannot undo a positive reply to DATA.
            rejected = isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused,
                                        smtplib.SMTPDataError, smtplib.SMTPHeloError))
            raise MailDeliveryError(uncertain=started and not rejected) from exc
