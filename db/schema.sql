-- ============================================================
-- Gaming Press Archive — SQLite Schema
-- ============================================================
-- Designed to be magazine-agnostic from day one.
-- Supports Japanese, English, and French magazines.
-- All text fields stored in their original language;
-- translated fields added in Phase 1 when AI runs.
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Magazines ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS magazines (
    id              TEXT PRIMARY KEY,          -- e.g. "famitsu", "edge", "joystick"
    name_original   TEXT NOT NULL,             -- Name in original language
    name_en         TEXT,
    name_fr         TEXT,
    country         TEXT,                      -- ISO 2-letter: JP, UK, US, FR
    language        TEXT NOT NULL,             -- ISO: ja, en, fr
    publisher       TEXT,
    started         TEXT,                      -- ISO date: YYYY-MM-DD
    ended           TEXT,                      -- NULL if still running
    review_format   TEXT,                      -- cross_4x10, percentage, scale_10...
    score_max       INTEGER,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ── Issues ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS issues (
    id              TEXT PRIMARY KEY,          -- e.g. "famitsu-001"
    magazine_id     TEXT NOT NULL REFERENCES magazines(id),
    issue_number    INTEGER NOT NULL,
    volume          INTEGER,
    release_date    TEXT,                      -- ISO date
    cover_subject   TEXT,                      -- What's on the cover
    page_count      INTEGER,
    pdf_path        TEXT,                      -- Original PDF location
    images_dir      TEXT,                      -- Extracted images folder
    ocr_dir         TEXT,                      -- OCR JSON folder
    phase0_done     INTEGER DEFAULT 0,         -- 1 = OCR complete
    phase1_done     INTEGER DEFAULT 0,         -- 1 = AI extraction complete
    indexed_at      TEXT DEFAULT (datetime('now')),
    notes           TEXT
);

-- ── Pages ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id        TEXT NOT NULL REFERENCES issues(id),
    page_number     INTEGER NOT NULL,
    image_path      TEXT,
    ocr_json_path   TEXT,
    ocr_full_text   TEXT,                      -- Concatenated OCR text
    ocr_block_count INTEGER,
    ocr_confidence  REAL,                      -- Average confidence 0.0–1.0
    page_type       TEXT,                      -- review/preview/interview/feature/ad/toc/other
    page_type_confidence REAL,                 -- AI confidence in classification
    is_ad           INTEGER DEFAULT 0,
    ocr_done        INTEGER DEFAULT 0,
    classified      INTEGER DEFAULT 0,
    extracted       INTEGER DEFAULT 0,
    UNIQUE(issue_id, page_number)
);

-- ── Games (canonical registry) ─────────────────────────────
-- Central table: every review, preview, mention links here.
-- Game titles normalized across magazines and languages.

CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title_original  TEXT NOT NULL,             -- Title as it appears in original magazine
    title_romaji    TEXT,                      -- Romanized (for Japanese games)
    title_en        TEXT,                      -- Official English title if known
    title_fr        TEXT,                      -- Official French title if known
    platform_id     TEXT,                      -- Primary platform (FK below)
    developer       TEXT,
    publisher_game  TEXT,
    release_date_jp TEXT,
    release_date_us TEXT,
    release_date_eu TEXT,
    genre           TEXT,
    wikidata_id     TEXT,                      -- For future linked data enrichment
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(title_original, platform_id)
);

-- ── Platforms ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS platforms (
    id              TEXT PRIMARY KEY,          -- canonical: "famicom", "snes", "mega_drive"
    name_ja         TEXT,
    name_en         TEXT NOT NULL,
    name_fr         TEXT,
    manufacturer    TEXT,
    released        TEXT,
    discontinued    TEXT
);

-- ── Reviews ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         INTEGER NOT NULL REFERENCES pages(id),
    issue_id        TEXT NOT NULL REFERENCES issues(id),
    game_id         INTEGER REFERENCES games(id),

    -- Raw extracted fields (original language)
    game_title_raw  TEXT NOT NULL,             -- Exactly as extracted by OCR
    platform_raw    TEXT,                      -- As written in magazine
    platform_id     TEXT REFERENCES platforms(id),

    -- Scores (flexible: not all magazines use all fields)
    score_1         REAL,
    score_2         REAL,
    score_3         REAL,
    score_4         REAL,
    score_total     REAL,
    score_max       REAL,
    reviewer_names  TEXT,                      -- JSON array: ["田尻智", "宮本茂"]

    -- Review text
    blurb_original  TEXT,                      -- Short review blurb as in magazine
    blurb_en        TEXT,                      -- AI translation (Phase 1)
    blurb_fr        TEXT,

    -- Metadata
    extraction_confidence REAL,               -- AI confidence in extraction
    extracted_at    TEXT DEFAULT (datetime('now'))
);

-- ── Articles (previews, interviews, features) ──────────────

CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         INTEGER NOT NULL REFERENCES pages(id),
    issue_id        TEXT NOT NULL REFERENCES issues(id),
    article_type    TEXT NOT NULL,             -- preview/interview/feature/column/letters/other

    title_original  TEXT,
    title_en        TEXT,
    title_fr        TEXT,

    -- For previews: game reference
    game_id         INTEGER REFERENCES games(id),
    game_title_raw  TEXT,
    platform_raw    TEXT,
    release_window  TEXT,                      -- "Winter 1986", "Q1 1990" etc.

    -- For interviews: who was interviewed
    interviewee     TEXT,
    interviewee_role TEXT,

    -- Body
    summary_original TEXT,                     -- AI-generated summary in original language
    summary_en      TEXT,
    summary_fr      TEXT,

    -- Mentions (denormalized for fast lookup — normalized in game_mentions)
    games_mentioned TEXT,                      -- JSON array of game title strings
    people_mentioned TEXT,                     -- JSON array of people names

    pages_span      TEXT,                      -- e.g. "12-15" (multi-page articles)
    extraction_confidence REAL,
    extracted_at    TEXT DEFAULT (datetime('now'))
);

-- ── Ads ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         INTEGER NOT NULL REFERENCES pages(id),
    issue_id        TEXT NOT NULL REFERENCES issues(id),

    brand           TEXT,
    product         TEXT,
    platforms       TEXT,                      -- JSON array
    tagline_original TEXT,
    tagline_en      TEXT,
    price           TEXT,                      -- As printed, e.g. "¥4,900"
    ad_type         TEXT,                      -- full_page/half_page/quarter/insert
    extraction_confidence REAL,
    extracted_at    TEXT DEFAULT (datetime('now'))
);

-- ── Game Mentions (cross-reference) ────────────────────────
-- Links every game mention across all content types

CREATE TABLE IF NOT EXISTS game_mentions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(id),
    issue_id        TEXT NOT NULL REFERENCES issues(id),
    page_id         INTEGER REFERENCES pages(id),
    mention_type    TEXT NOT NULL,             -- review/preview/interview/feature/ad/chart
    content_id      INTEGER,                   -- FK to reviews/articles/ads depending on type
    content_table   TEXT,                      -- "reviews" / "articles" / "ads"
    context_snippet TEXT                       -- Short quote showing mention context
);

-- ── Full-Text Search ───────────────────────────────────────
-- SQLite FTS5 for fast keyword search across all content

CREATE VIRTUAL TABLE IF NOT EXISTS fts_reviews USING fts5(
    game_title_raw,
    blurb_original,
    blurb_en,
    blurb_fr,
    reviewer_names,
    content=reviews,
    content_rowid=id,
    tokenize="unicode61"
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_articles USING fts5(
    title_original,
    title_en,
    summary_original,
    summary_en,
    games_mentioned,
    people_mentioned,
    content=articles,
    content_rowid=id,
    tokenize="unicode61"
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_pages USING fts5(
    ocr_full_text,
    content=pages,
    content_rowid=id,
    tokenize="unicode61"
);

-- ── Triggers to keep FTS in sync ───────────────────────────

CREATE TRIGGER IF NOT EXISTS reviews_ai AFTER INSERT ON reviews BEGIN
    INSERT INTO fts_reviews(rowid, game_title_raw, blurb_original, blurb_en, blurb_fr, reviewer_names)
    VALUES (new.id, new.game_title_raw, new.blurb_original, new.blurb_en, new.blurb_fr, new.reviewer_names);
END;

CREATE TRIGGER IF NOT EXISTS reviews_ad AFTER DELETE ON reviews BEGIN
    INSERT INTO fts_reviews(fts_reviews, rowid, game_title_raw, blurb_original, blurb_en, blurb_fr, reviewer_names)
    VALUES ('delete', old.id, old.game_title_raw, old.blurb_original, old.blurb_en, old.blurb_fr, old.reviewer_names);
END;

CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO fts_articles(rowid, title_original, title_en, summary_original, summary_en, games_mentioned, people_mentioned)
    VALUES (new.id, new.title_original, new.title_en, new.summary_original, new.summary_en, new.games_mentioned, new.people_mentioned);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO fts_articles(fts_articles, rowid, title_original, title_en, summary_original, summary_en, games_mentioned, people_mentioned)
    VALUES ('delete', old.id, old.title_original, old.title_en, old.summary_original, old.summary_en, old.games_mentioned, old.people_mentioned);
END;

-- ── Indexes ────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_reviews_issue     ON reviews(issue_id);
CREATE INDEX IF NOT EXISTS idx_reviews_game      ON reviews(game_id);
CREATE INDEX IF NOT EXISTS idx_reviews_platform  ON reviews(platform_id);
CREATE INDEX IF NOT EXISTS idx_articles_issue    ON articles(issue_id);
CREATE INDEX IF NOT EXISTS idx_articles_type     ON articles(article_type);
CREATE INDEX IF NOT EXISTS idx_articles_game     ON articles(game_id);
CREATE INDEX IF NOT EXISTS idx_pages_issue       ON pages(issue_id);
CREATE INDEX IF NOT EXISTS idx_pages_type        ON pages(page_type);
CREATE INDEX IF NOT EXISTS idx_issues_magazine   ON issues(magazine_id);
CREATE INDEX IF NOT EXISTS idx_issues_date       ON issues(release_date);
CREATE INDEX IF NOT EXISTS idx_game_mentions_game ON game_mentions(game_id);
CREATE INDEX IF NOT EXISTS idx_game_mentions_issue ON game_mentions(issue_id);
