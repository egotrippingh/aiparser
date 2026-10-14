"""Persisted top-up mail outbox; payment commits never wait for SMTP."""
import logging
from datetime import timedelta
from threading import Event, Thread

from sqlalchemy import select, update

from .mailer import MailDeliveryError
from .models import TopupEmail, utcnow

log = logging.getLogger(__name__)


class TopupEmailWorker:
    def __init__(self, session_factory, mailer):
        self.sessions, self.mailer = session_factory, mailer
        self.stop = Event()
        self.thread = Thread(target=self.run, name="topup-emails", daemon=True)

    def send_once(self) -> bool:
        with self.sessions() as db:
            row = db.scalar(select(TopupEmail).where(
                TopupEmail.status == "pending", TopupEmail.next_attempt_at <= utcnow(),
            ).order_by(TopupEmail.next_attempt_at, TopupEmail.order_id).limit(1))
            if row is None:
                return False
            claimed = db.execute(update(TopupEmail).where(
                TopupEmail.order_id == row.order_id, TopupEmail.status == "pending",
            ).values(status="sending", attempts=TopupEmail.attempts + 1))
            if claimed.rowcount != 1:
                return False
            db.commit()
            order_id, email = row.order_id, row.email
            amount, balance, attempts = row.amount_kopeks, row.balance_kopeks, row.attempts
        status, sent_at = "sent", None
        try:
            self.mailer.send_topup(email, order_id, amount, balance)
            sent_at = utcnow()
        except MailDeliveryError as exc:
            status, sent_at = ("uncertain" if exc.uncertain else "pending"), None
            log.warning("Top-up mail %s (%s)", status, type(exc.__cause__).__name__)
        except Exception as exc:
            status, sent_at = "uncertain", None
            log.error("Top-up mail requires inspection (%s)", type(exc).__name__)
        with self.sessions() as db:
            db.execute(update(TopupEmail).where(
                TopupEmail.order_id == order_id, TopupEmail.status == "sending",
            ).values(status=status, sent_at=sent_at,
                     next_attempt_at=utcnow() + timedelta(seconds=min(3600, 30 * 2 ** min(attempts, 7)))))
            db.commit()
        return True

    def run(self):
        while not self.stop.is_set():
            try:
                self.send_once()
            except Exception as exc:
                # A committed claim is never automatically retried after an unknown result.
                log.error("Top-up mail worker unavailable (%s)", type(exc).__name__)
            self.stop.wait(15)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=90)
        if self.thread.is_alive():
            raise RuntimeError("Top-up mail worker did not stop within SMTP shutdown deadline")
