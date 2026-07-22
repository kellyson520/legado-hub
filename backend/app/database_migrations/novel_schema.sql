-- NovelUnderstanding 系统数据库 Schema
-- SQLite 兼容，含 JSON 字段（以 TEXT 存储）

-- novels: 小说索引
CREATE TABLE IF NOT EXISTS novels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_url TEXT NOT NULL,
    book_name TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    total_chapters INTEGER NOT NULL DEFAULT 0,
    total_words INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    source_type TEXT NOT NULL DEFAULT 'book_source',
    ingest_progress REAL NOT NULL DEFAULT 0.0,
    ingest_error_msg TEXT,
    character_count INTEGER NOT NULL DEFAULT 0,
    entity_count INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    summary_global TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_scope TEXT NOT NULL DEFAULT 'legacy'
);
CREATE INDEX IF NOT EXISTS idx_novels_status ON novels(status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_novels_owner_url ON novels(owner_scope, book_url);
CREATE INDEX IF NOT EXISTS idx_novels_owner_updated ON novels(owner_scope, updated_at DESC);

-- Incremental understanding checkpoints.  A NULL chapter_id is the optional
-- book-level checkpoint; chapter rows are always filtered by owner_scope.
CREATE TABLE IF NOT EXISTS novel_index_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_scope TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER,
    content_hash TEXT NOT NULL DEFAULT '',
    knowledge_version TEXT NOT NULL DEFAULT '',
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    bm25_status TEXT NOT NULL DEFAULT 'pending',
    vector_status TEXT NOT NULL DEFAULT 'disabled',
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_dimension INTEGER NOT NULL DEFAULT 0,
    extraction_payload TEXT NOT NULL DEFAULT '{}',
    last_success_at TIMESTAMP,
    failure_reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_novel_index_states_owner_book
    ON novel_index_states(owner_scope, book_id, chapter_id);

CREATE TABLE IF NOT EXISTS novel_adjudication_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_scope TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER,
    candidate_key TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    candidate_payload TEXT NOT NULL DEFAULT '{}',
    evidence_payload TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    decision_payload TEXT NOT NULL DEFAULT '{}',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(owner_scope, book_id, chapter_id, candidate_key)
);
CREATE INDEX IF NOT EXISTS idx_novel_adjudication_scope_status
    ON novel_adjudication_candidates(owner_scope, book_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS novel_reading_progress (
    owner_scope TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    offset_chars INTEGER NOT NULL DEFAULT 0,
    percent REAL NOT NULL DEFAULT 0.0,
    theme TEXT NOT NULL DEFAULT 'paper',
    background TEXT NOT NULL DEFAULT '',
    font_size INTEGER NOT NULL DEFAULT 18,
    line_height REAL NOT NULL DEFAULT 1.9,
    content_width TEXT NOT NULL DEFAULT 'comfortable',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(owner_scope, book_id),
    FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
);

-- Local vector backend.  Vectors and payloads are JSON because SQLite has no
-- native vector type; the adapter computes cosine scores in Python.
CREATE TABLE IF NOT EXISTS novel_vectors (
    owner_scope TEXT NOT NULL,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    knowledge_version TEXT NOT NULL,
    record_key TEXT NOT NULL DEFAULT '',
    vector TEXT NOT NULL DEFAULT '[]',
    payload TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(owner_scope, book_id, knowledge_version, record_key),
    FOREIGN KEY(book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_novel_vectors_scope_book_version
    ON novel_vectors(owner_scope, book_id, knowledge_version);

CREATE TABLE IF NOT EXISTS novel_model_preferences (
    owner_scope TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    model_ref TEXT NOT NULL,
    provider_group TEXT NOT NULL DEFAULT 'novel',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(owner_scope, scope_type, scope_id, task_type)
);

-- novel_source_mirrors: 书源镜像
CREATE TABLE IF NOT EXISTS novel_source_mirrors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    last_check_at TIMESTAMP,
    last_check_result TEXT NOT NULL DEFAULT '',
    avg_response_ms INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    total_chapters_available INTEGER NOT NULL DEFAULT 0,
    chapters_fetched INTEGER NOT NULL DEFAULT 0,
    content_fingerprint TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(book_id, source_url)
);
CREATE INDEX IF NOT EXISTS idx_mirrors_book_status ON novel_source_mirrors(book_id, status);

-- novel_chapters: 章节元数据
CREATE TABLE IF NOT EXISTS novel_chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    canonical_type TEXT NOT NULL DEFAULT 'C',
    canonical_num INTEGER NOT NULL DEFAULT 0,
    canonical_full TEXT NOT NULL DEFAULT '',
    raw_title TEXT NOT NULL DEFAULT '',
    parsed_title_core TEXT NOT NULL DEFAULT '',
    raw_chapter_num TEXT NOT NULL DEFAULT '',
    source_volume TEXT NOT NULL DEFAULT '',
    chapter_num INTEGER NOT NULL DEFAULT 0,
    chapter_title TEXT NOT NULL DEFAULT '',
    word_count INTEGER NOT NULL DEFAULT 0,
    raw_text_hash TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL DEFAULT '',
    quality_score REAL NOT NULL DEFAULT 0.0,
    summary TEXT NOT NULL DEFAULT '',
    key_events TEXT NOT NULL DEFAULT '[]',
    character_appearances TEXT NOT NULL DEFAULT '{}',
    location_appearances TEXT NOT NULL DEFAULT '{}',
    mood_tags TEXT NOT NULL DEFAULT '[]',
    arc_tag TEXT NOT NULL DEFAULT '',
    arc_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(book_id, canonical_full)
);
CREATE INDEX IF NOT EXISTS idx_chapters_book_canonical ON novel_chapters(book_id, canonical_type, canonical_num);

-- novel_chapter_mirrors: 章节镜像
CREATE TABLE IF NOT EXISTS novel_chapter_mirrors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    mirror_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    chapter_num INTEGER NOT NULL,
    fetch_status TEXT NOT NULL DEFAULT 'pending',
    word_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    fetch_error TEXT,
    fetched_at TIMESTAMP,
    response_time_ms INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (chapter_id) REFERENCES novel_chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (mirror_id) REFERENCES novel_source_mirrors(id) ON DELETE CASCADE,
    UNIQUE(chapter_id, mirror_id)
);

