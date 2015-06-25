#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Data grid test cases."""

import contextlib
import datetime
import os
import unittest

from gi.repository import (
    Gtk,
    GdkPixbuf,
)
from PIL import Image
import mock

from datagrid_gtk3.db.sqlite import SQLiteDataSource
from datagrid_gtk3.tests.data import create_db, TEST_DATA
from datagrid_gtk3.ui.grid import (
    DataGridContainer,
    DataGridController,
    DataGridIconView,
    DataGridModel,
    DataGridView,
    OptionsPopup,
)
from datagrid_gtk3.utils import imageutils, transformations
from datagrid_gtk3.utils.transformations import html_transform


class _FilesDataSource(SQLiteDataSource):

    """SQLiteDataSource to use with 'files' test database."""

    PARENT_ID_COLUMN = '__parent'
    CHILDREN_LEN_COLUMN = 'children_len'
    FLAT_COLUMN = 'flatname'


class DataGridControllerTest(unittest.TestCase):

    """Test DataGridController."""

    def setUp(self):  # noqa
        """Create test data."""
        self.table = 'people'
        self.db_file = create_db(self.table)
        self.datasource = SQLiteDataSource(
            self.db_file,
            self.table,
            None,
            [
                {'column': 'First name', 'type': 'str'},
                {'column': 'Last name', 'type': 'str'},
                {'column': 'Age', 'type': 'int'},
                {'column': 'Start', 'type': 'int', 'encoding': 'timestamp'},
                {'column': 'Image', 'type': 'buffer', 'encoding': 'image'},
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
        self.assertEqual(icon_view.pixbuf_column, 5)

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


class DataGridModelTreeTest(unittest.TestCase):

    """Test for DataGridModel using an hierarchical data source."""

    def setUp(self):  # noqa
        """Create test data."""
        self.table = 'files'
        self.db_file = create_db(self.table)

        self.datasource = _FilesDataSource(
            self.db_file, self.table, None,
            [
                {'column': 'Parent', 'type': 'str'},
                {'column': 'Filename', 'type': 'str'},
                {'column': 'Flatname', 'type': 'str'},
                {'column': 'CHildren', 'type': 'int'},
            ],
            ensure_selected_column=False,
        )
        self.model = DataGridModel(self.datasource, None, None)
        self.model.active_params['order_by'] = '__id'
        self.model.refresh()

    def test_hierarchy(self):
        """Test that iter rows will load database rows as required."""
        self.assertEqual(self.model.rows.children_len, 4)
        self.assertEqual(
            [row.data[0] for row in self.model.rows],
            ['file-0', 'file-1', 'folder-0', 'folder-1'])
        self.assertEqual(self.model.rows.path, ())

        # folder-0
        self.assertEqual(len(self.model.rows[2]), 0)
        self.assertEqual(self.model.rows[2].children_len, 2)
        self.model.add_rows(parent_node=self.model.rows[2])
        self.assertEqual(
            [row.data[0] for row in self.model.rows[2]],
            ['file-0-0', 'file-0-1'])
        self.assertEqual(self.model.rows[2].path, (2, ))

        # folder-1
        self.assertEqual(len(self.model.rows[3]), 0)
        self.assertEqual(self.model.rows[3].children_len, 3)
        self.model.add_rows(parent_node=self.model.rows[3])
        self.assertEqual(
            [row.data[0] for row in self.model.rows[3]],
            ['file-1-0', 'file-1-1', 'folder-1-0'])
        self.assertEqual(self.model.rows[3].path, (3, ))

        # folder-1-0
        self.assertEqual(len(self.model.rows[3][2]), 0)
        self.assertEqual(self.model.rows[3][2].children_len, 1)
        self.model.add_rows(parent_node=self.model.rows[3][2])
        self.assertEqual(
            [row.data[0] for row in self.model.rows[3][2]],
            ['file-1-0-0'])
        self.assertEqual(self.model.rows[3][2].path, (3, 2))

    def test_iter_rows(self):
        """Test that iter rows will load database rows as required."""
        self.assertNotEqual(
            {tuple(row.data) for row in self.model.iter_rows(load_rows=False)},
            set(TEST_DATA[self.table]['data']))
        self.assertEqual(
            {tuple(row.data) for row in self.model.iter_rows(load_rows=True)},
            set(TEST_DATA[self.table]['data']))

    def test_get_iter(self):
        """Test that get_iter returns a valid way to access data."""
        for path, expected_value in [
                ((0, ), 'file-0'),
                ((3, ), 'folder-1'),
                ((3, 2), 'folder-1-0'),
                ((3, 1), 'file-1-1')]:
            itr = self.model.get_iter(path)
            self.assertEqual(self.model.get_value(itr, 0), expected_value)

    def test_iter_has_child(self):
        """Test that iter_has_child returns valid information."""
        for path, has_children in [
                ((0, ), False),
                ((3, ), True),
                ((3, 2), True),
                ((3, 1), False)]:
            itr = self.model.get_iter(path)
            self.assertEqual(self.model.iter_has_child(itr), has_children)

    def test_iter_n_children(self):
        """Test that iter_m_childrem returns valid number of children."""
        for path, children_len in [
                ((0, ), 0),
                ((3, ), 3),
                ((3, 2), 1),
                ((3, 1), 0)]:
            itr = self.model.get_iter(path)
            self.assertEqual(self.model.iter_n_children(itr), children_len)

    def test_iter_parent(self):
        """Test that iter_parent returns valid parent for row."""
        for path in [(0, ), (3, )]:
            itr = self.model.get_iter(path)
            self.assertEqual(self.model.iter_parent(itr), None)

        for path, parent_path in [
                ((3, 2), (3, )),
                ((3, 1), (3, ))]:
            # Iter is not the same and comparing them will fail, even if they
            # are pointing to the same row. Use path for this comparison.
            parent = self.model.get_path(self.model.get_iter(parent_path))
            itr = self.model.get_iter(path)

    def test_iter_next(self):
        """Test that iter_next returns iter for parent's next row."""
        for path, next_path in [
                ((2, ), (3, )),
                ((3, 1), (3, 2))]:
            # Iter is not the same and comparing them will fail, even if they
            # are pointing to the same row. Use path for this comparison.
            itr = self.model.get_iter(path)
            self.assertEqual(
                self.model.get_path(self.model.iter_next(itr)),
                self.model.get_path(self.model.get_iter(next_path)))

    def test_iter_nth_child(self):
        """Test that iter_nth_child returns iter parent's for nth child."""
        for path, pos, child_path in [
                (None, 1, (1, )),
                ((3, ), 1, (3, 1))]:
            # Iter is not the same and comparing them will fail, even if they
            # are pointing to the same row. Use path for this comparison.
            itr = path and self.model.get_iter(path)
            self.assertEqual(
                self.model.get_path(self.model.iter_nth_child(itr, pos)),
                self.model.get_path(self.model.get_iter(child_path)))

    def test_iter_children(self):
        """Test that iter_children returns iter fir parent's first child."""
        # Iter is not the same and comparing them will fail, even if they
        # are pointing to the same row. Use path for this comparison.
        path = self.model.get_path(self.model.get_iter((0, )))
        self.assertEqual(
            self.model.get_path(self.model.iter_children()), path)

        itr = self.model.get_iter((3, ))
        self.assertEqual(
            self.model.get_path(self.model.iter_children(itr)),
            self.model.get_path(self.model.get_iter((3, 0))))


class TransformationsTest(unittest.TestCase):

    """Test transformations done by DataGridModel."""

    _ESCAPED_HTML = """
        &lt;img class=&quot;size-medium wp-image-113&quot;
             style=&quot;margin: 666px;&quot; title=&quot;xxx&quot;
             src=&quot;http://something.org/xxx-111x222.jpg&quot;
             alt=&quot;&quot; width=&quot;300&quot; /&gt;
    """
    _UNESCAPED_HTML = """
        <img class="size-medium wp-image-113"
             style="margin: 666px;" title="xxx"
             src="http://something.org/xxx-111x222.jpg"
             alt="" width="300" />
    """

    def setUp(self):  # noqa
        """Create test data."""
        self.datagrid_model = DataGridModel(
            data_source=SQLiteDataSource(
                '', 'test',
                ensure_selected_column=False),
            get_media_callback=mock.MagicMock(),
            decode_fallback=mock.MagicMock()
        )

    def test_html_transform(self):
        """Test html transformation on datagrid."""
        self.assertEqual(self._transform('html', None), '<NULL>')
        self.assertEqual(
            self._transform('html', self._ESCAPED_HTML),
            '<img class="size-medium wp-image-113" style="margin: 666px;" '
            'title="xxx" src="http://something.org/x [...]')

    def test_html_transform_no_max_lenth(self):
        """Test html transformation on datagrid without max_length."""
        with mock.patch('datagrid_gtk3.ui.grid.get_transformer') as gt:
            gt.return_value = lambda v, **kw: html_transform(
                v, max_length=None, oneline=True)
            self.assertEqual(
                self._transform('html', self._ESCAPED_HTML),
                '<img class="size-medium wp-image-113" style="margin: 666px;" '
                'title="xxx" src="http://something.org/xxx-111x222.jpg" '
                'alt="" width="300" />')

    def test_html_transform_no_oneline(self):
        """Test html transformation on datagrid without oneline."""
        with mock.patch('datagrid_gtk3.ui.grid.get_transformer') as gt:
            gt.return_value = lambda v, **kw: html_transform(
                v, max_length=None, oneline=False)
            self.assertEqual(
                self._transform('html', self._ESCAPED_HTML),
                self._UNESCAPED_HTML)

    def test_timestamp_transform(self):
        """Return valid datetime with valid seconds input."""
        self.assertEqual(
            self._transform('timestamp', None), '')
        self.assertEqual(
            self._transform('timestamp', 0),
            '1970-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp', 1104537600),
            '2005-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp', -134843428),
            '1965-09-23 07:29:32')
        self.assertEqual(
            self._transform('timestamp', -1),
            '1969-12-31 23:59:59')

    def test_timestamp_transform_invalid(self):
        """Return the value as a string when it could not be converted."""
        self.assertEqual(
            self._transform('timestamp', 315532801000), '315532801000')
        self.assertEqual(
            self._transform('timestamp', -315532801000), '-315532801000')
        self.assertEqual(
            self._transform('timestamp', 'invalid string'), 'invalid string')
        self.assertEqual(
            self._transform('timestamp', []), '[]')

    def test_timestamp_ms_transform(self):
        """Return valid datetime with valid miliseconds input."""
        self.assertEqual(
            self._transform('timestamp_ms', 1104537600 * 10 ** 3),
            '2005-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp_ms', -134843428 * 10 ** 3),
            '1965-09-23 07:29:32')

    def test_timestamp_Ms_transform(self):
        """Return valid datetime with valid microseconds input."""
        self.assertEqual(
            self._transform('timestamp_Ms', None), '')
        self.assertEqual(
            self._transform('timestamp_Ms', 1104537600 * 10 ** 6),
            '2005-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp_Ms', -134843428 * 10 ** 6),
            '1965-09-23 07:29:32')

    def test_timestamp_apple_transform(self):
        """Return valid datetime with valid apple timestamp input."""
        self.assertEqual(
            self._transform('timestamp_apple', None), '')
        self.assertEqual(
            self._transform('timestamp_apple', 0),
            '2001-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp_apple', 1104537600),
            '2036-01-02 00:00:00')
        self.assertEqual(
            self._transform('timestamp_apple', -134843428),
            '1996-09-23 07:29:32')
        self.assertEqual(
            self._transform('timestamp_apple', -1),
            '2000-12-31 23:59:59')

    def test_timestamp_webkit_transform(self):
        """Return valid datetime with valid webkit timestamp input."""
        self.assertEqual(
            self._transform('timestamp_webkit', None), '')
        self.assertEqual(
            self._transform('timestamp_webkit', 0),
            '1601-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp_webkit', 1104537600),
            '1601-01-01 00:18:24')
        self.assertEqual(
            self._transform('timestamp_webkit', 1104537600 * 10 ** 6),
            '1636-01-02 00:00:00')
        self.assertEqual(
            self._transform('timestamp_webkit', -134843428 * 10 ** 6),
            '1596-09-23 07:29:32')
        self.assertEqual(
            self._transform('timestamp_webkit', -1),
            '1600-12-31 23:59:59')

    def test_timestamp_julian_transform(self):
        """Return valid datetime with valid julian date input."""
        self.assertEqual(
            self._transform('timestamp_julian', None), '')
        self.assertEqual(
            self._transform('timestamp_julian', 2457093.5),
            '2015-03-12 00:00:00')
        self.assertEqual(
            self._transform('timestamp_julian', 2457093.75),
            '2015-03-12 06:00:00')
        self.assertEqual(
            self._transform('timestamp_julian', 2440587.5),
            '1970-01-01 00:00:00')
        self.assertEqual(
            self._transform('timestamp_julian', 2439283.0),
            '1966-06-06 12:00:00')

    def test_timestamp_julian_date_transform(self):
        """Return valid datetime with valid julian date input."""
        self.assertEqual(
            self._transform('timestamp_julian_date', None), '')
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
            self._transform('timestamp_midnight', None), '')
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
            self._transform('timestamp_midnight_ms', None), '')
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
            self._transform('timestamp_midnight_Ms', None), '')
        self.assertEqual(
            self._transform('timestamp_midnight_Ms', 0),
            '00:00:00')
        self.assertEqual(
            self._transform('timestamp_midnight_Ms', 530 * 10 ** 6),
            '00:08:50')
        self.assertEqual(
            self._transform('timestamp_midnight_Ms', 8493 * 10 ** 6),
            '02:21:33')

    def test_datetime_transform(self):
        """Return datetime in isoformat after datetime.datetime input."""
        self.assertEqual(
            self._transform('datetime', datetime.datetime(2015, 3, 11)),
            '2015-03-11 00:00:00')
        self.assertEqual(
            self._transform('datetime', datetime.datetime(2000, 8, 22, 6, 12)),
            '2000-08-22 06:12:00')

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
        image = Image.open(imageutils.get_icon_filename(['image'], 48))
        image.load()

        _add_border_func = imageutils.add_border
        def _add_border(*args, **kwargs):
            _add_border_func(*args, **kwargs)
            return image

        _add_drop_shadow_func = imageutils.add_drop_shadow
        def _add_drop_shadow(*args, **kwargs):
            _add_drop_shadow_func(*args, **kwargs)
            return image

        cm = imageutils.ImageCacheManager.get_default()
        self.datagrid_model.image_draw_border = True
        self.datagrid_model.image_load_on_thread = False
        self.datagrid_model.image_max_size = 123

        with contextlib.nested(
                mock.patch('datagrid_gtk3.utils.imageutils.add_drop_shadow'),
                mock.patch('datagrid_gtk3.utils.imageutils.add_border'),
                mock.patch('datagrid_gtk3.utils.imageutils.Image.open'),
                mock.patch.object(image, 'thumbnail')) as (
                    add_drop_shadow, add_border, open_, thumbnail):
            add_border.side_effect = _add_border
            add_drop_shadow.side_effect = _add_drop_shadow

            open_.return_value = image
            self.assertIsInstance(
                self._transform('image', 'file:///xxx'),
                GdkPixbuf.Pixbuf)

            thumbnail.assert_called_once_with((123, 123), Image.BICUBIC)
            open_.assert_called_once_with('/xxx')
            add_border.assert_called_once_with(
                image, border_size=cm.IMAGE_BORDER_SIZE)
            add_drop_shadow.assert_called_once_with(
                image, border_size=cm.IMAGE_BORDER_SIZE,
                offset=(cm.IMAGE_SHADOW_OFFSET, cm.IMAGE_SHADOW_OFFSET))

    @mock.patch('datagrid_gtk3.utils.imageutils.add_drop_shadow')
    @mock.patch('datagrid_gtk3.utils.imageutils.add_border')
    def test_image_transform_without_border(self, add_border, add_drop_shadow):
        """Make sure the right functions are called to transform the image."""
        image = Image.open(imageutils.get_icon_filename(['unknown'], 48))
        image.load()

        add_border.return_value = image
        add_drop_shadow.return_value = image

        self.datagrid_model.image_max_size = 123
        self.datagrid_model.image_draw_border = False
        self.datagrid_model.image_load_on_thread = False

        with contextlib.nested(
                mock.patch('datagrid_gtk3.utils.imageutils.Image.open'),
                mock.patch.object(image, 'thumbnail')) as (open_, thumbnail):
            open_.return_value = image
            self.assertIsInstance(
                self._transform('image', 'file:///xxx'),
                GdkPixbuf.Pixbuf)

            thumbnail.assert_called_once_with((123, 123), Image.BICUBIC)
            open_.assert_called_once_with('/xxx')
            # This is because of a PIL issue. See
            # datagrid_gtk3.utils.transformations.image_transform for more
            # details
            self.assertEqual(add_border.call_count, 1)
            self.assertEqual(add_drop_shadow.call_count, 0)

    def test_custom_transform(self):
        """Test custom transformations."""
        def test_transform(value, options=1):
            return options * value.upper()

        transformations.register_transformer('test', test_transform)
        try:
            self.assertEqual(self._transform('test', 'x'), 'X')
            self.assertEqual(
                self._transform('test', 'x', transform_options=2), 'XX')
        finally:
            transformations.unregister_transformer('test')

    def _transform(self, transform_type, value, transform_options=None):
        self.datagrid_model.columns = [
            {'name': transform_type,
             'transform': transform_type,
             'transform_options': transform_options,
             'from_config': True}]
        return self.datagrid_model.get_formatted_value(value, 0)


if __name__ == '__main__':
    unittest.main()
