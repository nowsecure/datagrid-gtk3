from contextlib import closing
import sqlite3
import tempfile

from datagrid_gtk3.ui.grid import default_get_full_path


TEST_DATA = [
    (1, 'Dee', 'Timberlake', 30, 1286755200,
     'file://' + default_get_full_path('icons/image.png')),
    (2, 'Steve', 'Austin', 35, 1318291200,
     'file://' + default_get_full_path('icons/calendar22.png')),
    (3, 'Oscar', 'Goldman', 50, 1349913600, None),
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
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS %s
                    (__viaextract_id INTEGER,
                     first_name TEXT,
                     last_name TEXT,
                     age INTEGER,
                     start_date INTEGER,
                     image_path TEXT)
                """ % (TEST_DATA_TABLE, ))

                for i in TEST_DATA:
                    insert_sql = """
                        INSERT INTO %s
                        (__viaextract_id,
                         first_name,
                         last_name,
                         age,
                         start_date,
                         image_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """ % (TEST_DATA_TABLE, )
                    cursor.execute(insert_sql, i)
                conn.commit()
    return fi.name
