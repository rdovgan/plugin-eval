"""Writes results to MariaDB (optional: without PE_DB_URL everything works on files).

The source of truth is results/<key>/{manifest,aggregate}.json; the database is an index for queries and
trends that can always be rebuilt with the import command.

    python -m evalkit.db init      # create or update the tables
    python -m evalkit.db import    # write all runs from results/ (safe to re-run)
    python -m evalkit.db status    # row counts and the latest runs

Variables (.env or environment):
    PE_DB_URL=mysql://user:password@127.0.0.1:3307/plugin_eval
    PE_DB_SSH=-p 22 user@db-host.example.com   # if set and the port is closed, an SSH tunnel is opened
"""
from __future__ import annotations

import argparse
import atexit
import datetime as dt
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import unquote

from .config import ROOT, load_dotenv
from . import store

# ---------- schema ----------

MIGRATIONS: List[Tuple[int, List[str]]] = [
    (1, [
        """CREATE TABLE runs (
            run_key         VARCHAR(40)   NOT NULL PRIMARY KEY,
            plugin          VARCHAR(64)   NOT NULL,
            ref             VARCHAR(255)  NOT NULL,
            commit_sha      CHAR(40)      NOT NULL,
            model_name      VARCHAR(64)   NOT NULL,
            model           VARCHAR(128)  NOT NULL,
            base_url        VARCHAR(255)  NOT NULL DEFAULT '',
            judge_model     VARCHAR(64)   NOT NULL,
            suite_hash      CHAR(16)      NOT NULL,
            claude_version  VARCHAR(32)   NOT NULL,
            runs_per_case   SMALLINT      NOT NULL,
            smoke           BOOLEAN       NOT NULL DEFAULT FALSE,
            hidden          BOOLEAN       NOT NULL DEFAULT FALSE,
            case_filter     VARCHAR(255)  NULL,
            mocked_servers  JSON          NULL,
            started_at      DATETIME(3)   NULL,
            created_at      DATETIME      NOT NULL,
            cost_usd        DECIMAL(10,4) NULL,
            duration_sec    INT           NULL,
            overall_score   DECIMAL(6,4)  NULL,
            pass_rate       DECIMAL(6,4)  NULL,
            cases_total     SMALLINT      NULL,
            cases_passed    SMALLINT      NULL,
            partial         BOOLEAN       NOT NULL DEFAULT FALSE,
            partial_reason  VARCHAR(64)   NULL,
            exit_code       SMALLINT      NULL,
            raw_dir         VARCHAR(512)  NOT NULL,
            imported_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY ix_runs_plugin_model (plugin, model_name, created_at),
            KEY ix_runs_commit (commit_sha),
            KEY ix_runs_suite (suite_hash)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE case_results (
            run_key          VARCHAR(40)   NOT NULL,
            case_name        VARCHAR(128)  NOT NULL,
            tags             JSON          NULL,
            is_control       BOOLEAN       NOT NULL DEFAULT FALSE,
            score            DECIMAL(6,4)  NULL,
            pass_rate        DECIMAL(6,4)  NULL,
            stdev            DECIMAL(6,4)  NULL,
            attempts         SMALLINT      NOT NULL,
            errors           SMALLINT      NOT NULL DEFAULT 0,
            max_turns        SMALLINT      NULL,
            timeout_seconds  INT           NULL,
            PRIMARY KEY (run_key, case_name),
            KEY ix_case_name (case_name),
            CONSTRAINT fk_case_run FOREIGN KEY (run_key) REFERENCES runs (run_key) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE attempts (
            run_key               VARCHAR(40)   NOT NULL,
            case_name             VARCHAR(128)  NOT NULL,
            arm                   VARCHAR(8)    NOT NULL,
            attempt_no            SMALLINT      NOT NULL,
            score                 DECIMAL(6,4)  NULL,
            passed                BOOLEAN       NULL,
            error                 TEXT          NULL,
            turns                 SMALLINT      NULL,
            cost_usd              DECIMAL(10,5) NULL,
            judge_cost_usd        DECIMAL(10,5) NULL,
            duration_sec          INT           NULL,
            started_at            DATETIME(3)   NULL,
            skipped_paid_graders  BOOLEAN       NOT NULL DEFAULT FALSE,
            mock_calls            SMALLINT      NULL,
            mock_errors           SMALLINT      NULL,
            trace_path            VARCHAR(512)  NULL,
            PRIMARY KEY (run_key, case_name, arm, attempt_no),
            CONSTRAINT fk_attempt_case FOREIGN KEY (run_key, case_name)
                REFERENCES case_results (run_key, case_name) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE grader_results (
            run_key      VARCHAR(40)   NOT NULL,
            case_name    VARCHAR(128)  NOT NULL,
            arm          VARCHAR(8)    NOT NULL,
            attempt_no   SMALLINT      NOT NULL,
            grader       VARCHAR(128)  NOT NULL,
            type         VARCHAR(32)   NULL,
            weight       DECIMAL(6,2)  NULL,
            passed       BOOLEAN       NULL,
            scored       BOOLEAN       NULL,
            explanation  TEXT          NULL,
            PRIMARY KEY (run_key, case_name, arm, attempt_no, grader),
            KEY ix_grader (case_name, grader),
            CONSTRAINT fk_grader_attempt FOREIGN KEY (run_key, case_name, arm, attempt_no)
                REFERENCES attempts (run_key, case_name, arm, attempt_no) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        """CREATE TABLE comparisons (
            id                   BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
            plugin               VARCHAR(64)   NOT NULL,
            model_name           VARCHAR(64)   NOT NULL,
            ref_a                VARCHAR(255)  NOT NULL,
            ref_b                VARCHAR(255)  NOT NULL,
            run_key_a            VARCHAR(40)   NOT NULL,
            run_key_b            VARCHAR(40)   NOT NULL,
            n                    SMALLINT      NOT NULL,
            mean_diff            DECIMAL(7,4)  NOT NULL,
            ci_lo                DECIMAL(7,4)  NOT NULL,
            ci_hi                DECIMAL(7,4)  NOT NULL,
            verdict              VARCHAR(32)   NOT NULL,
            control_regressions  JSON          NULL,
            cost_a_usd           DECIMAL(10,4) NULL,
            cost_b_usd           DECIMAL(10,4) NULL,
            report_path          VARCHAR(512)  NULL,
            created_at           DATETIME      NOT NULL,
            KEY ix_cmp_plugin (plugin, model_name, created_at),
            CONSTRAINT fk_cmp_a FOREIGN KEY (run_key_a) REFERENCES runs (run_key),
            CONSTRAINT fk_cmp_b FOREIGN KEY (run_key_b) REFERENCES runs (run_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
        # Latest score of each case per commit: the basis for trend charts.
        """CREATE OR REPLACE VIEW case_trend AS
            SELECT r.plugin, r.model_name, r.ref, r.commit_sha, r.created_at, r.suite_hash, r.smoke,
                   c.case_name, c.is_control, c.score, c.stdev, c.attempts, c.errors
            FROM runs r JOIN case_results c ON c.run_key = r.run_key
            WHERE r.partial = FALSE AND r.case_filter IS NULL""",
    ]),
]


# ---------- connection ----------

def _env() -> Dict[str, str]:
    return {**load_dotenv(ROOT / ".env"), **os.environ}


def configured() -> bool:
    return bool(_env().get("PE_DB_URL"))


def parse_url(url: str) -> Dict[str, Any]:
    m = re.fullmatch(r"(?:mysql|mariadb)://([^:@/]+):([^@]*)@([^:/]+)(?::(\d+))?/(\w+)", url.strip())
    if not m:
        raise SystemExit("PE_DB_URL must have the form mysql://user:password@host:port/database")
    return {"user": unquote(m[1]), "password": unquote(m[2]), "host": m[3],
            "port": int(m[4] or 3306), "database": m[5]}


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


_tunnel: Optional[subprocess.Popen] = None


def _ensure_tunnel(params: Dict[str, Any], ssh_target: str) -> None:
    """Opens ssh -L if the local port is closed; it is closed when the process exits."""
    global _tunnel
    host, port = params["host"], params["port"]
    if host not in ("127.0.0.1", "localhost") or _port_open(host, port) or not ssh_target:
        return
    remote = int(_env().get("PE_DB_SSH_REMOTE_PORT", port))
    cmd = ["ssh", *shlex.split(ssh_target), "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
           "-L", f"{port}:127.0.0.1:{remote}"]
    _tunnel = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    atexit.register(_close_tunnel)
    for _ in range(50):
        if _port_open(host, port):
            return
        if _tunnel.poll() is not None:
            raise RuntimeError(f"SSH tunnel did not open: {_tunnel.stderr.read().decode().strip()}")
        time.sleep(0.2)
    raise RuntimeError("SSH tunnel did not open within 10 s")


def _close_tunnel() -> None:
    global _tunnel
    if _tunnel and _tunnel.poll() is None:
        _tunnel.terminate()
        try:
            _tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _tunnel.kill()
    _tunnel = None


@contextmanager
def connect() -> Iterator[Any]:
    import pymysql  # imported here: the driver is not needed without a database

    env = _env()
    if not env.get("PE_DB_URL"):
        raise SystemExit("PE_DB_URL is not set (.env or environment)")
    params = parse_url(env["PE_DB_URL"])
    _ensure_tunnel(params, env.get("PE_DB_SSH", ""))
    conn = pymysql.connect(**params, charset="utf8mb4", autocommit=False, connect_timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def migrate(conn: Any) -> List[int]:
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                           version INT NOT NULL PRIMARY KEY,
                           applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("SELECT version FROM schema_migrations")
        done = {row[0] for row in cur.fetchall()}
        applied = []
        for version, statements in MIGRATIONS:
            if version in done:
                continue
            for sql in statements:   # DDL in MariaDB commits implicitly: every migration must be re-runnable
                cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
    conn.commit()
    return applied


# ---------- writing ----------

def _ts(v: Optional[str]) -> Optional[dt.datetime]:
    if not v:
        return None
    return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def _j(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _run_row(key: str, m: Dict[str, Any], agg: Dict[str, Any], raw_dir: Path) -> Dict[str, Any]:
    a = agg.get("aggregates") or {}
    return {
        "run_key": key, "plugin": m["plugin"], "ref": m["ref"], "commit_sha": m["commit"],
        "model_name": m["model_name"], "model": m["model"], "base_url": m.get("base_url") or "",
        "judge_model": m["judge_model"], "suite_hash": m["suite_hash"], "claude_version": m["claude_version"],
        "runs_per_case": m["runs"], "smoke": bool(m.get("smoke")), "hidden": bool(m.get("hidden")),
        "case_filter": m.get("case_filter"), "mocked_servers": _j(m.get("mocked_servers")),
        "started_at": _ts(agg.get("startedAt")), "created_at": dt.datetime.fromisoformat(m["created_at"]),
        "cost_usd": agg.get("costUsd"), "duration_sec": agg.get("durationSeconds"),
        "overall_score": a.get("overallScore"), "pass_rate": a.get("overallPassRate"),
        "cases_total": a.get("casesTotal"), "cases_passed": a.get("casesPassed"),
        "partial": bool(agg.get("partial")), "partial_reason": agg.get("partialReason"),
        "exit_code": m.get("exit_code"), "raw_dir": str(raw_dir),
    }


def _insert(cur: Any, table: str, row: Dict[str, Any], upsert: bool = False) -> None:
    cols = ", ".join(row)
    vals = ", ".join(["%s"] * len(row))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({vals})"
    if upsert:
        sql += " ON DUPLICATE KEY UPDATE " + ", ".join(f"{c}=VALUES({c})" for c in row)
    cur.execute(sql, list(row.values()))


def record_run(conn: Any, key: str) -> None:
    """Writes one run from results/<key>/ (replaces the previous record with the same key)."""
    from . import aggregate

    d = store.run_dir(key)
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    agg = aggregate.load(d / "aggregate.json")
    tags = {c["name"]: c.get("tags") or [] for c in m.get("cases") or []}
    scores = aggregate.case_scores(agg)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM runs WHERE run_key = %s", (key,))   # cascades to cases/attempts/graders
        _insert(cur, "runs", _run_row(key, m, agg, d))
        for case in agg.get("cases") or []:
            name = case["name"]
            ca = case.get("aggregates") or {}
            t = tags.get(name, [])
            arms = case.get("arms") or {}
            _insert(cur, "case_results", {
                "run_key": key, "case_name": name, "tags": _j(t), "is_control": "control" in t,
                "score": ca.get("score"), "pass_rate": ca.get("passRate"),
                "stdev": scores.get(name, {}).get("stdev"),
                "attempts": len(arms.get("with") or []), "errors": scores.get(name, {}).get("errors", 0),
                "max_turns": case.get("maxTurns"), "timeout_seconds": case.get("timeoutSeconds"),
            })
            defs = {g["name"]: g for g in case.get("graders") or []}
            for arm, attempts in arms.items():
                for no, at in enumerate(attempts or [], 1):
                    calls = ((at.get("mocks") or {}).get("calls") or {})
                    _insert(cur, "attempts", {
                        "run_key": key, "case_name": name, "arm": arm, "attempt_no": no,
                        "score": at.get("score"), "passed": at.get("passed"), "error": at.get("error"),
                        "turns": at.get("turns"), "cost_usd": at.get("costUsd"),
                        "judge_cost_usd": at.get("judgeCostUsd"), "duration_sec": at.get("durationSeconds"),
                        "started_at": _ts(at.get("startedAt")),
                        "skipped_paid_graders": bool(at.get("skippedPaidGraders")),
                        "mock_calls": calls.get("total"), "mock_errors": calls.get("errors"),
                        "trace_path": at.get("tracePath"),
                    })
                    for g in at.get("graders") or []:
                        _insert(cur, "grader_results", {
                            "run_key": key, "case_name": name, "arm": arm, "attempt_no": no,
                            "grader": g["name"], "type": (defs.get(g["name"]) or {}).get("type"),
                            "weight": g.get("weight"), "passed": g.get("passed"), "scored": g.get("scored"),
                            "explanation": g.get("explanation"),
                        })
    conn.commit()


def record_comparison(conn: Any, plugin: str, model: str, ref_a: str, ref_b: str,
                      ma: Dict[str, Any], mb: Dict[str, Any], result: Dict[str, Any],
                      report_path: Optional[Path]) -> None:
    lo, hi = result["ci"]
    with conn.cursor() as cur:
        _insert(cur, "comparisons", {
            "plugin": plugin, "model_name": model, "ref_a": ref_a, "ref_b": ref_b,
            "run_key_a": Path(ma["_dir"]).name, "run_key_b": Path(mb["_dir"]).name,
            "n": result["n"], "mean_diff": round(result["mean_diff"], 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
            "verdict": result["verdict"], "control_regressions": _j(result["control_regressions"]),
            "cost_a_usd": ma.get("cost_usd"), "cost_b_usd": mb.get("cost_usd"),
            "report_path": str(report_path) if report_path else None,
            "created_at": dt.datetime.now().replace(microsecond=0),
        })
    conn.commit()


# ---------- calls from run/compare: the database must not break a run ----------

def try_record_run(key: str) -> None:
    if not configured():
        return
    try:
        with connect() as conn:
            migrate(conn)
            record_run(conn, key)
        print(f"    written to MariaDB: runs.{key}")
    except Exception as e:  # noqa: BLE001 - files are already written, the database can be filled later via import
        print(f"    warning: could not write to MariaDB ({e}); later run: python -m evalkit.db import", file=sys.stderr)


def try_record_comparison(*args: Any, **kwargs: Any) -> None:
    if not configured():
        return
    try:
        with connect() as conn:
            migrate(conn)
            for m in (args[4], args[5]):                 # both runs must be in the database
                record_run(conn, Path(m["_dir"]).name)
            record_comparison(conn, *args, **kwargs)
        print("written to MariaDB: comparisons")
    except Exception as e:  # noqa: BLE001
        print(f"warning: could not write the comparison to MariaDB ({e})", file=sys.stderr)


# ---------- CLI ----------

def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["init", "import", "status"])
    args = p.parse_args(argv)
    with connect() as conn:
        applied = migrate(conn)
        if args.cmd == "init":
            print(f"migrations applied: {applied or 'nothing new'}")
        elif args.cmd == "import":
            keys = [Path(m["_dir"]).name for m in store.manifests()]
            for k in keys:
                record_run(conn, k)
                print(f"  {k}")
            print(f"runs written: {len(keys)}")
        with conn.cursor() as cur:
            for t in ("runs", "case_results", "attempts", "grader_results", "comparisons"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"{t:15} {cur.fetchone()[0]}")
            if args.cmd == "status":
                cur.execute("""SELECT created_at, plugin, ref, LEFT(commit_sha, 8), model_name, overall_score,
                                      cost_usd, COALESCE(case_filter, '') FROM runs ORDER BY created_at DESC LIMIT 10""")
                for row in cur.fetchall():
                    print("  ", *row)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
