"""Operate on parked / waiting rows of the remote outbox (PL-9).

  python -m remote.requeue status                                   # counts by state and reason
  python -m remote.requeue requeue --reason member_mapping_required   # parked -> pending (try again now)
  python -m remote.requeue requeue --reason sequence_gap             # reason prefix match
  python -m remote.requeue park --reason member_mapping_required --state waiting_context
                                                                    # stop retrying now (e.g. test data)

Rows are never deleted here. Inside the containers:
  docker compose -p nodeverse --env-file .env --profile remote -f compose.json exec remote-writer python -m remote.requeue status
"""
from __future__ import annotations

import argparse
import json
import re

from common.db import local_mongo
from common.timeutil import utc_now


def _query(state: str, reason: str | None, player: str | None) -> dict:
    q: dict = {"state": state}
    if reason:
        q["reason"] = {"$regex": "^" + re.escape(reason)}
    if player:
        q["event.player_id"] = {"$regex": "^" + re.escape(player)}
    return q


def status(db) -> dict:
    by_state = {d["_id"]: d["n"] for d in db.remote_event_outbox.aggregate([{"$group": {"_id": "$state", "n": {"$sum": 1}}}])}
    reasons = {}
    for state in ("parked", "waiting_context", "blocked"):
        reasons[state] = [{"reason": d["_id"], "n": d["n"]} for d in db.remote_event_outbox.aggregate([
            {"$match": {"state": state}}, {"$group": {"_id": "$reason", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": 10}])]
    return {"states": by_state, "reasons": reasons}


def requeue(db, reason: str | None, player: str | None, state: str = "parked") -> int:
    return db.remote_event_outbox.update_many(
        _query(state, reason, player),
        {"$set": {"state": "pending", "next_attempt_at": utc_now(), "updated_at": utc_now()},
         "$unset": {"parked_at": "", "waiting_since": ""}}).modified_count


def park(db, reason: str | None, player: str | None, state: str = "waiting_context") -> int:
    if not reason and not player:
        raise SystemExit("park needs --reason or --player")
    return db.remote_event_outbox.update_many(
        _query(state, reason, player),
        {"$set": {"state": "parked", "parked_at": utc_now(), "updated_at": utc_now()},
         "$unset": {"next_attempt_at": ""}}).modified_count


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["status", "requeue", "park"])
    p.add_argument("--reason", help="reason prefix, e.g. member_mapping_required, sequence_gap, retry_limit")
    p.add_argument("--player", help="player_id prefix")
    p.add_argument("--state", help="source state (requeue: parked, park: waiting_context)")
    a = p.parse_args(argv)
    db = local_mongo()
    if a.action == "status":
        out = status(db)
    elif a.action == "requeue":
        out = {"requeued": requeue(db, a.reason, a.player, a.state or "parked")}
    else:
        out = {"parked": park(db, a.reason, a.player, a.state or "waiting_context")}
    print(json.dumps(out, ensure_ascii=False, default=str))
    return out


if __name__ == "__main__":
    main()
