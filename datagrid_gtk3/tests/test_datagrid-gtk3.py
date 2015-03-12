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

from datagrid_gtk3.db.sqlite import SQLiteDataSource
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

    def test_timestamp_transform(self):
        """Return valid datetime with valid seconds input."""
        self.assertEqual(
            self._transform('timestamp', 0),
            '1970-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp', 1104537600),
            '2005-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp', -134843428),
            '1965-09-23T07:29:32')
        self.assertEqual(
            self._transform('timestamp', -1),
            '1969-12-31T23:59:59')

    def test_timestamp_transform_invalid(self):
        """Return the value itself when it could not be converted."""
        self.assertEqual(
            self._transform('timestamp', 315532801000), 315532801000)
        self.assertEqual(
            self._transform('timestamp', -315532801000), -315532801000)

    def test_timestamp_ms_transform(self):
        """Return valid datetime with valid miliseconds input."""
        self.assertEqual(
            self._transform('timestamp_ms', 1104537600 * 10 ** 3),
            '2005-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp_ms', -134843428 * 10 ** 3),
            '1965-09-23T07:29:32')

    def test_timestamp_Ms_transform(self):
        """Return valid datetime with valid microseconds input."""
        self.assertEqual(
            self._transform('timestamp_Ms', 1104537600 * 10 ** 6),
            '2005-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp_Ms', -134843428 * 10 ** 6),
            '1965-09-23T07:29:32')

    def test_timestamp_apple_transform(self):
        """Return valid datetime with valid apple timestamp input."""
        self.assertEqual(
            self._transform('timestamp_apple', 0),
            '2001-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp_apple', 1104537600),
            '2036-01-02T00:00:00')
        self.assertEqual(
            self._transform('timestamp_apple', -134843428),
            '1996-09-23T07:29:32')
        self.assertEqual(
            self._transform('timestamp_apple', -1),
            '2000-12-31T23:59:59')

    def test_timestamp_webkit_transform(self):
        """Return valid datetime with valid webkit timestamp input."""
        self.assertEqual(
            self._transform('timestamp_webkit', 0),
            '1601-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp_webkit', 1104537600),
            '1601-01-01T00:18:24')
        self.assertEqual(
            self._transform('timestamp_webkit', 1104537600 * 10 ** 6),
            '1636-01-02T00:00:00')
        self.assertEqual(
            self._transform('timestamp_webkit', -134843428 * 10 ** 6),
            '1596-09-23T07:29:32')
        self.assertEqual(
            self._transform('timestamp_webkit', -1),
            '1600-12-31T23:59:59')

    def test_timestamp_julian_transform(self):
        """Return valid datetime with valid julian date input."""
        self.assertEqual(
            self._transform('timestamp_julian', 2457093.5),
            '2015-03-12T00:00:00')
        self.assertEqual(
            self._transform('timestamp_julian', 2457093.75),
            '2015-03-12T06:00:00')
        self.assertEqual(
            self._transform('timestamp_julian', 2440587.5),
            '1970-01-01T00:00:00')
        self.assertEqual(
            self._transform('timestamp_julian', 2439283.0),
            '1966-06-06T12:00:00')

    def test_timestamp_julian_date_transform(self):
        """Return valid datetime with valid julian date input."""
        self.assertEqual(
            self._transform('timestamp_julian_date', 2457093.5),
            '2015-03-12')
        self.assertEqual(
            self._transform('timestamp_julian_date', 2457093.75),
            '2015-03-12')
        self.assertEqual(
            self._transform('timestamp_julian_date', 2440587.5),
            '1970-01-01')
        self.assertEqual(
            self._transform('timestamp_julian_date', 2439283.0),
            '1966-06-06')

    def test_timestamp_midnight_transform(self):
        """Return valid time with valid seconds after midnight input."""
        self.assertEqual(
            self._transform('timestamp_midnight', 0),
            '00:00:00')
        self.assertEqual(
            self._transform('timestamp_midnight', 530),
            '00:08:50')
        self.assertEqual(
            self._transform('timestamp_midnight', 8493),
            '02:21:33')

    def test_timestamp_midnight_ms_transform(self):
        """Return valid time with valid miliseconds after midnight input."""
        self.assertEqual(
            self._transform('timestamp_midnight_ms', 0),
            '00:00:00')
        self.assertEqual(
            self._transform('timestamp_midnight_ms', 530 * 10 ** 3),
            '00:08:50')
        self.assertEqual(
            self._transform('timestamp_midnight_ms', 8493 * 10 ** 3),
            '02:21:33')

    def test_timestamp_midnight_Ms_transform(self):
        """Return valid time with valid microseconds after midnight input."""
        self.assertEqual(
            self._transform('timestamp_midnight_Ms', 0),
            '00:00:00')
        self.assertEqual(
            self._transform('timestamp_midnight_Ms', 530 * 10 ** 6),
            '00:08:50')
        self.assertEqual(
            self._transform('timestamp_midnight_Ms', 8493 * 10 ** 6),
            '02:21:33')

    def test_bytes_transform(self):
        """Test bytes humanization."""
        self.assertEqual(
            self._transform('bytes', 1),
            '1.0 B')
        self.assertEqual(
            self._transform('bytes', 50),
            '50.0 B')
        self.assertEqual(
            self._transform('bytes', 2348),
            '2.3 kB')
        self.assertEqual(
            self._transform('bytes', 1420000),
            '1.4 MB')
        self.assertEqual(
            self._transform('bytes', 1420000328),
            '1.3 GB')
        self.assertEqual(
            self._transform('bytes', 24200003283214),
            '22.0 TB')

    @mock.patch('datagrid_gtk3.ui.grid.NO_IMAGE_PIXBUF.scale_simple')
    def test_image_transform_no_value(self, scale_simple):
        """Return an invisible image when no value is provided."""
        returned_value = object()
        scale_simple.return_value = returned_value
        self.datagrid_model.image_max_size = 50

        self.assertEqual(
            self._transform('image', None), returned_value)
        self.assertEqual(
            self._transform('image', None), returned_value)
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
                mock.patch('datagrid_gtk3.utils.transformations.Image.open'),
                mock.patch.object(image, 'thumbnail')) as (
                    add_drop_shadow, add_border, open_, thumbnail):
            add_border.side_effect = _add_border
            add_drop_shadow.side_effect = _add_drop_shadow

            open_.return_value = image
            self.assertIsInstance(
                self._transform('image', 'file://xxx'),
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
                mock.patch('datagrid_gtk3.utils.transformations.Image.open'),
                mock.patch.object(image, 'thumbnail')) as (open_, thumbnail):
            open_.return_value = image
            self.assertIsInstance(
                self._transform('image', 'file://xxx'),
                GdkPixbuf.Pixbuf)

            thumbnail.assert_called_once_with((123, 123), Image.BICUBIC)
            open_.assert_called_once_with('xxx')
            self.assertEqual(add_border.call_count, 0)
            self.assertEqual(add_drop_shadow.call_count, 0)

    def _transform(self, transform_type, value):
        self.datagrid_model.columns = [
            {'name': transform_type, 'transform': transform_type}]
        return self.datagrid_model.get_formatted_value(value, 0)


if __name__ == '__main__':
    unittest.main()
