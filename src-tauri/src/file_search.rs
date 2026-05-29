use rusqlite::types::Value;
use rusqlite::{params, params_from_iter, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};
use tauri_plugin_opener::OpenerExt;

pub struct FileSearchState {
    db_path: PathBuf,
    conn: Mutex<Connection>,
    status: Arc<Mutex<FileSearchIndexStatus>>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchSourceConfig {
    pub id: String,
    pub name: String,
    pub path: String,
    pub enabled: bool,
    pub frozen: Option<bool>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchQuery {
    pub query: Option<String>,
    pub keywords: Option<Vec<String>>,
    pub hard_terms: Option<Vec<String>>,
    pub soft_terms: Option<Vec<String>>,
    pub file_type: Option<String>,
    pub extension: Option<String>,
    pub folder: Option<String>,
    pub date_from: Option<String>,
    pub date_to: Option<String>,
    pub sort_by: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchResult {
    pub id: i64,
    pub file_path: String,
    pub file_name: String,
    pub parent_folder: String,
    pub file_extension: String,
    pub file_size: i64,
    pub file_modified: i64,
    pub file_type: String,
    pub indexed_at: i64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchQueryResponse {
    pub items: Vec<FileSearchResult>,
    pub total: i64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchFileDetail {
    pub id: i64,
    pub file_path: String,
    pub file_name: String,
    pub parent_folder: String,
    pub file_extension: String,
    pub file_size: i64,
    pub file_modified: i64,
    pub file_type: String,
    pub indexed_at: i64,
    pub exists: bool,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchPreview {
    pub id: i64,
    pub kind: String,
    pub file_path: String,
    pub asset_path: Option<String>,
    pub file_name: String,
    pub content: Option<String>,
    pub mime_type: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileSearchIndexStatus {
    pub phase: String,
    pub running: bool,
    pub current: i64,
    pub total: i64,
    pub percent: i64,
    pub message: String,
    pub started_at: Option<i64>,
    pub finished_at: Option<i64>,
    pub total_files: i64,
    pub last_error: Option<String>,
}

struct IndexedEntry {
    file_path: String,
    file_name: String,
    parent_folder: String,
    file_extension: String,
    file_size: i64,
    file_modified: i64,
    file_type: String,
}

#[derive(Debug, PartialEq, Eq)]
enum FilePathAccess {
    Available,
    Missing,
    Unreachable,
}

impl Default for FileSearchIndexStatus {
    fn default() -> Self {
        Self {
            phase: "idle".to_string(),
            running: false,
            current: 0,
            total: 0,
            percent: 0,
            message: String::new(),
            started_at: None,
            finished_at: None,
            total_files: 0,
            last_error: None,
        }
    }
}

impl FileSearchState {
    pub fn open(path: &Path) -> Result<Self, String> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create file search DB dir: {}", e))?;
        }
        let conn =
            Connection::open(path).map_err(|e| format!("Failed to open file search DB: {}", e))?;
        init_schema(&conn)?;
        let total_files = count_files(&conn).unwrap_or(0);
        Ok(Self {
            db_path: path.to_path_buf(),
            conn: Mutex::new(conn),
            status: Arc::new(Mutex::new(FileSearchIndexStatus {
                total_files,
                ..FileSearchIndexStatus::default()
            })),
        })
    }
}

fn get_state(app: &AppHandle) -> Result<&FileSearchState, String> {
    app.try_state::<FileSearchState>()
        .ok_or_else(|| "File search DB not initialized".to_string())
        .map(|s| s.inner())
}

#[tauri::command]
pub fn file_search_query(
    app: AppHandle,
    query: FileSearchQuery,
) -> Result<FileSearchQueryResponse, String> {
    let state = get_state(&app)?;
    let conn = state.conn.lock().map_err(|e| e.to_string())?;
    query_files(&conn, &query)
}

#[tauri::command]
pub fn file_search_get_file(app: AppHandle, id: i64) -> Result<FileSearchFileDetail, String> {
    let state = get_state(&app)?;
    let conn = state.conn.lock().map_err(|e| e.to_string())?;
    let item = get_file_by_id(&conn, id)?;
    Ok(FileSearchFileDetail {
        exists: Path::new(&item.file_path).exists(),
        id: item.id,
        file_path: item.file_path,
        file_name: item.file_name,
        parent_folder: item.parent_folder,
        file_extension: item.file_extension,
        file_size: item.file_size,
        file_modified: item.file_modified,
        file_type: item.file_type,
        indexed_at: item.indexed_at,
    })
}

#[tauri::command]
pub fn file_search_preview(app: AppHandle, id: i64) -> Result<FileSearchPreview, String> {
    let state = get_state(&app)?;
    let conn = state.conn.lock().map_err(|e| e.to_string())?;
    let item = get_file_by_id(&conn, id)?;
    let path = Path::new(&item.file_path);
    match file_path_access(path) {
        FilePathAccess::Available => {}
        FilePathAccess::Missing => return Ok(missing_preview(id, item)),
        FilePathAccess::Unreachable => return Ok(unreachable_preview(id, item)),
    }

    let kind = preview_kind(&item.file_type, &item.file_extension);
    let content = if kind == "text" {
        Some(read_text_preview(path)?)
    } else {
        None
    };
    let mime_type = mime_for(&item.file_extension).map(str::to_string);
    let asset_path = prepare_preview_asset_path(&app, &item, &kind, path);

    Ok(FileSearchPreview {
        id,
        kind,
        file_path: item.file_path,
        asset_path,
        file_name: item.file_name,
        content,
        mime_type,
    })
}

#[tauri::command]
pub fn file_search_open_file(app: AppHandle, id: i64) -> Result<(), String> {
    let state = get_state(&app)?;
    let conn = state.conn.lock().map_err(|e| e.to_string())?;
    let item = get_file_by_id(&conn, id)?;
    let path = Path::new(&item.file_path);
    match file_path_access(path) {
        FilePathAccess::Available => app
            .opener()
            .open_path(item.file_path, None::<&str>)
            .map_err(|e| e.to_string()),
        FilePathAccess::Missing => {
            if let Some(root) = network_share_root(&item.file_path) {
                return app
                    .opener()
                    .open_path(root, None::<&str>)
                    .map_err(|e| e.to_string());
            }
            Err("File is not reachable from this machine".to_string())
        }
        FilePathAccess::Unreachable => {
            let target = network_share_root(&item.file_path).unwrap_or(item.file_path);
            app.opener()
                .open_path(target, None::<&str>)
                .map_err(|e| e.to_string())
        }
    }
}

fn missing_preview(id: i64, item: FileSearchResult) -> FileSearchPreview {
    FileSearchPreview {
        id,
        kind: "missing".to_string(),
        file_path: item.file_path,
        asset_path: None,
        file_name: item.file_name,
        content: None,
        mime_type: None,
    }
}

fn unreachable_preview(id: i64, item: FileSearchResult) -> FileSearchPreview {
    FileSearchPreview {
        id,
        kind: "unreachable".to_string(),
        file_path: item.file_path,
        asset_path: None,
        file_name: item.file_name,
        content: None,
        mime_type: None,
    }
}

#[tauri::command]
pub fn file_search_start_index(
    app: AppHandle,
    sources: Vec<FileSearchSourceConfig>,
    full: Option<bool>,
) -> Result<FileSearchIndexStatus, String> {
    let state = get_state(&app)?;
    let enabled: Vec<FileSearchSourceConfig> = sources
        .into_iter()
        .filter(|source| source.enabled)
        .collect();
    if enabled.is_empty() {
        return Err("No enabled file search sources".to_string());
    }

    {
        let mut status = state.status.lock().map_err(|e| e.to_string())?;
        if status.running {
            return Ok(status.clone());
        }
        *status = FileSearchIndexStatus {
            phase: "scanning".to_string(),
            running: true,
            current: 0,
            total: 0,
            percent: 0,
            message: "Preparing index".to_string(),
            started_at: Some(now_secs()),
            finished_at: None,
            total_files: status.total_files,
            last_error: None,
        };
    }

    let db_path = state.db_path.clone();
    let status = Arc::clone(&state.status);
    let full_index = full.unwrap_or(true);
    std::thread::spawn(move || {
        if let Err(err) = run_index(db_path, enabled, full_index, Arc::clone(&status)) {
            if let Ok(mut s) = status.lock() {
                s.phase = "error".to_string();
                s.running = false;
                s.finished_at = Some(now_secs());
                s.last_error = Some(err.clone());
                s.message = err;
            }
        }
    });

    let status = state.status.lock().map_err(|e| e.to_string())?;
    Ok(status.clone())
}

#[tauri::command]
pub fn file_search_index_status(app: AppHandle) -> Result<FileSearchIndexStatus, String> {
    let state = get_state(&app)?;
    let status = state.status.lock().map_err(|e| e.to_string())?;
    Ok(status.clone())
}

#[tauri::command]
pub fn file_search_suggest(app: AppHandle, query: String) -> Result<Vec<String>, String> {
    let state = get_state(&app)?;
    let conn = state.conn.lock().map_err(|e| e.to_string())?;
    let like = format!("%{}%", escape_like(query.trim()));
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT file_name FROM files
             WHERE file_name LIKE ?1 ESCAPE '\\'
             ORDER BY file_modified DESC
             LIMIT 8",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map(params![like], |row| row.get::<_, String>(0))
        .map_err(|e| e.to_string())?;
    let mut suggestions = Vec::new();
    for row in rows {
        suggestions.push(row.map_err(|e| e.to_string())?);
    }
    Ok(suggestions)
}

#[tauri::command]
pub fn file_search_entity_candidates(app: AppHandle, query: String) -> Result<Vec<String>, String> {
    let state = get_state(&app)?;
    let conn = state.conn.lock().map_err(|e| e.to_string())?;
    query_entity_candidates(&conn, &query)
}

fn init_schema(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;

        CREATE TABLE IF NOT EXISTS files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path       TEXT NOT NULL UNIQUE,
            file_name       TEXT NOT NULL,
            parent_folder   TEXT NOT NULL DEFAULT '',
            file_extension  TEXT NOT NULL DEFAULT '',
            file_size       INTEGER NOT NULL DEFAULT 0,
            file_modified   INTEGER NOT NULL DEFAULT 0,
            file_type       TEXT NOT NULL DEFAULT 'other',
            indexed_at      INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type);
        CREATE INDEX IF NOT EXISTS idx_files_extension ON files(file_extension);
        CREATE INDEX IF NOT EXISTS idx_files_modified ON files(file_modified);

        CREATE TABLE IF NOT EXISTS file_search_entities (
            term        TEXT PRIMARY KEY,
            frequency   INTEGER NOT NULL DEFAULT 0,
            updated_at  INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_file_search_entities_frequency
            ON file_search_entities(frequency DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
            file_name,
            parent_folder,
            file_path,
            content='files',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, file_name, parent_folder, file_path)
            VALUES (new.id, new.file_name, new.parent_folder, new.file_path);
        END;
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, file_name, parent_folder, file_path)
            VALUES('delete', old.id, old.file_name, old.parent_folder, old.file_path);
        END;
        CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, file_name, parent_folder, file_path)
            VALUES('delete', old.id, old.file_name, old.parent_folder, old.file_path);
            INSERT INTO files_fts(rowid, file_name, parent_folder, file_path)
            VALUES (new.id, new.file_name, new.parent_folder, new.file_path);
        END;
        ",
    )
    .map_err(|e| format!("Failed to init file search schema: {}", e))?;
    conn.execute("INSERT INTO files_fts(files_fts) VALUES('rebuild')", [])
        .map_err(|e| format!("Failed to rebuild file search FTS: {}", e))?;
    Ok(())
}

fn query_files(
    conn: &Connection,
    query: &FileSearchQuery,
) -> Result<FileSearchQueryResponse, String> {
    let hard_terms = hard_search_terms(query);
    let soft_terms = soft_search_terms(query);
    let relevance_terms = relevance_terms(&hard_terms, &soft_terms);
    let (where_sql, params) = build_filters(query, &hard_terms);
    let total_sql = format!("SELECT COUNT(*) FROM files {}", where_sql);
    let total: i64 = conn
        .query_row(&total_sql, params_from_iter(params.iter()), |row| {
            row.get(0)
        })
        .map_err(|e| e.to_string())?;

    let limit = query.limit.unwrap_or(50).clamp(1, 200);
    let offset = query.offset.unwrap_or(0).max(0);
    let relevance_order = !relevance_terms.is_empty()
        && matches!(
            query.sort_by.as_deref().unwrap_or("modified_desc"),
            "modified_desc"
        );
    let order_sql = if relevance_order {
        "ORDER BY file_modified DESC, file_name ASC"
    } else {
        match query.sort_by.as_deref().unwrap_or("modified_desc") {
            "modified_asc" => "ORDER BY file_modified ASC, file_name ASC",
            "name_asc" => "ORDER BY file_name COLLATE NOCASE ASC",
            "size_desc" => "ORDER BY file_size DESC, file_modified DESC",
            _ => "ORDER BY file_modified DESC, file_name ASC",
        }
    };
    let sql = format!(
        "SELECT id, file_path, file_name, parent_folder, file_extension, file_size, file_modified, file_type, indexed_at
         FROM files {} {} LIMIT ? OFFSET ?",
        where_sql, order_sql
    );
    let mut data_params = params.clone();
    let fetch_limit = if relevance_order {
        (offset + limit).max(limit).clamp(1, 5000)
    } else {
        limit
    };
    let fetch_offset = if relevance_order { 0 } else { offset };
    data_params.push(Value::Integer(fetch_limit));
    data_params.push(Value::Integer(fetch_offset));
    let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map(params_from_iter(data_params.iter()), map_file_row)
        .map_err(|e| e.to_string())?;
    let mut items = Vec::new();
    for row in rows {
        items.push(row.map_err(|e| e.to_string())?);
    }
    if relevance_order {
        let date_range = date_range_secs(query);
        items.sort_by(|a, b| {
            let score_b = relevance_score(b, &hard_terms, &soft_terms, date_range);
            let score_a = relevance_score(a, &hard_terms, &soft_terms, date_range);
            score_b
                .cmp(&score_a)
                .then_with(|| b.file_modified.cmp(&a.file_modified))
                .then_with(|| a.file_name.to_lowercase().cmp(&b.file_name.to_lowercase()))
        });
        items = items
            .into_iter()
            .skip(offset as usize)
            .take(limit as usize)
            .collect();
    }
    Ok(FileSearchQueryResponse { items, total })
}

fn build_filters(query: &FileSearchQuery, terms: &[String]) -> (String, Vec<Value>) {
    let mut clauses: Vec<String> = Vec::new();
    let mut values: Vec<Value> = Vec::new();

    for text in terms {
        let like = format!("%{}%", escape_like(text));
        if let Some(fts) = build_fts_query(text) {
            clauses.push(
                "(id IN (SELECT rowid FROM files_fts WHERE files_fts MATCH ?)
                  OR file_name LIKE ? ESCAPE '\\'
                  OR parent_folder LIKE ? ESCAPE '\\'
                  OR file_path LIKE ? ESCAPE '\\')"
                    .to_string(),
            );
            values.push(Value::Text(fts));
            values.push(Value::Text(like.clone()));
            values.push(Value::Text(like.clone()));
            values.push(Value::Text(like));
        } else {
            clauses.push(
                "(file_name LIKE ? ESCAPE '\\'
                  OR parent_folder LIKE ? ESCAPE '\\'
                  OR file_path LIKE ? ESCAPE '\\')"
                    .to_string(),
            );
            values.push(Value::Text(like.clone()));
            values.push(Value::Text(like.clone()));
            values.push(Value::Text(like));
        }
    }

