"""State store: JSON Lines tables on disk, in-memory SQLite while a run works.

Canonical state lives in the private data repo as `db/<table>.jsonl`, or `db/<table>/<YYYY-MM>.jsonl`
for high-volume tables. Rows are one JSON object per line, sorted by id, with sorted keys and no
null fields, so git diffs stay small and readable. Only files whose content changed are rewritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import timeutil

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[str, ...]
    json_cols: frozenset[str] = frozenset()
    bool_cols: frozenset[str] = frozenset()
    shard: str | None = None
    indexes: tuple[str, ...] = ()


def _t(name: str, cols: str, json_cols: str = "", bool_cols: str = "", shard: str | None = None,
       indexes: str = "") -> Table:
    return Table(
        name=name,
        columns=tuple(["id", *cols.split()]),
        json_cols=frozenset(json_cols.split()),
        bool_cols=frozenset(bool_cols.split()),
        shard=shard,
        indexes=tuple(indexes.split()),
    )


TABLES: dict[str, Table] = {
    t.name: t
    for t in [
        _t("sources",
           "name kind url query lang hl gl ceid scout pillar_hints tier best_effort max_items active "
           "paused_reason added_by notes created_at updated_at last_fetch_at last_success_at "
           "consecutive_failures last_error etag last_modified items_total items_last_run yield_stats extra",
           json_cols="pillar_hints yield_stats extra", bool_cols="best_effort active", indexes="scout"),
        _t("items",
           "source_id scout tier url canonical_url title title_en summary summary_en lang published_at "
           "fetched_at title_key topic_id signals origin",
           json_cols="signals", shard="fetched_at", indexes="canonical_url title_key topic_id source_id"),
        _t("topics",
           "origin request_id scout tier title title_en summary item_ids source_ids publishers n_sources "
           "first_seen_at last_seen_at newest_published_at why_now fit scores triage status updated_at",
           json_cols="item_ids source_ids publishers why_now fit scores triage", shard="first_seen_at",
           indexes="status request_id"),
        _t("cards",
           "topic_id request_id delivery_id kind platform mode pillar format affairs_type issue_key title "
           "why_now angle format_note draft draft_original hooks hook_type sources claims flags questions "
           "answers status rank score score_parts explore experiment_id arm versions llm work working skip "
           "rewrite_count delivered_at expires_at status_changed_at post_id draft_state draft_basis created_at "
           "updated_at revision",
           json_cols="draft draft_original hooks sources claims flags questions answers score_parts versions "
                     "llm work working skip",
           bool_cols="explore", shard="created_at", indexes="status platform topic_id delivery_id request_id"),
        _t("posts",
           "card_id platform pillar format final_text final_posts posted_at post_url edit_ratio edit_stats "
           "hook_used features editing_seconds time_to_post_minutes reward reward_parts perf guard "
           "created_at updated_at",
           json_cols="final_posts edit_stats hook_used features reward_parts guard", indexes="card_id platform"),
        _t("metrics",
           "post_id platform captured_at impressions reactions comments reposts sends followers_gained "
           "profile_views link_clicks source upload_id extraction_confidence match_confidence status raw "
           "notes created_at",
           json_cols="raw", indexes="post_id status"),
        _t("metric_uploads", "paths week note status created_at processed_at results error",
           json_cols="paths results"),
        _t("account_stats", "date platform followers profile_views source created_at"),
        _t("interactions", "at type card_id post_id request_id platform data",
           json_cols="data", shard="at", indexes="card_id type"),
        _t("stances",
           "issue tier context positions chosen status sources keywords created_by created_at updated_at",
           json_cols="positions chosen sources keywords"),
        _t("requests",
           "query platforms notes status created_at started_at completed_at card_ids error search attempts",
           json_cols="platforms card_ids search"),
        _t("proposals",
           "kind title detail payload evidence confidence status created_at decided_at decision_note source",
           json_cols="payload evidence"),
        _t("playbook_versions",
           "version created_at status rules changes experiments summary source",
           json_cols="rules changes experiments"),
        _t("experiments",
           "created_at platform pillar instruction hypothesis status trials picks stats source_version "
           "updated_at",
           json_cols="stats"),
        _t("system_reports", "week created_at period sections actions proposals",
           json_cols="period sections actions proposals"),
        _t("voice_profiles",
           "version created_at stats rules avoid cut_phrases added_phrases examples summary",
           json_cols="stats rules avoid cut_phrases added_phrases examples"),
        _t("bandit_arms", "platform pillar format alpha beta mean n_obs prior_mean updated_at"),
        _t("deliveries", "local_date delivered_at counts degraded notes run_id kind",
           json_cols="counts notes"),
        _t("runs",
           "task trigger started_at ended_at status steps llm errors degraded notes journal versions",
           json_cols="steps llm errors notes journal versions", shard="started_at"),
        _t("quota", "provider day requests tokens_in tokens_out exhausted_at last_error last_error_at last_ok_at model "
           "updated_at"),
        _t("settings", "value updated_at", json_cols="value"),
        _t("processed_events", "batch_id at type status error", shard="at"),
        _t("doctor_reports", "created_at checks summary", json_cols="checks summary"),
    ]
}


def _encode(table: Table, col: str, value: Any) -> Any:
    if value is None:
        return None
    if col in table.json_cols:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if col in table.bool_cols:
        return 1 if value else 0
    return value


def _decode_row(table: Table, row: sqlite3.Row) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in table.columns:
        value = row[col]
        if value is None:
            out[col] = None
        elif col in table.json_cols:
            out[col] = json.loads(value)
        elif col in table.bool_cols:
            out[col] = bool(value)
        else:
            out[col] = value
    return out


def _dump_line(row: dict[str, Any]) -> str:
    compact = {k: v for k, v in row.items() if v is not None}
    return json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class Store:
    root: Path
    conn: sqlite3.Connection = field(init=False)
    _file_hashes: dict[str, str] = field(default_factory=dict, init=False)
    _dropped_keys: dict[str, set[str]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for table in TABLES.values():
            cols = ", ".join(["id TEXT PRIMARY KEY", *[f'"{c}"' for c in table.columns[1:]]])
            self.conn.execute(f'CREATE TABLE "{table.name}" ({cols})')
            for idx in table.indexes:
                self.conn.execute(f'CREATE INDEX "ix_{table.name}_{idx}" ON "{table.name}" ("{idx}")')

    # -- paths ------------------------------------------------------------------------------------
    @property
    def db_dir(self) -> Path:
        return self.root / "db"

    def _files_for(self, table: Table) -> list[Path]:
        if table.shard:
            folder = self.db_dir / table.name
            return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []
        path = self.db_dir / f"{table.name}.jsonl"
        return [path] if path.exists() else []

    def _path_for(self, table: Table, shard_key: str | None) -> Path:
        if table.shard:
            return self.db_dir / table.name / f"{shard_key}.jsonl"
        return self.db_dir / f"{table.name}.jsonl"

    # -- load / save ------------------------------------------------------------------------------
    @classmethod
    def open(cls, root: str | Path) -> Store:
        store = cls(Path(root))
        store.load()
        return store

    def load(self) -> None:
        for table in TABLES.values():
            placeholders = ", ".join("?" for _ in table.columns)
            cols = ", ".join(f'"{c}"' for c in table.columns)
            sql = f'INSERT OR REPLACE INTO "{table.name}" ({cols}) VALUES ({placeholders})'
            for path in self._files_for(table):
                text = path.read_text(encoding="utf-8")
                self._file_hashes[str(path.relative_to(self.root))] = hashlib.sha1(text.encode()).hexdigest()
                batch = []
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    extra = set(row) - set(table.columns)
                    if extra:
                        self._dropped_keys.setdefault(table.name, set()).update(extra)
                    batch.append(tuple(_encode(table, c, row.get(c)) for c in table.columns))
                self.conn.executemany(sql, batch)

    def save(self) -> list[str]:
        """Write changed tables back to disk. Returns relative paths that changed."""
        changed: list[str] = []
        self.db_dir.mkdir(parents=True, exist_ok=True)
        meta = self.db_dir / "_meta.json"
        if not meta.exists():
            meta.write_text(json.dumps({"schema": SCHEMA_VERSION}) + "\n", encoding="utf-8")
            changed.append(str(meta.relative_to(self.root)))
        for table in TABLES.values():
            groups: dict[str | None, list[str]] = {}
            for row in self.select(table.name):
                key = timeutil.month_key(row.get(table.shard)) if table.shard else None
                groups.setdefault(key, []).append(_dump_line(row))
            written: set[str] = set()
            for key, lines in groups.items():
                path = self._path_for(table, key)
                rel = str(path.relative_to(self.root))
                written.add(rel)
                text = "\n".join(lines) + "\n"
                digest = hashlib.sha1(text.encode()).hexdigest()
                if self._file_hashes.get(rel) == digest:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".jsonl.tmp")
                tmp.write_text(text, encoding="utf-8")
                os.replace(tmp, path)
                self._file_hashes[rel] = digest
                changed.append(rel)
            for rel in [r for r in self._file_hashes if self._belongs(table, r) and r not in written]:
                path = self.root / rel
                if path.exists():
                    path.unlink()
                del self._file_hashes[rel]
                changed.append(rel)
        return changed

    def _belongs(self, table: Table, rel: str) -> bool:
        if table.shard:
            return rel.startswith(f"db/{table.name}/")
        return rel == f"db/{table.name}.jsonl"

    # -- reads -----------------------------------------------------------------------------------
    def get(self, table: str, id: str) -> dict[str, Any] | None:
        spec = TABLES[table]
        row = self.conn.execute(f'SELECT * FROM "{table}" WHERE id = ?', (id,)).fetchone()
        return _decode_row(spec, row) if row else None

    def select(self, table: str, where: str = "", params: Iterable[Any] = (), order: str = "id",
               limit: int | None = None) -> list[dict[str, Any]]:
        spec = TABLES[table]
        sql = f'SELECT * FROM "{table}"'
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_decode_row(spec, r) for r in self.conn.execute(sql, tuple(params))]

    def iter(self, table: str, where: str = "", params: Iterable[Any] = ()) -> Iterator[dict[str, Any]]:
        spec = TABLES[table]
        sql = f'SELECT * FROM "{table}"' + (f" WHERE {where}" if where else "") + " ORDER BY id"
        for r in self.conn.execute(sql, tuple(params)):
            yield _decode_row(spec, r)

    def count(self, table: str, where: str = "", params: Iterable[Any] = ()) -> int:
        sql = f'SELECT COUNT(*) FROM "{table}"' + (f" WHERE {where}" if where else "")
        return int(self.conn.execute(sql, tuple(params)).fetchone()[0])

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row else None

    # -- writes ----------------------------------------------------------------------------------
    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        spec = TABLES[table]
        self._check_keys(spec, row)
        cols = [c for c in spec.columns if c in row]
        col_list = ", ".join(f'"{c}"' for c in cols)
        marks = ", ".join("?" for _ in cols)
        self.conn.execute(f'INSERT INTO "{table}" ({col_list}) VALUES ({marks})',
                          tuple(_encode(spec, c, row[c]) for c in cols))
        return row

    def upsert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        """Insert, or update only the columns present in `row`."""
        spec = TABLES[table]
        self._check_keys(spec, row)
        cols = [c for c in spec.columns if c in row]
        col_list = ", ".join(f'"{c}"' for c in cols)
        marks = ", ".join("?" for _ in cols)
        updates = ", ".join(f'"{c}" = excluded."{c}"' for c in cols if c != "id")
        conflict = f"ON CONFLICT(id) DO UPDATE SET {updates}" if updates else "ON CONFLICT(id) DO NOTHING"
        self.conn.execute(f'INSERT INTO "{table}" ({col_list}) VALUES ({marks}) {conflict}',
                          tuple(_encode(spec, c, row[c]) for c in cols))
        return row

    def update(self, table: str, id: str, **fields: Any) -> None:
        if not fields:
            return
        spec = TABLES[table]
        self._check_keys(spec, fields)
        sets = ", ".join(f'"{c}" = ?' for c in fields)
        self.conn.execute(f'UPDATE "{table}" SET {sets} WHERE id = ?',
                          (*[_encode(spec, c, v) for c, v in fields.items()], id))

    def delete(self, table: str, id: str) -> None:
        self.conn.execute(f'DELETE FROM "{table}" WHERE id = ?', (id,))

    def delete_where(self, table: str, where: str, params: Iterable[Any] = ()) -> int:
        cur = self.conn.execute(f'DELETE FROM "{table}" WHERE {where}', tuple(params))
        return cur.rowcount

    @staticmethod
    def _check_keys(spec: Table, row: dict[str, Any]) -> None:
        unknown = set(row) - set(spec.columns)
        if unknown:
            raise KeyError(f"unknown columns for {spec.name}: {sorted(unknown)}")

    # -- settings helpers ------------------------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.get("settings", key)
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.upsert("settings", {"id": key, "value": value, "updated_at": timeutil.now_iso()})
