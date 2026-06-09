# Python SQLite3 Cheatsheet

Quick reference for using SQLite with Python’s built-in `sqlite3` module.

---

## Basic Setup

```python
import sqlite3

conn = sqlite3.connect('app.db')
cursor = conn.cursor()

cursor.execute('SELECT sqlite_version()')
print(cursor.fetchone())

conn.close()
```

| Code                        | Use                            |
| --------------------------- | ------------------------------ |
| `import sqlite3`            | Import built-in SQLite module  |
| `sqlite3.connect('app.db')` | Open/create database file      |
| `conn.cursor()`             | Create cursor for SQL commands |
| `cursor.execute(sql)`       | Run one SQL statement          |
| `conn.commit()`             | Save changes                   |
| `conn.close()`              | Close connection               |

---

## Recommended Connection Pattern

```python
import sqlite3

with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
```

Using `with` automatically commits if successful and rolls back on error.

---

## Create Table

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            value TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
```

Common column types:

| Type      | Use             |
| --------- | --------------- |
| `INTEGER` | Whole numbers   |
| `REAL`    | Decimal numbers |
| `TEXT`    | Strings         |
| `BLOB`    | Binary data     |
| `NULL`    | Empty value     |

---

## Insert Data

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?)',
        ('theme', 'dark')
    )
```

Use `?` placeholders. Do **not** build SQL with f-strings for user values.

Bad:

```python
cursor.execute(f"INSERT INTO settings VALUES ('{key}', '{value}')")
```

Good:

```python
cursor.execute(
    'INSERT INTO settings (key, value) VALUES (?, ?)',
    (key, value)
)
```

---

## Insert Multiple Rows

```python
rows = [
    ('theme', 'dark'),
    ('language', 'en'),
    ('page_size', '50'),
]

with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.executemany(
        'INSERT INTO settings (key, value) VALUES (?, ?)',
        rows
    )
```

---

## Select Data

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute('SELECT id, key, value FROM settings')
    rows = cursor.fetchall()

    for row in rows:
        print(row)
```

| Method         | Use               |
| -------------- | ----------------- |
| `fetchone()`   | Get one row       |
| `fetchall()`   | Get all rows      |
| `fetchmany(n)` | Get next `n` rows |

---

## Select with Parameters

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute(
        'SELECT value FROM settings WHERE key = ?',
        ('theme',)
    )

    row = cursor.fetchone()
```

Important: single-value tuples need a trailing comma:

```python
('theme',)
```

Not:

```python
('theme')
```

Python trap. Tiny comma, large pain.

---

## Update Data

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute(
        'UPDATE settings SET value = ? WHERE key = ?',
        ('light', 'theme')
    )
```

---

## Delete Data

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute(
        'DELETE FROM settings WHERE key = ?',
        ('theme',)
    )
```

---

## Upsert

Insert if missing, update if already exists.

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value
    """, ('theme', 'dark'))
```

Useful for settings/config tables.

---

## Get Last Inserted ID

```python
with sqlite3.connect('app.db') as conn:
    cursor = conn.cursor()

    cursor.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?)',
        ('theme', 'dark')
    )

    new_id = cursor.lastrowid
    print(new_id)
```

---

## Row Count

```python
cursor.execute(
    'UPDATE settings SET value = ? WHERE key = ?',
    ('dark', 'theme')
)

print(cursor.rowcount)
```

---

## Dictionary-Like Rows

By default, SQLite rows are tuples. This makes them easier to use.

```python
with sqlite3.connect('app.db') as conn:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT id, key, value FROM settings')
    row = cursor.fetchone()

    print(row['key'])
    print(row['value'])
```

Recommended for app code.

---

## Simple Helper Function

```python
import sqlite3

DB_PATH = 'app.db'

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
```

Usage:

```python
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM settings')
    rows = cursor.fetchall()
    for row in rows:
        print(f"{row[0]}\t= {row[1]}") # column = value
```

---

## Create DB Schema Function

```python
def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

Call once when app starts:

```python
init_db()
```

---

## Settings Table Example

```python
def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))


def get_setting(key: str, default=None):
    with get_connection() as conn:
        row = conn.execute(
            'SELECT value FROM settings WHERE key = ?',
            (key,)
        ).fetchone()

        return row['value'] if row else default
```

Usage:

```python
set_setting('theme', 'dark')

theme = get_setting('theme', 'light')
print(theme)
```

---

## Store JSON

SQLite does not require a special JSON column type. Store JSON as `TEXT`.

```python
import json

data = {
    'theme': 'dark',
    'page_size': 50,
    'show_advanced': True,
}

with get_connection() as conn:
    conn.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?)',
        ('ui_config', json.dumps(data))
    )
```

Read JSON:

```python
with get_connection() as conn:
    row = conn.execute(
        'SELECT value FROM settings WHERE key = ?',
        ('ui_config',)
    ).fetchone()

    config = json.loads(row['value'])
```

---

## Store Binary Data

Use `BLOB` for small binary data.

```python
with open('image.png', 'rb') as f:
    image_bytes = f.read()

with get_connection() as conn:
    conn.execute(
        'INSERT INTO files (name, data) VALUES (?, ?)',
        ('image.png', image_bytes)
    )
```

Create table:

```python
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    data BLOB NOT NULL
)
```

For large images/audio/video, prefer storing files on disk and saving file paths in SQLite.

---

## File Metadata Table

Good pattern for images, audio, and generated files:

```sql
CREATE TABLE media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    thumbnail_path TEXT,
    prompt TEXT,
    metadata_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Example insert:

```python
with get_connection() as conn:
    conn.execute("""
        INSERT INTO media (
            type,
            file_path,
            thumbnail_path,
            prompt,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        'image',
        'outputs/image_001.png',
        'outputs/thumbs/image_001.webp',
        'girl in fantasy armor',
        json.dumps({'seed': 123, 'steps': 30}),
    ))
