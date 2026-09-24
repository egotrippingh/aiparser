"""После падения сохранённая проверка списывается, незавершённая освобождается."""

import asyncio

from app import billing, config
from app.db import repo


def test_recovery_reconciles_results_before_releasing(tmp_path, monkeypatch):
    old_conn = getattr(repo._local, "conn", None)
    if old_conn is not None:
        old_conn.close()
        del repo._local.conn
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "recovery.db")
    repo.init_db()
    try:
        project_id = repo.create_project("Recovery", "Brand")
        repo.add_queries(project_id, ["one", "two"])
        first, second = [q["id"] for q in repo.list_queries(project_id)]
        keys = [billing.check_id("run", query_id, "chatgpt") for query_id in (first, second)]
        scan_id = repo.create_scan(project_id, ["chatgpt"], {
            "billing_run_id": "run", "billing_reserved_ids": keys,
        })
        repo.save_result(scan_id, first, "chatgpt", "not_found")
        for key in keys:
            repo.queue_billing(key, "release")

        calls = []

        async def complete(check_key, status):
            calls.append(("complete", check_key, status))
            return {"status": "settled"}

        async def release(check_ids):
            calls.append(("release", list(check_ids)))
            return {"released": len(check_ids)}

        monkeypatch.setattr(billing, "complete", complete)
        monkeypatch.setattr(billing, "release", release)
        asyncio.run(billing.recover_interrupted_scans())

        assert calls == [("complete", keys[0], "not_found"), ("release", [keys[1]])]
        assert repo.pending_billing() == []
        assert repo.get_scan(scan_id)["status"] == "stopped"
    finally:
        repo._local.conn.close()
        del repo._local.conn
