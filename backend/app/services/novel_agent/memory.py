"""
Agent 记忆系统 - 参考 DeepSeek-Reasonix 的项目内存设计

包含：
- SQLite 持久化记忆（审计日志、修正历史、问答历史）
- 项目内存（AGENTS.md 风格的项目级记忆文件）
- 会话记忆（短期对话上下文）
"""

import json
import os
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path


class AgentMemory:
    """Agent 记忆系统

    三层记忆结构（参考 Reasonix）：
    1. 工作记忆（Working Memory）：当前会话上下文
    2. 情景记忆（Episodic Memory）：历史交互记录（SQLite）
    3. 语义记忆（Semantic Memory）：项目级知识（AGENTS.md）
    """

    def __init__(self, config=None, session_id: str | None = None):
        self.config = config or {}
        self.db_path = self._get_config('memory.sqlite_path', 'data/novel_agent.db')
        self.project_memory_file = self._get_config(
            'memory.project_memory_file', '.novel_agent/AGENTS.md'
        )
        self.max_history = self._get_config('memory.max_history', 100)
        self.session_id = str(session_id or self._get_config('memory.session_id', 'default'))

        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)

        self._init_db()
        self._init_project_memory()

        self.conversation_history: List[Dict] = self._load_conversation_history()

    def _get_config(self, key: str, default: Any = None) -> Any:
        if hasattr(self.config, 'get'):
            return self.config.get(key, default)
        if not isinstance(self.config, dict):
            return default
        value = self.config
        for part in key.split('.'):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT 'default',
            action TEXT,
            tool TEXT,
            params TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            char1 TEXT,
            char2 TEXT,
            old_type TEXT,
            new_type TEXT,
            evidence TEXT,
            confidence REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT 'default',
            question TEXT,
            answer TEXT,
            context TEXT,
            tools_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS project_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT,
            category TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT 'default',
            tool_name TEXT,
            params TEXT,
            result TEXT,
            success INTEGER,
            duration_ms REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        for table in ('audit_log', 'qa_history', 'tool_calls'):
            columns = {row[1] for row in c.execute(f'PRAGMA table_info({table})').fetchall()}
            if 'session_id' not in columns:
                c.execute(f"ALTER TABLE {table} ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default'")

        conn.commit()
        conn.close()

    def _init_project_memory(self):
        if self._get_config('memory.enable_project_memory', True):
            Path(self.project_memory_file).parent.mkdir(parents=True, exist_ok=True)
            if not os.path.exists(self.project_memory_file):
                initial = f"""# NovelAgent 项目记忆

> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 项目概述

小说智能分析项目，使用 NovelAgent 进行人物关系提取、图谱构建和情节分析。

## 技能配置

- collector: 小说采集
- extractor: 实体与关系抽取
- auditor: 质量审计
- grapher: 图谱生成
- qa: 智能问答
- summarizer: 摘要生成
- writer: 写作辅助
- reasoner: 推理分析

## 已知人物

（待分析后填充）

## 修正记录

（待审计后填充）

---
*本文件由 NovelAgent 自动维护*
"""
                with open(self.project_memory_file, 'w', encoding='utf-8') as f:
                    f.write(initial)

    def log_tool_call(self, tool_name: str, params: Dict, result: Any, success: bool = True, duration_ms: float = 0):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'INSERT INTO tool_calls (session_id, tool_name, params, result, success, duration_ms) VALUES (?, ?, ?, ?, ?, ?)',
            (self.session_id, tool_name, json.dumps(params, ensure_ascii=False), str(result)[:500], 1 if success else 0, duration_ms)
        )
        conn.commit()
        conn.close()

    def log_audit(self, action: str, tool: str, params: Dict, result: str = ''):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'INSERT INTO audit_log (session_id, action, tool, params, result) VALUES (?, ?, ?, ?, ?)',
            (self.session_id, action, tool, json.dumps(params, ensure_ascii=False), result[:500])
        )
        conn.commit()
        conn.close()

    def add_correction(self, c1: str, c2: str, old_type: str, new_type: str, evidence: str, confidence: float):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'INSERT INTO corrections (char1, char2, old_type, new_type, evidence, confidence) VALUES (?, ?, ?, ?, ?, ?)',
            (c1, c2, old_type or 'N/A', new_type, evidence, confidence)
        )
        conn.commit()
        conn.close()

    def add_qa(self, question: str, answer: str, context: str = '', tools_used: List[str] = None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'INSERT INTO qa_history (session_id, question, answer, context, tools_used) VALUES (?, ?, ?, ?, ?)',
            (self.session_id, question, answer, context, json.dumps(tools_used or [], ensure_ascii=False))
        )
        c.execute(
            'INSERT OR REPLACE INTO project_memory (key, value, category, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
            (
                f"session:{self.session_id}:last_qa",
                json.dumps({"question": question, "answer": answer[:1000]}, ensure_ascii=False),
                "session",
            ),
        )
        conn.commit()
        conn.close()

    def add_to_conversation(self, role: str, content: str, metadata: Dict = None):
        item = {
            'role': role,
            'content': content,
            'metadata': metadata or {},
            'timestamp': datetime.now().isoformat(),
        }
        self.conversation_history.append(item)
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute(
                'INSERT INTO conversation_history (session_id, role, content, metadata) VALUES (?, ?, ?, ?)',
                (self.session_id, role, content, json.dumps(metadata or {}, ensure_ascii=False)),
            )
            conn.execute(
                'DELETE FROM conversation_history WHERE session_id = ? AND id NOT IN '
                '(SELECT id FROM conversation_history WHERE session_id = ? ORDER BY id DESC LIMIT ?)',
                (self.session_id, self.session_id, int(self.max_history)),
            )
            conn.commit()
        finally:
            conn.close()
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

    def get_recent_qa(self, limit: int = 10, query: str = '') -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if query and str(query).strip():
            term = f"%{str(query).strip()}%"
            c.execute(
                'SELECT question, answer, created_at FROM qa_history '
                'WHERE session_id = ? AND (question LIKE ? OR answer LIKE ?) ORDER BY id DESC LIMIT ?',
                (self.session_id, term, term, limit),
            )
        else:
            c.execute(
                'SELECT question, answer, created_at FROM qa_history '
                'WHERE session_id = ? ORDER BY id DESC LIMIT ?',
                (self.session_id, limit),
            )
        rows = c.fetchall()
        conn.close()
        return [
            {'question': r[0], 'answer': r[1], 'created_at': r[2]}
            for r in rows
        ]

    def get_corrections(self, status: str = 'pending', limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'SELECT char1, char2, old_type, new_type, evidence, confidence, created_at FROM corrections WHERE status = ? ORDER BY id DESC LIMIT ?',
            (status, limit)
        )
        rows = c.fetchall()
        conn.close()
        return [
            {'char1': r[0], 'char2': r[1], 'old_type': r[2], 'new_type': r[3],
             'evidence': r[4], 'confidence': r[5], 'created_at': r[6]}
            for r in rows
        ]

    def update_project_memory(self, key: str, value: str, category: str = 'general'):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'INSERT OR REPLACE INTO project_memory (key, value, category, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
            (key, value, category)
        )
        conn.commit()
        conn.close()

    def get_project_memory(self, key: str = None, category: str = None) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if key:
            c.execute('SELECT key, value, category FROM project_memory WHERE key = ?', (key,))
            row = c.fetchone()
            conn.close()
            return {row[0]: {'value': row[1], 'category': row[2]}} if row else {}
        elif category:
            c.execute('SELECT key, value, category FROM project_memory WHERE category = ?', (category,))
        else:
            c.execute('SELECT key, value, category FROM project_memory')
        rows = c.fetchall()
        conn.close()
        return {r[0]: {'value': r[1], 'category': r[2]} for r in rows}

    def stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        stats = {}
        for table in ['audit_log', 'corrections', 'qa_history', 'tool_calls', 'project_memory', 'conversation_history']:
            if table in {'audit_log', 'qa_history', 'tool_calls', 'conversation_history'}:
                c.execute(f'SELECT COUNT(*) FROM {table} WHERE session_id = ?', (self.session_id,))
            else:
                c.execute(f'SELECT COUNT(*) FROM {table}')
            stats[table] = c.fetchone()[0]
        conn.close()
        return stats

    def _load_conversation_history(self) -> List[Dict]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            rows = conn.execute(
                'SELECT role, content, metadata, created_at FROM conversation_history '
                'WHERE session_id = ? ORDER BY id DESC LIMIT ?',
                (self.session_id, int(self.max_history)),
            ).fetchall()
        finally:
            conn.close()
        history = []
        for role, content, metadata, created_at in reversed(rows):
            try:
                parsed = json.loads(metadata or '{}')
            except (TypeError, ValueError):
                parsed = {}
            history.append({
                'role': role,
                'content': content,
                'metadata': parsed if isinstance(parsed, dict) else {},
                'timestamp': created_at,
            })
        return history
