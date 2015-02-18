#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Data grid test cases."""

import contextlib
import os
import unittest

from gi.repository import (
    Gdk,
    Gtk,
    GdkPixbuf,
)
from PIL import Image
import mock

from datagrid_gtk3.db import sqlite
from datagrid_gtk3.tests.data import create_db
from datagrid_gtk3.ui.grid import (
    DataGridContainer,
    DataGridController,
    DataGridIconView,
    DataGridModel,
    DataGridView,
    OptionsPopup,
    default_get_full_path,
)
from datagrid_gtk3.utils import imageutils


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
                ('Start', (int, 'datetime')),
                ('Image', (str, 'image')),
            ]
        )
        self.datasource.MAX_RECS = 2  # 2 records per page
        win = mock.MagicMock()
        datagrid_container = DataGridContainer(win)
        self.datagrid_controller = DataGridController(
            datagrid_container, self.datasource)
        self.model = self.datagrid_controller.model

    def tearDown(self):  # noqa
        """Remove test data file."""
        os.unlink(self.db_file)

    def test_grid_init(self):
        """The grid is populated correctly with data."""
        # the first column is the toggle button column. It has not title
        self.assertEqual(
            self.datagrid_controller.view.get_column(0).get_title(), '')
        self.assertIsInstance(
            self.datagrid_controller.view.get_column(0).get_widget(),
            Gtk.CheckButton)

        # ensure custom column titles are being used
        self.assertEqual(
            self.datagrid_controller.view.get_column(1).get_title(),
            'First name')
        # ensure only first page of data is being populated
        self.assertEqual(len(self.datagrid_controller.model), 2)
        # ensure datetime column is being added
        self.assertEqual(
            self.datagrid_controller.model.datetime_columns[0]['name'],
            'start_date'
        )

    def test_view_types(self):
        """The views are instances of the right classes."""
        self.assertIsInstance(
            self.datagrid_controller.tree_view, DataGridView)
        self.assertIsInstance(
            self.datagrid_controller.icon_view, DataGridIconView)

    def test_change_view(self):
        """The views are instances of the right classes."""
        scrolledwindow = self.datagrid_controller.container.grid_scrolledwindow
        icon_view = self.datagrid_controller.icon_view
        tree_view = self.datagrid_controller.tree_view

        # IconView
        self.datagrid_controller.options_popup.emit(
            'view-changed', OptionsPopup.VIEW_ICON)
        self.assertIs(
            self.datagrid_controller.view, icon_view)
        self.assertIs(
            scrolledwindow.get_child(), icon_view)
        self.assertEqual(self.model.image_max_size, 100.0)
        self.assertTrue(self.model.image_draw_border)
        self.assertEqual(icon_view.pixbuf_column, 6)

        # TreeView
        self.datagrid_controller.options_popup.emit(
            'view-changed', OptionsPopup.VIEW_TREE)
        self.assertIs(
            self.datagrid_controller.view, tree_view)
        self.assertIs(
            scrolledwindow.get_child(), tree_view)
        self.assertEqual(self.model.image_max_size, 24.0)
        self.assertFalse(self.model.image_draw_border)

    def test_change_columns_visibility(self):
        """The views are instances of the right classes."""
        tree_view = self.datagrid_controller.tree_view

        self.assertIsNone(self.model.display_columns)
        # Make sure model.display_columns will not be None
        self.datagrid_controller.options_popup._get_visibility_options().next()

        self.assertEqual(len(tree_view.get_columns()), 6)
        self.assertEqual(
            self.model.display_columns,
            set(['first_name', 'last_name', 'age', 'start_date', 'image_path']))

        # Make last_name invisible
        self.datagrid_controller.options_popup.emit(
            'column-visibility-changed', 'last_name', False)
        self.assertEqual(len(tree_view.get_columns()), 5)
        self.assertEqual(
            self.model.display_columns,
            set(['first_name', 'age', 'start_date', 'image_path']))

        # Make last_name visible again
        self.datagrid_controller.options_popup.emit(
            'column-visibility-changed', 'last_name', True)
        self.assertEqual(len(tree_view.get_columns()), 6)
        self.assertEqual(
            self.model.display_columns,
            set(['first_name', 'last_name', 'age', 'start_date', 'image_path']))

    def test_togglebutton_options_toggled(self):
        """The popup should popup when clicking on togglebutton_options."""
        popup = self.datagrid_controller.options_popup
        togglebutton = self.datagrid_controller.container.togglebutton_options

        with contextlib.nested(
                mock.patch.object(togglebutton, 'get_realized'),
                mock.patch.object(togglebutton, 'get_window')) as (gr, gw):
            gr.return_value = True
            gw.return_value = mock.MagicMock()
            gw.return_value.get_root_coords.return_value = (0, 0)

            original_popup = popup.popup
            with mock.patch.object(popup, 'popup') as popup_popup:
                popup_popup.side_effect = original_popup
                togglebutton.set_active(True)
                popup_popup.assert_called_once_with()

            original_popdown = popup.popdown
            with mock.patch.object(popup, 'popdown') as popup_popdown:
                popup_popdown.side_effect = original_popdown
                togglebutton.set_active(False)
                popup_popdown.assert_called_once_with()

    def test_on_scrolled(self):
        """Test that more results are loaded after scrolling to the bottom."""
        vscroll = self.datagrid_controller.vscroll

        original_add_rows = self.model.add_rows
        with mock.patch.object(self.model, 'add_rows') as add_rows:
            add_rows.side_effect = original_add_rows
            vscroll.set_value(vscroll.get_upper() - vscroll.get_page_size())
            vscroll.emit('value-changed')
            add_rows.assert_called_once_with()


