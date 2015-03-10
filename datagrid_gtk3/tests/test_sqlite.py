import contextlib
import os
import sqlite3
import unittest

from datagrid_gtk3.tests.data import create_db
from datagrid_gtk3.db.sqlite import SQLiteDataSource


class SQLiteDataSourceTest(unittest.TestCase):

    """Test SQLiteDataSource."""

    def setUp(self):
        """Create test data."""
        self.db_file = create_db()
        self.table = 'people'
        self.datasource = SQLiteDataSource(
            self.db_file,
            table=self.table,
            config=[
                ('First name', (str, None)),
                ('Last name', (str, None)),
                ('Age', (int, None)),
                ('Start', (int, 'datetime')),
                ('Image', (str, 'image')),
            ],
        )
        self.datasource.MAX_RECS = 2

    def tearDown(self):
        """Remove test data file."""
        os.unlink(self.db_file)

    def test_load(self):
        """Load first page of records and get total."""
        rows = self.datasource.load()
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.datasource.total_recs, 3)

    def test_load_with_params(self):
        """Filter and order records."""
        param = {
            'where': {
                'age': {
                    'param': 30, 'operator': '>'
                }
            },
            'order_by': 'age',
            'desc': True
        }
        rows = self.datasource.load(param)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].data[3], 'Goldman')

    def test_load_paging(self):
        """Load first and second pages of records."""
        self.datasource.load()  # initial load is always without paging
        rows = self.datasource.load({'page': 1})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].data[3], 'Goldman')

    def test_update(self):
        """Update __selected in first record in data set."""
        self.datasource.update({'__selected': True}, [1])
        # ^^ update row with id 1
        rows = self.datasource.load()
        self.assertEqual(rows[0].data[1], 1)

    def test_get_all_record_ids(self):
        """Get all record ids for a particular query."""
        param = {
            'where': {
                'age': {
                    'param': 30, 'operator': '>'
                }
            }
        }
        ids = self.datasource.get_all_record_ids(param)
        self.assertEqual(ids, [2, 3])

    def test_selected_columns(self):
        """Set selected columns and ensure they're persisted."""
        self.datasource.update_selected_columns(['last_name'])
        cols = self.datasource.get_selected_columns()
        self.assertEqual(cols, ['last_name'])

    def test_get_single_record(self):
        """Retrieve a single record as a tuple of values."""
        row = self.datasource.get_single_record(1)
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 'Dee')
        self.assertEqual(row[3], 'Timberlake')

    def test_select(self):
        """Get data without class instance or paging."""
        db_file = self.datasource.db_file
        with contextlib.closing(sqlite3.connect(db_file)) as conn:
            results = list(self.datasource.select(conn, self.datasource.table))
        self.assertEqual(len(results), 3)


if __name__ == '__main__':
    unittest.main()