    if let Some(file_type) = query.file_type.as_deref() {
        if !file_type.is_empty() && file_type != "all" {
            clauses.push("file_type = ?".to_string());
            values.push(Value::Text(file_type.to_string()));
        }
    }

    if let Some(extension) = query
        .extension
        .as_deref()
        .map(clean_extension)
        .filter(|s| !s.is_empty())
    {
        clauses.push("file_extension = ?".to_string());
        values.push(Value::Text(extension));
    }

    if let Some(folder) = query
        .folder
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        let like = format!("%{}%", escape_like(folder));
        clauses
            .push("(parent_folder LIKE ? ESCAPE '\\' OR file_path LIKE ? ESCAPE '\\')".to_string());
        values.push(Value::Text(like.clone()));
        values.push(Value::Text(like));
    }

    if let Some(from) = query.date_from.as_deref().and_then(date_start_secs) {
        clauses.push("file_modified >= ?".to_string());
        values.push(Value::Integer(from));
    }

    if let Some(to) = query.date_to.as_deref().and_then(date_start_secs) {
        clauses.push("file_modified < ?".to_string());
        values.push(Value::Integer(to + 86_400));
    }

    if clauses.is_empty() {
        (String::new(), values)
    } else {
        (format!("WHERE {}", clauses.join(" AND ")), values)
    }
}

