#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Data grid test cases."""
import os
import unittest

from mock import MagicMock as Mock

from datagrid_gtk2.db import sqlite
from datagrid_gtk2.tests.data import create_db
from datagrid_gtk2.ui.grid import (
    DataGridContainer,
    DataGridController,
    DataGridModel
)


class SQLiteDataSource(sqlite.SQLiteDataSource):
    ID_COLUMN = '__viaextract_id'


class DataGridControllerTest(unittest.TestCase):

    """Test DataGridController."""

    def setUp(self):  # noqa
        """Create test data."""
        self.db_file = create_db()
        self.table = 'people'
        self.datasource = SQLiteDataSource(
            self.db_file,
            self.table,
            None,
            [
                ('First name', (str, None)),
                ('Last name', (str, None)),
                ('Age', (int, None)),
                ('Start', (int, 'datetime'))
            ]
        )
        self.datasource.MAX_RECS = 2  # 2 records per page
        win = Mock()
        datagrid_container = DataGridContainer(win)
        self.datagrid_controller = DataGridController(
            datagrid_container, self.datasource)

    def tearDown(self):  # noqa
        """Remove test data file."""
        os.unlink(self.db_file)

    def test_grid_init(self):
        """The grid is populated correctly with data."""
        # ensure custom column titles are being used
        self.assertEqual(
            self.datagrid_controller.view.tv_columns[0].get_title(),
            'First name'
        )
        # ensure only first page of data is being populated
        self.assertEqual(len(self.datagrid_controller.model), 2)
        # ensure datetime column is being added
        self.assertEqual(
            self.datagrid_controller.model.datetime_columns[0]['name'],
            'start_date'
        )

    def test_no_checkboxes(self):
        """Test that checkboxes are invisible if desired."""
        win = Mock()
        datagrid_container = DataGridContainer(win)
        datagrid_controller = DataGridController(
            datagrid_container, self.datasource, None, has_checkboxes=False)
        self.assertFalse(
            datagrid_controller.container.checkbutton_select_all.get_visible())
        self.assertNotEqual(
            datagrid_controller.view.get_columns()[0].get_title(), "__selected")


class DataGridModelTest(unittest.TestCase):

    """Test DataGridModel."""

    def setUp(self):  # noqa
        """Create test data."""
        self.datagrid_model = DataGridModel(Mock(), Mock(), Mock())

    def test_datetime_transform_zero(self):
        """Return input value with invalid datetime input of 0."""
        self.assertEqual(self.datagrid_model._datetime_transform(0), 0)

    def test_datetime_transform_invalid_to_big(self):
        """Return input value with invalid datetime input over max value."""
        self.assertEqual(
            self.datagrid_model._datetime_transform(315532801000000000),
            315532801000000000)

    def test_datetime_transform_second_time(self):
        """Return valid datetime with valid seconds input."""
        self.assertEqual(
            self.datagrid_model._datetime_transform(1104537600),
            '2005-01-01T00:00:00')

    def test_datetime_transform_millisecond_time(self):
        """Return valid datetime with valid milliseconds input."""
        self.assertEqual(
            self.datagrid_model._datetime_transform(315532801000),
            '1980-01-01T00:00:01')

    def test_datetime_transform_microseconds_time(self):
        """Return valid datetime with valid microseconds input."""
        self.assertEqual(
            self.datagrid_model._datetime_transform(315532801000000),
            '1980-01-01T00:00:01')


if __name__ == '__main__':
    unittest.main()
