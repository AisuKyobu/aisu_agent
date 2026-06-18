"""Episodic / Semantic / Reflective Memory — SQLite FTS 存储

实现 MemoryProvider 接口，支持 Profile 隔离。
语义检索优先使用 ChromaDB 向量相似度，不可用时回退 SQLite FTS。
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import List, Optional

from langchain_deepseek import ChatDeepSeek

from agent.memory.memory_provider import MemoryProvider
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME, MEMORY_DIR

logger = logging.getLogger("aisu.memory")

_memory_llm = ChatDeepSeek(model=MODEL_NAME, temperature=0, api_key=DEEPSEEK_API_KEY, api_base=DEEPSEEK_BASE_URL)


def _get_vector_store(profile: str = "dev"):
    """获取 ChromaDB 向量存储实例（懒加载）。"""
    try:
        from agent.memory.vector_store import VectorStore
    except ImportError:
        return None
    vs = VectorStore(profile=profile)
    return vs if vs.available else None


class MemoryStore(MemoryProvider):
    name = "builtin"

    def __init__(self):
        self._conn: Optional[sqlite3.Connection] = None
        self._task_count = 0
        self._profile = "dev"
        self._initialized = False
        self._vector: Optional[object] = None

    @property
    def db_path(self) -> str:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        return os.path.join(MEMORY_DIR, f"{self._profile}.db")

    def is_available(self) -> bool:
        return True

    def initialize(self, profile: str = "dev", **kwargs) -> None:
        self._profile = profile
        path = self.db_path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._run_migrations()
        self._task_count = self._count_tasks()
        self._vector = _get_vector_store(profile)
        # 如果向量库可用，把 SQLite 中已有的语义记录补齐
        if self._vector:
            self._sync_semantic_to_vector()
        self._initialized = True
        logger.info("MemoryStore(%s) init: %d tasks in %s, vector=%s",
                    profile, self._task_count, path,
                    "enabled" if self._vector else "disabled")

    def prefetch(self, query: str, **kwargs) -> str:
        if not self._initialized:
            return ""
        user_id = kwargs.get("user_id", "guest")
        refl = self.get_reflections()
        facts = self._get_semantic_snapshot(user_id, limit=10)
        parts = []
        if facts:
            parts.append(f"[用户记忆]\n{facts}")
        if refl:
            parts.append(f"[经验反思]\n{refl}")
        return "\n\n".join(parts) if parts else ""

    def sync_turn(self, user_content: str, assistant_content: str, **kwargs) -> None:
        pass

    def save_episode(self, goal: str, steps: list, errors: list, outcome: str, summary: str = "") -> None:
        if not self._initialized:
            return
        self._save_episode_internal("", goal, steps, errors, outcome, summary)

    def search_similar(self, goal: str, k: int = 3) -> List[dict]:
        if not self._initialized:
            return []
        return self._search_similar_internal(goal, k)

    def remember_value(self, key: str, value: str, source: str = "", user_id: str = "guest") -> None:
        if not self._initialized:
            return
        self._remember_internal(key, value, source, user_id)

    def search_semantic(self, query: str, user_id: str = "guest") -> str:
        if not self._initialized:
            return "未找到匹配的记忆"
        return self._search_semantic_internal(query, user_id)

    def get_reflections(self) -> str:
        if not self._initialized:
            return ""
        return self._get_reflections_internal()

    def maybe_reflect(self, force: bool = False) -> None:
        if not self._initialized:
            return
        self._maybe_reflect_internal(force)

    def save_reflection(self, pattern: str, confidence: float = 0.15) -> None:
        if not self._initialized:
            return
        self._save_reflection_internal(pattern, confidence)

    def shutdown(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False

    # ── Schema migrations ──

    MIGRATIONS = [
        (1, "episodic",
         """CREATE TABLE IF NOT EXISTS episodic (
            id TEXT PRIMARY KEY, task_id TEXT, goal TEXT,
            steps_json TEXT, errors_json TEXT, outcome TEXT,
            summary TEXT, created_at REAL)"""),
        (2, "episodic_fts",
         """CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts
            USING fts5(eid, task_id, goal, content)"""),
        (3, "semantic",
         """CREATE TABLE IF NOT EXISTS semantic (
            id TEXT PRIMARY KEY, key TEXT, value TEXT,
            source TEXT, created_at REAL, last_accessed REAL,
            confidence REAL DEFAULT 0.5)"""),
        (4, "reflective",
         """CREATE TABLE IF NOT EXISTS reflective (
            id TEXT PRIMARY KEY, pattern TEXT, evidence_count INT DEFAULT 1,
            confidence REAL DEFAULT 0.3, created_at REAL)"""),
        (5, "semantic_user_id",
         """ALTER TABLE semantic ADD COLUMN user_id TEXT DEFAULT 'guest'"""),
        (6, "semantic_backfill",
         """UPDATE semantic SET user_id='guest' WHERE user_id IS NULL"""),
    ]

    def _run_migrations(self):
        c = self._conn
        c.execute("""CREATE TABLE IF NOT EXISTS _migrations (
            version INTEGER PRIMARY KEY, name TEXT, applied_at REAL)""")
        row = c.execute("SELECT COALESCE(MAX(version), 0) FROM _migrations").fetchone()
        current = row[0] if row else 0
        for ver, name, sql in self.MIGRATIONS:
            if ver <= current:
                continue
            try:
                if name == "semantic_user_id":
                    cols = {r[1] for r in c.execute("PRAGMA table_info(semantic)").fetchall()}
                    if "user_id" in cols:
                        c.execute("INSERT INTO _migrations (version, name, applied_at) VALUES (?,?,?)",
                                  (ver, name, time.time()))
                        c.commit()
                        continue
                c.executescript(sql)
                c.execute(
                    "INSERT INTO _migrations (version, name, applied_at) VALUES (?,?,?)",
                    (ver, name, time.time()))
                c.commit()
            except Exception as e:
                logger.warning("Migration %d (%s) failed: %s", ver, name, e)
        c.commit()

    def _count_tasks(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM episodic").fetchone()
        return row[0] if row else 0

    def _save_episode_internal(self, task_id: str, goal: str, steps: list,
                                errors: list, outcome: str, summary: str = ""):
        eid = f"ep_{int(time.time())}_{(task_id or 'mem')[:8]}"
        steps_json = json.dumps(steps, ensure_ascii=False)
        errors_json = json.dumps(errors, ensure_ascii=False)
        self._conn.execute(
            "INSERT OR REPLACE INTO episodic VALUES (?,?,?,?,?,?,?,?)",
            (eid, task_id, goal, steps_json, errors_json, outcome, summary, time.time()))
        content = goal + " " + " ".join(s.get("desc", "") for s in steps) + " " + summary
        self._conn.execute(
            "INSERT OR REPLACE INTO episodic_fts VALUES (?,?,?,?)",
            (eid, task_id, goal, content))
        self._conn.commit()
        self._task_count += 1

    def _search_similar_internal(self, goal: str, k: int = 3) -> List[dict]:
        try:
            rows = self._conn.execute(
                "SELECT task_id, goal, content, rank FROM episodic_fts "
                "WHERE episodic_fts MATCH ? ORDER BY rank LIMIT ?",
                (goal, k)).fetchall()
        except Exception:
            return []
        results = []
        for row in rows:
            task_id = row[0]
            ep = self._conn.execute(
                "SELECT goal, steps_json, outcome, summary, created_at "
                "FROM episodic WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                (task_id,)).fetchone()
            if ep:
                results.append({
                    "task_id": task_id, "goal": ep[0],
                    "steps": json.loads(ep[1]) if ep[1] else [],
                    "outcome": ep[2], "summary": ep[3],
                    "created_at": datetime.fromtimestamp(ep[4]).strftime("%m-%d %H:%M"),
                })
        return results

    def _remember_internal(self, key: str, value: str, source: str = "", user_id: str = "guest"):
        import uuid
        existing = self._conn.execute(
            "SELECT id FROM semantic WHERE key=? AND user_id=?", (key, user_id)).fetchone()
        now = time.time()
        if existing:
            self._conn.execute(
                "UPDATE semantic SET value=?, source=?, last_accessed=?, confidence=0.7 WHERE id=?",
                (value, source, now, existing[0]))
        else:
            sid = "sem_" + uuid.uuid4().hex[:12]
            self._conn.execute(
                "INSERT INTO semantic VALUES (?,?,?,?,?,?,?,?)",
                (sid, key, value, source, now, now, 0.7, user_id))
        self._conn.commit()
        # 同步到向量库
        if self._vector:
            self._vector.update(key, value, user_id, source="agent", confidence=0.7)

    def _get_semantic_snapshot(self, user_id: str = "guest", limit: int = 10) -> str:
        rows = self._conn.execute(
            "SELECT key, value FROM semantic WHERE user_id=? ORDER BY last_accessed DESC LIMIT ?",
            (user_id, limit)).fetchall()
        if not rows:
            return ""
        return "\n".join(f"- {r[0]}: {r[1]}" for r in rows)

    def _search_semantic_internal(self, query: str, user_id: str = "guest") -> str:
        # 向量语义检索优先
        if self._vector:
            results = self._vector.search(query, user_id, k=5)
            if results:
                lines = []
                for r in results:
                    lines.append(f"- **{r['key']}**: {r['value']}"
                                 f" (置信: {r['confidence']:.1f}, 相似度: {r['score']:.2f})")
                self._conn.execute(
                    "UPDATE semantic SET last_accessed=? WHERE key=? AND user_id=?",
                    (time.time(), results[0]["key"], user_id))
                self._conn.commit()
                return "\n".join(lines)
        # SQLite LIKE 回退
        terms = [t for t in query.strip().split() if len(t) > 1]
        if not terms:
            return "未找到匹配的记忆"
        or_clauses = " OR ".join(["(key LIKE ? OR value LIKE ?)" for _ in terms])
        params = []
        for t in terms:
            params.extend([f"%{t}%", f"%{t}%"])
        params.append(user_id)
        rows = self._conn.execute(
            f"SELECT key, value, source, confidence FROM semantic "
            f"WHERE ({or_clauses}) AND user_id=? ORDER BY last_accessed DESC LIMIT 20",
            params).fetchall()
        if not rows:
            return "未找到匹配的记忆"

        def score(row):
            text = (row[0] + " " + row[1]).lower()
            return sum(1 for t in terms if t.lower() in text)
        rows = list(rows)
        rows.sort(key=score, reverse=True)
        rows = rows[:5]

        lines = []
        for r in rows:
            lines.append(f"- **{r[0]}**: {r[1]} (来源: {r[2]}, 置信: {r[3]:.1f})")
            self._conn.execute("UPDATE semantic SET last_accessed=? WHERE key=?", (time.time(), r[0]))
        self._conn.commit()
        return "\n".join(lines)

    def _maybe_reflect_internal(self, force: bool = False):
        threshold = 10
        if force or (self._task_count > 0 and self._task_count % threshold == 0):
            try:
                self._generate_reflection()
                logger.info("Reflective memory updated (task #%d, profile=%s)", self._task_count, self._profile)
            except Exception as e:
                logger.warning("Reflection skipped: %s", e)

    def _generate_reflection(self):
        episodes = self._conn.execute(
            "SELECT goal, outcome, steps_json, errors_json FROM episodic "
            "ORDER BY created_at DESC LIMIT 10").fetchall()
        if not episodes:
            return
        text = "\n".join(
            f"- 目标: {e[0]}, 结果: {e[1]}, 步骤: {e[2][:100]}, 错误: {e[3][:100]}"
            for e in episodes)
        prompt = (f"分析以下 10 次 AI Agent 任务执行记录，提取出 1-3 条可复用的策略或教训。"
                  f"每条用一句话，格式: - [策略] 描述\n\n{text}")
        try:
            result = _memory_llm.invoke(prompt)
            content = result.content if hasattr(result, "content") else ""
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("- ") and len(line) > 10:
                    pattern = line[2:]
                    existing = self._conn.execute(
                        "SELECT id, evidence_count, confidence FROM reflective "
                        "WHERE pattern LIKE ? OR ? LIKE '%' || pattern || '%'",
                        (f"%{pattern[:30]}%", pattern[:30])).fetchone()
                    if existing:
                        new_count = existing[1] + 1
                        new_conf = min(0.9, 0.3 + new_count * 0.05)
                        self._conn.execute(
                            "UPDATE reflective SET evidence_count=?, confidence=?, created_at=? "
                            "WHERE id=?", (new_count, new_conf, time.time(), existing[0]))
                    else:
                        rid = f"ref_{int(time.time())}_{hash(line) & 0xFFFF:04x}"
                        self._conn.execute(
                            "INSERT INTO reflective VALUES (?,?,?,?,?)",
                            (rid, pattern, 1, 0.3, time.time()))
            self._conn.commit()
        except Exception:
            pass

    def _save_reflection_internal(self, pattern: str, confidence: float = 0.15):
        existing = self._conn.execute(
            "SELECT id, evidence_count, confidence FROM reflective "
            "WHERE pattern LIKE ? OR ? LIKE '%' || pattern || '%'",
            (f"%{pattern[:30]}%", pattern[:30])).fetchone()
        if existing:
            new_count = existing[1] + 1
            new_conf = min(0.9, existing[2] + 0.05)
            self._conn.execute(
                "UPDATE reflective SET evidence_count=?, confidence=?, created_at=? "
                "WHERE id=?", (new_count, new_conf, time.time(), existing[0]))
        else:
            rid = f"ref_{int(time.time())}_{hash(pattern) & 0xFFFF:04x}"
            self._conn.execute(
                "INSERT INTO reflective VALUES (?,?,?,?,?)",
                (rid, pattern, 1, confidence, time.time()))
        self._conn.commit()

    def _get_reflections_internal(self) -> str:
        rows = self._conn.execute(
            "SELECT pattern, confidence, evidence_count FROM reflective "
            "ORDER BY confidence DESC LIMIT 5").fetchall()
        if not rows:
            return ""
        return "\n".join(
            f"- [反思] {r[0]} (置信: {r[1]:.1f}, 证据: {r[2]}次)" for r in rows)

    def _sync_semantic_to_vector(self):
        """将 SQLite 中已有的语义记录分批补写入向量库。"""
        if not self._vector or not self._conn:
            return
        try:
            rows = self._conn.execute(
                "SELECT key, value, COALESCE(source,''), COALESCE(confidence,0.7),"
                " COALESCE(user_id,'guest') FROM semantic").fetchall()
            if rows:
                self._vector.ensure_synced(rows)
        except Exception:
            pass