fn hard_search_terms(query: &FileSearchQuery) -> Vec<String> {
    let mut terms = Vec::new();
    if let Some(hard_terms) = query.hard_terms.as_ref() {
        for keyword in hard_terms {
            let term = keyword.trim();
            if !term.is_empty()
                && !terms
                    .iter()
                    .any(|item: &String| item.eq_ignore_ascii_case(term))
            {
                terms.push(term.to_string());
            }
        }
    }
    if terms.is_empty() {
        if let Some(keywords) = query.keywords.as_ref() {
            for keyword in keywords {
                let term = keyword.trim();
                if !term.is_empty()
                    && !terms
                        .iter()
                        .any(|item: &String| item.eq_ignore_ascii_case(term))
                {
                    terms.push(term.to_string());
                }
            }
        }
    }
    if terms.is_empty() {
        if let Some(text) = query
            .query
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
        {
            terms.push(text.to_string());
        }
    }
    terms
}

fn soft_search_terms(query: &FileSearchQuery) -> Vec<String> {
    let mut terms = Vec::new();
    if let Some(soft_terms) = query.soft_terms.as_ref() {
        for keyword in soft_terms {
            let term = keyword.trim();
            if !term.is_empty()
                && !terms
                    .iter()
                    .any(|item: &String| item.eq_ignore_ascii_case(term))
            {
                terms.push(term.to_string());
            }
        }
    }
    terms
}

fn relevance_terms(hard_terms: &[String], soft_terms: &[String]) -> Vec<String> {
    let mut terms = hard_terms.to_vec();
    for term in soft_terms {
        if !terms.iter().any(|item| item.eq_ignore_ascii_case(term)) {
            terms.push(term.clone());
        }
    }
    terms
}