class DataGridModelTest(unittest.TestCase):

    """Test DataGridModel."""

    def setUp(self):  # noqa
        """Create test data."""
        self.datagrid_model = DataGridModel(
            mock.MagicMock(), mock.MagicMock(), mock.MagicMock())

    def test_datetime_transform_negative(self):
        """Return an empty string when timestamp is -1."""
        self.assertEqual(self.datagrid_model._datetime_transform(-1), '')

    def test_datetime_transform_zero(self):
        """Return valid datetime with valid timestamp input of 0."""
        self.assertEqual(
            self.datagrid_model._datetime_transform(0),
            '1970-01-01T00:00:00')

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

    def test_bytes_transform(self):
        """Test bytes humanization."""
        self.assertEqual(
            self.datagrid_model._bytes_transform(1),
            '1 byte')
        self.assertEqual(
            self.datagrid_model._bytes_transform(50),
            '50.0 bytes')
        self.assertEqual(
            self.datagrid_model._bytes_transform(2348),
            '2.3 kB')
        self.assertEqual(
            self.datagrid_model._bytes_transform(1420000),
            '1.4 MB')
        self.assertEqual(
            self.datagrid_model._bytes_transform(1420000328),
            '1.3 GB')
        self.assertEqual(
            self.datagrid_model._bytes_transform(24200003283214),
            '22.0 TB')

    @mock.patch('datagrid_gtk3.ui.grid.NO_IMAGE_PIXBUF.scale_simple')
    def test_image_transform_no_value(self, scale_simple):
        """Return an invisible image when no value is provided."""
        returned_value = object()
        scale_simple.return_value = returned_value
        self.datagrid_model.image_max_size = 50

        self.assertEqual(
            self.datagrid_model._image_transform(None), returned_value)
        self.assertEqual(
            self.datagrid_model._image_transform(None), returned_value)
        # Even though we called _image_transform twice, the second one
        # was taken from the cache
        scale_simple.assert_called_once_with(
            50, 50, GdkPixbuf.InterpType.NEAREST)

    def test_image_transform_with_border(self):
        """Make sure the right functions are called to transform the image."""
        image = Image.open(
            default_get_full_path('icons/image.png'))
        image.load()

        _add_border_func = imageutils.add_border
        def _add_border(*args, **kwargs):
            _add_border_func(*args, **kwargs)
            return image

        _add_drop_shadow_func = imageutils.add_drop_shadow
        def _add_drop_shadow(*args, **kwargs):
            _add_drop_shadow_func(*args, **kwargs)
            return image

        self.datagrid_model.image_draw_border = True
        self.datagrid_model.image_max_size = 123
        self.datagrid_model.IMAGE_BORDER_SIZE = 8
        self.datagrid_model.IMAGE_SHADOW_SIZE = 10
        self.datagrid_model.IMAGE_SHADOW_OFFSET = 4

        with contextlib.nested(
                mock.patch('datagrid_gtk3.utils.imageutils.add_drop_shadow'),
                mock.patch('datagrid_gtk3.utils.imageutils.add_border'),
                mock.patch('datagrid_gtk3.ui.grid.Image.open'),
                mock.patch.object(image, 'thumbnail')) as (
                    add_drop_shadow, add_border, open_, thumbnail):
            add_border.side_effect = _add_border
            add_drop_shadow.side_effect = _add_drop_shadow

            open_.return_value = image
            self.assertIsInstance(
                self.datagrid_model._image_transform('file://xxx'),
                GdkPixbuf.Pixbuf)

            thumbnail.assert_called_once_with((123, 123), Image.BICUBIC)
            open_.assert_called_once_with('xxx')
            add_border.assert_called_once_with(image, border_size=8)
            add_drop_shadow.assert_called_once_with(
                image, border_size=10, offset=(4, 4))

    @mock.patch('datagrid_gtk3.utils.imageutils.add_drop_shadow')
    @mock.patch('datagrid_gtk3.utils.imageutils.add_border')
    def test_image_transform_without_border(self, add_border, add_drop_shadow):
        """Make sure the right functions are called to transform the image."""
        image = Image.open(
            default_get_full_path('icons/image.png'))
        image.load()

        add_border.return_value = image
        add_drop_shadow.return_value = image

        self.datagrid_model.image_max_size = 123
        self.datagrid_model.image_draw_border = False

        with contextlib.nested(
                mock.patch('datagrid_gtk3.ui.grid.Image.open'),
                mock.patch.object(image, 'thumbnail')) as (open_, thumbnail):
            open_.return_value = image
            self.assertIsInstance(
                self.datagrid_model._image_transform('file://xxx'),
                GdkPixbuf.Pixbuf)

            thumbnail.assert_called_once_with((123, 123), Image.BICUBIC)
            open_.assert_called_once_with('xxx')
            self.assertEqual(add_border.call_count, 0)
            self.assertEqual(add_drop_shadow.call_count, 0)


if __name__ == '__main__':
    unittest.main()