-- novel_entities: 实体
CREATE TABLE IF NOT EXISTS novel_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    entity_type TEXT NOT NULL DEFAULT 'character',
    description TEXT NOT NULL DEFAULT '',
    first_appearance_ch INTEGER NOT NULL DEFAULT 0,
    last_appearance_ch INTEGER NOT NULL DEFAULT 0,
    appearance_count INTEGER NOT NULL DEFAULT 0,
    importance_score INTEGER NOT NULL DEFAULT 3,
    attributes TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE(book_id, name)
);
CREATE INDEX IF NOT EXISTS idx_entities_book_type ON novel_entities(book_id, entity_type);

-- novel_relationships: 关系
CREATE TABLE IF NOT EXISTS novel_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'custom',
    description TEXT NOT NULL DEFAULT '',
    since_chapter INTEGER NOT NULL DEFAULT 0,
    until_chapter INTEGER,
    confidence REAL NOT NULL DEFAULT 0.8,
    evidence TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rels_source ON novel_relationships(book_id, source_entity);

-- novel_events: 事件
CREATE TABLE IF NOT EXISTS novel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    chapter_num INTEGER NOT NULL,
    event_type TEXT NOT NULL DEFAULT 'custom',
    description TEXT NOT NULL DEFAULT '',
    participants TEXT NOT NULL DEFAULT '[]',
    location TEXT NOT NULL DEFAULT '',
    importance INTEGER NOT NULL DEFAULT 3,
    related_entities TEXT NOT NULL DEFAULT '[]',
    evidence TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_events_book_ch ON novel_events(book_id, chapter_num);
CREATE INDEX IF NOT EXISTS idx_events_importance ON novel_events(book_id, importance DESC);

-- novel_state_changes: 状态变迁
CREATE TABLE IF NOT EXISTS novel_state_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    entity_name TEXT NOT NULL,
    chapter_id INTEGER NOT NULL,
    chapter_num INTEGER NOT NULL,
    field_name TEXT NOT NULL DEFAULT 'custom',
    before_value TEXT NOT NULL DEFAULT '',
    after_value TEXT NOT NULL DEFAULT '',
    trigger_event TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.8,
    evidence TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sc_book_entity ON novel_state_changes(book_id, entity_name);

-- evolution_feedbacks: 反馈记录
CREATE TABLE IF NOT EXISTS evolution_feedbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    feedback_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    original_value TEXT NOT NULL DEFAULT '',
    corrected_value TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    user_id INTEGER,
    confidence REAL NOT NULL DEFAULT 1.0,
    applied BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_feedback_book ON evolution_feedbacks(book_id, target_type);

-- evolution_rules: 进化规则
CREATE TABLE IF NOT EXISTS evolution_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL DEFAULT 0,
    rule_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    replacement TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT '{}',
    hit_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_from_feedback_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rules_book ON evolution_rules(book_id, rule_type, active);

-- prompt_templates: Prompt版本管理
CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    template_text TEXT NOT NULL,
    success_rate REAL NOT NULL DEFAULT 0.0,
    avg_token_usage INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(template_name, version)
);