fn relevance_score(
    item: &FileSearchResult,
    hard_terms: &[String],
    soft_terms: &[String],
    date_range: Option<(i64, i64)>,
) -> i64 {
    let file_name = item.file_name.to_lowercase();
    let parent_folder = item.parent_folder.to_lowercase();
    let file_path = item.file_path.to_lowercase();
    let mut score = 0;
    let mut file_name_hits = 0;

    for term in hard_terms {
        let term = term.to_lowercase();
        if file_name.contains(&term) {
            score += 150;
            file_name_hits += 1;
            if file_name.starts_with(&term) {
                score += 60;
            }
            if file_name.contains(&format!("-{}", term))
                || file_name.contains(&format!("_{}", term))
            {
                score += 40;
            }
        } else if parent_folder.contains(&term) {
            score += 50;
        } else if file_path.contains(&term) {
            score += 20;
        }
    }

    for term in soft_terms {
        let term = term.to_lowercase();
        if file_name.contains(&term) {
            score += 40;
        } else if parent_folder.contains(&term) {
            score += 15;
        } else if file_path.contains(&term) {
            score += 5;
        }
    }

    if hard_terms.len() > 1 && file_name_hits == hard_terms.len() {
        score += 2_000;
    }

    if let Some((from, to_exclusive)) = date_range {
        if item.file_modified >= from && item.file_modified < to_exclusive {
            score += 100;
        }
    }

    score
}

fn date_range_secs(query: &FileSearchQuery) -> Option<(i64, i64)> {
    let from = query.date_from.as_deref().and_then(date_start_secs);
    let to = query.date_to.as_deref().and_then(date_start_secs);
    match (from, to) {
        (Some(start), Some(end)) => Some((start, end + 86_400)),
        (Some(start), None) => Some((start, i64::MAX)),
        (None, Some(end)) => Some((0, end + 86_400)),
        (None, None) => None,
    }
}

fn get_file_by_id(conn: &Connection, id: i64) -> Result<FileSearchResult, String> {
    conn.query_row(
        "SELECT id, file_path, file_name, parent_folder, file_extension, file_size, file_modified, file_type, indexed_at
         FROM files WHERE id = ?1",
        params![id],
        map_file_row,
    )
    .optional()
    .map_err(|e| e.to_string())?
    .ok_or_else(|| format!("File not found: {}", id))
}

fn map_file_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<FileSearchResult> {
    Ok(FileSearchResult {
        id: row.get(0)?,
        file_path: row.get(1)?,
        file_name: row.get(2)?,
        parent_folder: row.get(3)?,
        file_extension: row.get(4)?,
        file_size: row.get(5)?,
        file_modified: row.get(6)?,
        file_type: row.get(7)?,
        indexed_at: row.get(8)?,
    })
}

fn run_index(
    db_path: PathBuf,
    sources: Vec<FileSearchSourceConfig>,
    full: bool,
    status: Arc<Mutex<FileSearchIndexStatus>>,
) -> Result<(), String> {
    let mut conn = Connection::open(&db_path).map_err(|e| e.to_string())?;
    init_schema(&conn)?;
    if full {
        conn.execute("DELETE FROM files", [])
            .map_err(|e| format!("Failed to clear old file index: {}", e))?;
    }

    let mut all_entries = Vec::new();
    let mut errors = Vec::new();
    let active_sources: Vec<&FileSearchSourceConfig> = sources
        .iter()
        .filter(|source| full || !source.frozen.unwrap_or(false))
        .collect();
    let source_count = active_sources.len().max(1);
    for (index, source) in active_sources.iter().enumerate() {
        update_status(&status, |s| {
            s.phase = "scanning".to_string();
            s.percent = ((index as i64 * 35) / source_count as i64).clamp(0, 35);
            s.message = format!("Scanning {} ({})", source.name, source.id);
        });
        match scan_source(source, &status) {
            Ok(mut entries) => all_entries.append(&mut entries),
            Err(err) => errors.push(format!("{}: {}", source.name, err)),
        }
    }

    update_status(&status, |s| {
        s.phase = "indexing".to_string();
        s.current = 0;
        s.total = all_entries.len() as i64;
        s.percent = 40;
        s.message = format!("Indexing {} files", all_entries.len());
    });

    let indexed_at = now_secs();
    let tx = conn.transaction().map_err(|e| e.to_string())?;
    for (i, entry) in all_entries.iter().enumerate() {
        tx.execute(
            "INSERT INTO files
             (file_path, file_name, parent_folder, file_extension, file_size, file_modified, file_type, indexed_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
             ON CONFLICT(file_path) DO UPDATE SET
                file_name = excluded.file_name,
                parent_folder = excluded.parent_folder,
                file_extension = excluded.file_extension,
                file_size = excluded.file_size,
                file_modified = excluded.file_modified,
                file_type = excluded.file_type,
                indexed_at = excluded.indexed_at",
            params![
                entry.file_path,
                entry.file_name,
                entry.parent_folder,
                entry.file_extension,
                entry.file_size,
                entry.file_modified,
                entry.file_type,
                indexed_at,
            ],
        )
        .map_err(|e| e.to_string())?;

        if i % 100 == 0 || i + 1 == all_entries.len() {
            let current = (i + 1) as i64;
            let total = all_entries.len().max(1) as i64;
            update_status(&status, |s| {
                s.current = current;
                s.total = all_entries.len() as i64;
                s.percent = 40 + ((current * 55) / total);
                s.message = format!("Indexed {}/{}", current, all_entries.len());
            });
        }
    }
    tx.commit().map_err(|e| e.to_string())?;
    rebuild_entities_from_files(&conn, indexed_at)?;
    conn.execute("INSERT INTO files_fts(files_fts) VALUES('optimize')", [])
        .map_err(|e| e.to_string())?;
    let total_files = count_files(&conn)?;

    update_status(&status, |s| {
        s.phase = if errors.is_empty() { "done" } else { "error" }.to_string();
        s.running = false;
        s.current = all_entries.len() as i64;
        s.total = all_entries.len() as i64;
        s.percent = 100;
        s.message = if errors.is_empty() {
            format!("Indexed {} files", all_entries.len())
        } else {
            errors.join("; ")
        };
        s.finished_at = Some(now_secs());
        s.total_files = total_files;
        s.last_error = if errors.is_empty() {
            None
        } else {
            Some(errors.join("; "))
        };
    });

    Ok(())
}

fn scan_source(
    source: &FileSearchSourceConfig,
    status: &Arc<Mutex<FileSearchIndexStatus>>,
) -> Result<Vec<IndexedEntry>, String> {
    let root = PathBuf::from(&source.path);
    if !root.exists() {
        return Err("path is not reachable".to_string());
    }
    let mut entries = Vec::new();
    scan_directory(&root, &mut entries, status)?;
    Ok(entries)
}

fn scan_directory(
    dir: &Path,
    entries: &mut Vec<IndexedEntry>,
    status: &Arc<Mutex<FileSearchIndexStatus>>,
) -> Result<(), String> {
    let read_dir =
        fs::read_dir(dir).map_err(|e| format!("read_dir({}) failed: {}", dir.display(), e))?;
    for entry in read_dir.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') {
            continue;
        }
        let file_type = match entry.file_type() {
            Ok(value) => value,
            Err(_) => continue,
        };
        let path = entry.path();
        if file_type.is_dir() {
            if let Some(folder) = entry_from_path(&path, true) {
                entries.push(folder);
            }
            if entries.len() % 200 == 0 {
                update_status(status, |s| {
                    s.current = entries.len() as i64;
                    s.message = format!("Scanning {}", path.display());
                });
            }
            let _ = scan_directory(&path, entries, status);
        } else if file_type.is_file() {
            let extension = clean_extension(
                path.extension()
                    .and_then(|v| v.to_str())
                    .unwrap_or_default(),
            );
            if supported_extension(&extension) {
                if let Some(file) = entry_from_path(&path, false) {
                    entries.push(file);
                }
            }
        }
    }
    Ok(())
}

