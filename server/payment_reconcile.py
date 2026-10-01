"""Recover missed Coinso callbacks with bounded, rotating status checks."""
import logging
import telemetry
from datetime import timedelta
from threading import Event, Thread

from sqlalchemy import select
from .models import PaymentOrder, utcnow

log = logging.getLogger(__name__)


class PaymentReconciler:
    def __init__(self, session_factory, confirm):
        self.sessions = session_factory
        self.confirm = confirm
        self.stop = Event()
        self.cursor = ""
        self.thread = Thread(target=self.run, name="payment-reconcile", daemon=True)

    def reconcile_once(self):
        with self.sessions() as db:
            rows = db.scalars(select(PaymentOrder).where(
                PaymentOrder.status == "pending", PaymentOrder.invoice_id.is_not(None),
                PaymentOrder.created_at < utcnow() - timedelta(seconds=5),
                PaymentOrder.id > self.cursor,
            ).order_by(PaymentOrder.id).limit(10)).all()
            if not rows:
                self.cursor = ""
            for row in rows:
                if self.stop.is_set():
                    break
                self.cursor = row.id
                owner = row.user_id
                try:
                    self.confirm(db, row, row.invoice_id)
                except Exception as exc:
                    db.rollback()
                    telemetry.capture(exc, component="server", operation="payment_reconcile", user_id=owner)
                    # Do not log payment bodies, user identifiers or credentials.
                    log.warning("Payment reconciliation will retry a pending invoice")

    def run(self):
        while not self.stop.wait(15):
            try:
                self.reconcile_once()
            except Exception as exc:
                telemetry.capture(exc, component="server", operation="payment_reconcile")
                log.warning("Payment reconciliation temporarily unavailable")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=20)