```

---

## Transactions

Multiple statements can be committed together.

```python
with get_connection() as conn:
    conn.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('a', '1'))
    conn.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('b', '2'))
```

If an exception happens inside the `with` block, SQLite rolls back automatically.

Manual transaction:

```python
conn = get_connection()

try:
    conn.execute('BEGIN')
    conn.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('a', '1'))
    conn.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ('b', '2'))
    conn.commit()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
```

---

## Indexes

Indexes make searches faster.

```sql
CREATE INDEX IF NOT EXISTS idx_settings_key
ON settings(key);
```

For media:

```sql
CREATE INDEX IF NOT EXISTS idx_media_type
ON media(type);

CREATE INDEX IF NOT EXISTS idx_media_created_at
ON media(created_at);
```

---

## Foreign Keys

SQLite supports foreign keys, but you should enable them per connection.

```python
def get_connection():
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn
```

Example:

```sql
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

---

## Useful PRAGMA Settings

```python
with get_connection() as conn:
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
```

| PRAGMA                 | Use                                |
| ---------------------- | ---------------------------------- |
| `foreign_keys = ON`    | Enforce foreign key rules          |
| `journal_mode = WAL`   | Better read/write concurrency      |
| `synchronous = NORMAL` | Good speed/safety balance with WAL |
| `busy_timeout = 5000`  | Wait before failing on locked DB   |

Example:

```python
conn.execute('PRAGMA busy_timeout = 5000')
```

---

## Check If Table Exists

```python
with get_connection() as conn:
    row = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, ('settings',)).fetchone()

    exists = row is not None
```

---

## List Tables

```python
with get_connection() as conn:
    rows = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
    """).fetchall()

    for row in rows:
        print(row['name'])
```

---

## Add Column

```sql
ALTER TABLE settings ADD COLUMN description TEXT;
```

Python:

```python
with get_connection() as conn:
    conn.execute('ALTER TABLE settings ADD COLUMN description TEXT')
```

SQLite migrations are simple until they are not. Keep migrations explicit.

---

## Backup Database

```python
source = sqlite3.connect('app.db')
target = sqlite3.connect('backup.db')

with target:
    source.backup(target)

source.close()
target.close()
```

---

## In-Memory Database

Useful for tests.

```python
conn = sqlite3.connect(':memory:')
```

Example:

```python
def test_db():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)')
    conn.execute('INSERT INTO test (name) VALUES (?)', ('Alice',))
    row = conn.execute('SELECT name FROM test').fetchone()
    assert row[0] == 'Alice'
```

---

## Error Handling

```python
try:
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO settings (key, value) VALUES (?, ?)',
            ('theme', 'dark')
        )
except sqlite3.IntegrityError:
    print('Duplicate key or constraint error')
except sqlite3.OperationalError as e:
    print(f'Database error: {e}')
```

Common exceptions:

| Exception                  | Meaning                       |
| -------------------------- | ----------------------------- |
| `sqlite3.IntegrityError`   | Constraint failed             |
| `sqlite3.OperationalError` | SQL/database operation failed |
| `sqlite3.ProgrammingError` | Wrong API usage               |
| `sqlite3.DatabaseError`    | General database error        |

---

## Common App Pattern

```python
from pathlib import Path
import sqlite3
import json

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / 'app.db'


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


def set_setting(key: str, value):
    if not isinstance(value, str):
        value = json.dumps(value)

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))


def get_setting(key: str, default=None):
    with get_connection() as conn:
        row = conn.execute(
            'SELECT value FROM settings WHERE key = ?',
            (key,)
        ).fetchone()

    return row['value'] if row else default
```

---

## Quick Reference

| Task               | Code                             |
| ------------------ | -------------------------------- |
| Connect            | `sqlite3.connect('app.db')`      |
| Cursor             | `conn.cursor()`                  |
| Execute SQL        | `cursor.execute(sql, params)`    |
| Insert many        | `cursor.executemany(sql, rows)`  |
| Commit             | `conn.commit()`                  |
| Rollback           | `conn.rollback()`                |
| Close              | `conn.close()`                   |
| One row            | `cursor.fetchone()`              |
| All rows           | `cursor.fetchall()`              |
| Dict rows          | `conn.row_factory = sqlite3.Row` |
| Last ID            | `cursor.lastrowid`               |
| Affected rows      | `cursor.rowcount`                |
| In-memory DB       | `sqlite3.connect(':memory:')`    |
| Enable FK          | `PRAGMA foreign_keys = ON`       |
| Better concurrency | `PRAGMA journal_mode = WAL`      |

---

## Best Practices

* Use parameterized SQL with `?`.
* Use `with sqlite3.connect(...) as conn:` for simple transactions.
* Set `row_factory = sqlite3.Row` for readable row access.
* Enable `PRAGMA foreign_keys = ON`.
* Use `WAL` mode for app-style databases.
* Store large media files on disk, not directly in SQLite.
* Store paths and metadata in SQLite.
* Use indexes for columns you search/filter often.
* Keep schema creation and migrations in separate functions.
* Avoid sharing the same connection across many threads.
* Open short-lived connections unless you have a good reason not to.