fn entry_from_path(path: &Path, is_dir: bool) -> Option<IndexedEntry> {
    let metadata = fs::metadata(path).ok()?;
    let file_path = path.to_string_lossy().to_string();
    let file_name = path.file_name()?.to_string_lossy().to_string();
    let extension = if is_dir {
        String::new()
    } else {
        clean_extension(
            path.extension()
                .and_then(|v| v.to_str())
                .unwrap_or_default(),
        )
    };
    Some(IndexedEntry {
        parent_folder: parent_folder_label(path),
        file_type: if is_dir {
            "folder".to_string()
        } else {
            file_type_for_extension(&extension).to_string()
        },
        file_path,
        file_name,
        file_extension: extension,
        file_size: if is_dir { 0 } else { metadata.len() as i64 },
        file_modified: system_time_secs(metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH)),
    })
}

fn parent_folder_label(path: &Path) -> String {
    let parent = match path.parent() {
        Some(value) => value.to_string_lossy().replace('/', "\\"),
        None => return String::new(),
    };
    let parts: Vec<&str> = parent.split('\\').filter(|part| !part.is_empty()).collect();
    if parts.len() >= 3 && (parent.starts_with("\\\\") || parent.starts_with("//")) {
        return parts[2..].join(",");
    }
    if parts.len() >= 2 && parts[0].ends_with(':') {
        return parts[1..].join(",");
    }
    parts.join(",")
}

