import sqlite3
import datetime
import logging

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "legislative_tracker.db"

def initialize_db(db_path=DEFAULT_DB_PATH):
    """Initialize the SQLite database and create the tables if they do not exist.
    
    Args:
        db_path (str): Path to the SQLite database file.
    """
    logger.info("Initializing database at %s...", db_path)
    
    tracked_laws_query = """
    CREATE TABLE IF NOT EXISTS tracked_laws (
        matter_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        last_modified_date TEXT NOT NULL,
        finlex_statute_id TEXT,
        status TEXT NOT NULL,
        processed_at TEXT NOT NULL
    );
    """
    
    summaries_query = """
    CREATE TABLE IF NOT EXISTS summaries (
        matter_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        ground_truth_url TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(matter_id) REFERENCES tracked_laws(matter_id)
    );
    """
    
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(tracked_laws_query)
            conn.execute(summaries_query)
        logger.info("Database tables initialized successfully.")
    except sqlite3.Error as e:
        logger.error("Database initialization error: %s", e)
        raise
    finally:
        conn.close()

def is_law_tracked(matter_id, db_path=DEFAULT_DB_PATH):
    """Check if a legislative matter is already tracked in the database.
    
    Args:
        matter_id (str): The unique ID of the legislative matter.
        db_path (str): Path to the SQLite database file.
        
    Returns:
        bool: True if tracked, False otherwise.
    """
    query = "SELECT 1 FROM tracked_laws WHERE matter_id = ? LIMIT 1;"
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query, (str(matter_id),))
        result = cursor.fetchone()
        return result is not None
    except sqlite3.Error as e:
        logger.error("Error checking if law is tracked (ID %s): %s", matter_id, e)
        return False
    finally:
        conn.close()

def insert_or_update_law(matter_id, title, last_modified_date, status, finlex_statute_id=None, db_path=DEFAULT_DB_PATH):
    """Insert a new tracked law or update an existing one.
    
    Automatically records the current UTC timestamp under 'processed_at'.
    
    Args:
        matter_id (str): Unique ID of the matter.
        title (str): Title of the law/proposal.
        last_modified_date (str): Date when it was last modified.
        status (str): Current status of the matter.
        finlex_statute_id (str, optional): The associated Finlex ID. Defaults to None.
        db_path (str): Path to the SQLite database file.
    """
    processed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # We use an UPSERT query (INSERT OR REPLACE, or INSERT ... ON CONFLICT DO UPDATE)
    query = """
    INSERT INTO tracked_laws (matter_id, title, last_modified_date, status, finlex_statute_id, processed_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(matter_id) DO UPDATE SET
        title=excluded.title,
        last_modified_date=excluded.last_modified_date,
        status=excluded.status,
        finlex_statute_id=COALESCE(excluded.finlex_statute_id, tracked_laws.finlex_statute_id),
        processed_at=excluded.processed_at;
    """
    
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(query, (
                str(matter_id),
                title,
                last_modified_date,
                status,
                finlex_statute_id,
                processed_at
            ))
        logger.info("Successfully saved/updated tracked law: ID=%s, Title='%s'", matter_id, title)
    except sqlite3.Error as e:
        logger.error("Failed to insert or update law (ID %s): %s", matter_id, e)
        raise
    finally:
        conn.close()

def insert_or_update_summary(matter_id, title, summary_text, ground_truth_url, db_path=DEFAULT_DB_PATH):
    """Insert or update a summary report for a tracked law.
    
    Args:
        matter_id (str): Unique ID of the matter.
        title (str): Title of the law/proposal.
        summary_text (str): AI generated summary.
        ground_truth_url (str): Verified URL to the source.
        db_path (str): Path to the SQLite database file.
    """
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    query = """
    INSERT INTO summaries (matter_id, title, summary_text, ground_truth_url, created_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(matter_id) DO UPDATE SET
        title=excluded.title,
        summary_text=excluded.summary_text,
        ground_truth_url=excluded.ground_truth_url,
        created_at=excluded.created_at;
    """
    
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(query, (
                str(matter_id),
                title,
                summary_text,
                ground_truth_url,
                created_at
            ))
        logger.info("Successfully saved/updated summary: ID=%s", matter_id)
    except sqlite3.Error as e:
        logger.error("Failed to insert or update summary (ID %s): %s", matter_id, e)
        raise
    finally:
        conn.close()
