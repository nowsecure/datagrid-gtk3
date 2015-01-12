from contextlib import closing
import sqlite3
import tempfile

TEST_DATA = [
    (1, 'Dee', 'Timberlake', 30, 1286755200),
    (2, 'Steve', 'Austin', 35, 1318291200),
    (3, 'Oscar', 'Goldman', 50, 1349913600),
]

TEST_DATA_TABLE = 'people'


def create_db():
    """Create a test SQLite DB for use with data grid tests.

    :return: path to created DB temporary file
    :rtype: str
    """
    with tempfile.NamedTemporaryFile(delete=False) as fi:
        with closing(sqlite3.connect(fi.name)) as conn:
            with closing(conn.cursor()) as cursor:
                create_sql = (
                    "CREATE TABLE IF NOT EXISTS %s "
                    "(__viaextract_id INTEGER, first_name TEXT, "
                    "last_name TEXT, age INTEGER, start_date INTEGER) "
                    % TEST_DATA_TABLE
                )
                cursor.execute(create_sql)
                for i in TEST_DATA:
                    insert_sql = (
                        'INSERT INTO %s '
                        '(__viaextract_id, first_name, last_name, age, start_date) '
                        'VALUES (?, ?, ?, ?, ?)' % TEST_DATA_TABLE
                    )
                    cursor.execute(insert_sql, i)
                conn.commit()
    return fi.name