fn rebuild_entities_from_files(conn: &Connection, indexed_at: i64) -> Result<(), String> {
    let mut stmt = conn
        .prepare(
            "SELECT file_path, file_name, parent_folder, file_extension, file_size, file_modified, file_type
             FROM files",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map([], |row| {
            Ok(IndexedEntry {
                file_path: row.get(0)?,
                file_name: row.get(1)?,
                parent_folder: row.get(2)?,
                file_extension: row.get(3)?,
                file_size: row.get(4)?,
                file_modified: row.get(5)?,
                file_type: row.get(6)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut counts: HashMap<String, i64> = HashMap::new();
    for row in rows {
        let entry = row.map_err(|e| e.to_string())?;
        for entity in extract_entities_from_entry(&entry) {
            *counts.entry(entity).or_insert(0) += 1;
        }
    }

    conn.execute("DELETE FROM file_search_entities", [])
        .map_err(|e| e.to_string())?;
    let mut insert_stmt = conn
        .prepare(
            "INSERT INTO file_search_entities (term, frequency, updated_at)
             VALUES (?1, ?2, ?3)",
        )
        .map_err(|e| e.to_string())?;
    for (term, frequency) in counts {
        insert_stmt
            .execute(params![term, frequency, indexed_at])
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn query_entity_candidates(conn: &Connection, query: &str) -> Result<Vec<String>, String> {
    let mut lookup_terms = extract_entities_from_text(query);
    let normalized_query = query.trim();
    if !normalized_query.is_empty()
        && !lookup_terms
            .iter()
            .any(|term| term.eq_ignore_ascii_case(normalized_query))
    {
        lookup_terms.push(normalized_query.to_string());
    }
    if lookup_terms.is_empty() {
        return Ok(Vec::new());
    }

    let mut candidates = Vec::new();
    for term in &lookup_terms {
        push_entity_candidates(conn, term, &mut candidates)?;
    }

    if candidates.is_empty() {
        for term in &lookup_terms {
            if has_index_match(conn, term)? {
                candidates.push(term.to_string());
            }
        }
    }

    candidates.sort_by_key(|value| value.to_lowercase());
    candidates.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
    Ok(candidates.into_iter().take(20).collect())
}

fn push_entity_candidates(
    conn: &Connection,
    query: &str,
    candidates: &mut Vec<String>,
) -> Result<(), String> {
    let like = format!("%{}%", escape_like(query));
    let mut stmt = conn
        .prepare(
            "SELECT term FROM file_search_entities
             WHERE term = ?1 OR term LIKE ?2 ESCAPE '\\' OR ?1 LIKE '%' || term || '%'
             ORDER BY
                CASE
                    WHEN term = ?1 THEN 0
                    WHEN ?1 LIKE '%' || term || '%' THEN 1
                    ELSE 2
                END,
                frequency DESC,
                length(term) DESC
             LIMIT 20",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map(params![query, like], |row| row.get::<_, String>(0))
        .map_err(|e| e.to_string())?;
    for row in rows {
        let term = row.map_err(|e| e.to_string())?;
        if !candidates
            .iter()
            .any(|item| item.eq_ignore_ascii_case(&term))
        {
            candidates.push(term);
        }
    }
    Ok(())
}

fn has_index_match(conn: &Connection, query: &str) -> Result<bool, String> {
    if query.trim().is_empty() {
        return Ok(false);
    }
    let like = format!("%{}%", escape_like(query));
    let count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM files
             WHERE file_name LIKE ?1 ESCAPE '\\'
                OR parent_folder LIKE ?1 ESCAPE '\\'
                OR file_path LIKE ?1 ESCAPE '\\'
             LIMIT 1",
            params![like],
            |row| row.get(0),
        )
        .map_err(|e| e.to_string())?;
    Ok(count > 0)
}

fn extract_entities_from_entry(entry: &IndexedEntry) -> Vec<String> {
    let mut set = HashSet::new();
    for value in [&entry.file_name, &entry.parent_folder, &entry.file_path] {
        for entity in extract_entities_from_text(value) {
            set.insert(entity);
        }
    }
    let mut entities: Vec<String> = set.into_iter().collect();
    entities.sort_by_key(|value| value.to_lowercase());
    entities
}

fn extract_entities_from_text(value: &str) -> Vec<String> {
    value
        .split(entity_separator)
        .filter_map(normalize_entity_token)
        .collect()
}

fn entity_separator(ch: char) -> bool {
    matches!(
        ch,
        '\\' | '/'
            | ','
            | '，'
            | '、'
            | '-'
            | '_'
            | ' '
            | '\t'
            | '.'
            | '+'
            | '('
            | ')'
            | '（'
            | '）'
            | '['
            | ']'
            | '【'
            | '】'
            | '@'
            | '#'
            | '&'
    )
}

fn normalize_entity_token(token: &str) -> Option<String> {
    let mut value = token
        .trim()
        .trim_matches(|ch: char| !ch.is_alphanumeric())
        .to_string();
    while value.chars().last().is_some_and(|ch| ch.is_ascii_digit())
        && value.chars().any(|ch| !ch.is_ascii_digit())
    {
        value.pop();
    }
    let char_count = value.chars().count();
    if !(2..=32).contains(&char_count) {
        return None;
    }
    if is_noise_entity(&value) || is_date_or_number_token(&value) {
        return None;
    }
    Some(value)
}

fn is_noise_entity(value: &str) -> bool {
    const NOISE: &[&str] = &[
        "文件",
        "资料",
        "素材",
        "图片",
        "照片",
        "视频",
        "音频",
        "文档",
        "目录",
        "文件夹",
        "搜索",
        "查找",
        "寻找",
        "这个",
        "那个",
        "最近",
        "最新",
        "修改",
        "拍摄",
        "拍的",
        "拍",
        "剪辑",
        "剪的",
        "剪",
        "制作",
        "做的",
        "做",
        "的",
        "了",
        "未使用",
    ];
    NOISE.iter().any(|word| value.eq_ignore_ascii_case(word))
}

fn is_date_or_number_token(value: &str) -> bool {
    if value.chars().all(|ch| ch.is_ascii_digit() || ch == '.') {
        return true;
    }
    if value
        .chars()
        .all(|ch| ch.is_ascii_digit() || matches!(ch, '年' | '月' | '日' | '-' | '.'))
    {
        return true;
    }
    let chinese_date_chars = "一二三四五六七八九十零〇年月日号";
    value.chars().all(|ch| chinese_date_chars.contains(ch))
}

fn count_files(conn: &Connection) -> Result<i64, String> {
    conn.query_row("SELECT COUNT(*) FROM files", [], |row| row.get(0))
        .map_err(|e| e.to_string())
}

fn update_status(
    status: &Arc<Mutex<FileSearchIndexStatus>>,
    update: impl FnOnce(&mut FileSearchIndexStatus),
) {
    if let Ok(mut s) = status.lock() {
        update(&mut s);
    }
}

fn supported_extension(extension: &str) -> bool {
    if extension.is_empty() {
        return false;
    }
    matches!(
        extension,
        "pdf"
            | "doc"
            | "docx"
            | "xls"
            | "xlsx"
            | "ppt"
            | "pptx"
            | "txt"
            | "rtf"
            | "csv"
            | "jpg"
            | "jpeg"
            | "png"
            | "gif"
            | "bmp"
            | "webp"
            | "svg"
            | "ico"
            | "mp4"
            | "avi"
            | "mov"
            | "wmv"
            | "flv"
            | "mkv"
            | "webm"
            | "mp3"
            | "wav"
            | "flac"
            | "aac"
            | "ogg"
            | "wma"
            | "zip"
            | "rar"
            | "7z"
            | "tar"
            | "gz"
    )
}

fn file_type_for_extension(extension: &str) -> &'static str {
    match extension {
        "pdf" | "doc" | "docx" | "xls" | "xlsx" | "ppt" | "pptx" | "txt" | "rtf" | "csv" => {
            "document"
        }
        "jpg" | "jpeg" | "png" | "gif" | "bmp" | "webp" | "svg" | "ico" => "image",
        "mp4" | "avi" | "mov" | "wmv" | "flv" | "mkv" | "webm" => "video",
        "mp3" | "wav" | "flac" | "aac" | "ogg" | "wma" => "audio",
        "zip" | "rar" | "7z" | "tar" | "gz" => "archive",
        _ => "other",
    }
}

fn preview_kind(file_type: &str, extension: &str) -> String {
    if matches!(extension, "txt" | "csv" | "rtf") {
        "text".to_string()
    } else if extension == "pdf" {
        "pdf".to_string()
    } else if matches!(file_type, "image" | "video" | "audio") {
        file_type.to_string()
    } else {
        "external".to_string()
    }
}

fn prepare_preview_asset_path(
    app: &AppHandle,
    item: &FileSearchResult,
    kind: &str,
    source_path: &Path,
) -> Option<String> {
    if !should_cache_preview_asset(&item.file_path, kind, item.file_size) {
        return None;
    }
    let cache_dir = app.path().app_cache_dir().ok()?.join("file-search-preview");
    fs::create_dir_all(&cache_dir).ok()?;
    let cache_path = cache_dir.join(preview_cache_file_name(item));
    if !cache_path.exists()
        || fs::metadata(&cache_path).map(|m| m.len() as i64).ok() != Some(item.file_size)
    {
        fs::copy(source_path, &cache_path).ok()?;
    }
    Some(cache_path.to_string_lossy().to_string())
}

fn should_cache_preview_asset(file_path: &str, kind: &str, file_size: i64) -> bool {
    const MAX_CACHED_PREVIEW_BYTES: i64 = 512 * 1024 * 1024;
    matches!(kind, "image" | "video" | "audio" | "pdf")
        && file_size > 0
        && file_size <= MAX_CACHED_PREVIEW_BYTES
        && is_network_path(file_path)
}

fn file_path_access(path: &Path) -> FilePathAccess {
    classify_path_access(path.try_exists())
}

fn classify_path_access(result: io::Result<bool>) -> FilePathAccess {
    match result {
        Ok(true) => FilePathAccess::Available,
        Ok(false) => FilePathAccess::Missing,
        Err(_) => FilePathAccess::Unreachable,
    }
}

fn is_network_path(file_path: &str) -> bool {
    file_path.starts_with("\\\\") || file_path.starts_with("//")
}

fn network_share_root(file_path: &str) -> Option<String> {
    if let Some(rest) = file_path.strip_prefix("\\\\") {
        let mut parts = rest.split('\\');
        let server = parts.next()?.trim();
        let share = parts.next()?.trim();
        if server.is_empty() || share.is_empty() {
            return None;
        }
        return Some(format!("\\\\{}\\{}", server, share));
    }

    if let Some(rest) = file_path.strip_prefix("//") {
        let mut parts = rest.split('/');
        let server = parts.next()?.trim();
        let share = parts.next()?.trim();
        if server.is_empty() || share.is_empty() {
            return None;
        }
        return Some(format!("//{}/{}", server, share));
    }

    None
}

fn preview_cache_file_name(item: &FileSearchResult) -> String {
    let extension = if item.file_extension.is_empty() {
        "bin"
    } else {
        item.file_extension.as_str()
    };
    format!(
        "{}-{}-{}.{}",
        item.id,
        item.file_modified.max(0),
        item.file_size.max(0),
        extension
    )
}

fn mime_for(extension: &str) -> Option<&'static str> {
    match extension {
        "pdf" => Some("application/pdf"),
        "jpg" | "jpeg" => Some("image/jpeg"),
        "png" => Some("image/png"),
        "gif" => Some("image/gif"),
        "webp" => Some("image/webp"),
        "svg" => Some("image/svg+xml"),
        "mp4" => Some("video/mp4"),
        "webm" => Some("video/webm"),
        "mp3" => Some("audio/mpeg"),
        "wav" => Some("audio/wav"),
        _ => None,
    }
}

fn read_text_preview(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    let end = bytes.len().min(64 * 1024);
    Ok(String::from_utf8_lossy(&bytes[..end]).to_string())
}

fn date_start_secs(value: &str) -> Option<i64> {
    let mut parts = value.split('-');
    let year = parts.next()?.parse::<i64>().ok()?;
    let month = parts.next()?.parse::<i64>().ok()?;
    let day = parts.next()?.parse::<i64>().ok()?;
    if parts.next().is_some() || !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return None;
    }
    Some(days_from_civil(year, month, day) * 86_400)
}

fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = year - if month <= 2 { 1 } else { 0 };
    let era = if year >= 0 { year } else { year - 399 } / 400;
    let year_of_era = year - era * 400;
    let adjusted_month = month + if month > 2 { -3 } else { 9 };
    let day_of_year = (153 * adjusted_month + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

fn clean_extension(extension: &str) -> String {
    extension
        .trim()
        .trim_start_matches('.')
        .to_ascii_lowercase()
}

fn escape_like(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('%', "\\%")
        .replace('_', "\\_")
}

fn build_fts_query(value: &str) -> Option<String> {
    let cleaned: String = value
        .chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ch == '_' {
                ch
            } else {
                ' '
            }
        })
        .collect();
    let tokens: Vec<String> = cleaned
        .split_whitespace()
        .take(8)
        .map(|token| format!("\"{}\"", token.replace('"', "\"\"")))
        .collect();
    if tokens.is_empty() {
        None
    } else {
        Some(tokens.join(" "))
    }
}

fn now_secs() -> i64 {
    system_time_secs(SystemTime::now())
}

fn system_time_secs(time: SystemTime) -> i64 {
    time.duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::{
        build_fts_query, classify_path_access, clean_extension, extract_entities_from_entry,
        file_type_for_extension, init_schema, network_share_root, parent_folder_label,
        preview_cache_file_name, query_entity_candidates, query_files, should_cache_preview_asset,
        FilePathAccess, FileSearchQuery, FileSearchResult, IndexedEntry,
    };
    use rusqlite::{params, Connection};
    use std::{io, path::Path};

    #[test]
    fn classifies_supported_file_types() {
        assert_eq!(file_type_for_extension("pdf"), "document");
        assert_eq!(file_type_for_extension("png"), "image");
        assert_eq!(file_type_for_extension("mp4"), "video");
        assert_eq!(file_type_for_extension("zip"), "archive");
    }

    #[test]
    fn cleans_extension_without_dot() {
        assert_eq!(clean_extension(".PDF"), "pdf");
    }

    #[test]
    fn builds_safe_fts_query() {
        assert_eq!(
            build_fts_query("合同 pdf").as_deref(),
            Some("\"合同\" \"pdf\"")
        );
    }

    #[test]
    fn labels_windows_parent_folders() {
        let label = parent_folder_label(Path::new(r"C:\Share\Brand\file.pdf"));
        assert!(label.contains("Share"));
    }

    #[test]
    fn caches_preview_assets_for_network_media_paths() {
        assert!(should_cache_preview_asset(
            r"\\192.168.0.118\share\video.mp4",
            "video",
            10
        ));
        assert!(should_cache_preview_asset(
            "//192.168.0.118/share/file.pdf",
            "pdf",
            10
        ));
        assert!(!should_cache_preview_asset(
            r"C:\Share\video.mp4",
            "video",
            10
        ));
        assert!(!should_cache_preview_asset(
            r"\\192.168.0.118\share\video.mp4",
            "external",
            10
        ));
    }

    #[test]
    fn classifies_permission_errors_as_unreachable() {
        assert_eq!(classify_path_access(Ok(true)), FilePathAccess::Available);
        assert_eq!(classify_path_access(Ok(false)), FilePathAccess::Missing);
        assert_eq!(
            classify_path_access(Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "denied"
            ))),
            FilePathAccess::Unreachable
        );
    }

    #[test]
    fn extracts_network_share_roots() {
        assert_eq!(
            network_share_root(r"\\192.168.0.118\法采共享盘2026\folder\video.mp4").as_deref(),
            Some(r"\\192.168.0.118\法采共享盘2026")
        );
        assert_eq!(
            network_share_root("//192.168.0.118/share/folder/video.mp4").as_deref(),
            Some("//192.168.0.118/share")
        );
        assert_eq!(network_share_root(r"C:\Share\video.mp4"), None);
    }

    #[test]
    fn builds_stable_preview_cache_file_names() {
        let item = FileSearchResult {
            id: 42,
            file_path: r"\\192.168.0.118\share\video.mp4".to_string(),
            file_name: "video.mp4".to_string(),
            parent_folder: "share".to_string(),
            file_extension: "mp4".to_string(),
            file_size: 1024,
            file_modified: 1_779_780_000,
            file_type: "video".to_string(),
            indexed_at: 1_779_800_000,
        };

        assert_eq!(preview_cache_file_name(&item), "42-1779780000-1024.mp4");
    }

    #[test]
    fn query_requires_all_ai_keywords() {
        let conn = seeded_conn();
        let result = query_files(
            &conn,
            &FileSearchQuery {
                query: None,
                keywords: Some(vec!["裳羽".to_string(), "刀叉".to_string()]),
                hard_terms: None,
                soft_terms: None,
                file_type: None,
                extension: None,
                folder: None,
                date_from: None,
                date_to: None,
                sort_by: None,
                limit: Some(20),
                offset: Some(0),
            },
        )
        .expect("query should succeed");

        assert_eq!(result.total, 1);
        assert_eq!(result.items[0].file_name, "裳羽-刀叉.mov");
    }

    #[test]
    fn query_filters_by_ai_date_range_and_extension() {
        let conn = seeded_conn();
        let result = query_files(
            &conn,
            &FileSearchQuery {
                query: None,
                keywords: Some(vec!["合同".to_string()]),
                hard_terms: None,
                soft_terms: None,
                file_type: Some("document".to_string()),
                extension: Some("pdf".to_string()),
                folder: None,
                date_from: Some("2026-05-01".to_string()),
                date_to: Some("2026-05-31".to_string()),
                sort_by: None,
                limit: Some(20),
                offset: Some(0),
            },
        )
        .expect("query should succeed");

        assert_eq!(result.total, 1);
        assert_eq!(result.items[0].file_name, "合同-2026-05.pdf");
    }

    #[test]
    fn query_orders_file_name_hits_before_folder_hits() {
        let conn = seeded_conn();
        let result = query_files(
            &conn,
            &FileSearchQuery {
                query: None,
                keywords: Some(vec!["刀叉".to_string()]),
                hard_terms: None,
                soft_terms: None,
                file_type: None,
                extension: None,
                folder: None,
                date_from: None,
                date_to: None,
                sort_by: None,
                limit: Some(20),
                offset: Some(0),
            },
        )
        .expect("query should succeed");

        assert_eq!(result.items[0].file_name, "裳羽-刀叉.mov");
        assert_eq!(result.items[1].file_name, "拍摄花絮.txt");
    }

    #[test]
    fn query_uses_hard_terms_as_filters_and_soft_terms_for_sorting_only() {
        let conn = seeded_conn();
        for (path, name, folder, modified) in [(
            r"C:\Share\素材\裳羽-奶冻粉.mov",
            "裳羽-奶冻粉.mov",
            "Share,素材",
            1_778_600_000_i64,
        )] {
            conn.execute(
                "INSERT INTO files (file_path, file_name, parent_folder, file_extension, file_size, file_modified, file_type, indexed_at)
                 VALUES (?1, ?2, ?3, 'mov', 100, ?4, 'video', ?4)",
                params![path, name, folder, modified],
            )
            .expect("insert hard term fixture");
        }
        let result = query_files(
            &conn,
            &FileSearchQuery {
                query: None,
                keywords: None,
                hard_terms: Some(vec!["裳羽".to_string()]),
                soft_terms: Some(vec!["刀叉".to_string()]),
                file_type: Some("video".to_string()),
                extension: None,
                folder: None,
                date_from: None,
                date_to: None,
                sort_by: None,
                limit: Some(20),
                offset: Some(0),
            },
        )
        .expect("query should succeed");

        assert_eq!(result.total, 2);
        assert_eq!(result.items[0].file_name, "裳羽-刀叉.mov");
        assert_eq!(result.items[1].file_name, "裳羽-奶冻粉.mov");
    }

    #[test]
    fn extracts_search_entities_from_file_names_and_folders() {
        let entry = IndexedEntry {
            file_path: r"\\192.168.0.118\法采共享盘2026\0-抖音素材库\调味果酱\成品\26.5\清爽-口味痛点-26.5.26-调味果酱-法采烘焙旗舰店-裳羽1.mp4".to_string(),
            file_name: "清爽-口味痛点-26.5.26-调味果酱-法采烘焙旗舰店-裳羽1.mp4".to_string(),
            parent_folder: "0-抖音素材库,调味果酱,成品,26.5".to_string(),
            file_extension: "mp4".to_string(),
            file_size: 100,
            file_modified: 1_779_780_000,
            file_type: "video".to_string(),
        };

        let entities = extract_entities_from_entry(&entry);

        assert!(entities.contains(&"裳羽".to_string()));
        assert!(entities.contains(&"调味果酱".to_string()));
        assert!(entities.contains(&"抖音素材库".to_string()));
        assert!(!entities.contains(&"26.5".to_string()));
        assert!(!entities.contains(&"视频".to_string()));
    }

    #[test]
    fn entity_candidates_fall_back_to_index_matches_when_entity_table_is_empty() {
        let conn = seeded_conn();
        let candidates = query_entity_candidates(&conn, "裳羽").expect("candidates");

        assert!(candidates.contains(&"裳羽".to_string()));
    }

    fn seeded_conn() -> Connection {
        let conn = Connection::open_in_memory().expect("in-memory db");
        init_schema(&conn).expect("schema");
        let rows = [
            (
                r"C:\Share\素材\裳羽-刀叉.mov",
                "裳羽-刀叉.mov",
                "Share,素材",
                "mov",
                100,
                1_778_371_200_i64,
                "video",
            ),
            (
                r"C:\Share\刀叉\拍摄花絮.txt",
                "拍摄花絮.txt",
                "Share,刀叉",
                "txt",
                10,
                1_778_457_600_i64,
                "document",
            ),
            (
                r"C:\Share\合同\合同-2026-05.pdf",
                "合同-2026-05.pdf",
                "Share,合同",
                "pdf",
                20,
                1_778_371_200_i64,
                "document",
            ),
            (
                r"C:\Share\合同\合同-2026-04.pdf",
                "合同-2026-04.pdf",
                "Share,合同",
                "pdf",
                20,
                1_775_779_200_i64,
                "document",
            ),
        ];
        for (path, name, folder, extension, size, modified, file_type) in rows {
            conn.execute(
                "INSERT INTO files (file_path, file_name, parent_folder, file_extension, file_size, file_modified, file_type, indexed_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?6)",
                params![path, name, folder, extension, size, modified, file_type],
            )
            .expect("insert file");
        }
        conn
    }
}
