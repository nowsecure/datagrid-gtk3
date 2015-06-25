import contextlib
import os
import sqlite3
import unittest

from datagrid_gtk3.tests.data import create_db, TEST_DATA
from datagrid_gtk3.db.sqlite import SQLiteDataSource


class SQLiteDataSourceTest(unittest.TestCase):

    """Test SQLiteDataSource."""

    def setUp(self):
        """Create test data."""
        self.table = 'people'
        self.db_file = create_db(self.table)
        self.datasource = SQLiteDataSource(
            self.db_file,
            table=self.table,
            config=[
                {'column': 'First name', 'type': 'str'},
                {'column': 'Last name', 'type': 'str'},
                {'column': 'Age', 'type': 'int'},
                {'column': 'Start', 'type': 'int', 'encoding': 'timestamp'},
                {'column': 'Image', 'type': 'int', 'encoding': 'image'},
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
        self.assertEqual(self.datasource.total_recs, 4)

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
        self.assertEqual(rows[0].data[2], 'Goldman')

    def test_load_with_where_param(self):
        """Filter results with a search param."""
        param = {
            'where': {
                'search': {
                    'param': 'gold',
                },
            },
        }
        rows = self.datasource.load(param)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {('Oscar', 'Goldman'), ('Monica', 'Goldman')},
            {(row.data[1], row.data[2]) for row in rows})

    def test_load_paging(self):
        """Load first and second pages of records."""
        self.datasource.load()  # initial load is always without paging
        rows = self.datasource.load({'page': 1})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].data[2], 'Goldman')

    def test_update(self):
        """Update __selected in first record in data set."""
        self.datasource.update({'__selected': True}, [1])
        # ^^ update row with id 1
        rows = self.datasource.load()
        self.assertEqual(rows[0].data[0], 1)

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
        self.assertEqual(ids, [2, 3, 4])

    def test_visible_columns(self):
        """Set visible columns and ensure they're persisted."""
        self.datasource.set_visible_columns(['last_name'])
        self.assertEqual(self.datasource.get_visible_columns(), ['last_name'])

    def test_get_single_record(self):
        """Retrieve a single record as a tuple of values."""
        row = self.datasource.get_single_record(1)
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 'Dee')
        self.assertEqual(row[2], 'Timberlake')

    def test_select(self):
        """Get data without class instance or paging."""
        db_file = self.datasource.db_file
        with contextlib.closing(sqlite3.connect(db_file)) as conn:
            results = list(self.datasource.select(conn, self.datasource.table))
        self.assertEqual(len(results), 4)

    def test_explicit_query(self):
        """Test using an explicit query for the data source."""
        # Important to not ensure "selected" column if there is no primary
        # key returned by the query.
        datasource = SQLiteDataSource(
            self.db_file, query='SELECT first_name, age FROM people',
            ensure_selected_column=False
        )
        rows = datasource.load()
        data = {tuple(row.data) for row in rows}
        reference_data = {(record[1], record[3])
                          for record in TEST_DATA[self.table]['data']}
        self.assertEqual(data, reference_data)


if __name__ == '__main__':
    unittest.main()
