"""Module containing classes for datagrid MVC implementation."""
import base64
import os
from datetime import datetime

from gi.repository import (
    GLib,
    GObject,
    GdkPixbuf,
    Gtk,
    Pango,
)
from pygtkcompat.generictreemodel import GenericTreeModel

from . import popupcal
from .uifile import UIFile

GRID_LABEL_MAX_LENGTH = 100
_MEDIA_FILES = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    os.pardir,
    "data",
    "media"
)

_no_image_loader = GdkPixbuf.PixbufLoader.new_with_type("png")
_no_image_loader.write(base64.b64decode("""
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAABmJLR0QA/wD/AP+gvaeTAAAACXBI
WXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3wEPEDYaIuf2wwAAABl0RVh0Q29tbWVudABDcmVhdGVk
IHdpdGggR0lNUFeBDhcAAAANSURBVAjXY2BgYGAAAAAFAAFe8yo6AAAAAElFTkSuQmCC
"""))
# A trivial 1px transparent png to be used on CellRendererPixbuf when there's
# no data there. Due to possible bug on gtk, passing None to it will make it
# repeat the lastest value read in a row for that column
NO_IMAGE_PIXBUF = _no_image_loader.get_pixbuf()


class DataGridContainer(UIFile):

    """Provides UI container for tabular data TreeStore grid.

    :param window: Window for main launching application -- needed for dialog
        interaction
    :type window: :class:`Gtk.Window`
    """

    UI_FNAME = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'glade',
        'datagrid.glade')

    def __init__(self, window):
        """Set up container."""
        self.window = window
        UIFile.__init__(self, self.UI_FNAME)


def default_decode_fallback(obj):
    """Called for decoding an object to a string when `unicode(obj)` fails.

    :param obj: Any python object.
    :rtype: unicode
    """
    return repr(obj)


def default_get_full_path(relative_path):
    """Returns a full paths to a file when
    given a relative path, or None if the file isn't available.

    :param relative_path: The relative path to a file.
    :type relative_path: str
    :rtype: str or None
    """
    full_path = os.path.join(_MEDIA_FILES, relative_path)
    if os.path.exists(full_path):
        return full_path


class DataGridController(object):

    """Sets up UI controls to manipulate datagrid model/view.

    :param container: ``UIFile`` instance providing ``Gtk.Box`` and
        access to GTK widgets for controller
    :type container: :class:`DataGridContainer`
    :param data_source: Database backend instance
    :type data_source: :class:`datagrid_gtk3.db.sqlite.SQLiteDataSource`
    :param selected_record_callback:
        Function to execute when a record is selected in the grid
    :type selected_record_callback: function
    :param bool has_checkboxes: Whether record rows have a checkbox
    :param decode_fallback: Optional callable for converting objects to
        strings in case `unicode(obj)` fails.
    :type decode_fallback: callable
    :param get_full_path: Callable for returning full paths to files when
        given a relative path, or None if the file isn't available.
    :type get_full_path: callable

    """

    MIN_TIMESTAMP = 0  # 1970
    MAX_TIMESTAMP = 2147485547  # 2038

    def __init__(self, container, data_source, selected_record_callback=None,
                 has_checkboxes=True, decode_fallback=None, get_full_path=None):
        """Setup UI controls and load initial data view."""
        if decode_fallback is None:
            decode_fallback = default_decode_fallback
        if get_full_path is None:
            get_full_path = default_get_full_path

        self.decode_fallback = decode_fallback
        self.get_full_path = get_full_path

        self.container = container
        self.selected_record_callback = selected_record_callback
        vscroll = container.grid_scrolledwindow.get_vadjustment()
        self.view = DataGridView(None, vscroll, has_checkboxes)
        self.container.grid_scrolledwindow.add(self.view)

        # select all checkbutton
        checkbutton_select_all = self.container.checkbutton_select_all
        if has_checkboxes:
            checkbutton_select_all.connect(
                'toggled', self.on_select_all_toggled)
            self.view.connect('cursor-changed', self.on_view_selection_changed)
        else:
            checkbutton_select_all.destroy()

        # select columns toggle button
        self.container.togglebutton_cols.connect(
            'toggled', self.on_columns_btn_toggled)

        # date range widgets
        self.container.image_start_date.set_from_file(
            get_full_path('icons/calendar22.png')
        )
        self.container.image_end_date.set_from_file(
            get_full_path('icons/calendar22.png')
        )
        self.date_start = popupcal.DateEntry(self.container.window)
        self.date_start.set_editable(False)
        self.date_start.set_sensitive(False)
        self.date_start.connect('date_changed', self.on_date_change, 'start')
        # FIXME: ^^ use hyphen in signal name
        self.container.vbox_start_date.pack_start(
            self.date_start, expand=False, fill=True, padding=0)
        self.date_end = popupcal.DateEntry(self.container.window)
        self.date_end.set_editable(False)
        self.date_end.set_sensitive(False)
        self.date_end.connect('date_changed', self.on_date_change, 'end')
        self.container.vbox_end_date.pack_start(
            self.date_end, expand=False, fill=True, padding=0)

        # search widget
        self.container.entry_search.connect('activate', self.on_search_clicked)
        self.container.button_search.connect('clicked', self.on_search_clicked)

        # clear button
        self.container.button_clear.connect('clicked', self.on_clear_clicked)

        self.container.grid_vbox.show_all()

        self.bind_datasource(data_source)

    def bind_datasource(self, data_source):
        """Binds a data source to the datagrid.

        :param data_source: The data source to bind.
        :type data_source: :class:`datagrid_gtk3.db.DataSource`
        """
        self.model = DataGridModel(data_source,
                                   self.get_full_path,
                                   self.decode_fallback)
        self.model.connect('data-loaded', self.on_data_loaded)
        self.view.model = self.model

        liststore_date_cols = Gtk.ListStore(str, str)
        if self.model.datetime_columns:
            self.date_start.set_sensitive(True)
            self.date_end.set_sensitive(True)

        for column in self.model.datetime_columns:
            liststore_date_cols.append((column['name'], column['display']))

        combox_date_cols = self.container.combobox_date_columns
        old_model = combox_date_cols.get_model()
        if old_model:
            del old_model
        combox_date_cols.set_model(liststore_date_cols)
        if not combox_date_cols.get_cells():
            cell = Gtk.CellRendererText()
            combox_date_cols.pack_start(cell, True)
            combox_date_cols.add_attribute(cell, 'text', 1)
            combox_date_cols.set_active(0)
            combox_date_cols.connect('changed', self.on_date_change, None)

        self.view.reset()
        self.view.set_result()

    ###
    # Callbacks
    ###

    def on_columns_btn_toggled(self, widget):
        """Show checkbox list of columns to display.

        :param widget: the ToggleButton that launches the list
        :type widget: :class:`Gtk.ToggleButton`
        """
        if widget.get_active():
            dialog = Gtk.Dialog(
                None, self.container.window,
                Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 Gtk.STOCK_OK, Gtk.ResponseType.OK)
            )
            for column in self.model.columns:
                checkbutton = Gtk.CheckButton(column['display'])
                if not column['name'].startswith('__'):
                    active = (self.model.display_columns is None
                              or column['name'] in self.model.display_columns)
                    checkbutton.set_active(active)
                    dialog.vbox.pack_start(
                        checkbutton, expand=True, fill=True, padding=0)
                checkbutton.connect(
                    'toggled',
                    self.on_column_checkbutton_toggled,
                    column['name'])
            dialog.set_decorated(False)
            dialog.action_area.hide()
            dialog.show_all()
            result = dialog.run()
            if result == Gtk.ResponseType.OK:
                self.model.data_source.update_selected_columns(
                    self.model.display_columns
                )
                self.view.reset()
                self.view.set_result(self.view.active_params)
                widget.set_active(False)
                dialog.destroy()
            else:
                widget.set_active(False)
                dialog.destroy()

    def on_column_checkbutton_toggled(self, widget, name):
        """Set the list of columns to display based on column checkboxes.

        :param widget: checkbox widget for selected/deselected column
        :type widget: :class:`Gtk.CheckButton`
        :param str name: name of the column to add/remove from list
        """
        if self.model.display_columns is None:
            self.model.display_columns = [
                column['name'] for column in self.model.columns
                if not column['name'].startswith('__')]
        if widget.get_active():
            self.model.display_columns.append(name)
        else:
            self.model.display_columns.remove(name)
        self.model.display_columns = list(set(self.model.display_columns))

    def on_view_selection_changed(self, view):
        """Get the data for a selected record and run optional callback.

        :param view: The treeview containing the row
        :type view: Gtk.TreeView

        """
        selection = view.get_selection()
        model, row_iterator = selection.get_selected()
        if row_iterator:
            row = model[row_iterator]
            selected_id = row[1]
            record = self.model.data_source.get_single_record(selected_id)
            if self.selected_record_callback:
                self.selected_record_callback(record)

    def on_data_loaded(self, model, total_recs):
        """Update the total records label.

        :param model: Current datagrid model
        :type model: :class:`DataGridModel`
        :param int total_recs: Total records for current query

        """
        self.container.label_num_recs.set_markup(
            '<small>%d records</small>' % total_recs
        )

    def on_select_all_toggled(self, checkbutton):
        """Select all records in current recordset and update model/view.

        :param checkbutton: "Select all" checkbutton
        :type: :class:`Gtk.CheckButton`

        """
        where_params = {}
        if checkbutton.get_active():
            val = True
        else:
            val = False
        if 'where' in self.view.active_params:
            where_params['where'] = self.view.active_params['where']
        ids = self.model.data_source.get_all_record_ids(where_params)
        self.model.update_data_source('__selected', val, ids)
        self.view.reset()
        self.view.set_result(self.view.active_params)

    def on_search_clicked(self, widget):
        """Execute the full-text search for given keyword.

        :param widget: The widget that called the event
        :type widget: :class:`Gtk.Widget`
        """
        search = self.container.entry_search.get_text()
        update_dict = {
            'search': {
                'operator': '=',
                'param': search
            }
        }
        self._refresh_view(update_dict)

    def on_date_change(self, widget, data=None):
        """Refresh the view with chosen date range.

        :param widget: The widget that called the event
        :type widget: :class:`Gtk.Widget`
        :param data: Arbitrary data passed by widget.
        :data type: None
        """
        start_date = self.date_start.get_text()
        end_date = self.date_end.get_text()
        if start_date:
            start_date_str = start_date + ' 00:00'
            # TODO: restore use of time as well as date in UI
            start_timestamp = self._get_timestamp_from_str(start_date_str)
        else:
            start_timestamp = self.MIN_TIMESTAMP
        if end_date:
            end_date_str = end_date + ' 23:59'
            end_timestamp = self._get_timestamp_from_str(end_date_str)
        else:
            end_timestamp = self.MAX_TIMESTAMP
        active_date_column = self.container.combobox_date_columns.get_active()
        model_date_columns = self.container.combobox_date_columns.get_model()
        # clear all params from previous date column range select
        remove_columns = [column[0] for column in model_date_columns]
        if active_date_column >= 0:
            column = model_date_columns[active_date_column][0]
        update_dict = {
            column: {
                'operator': 'range',
                'param': (start_timestamp, end_timestamp)
            }
        }
        self._refresh_view(update_dict, remove_columns)

    def on_clear_clicked(self, checkbutton):
        """Clear the UI controls and refresh the view to original table.

        :param checkbutton: The widget that called the event
        :type checkbutton: :class:`Gtk.CheckButton`
        """
        self.date_start.set_date(None)
        self.date_end.set_date(None)
        self.container.entry_search.set_text('')
        self._refresh_view(clear=True)

    ###
    # Private
    ###

    def _get_timestamp_from_str(self, date_str):
        """Convert timestamp from string to timestamp.

        Converts string in format supplied by ``popupcal.DateEntry`` widget
        to Unix timestamp.

        :param str date_str: Date string like ``'19-Jun-2014'``
        :return: timestamp
        :rtype: int
        """
        date = datetime.strptime(date_str, '%d-%b-%Y %H:%M')
        timestamp = int(date.strftime('%s'))
        # TODO: may need to restore below code when adding times to UI
        # utc_timestamp = int(datetime.fromutctimestamp(timestamp).
        #                     strftime("%s"))
        # diff = timestamp - utc_timestamp
        # timestamp = utc_timestamp += diff
        # ## END TODO
        return timestamp

    def _refresh_view(self, update_dict=None, remove_keys=None, clear=False):
        """Reload the grid with any filter/sort parameters.

        :param dict update_dict: Any ``where`` parameters with which to update
            the currently active parameters
        :param remove_keys: List of keys to delete from ``where`` parameters
        :type remove_keys: list
        :param bool clear: Remove all active params in view if True

        """
        if clear:
            self.view.active_params = {}
        else:
            if 'where' in self.view.active_params:
                if remove_keys:
                    for key in remove_keys:
                        if key in self.view.active_params['where']:
                            self.view.active_params['where'].pop(key)
                # add to existing parameters
                if update_dict:
                    self.view.active_params['where'].update(update_dict)
            else:
                if update_dict:
                    self.view.active_params['where'] = update_dict
        self.view.reset()
        self.view.set_result(self.view.active_params)


class DataGridView(Gtk.TreeView):

    """A ``Gtk.TreeView`` for displaying data from a ``DataGridModel``.

    :param model: The model providing the tabular data for the grid
    :type model: :class:`DataGridModel`
    :param vscroll: List of keys to delete from ``where`` parameters
    :type vscroll: :class:`Gtk.Adjustment`
    :param bool has_checkboxes: Whether record rows have a checkbox

    """

    # Column widths
    MIN_WIDTH = 40
    MAX_WIDTH = 400
    SAMPLE_SIZE = 50

    def __init__(self, model, vscroll, has_checkboxes=True):
        """Set the model and setup scroll bar."""
        super(DataGridView, self).__init__()
        self.model = model
        self.has_checkboxes = has_checkboxes
        vscroll.connect('value-changed', self.on_scrolled)
        self.tv_columns = []
        self.set_rules_hint(True)
        self.active_sort_column = None
        self.active_sort_column_order = None
        self.active_params = {}
        self.active_page = 0

    def set_result(self, params=None):
        """Set the result and update the grid.

        An example of the ``params`` dict looks like this::

            {
                'order_by': 'title',
                'where':
                {
                    'search':
                    {
                        'operator': '=',
                        'param': 'Google'
                    }
                },
                'desc': False
            }

        :param params: Dictionary of parameters
        :type params: dict
        """
        old_model = self.get_model()
        if old_model:
            del old_model
        self.model.refresh(params)
        self.set_model(self.model)
        self._setup_columns()

    def reset(self):
        """Reset the grid."""
        old_model = self.get_model()
        if old_model:
            del old_model
        model = Gtk.ListStore(int)
        self.set_model(model)
        while self.get_columns():
            col = self.get_column(0)
            self.remove_column(col)
        self.active_page = 0
        if 'page' in self.active_params:
            self.active_params.pop('page')

    ###
    # Callbacks
    ###

    def on_scrolled(self, vadj):
        """Load new records upon scroll to end of visible rows.

        :param vadj: Adjustment widget associated with vertical scrollbar
        :type vadj: :class:`Gtk.Adjustment`
        """
        scrolled_bottom = (
            vadj.get_value() == (vadj.get_upper() - vadj.get_page_size())
            or vadj.get_page_size() == vadj.get_upper()
        )
        if scrolled_bottom:
            self.active_params['page'] = self.active_page + 1
            recs_added = self.model.add_rows(self.active_params)
            if recs_added:
                self.active_page += 1
        return False

    def on_toggle(self, cell, path, col_index):
        """Toggle row selected checkbox, and update the model.

        :param cell: The toggle renderer widget
        :type cell: :class:`Gtk.CellRendererToggle`
        :param int path: int representing the row in the view
        :param int col_index: The column the toggle widget is in

        """
        if path is not None:
            itr = self.model.get_iter(path)
            val = self.model.get_value(itr, col_index)
            self.model.set_value(itr, col_index, not val)

    def on_tvcol_clicked(self, widget, column):
        """Sort the records by the given column.

        :param widget: The widget of the column being sorted
        :type widget: :class:`Gtk.TreeViewColumn`
        :param column: The column name being sorted, used for query construct
        :type column: str

        """
        sort_order = widget.get_sort_order()
        for col in self.tv_columns:
            # remove sort indicators from inactive cols
            col.set_sort_indicator(False)
        widget.set_sort_indicator(True)
        if sort_order == Gtk.SortType.ASCENDING:
            new_sort_order = Gtk.SortType.DESCENDING
        else:
            new_sort_order = Gtk.SortType.ASCENDING
        widget.set_sort_order(new_sort_order)
        self.active_sort_column = column
        self.active_sort_column_order = new_sort_order
        desc = sort_order == Gtk.SortType.DESCENDING
        self.active_params.update({'order_by': column, 'desc': desc})
        self.reset()
        self.set_result(self.active_params)

    ###
    # Private
    ###

    def _setup_columns(self):
        """Configure the column widgets in the view."""
        if self.has_checkboxes:
            # NOTE: assumption here is that col index 0 is _selected bool field
            toggle_cell = Gtk.CellRendererToggle()
            toggle_cell.connect('toggled', self.on_toggle, 0)
            col = Gtk.TreeViewColumn('', toggle_cell, active=0)
            self.append_column(col)

        samples = self.model.rows[:self.SAMPLE_SIZE]
        for column_index, column in enumerate(self.model.columns):
            item = column['name']
            display = (self.model.display_columns is None
                       or item in self.model.display_columns)
            if not self.model.data_source.display_all:
                # First column is "_selected" checkbox,
                # second is invisible primary key ID
                display = display and column_index > 1
            if display:
                item_display = column['display']
                if column['transform'] in ['boolean', 'image']:
                    renderer = Gtk.CellRendererPixbuf()
                    cell_renderer_kwargs = {'pixbuf': column_index}
                else:
                    renderer = Gtk.CellRendererText()
                    renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
                    if column['type'] in (int, long, float):
                        renderer.set_property('xalign', 1)
                    cell_renderer_kwargs = {'text': column_index}
                lbl = '%s' % (item_display.replace('_', '__'),)
                col = Gtk.TreeViewColumn(lbl, renderer, **cell_renderer_kwargs)
                col.connect('clicked', self.on_tvcol_clicked, item)
                col.set_resizable(True)
                # Set the minimum width for the column based on the width
                # of the label and some padding
                col.set_min_width(self._get_pango_string_width(lbl) + 14)
                col.set_fixed_width(
                    self._get_best_column_width(column_index, samples))
                col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                if item == self.active_sort_column:
                    col.set_sort_indicator(True)
                    col.set_sort_order(self.active_sort_column_order)
                self.append_column(col)
                self.tv_columns.append(col)
        self.set_headers_clickable(True)

    @staticmethod
    def _get_pango_string_width(string):
        """Get the width of a string in pixels.

        Based on:
        http://python.6.x6.nabble.com/Getting-string-with-in-pixels-td1944346.html

        :param string: String to be measured.
        :return: Width of the string in pixels using the default text font.
        :rtype: int
        """
        label = Gtk.Label()
        pango_layout = label.get_layout()
        pango_layout.set_markup(string)
        pango_layout.set_font_description(label.get_style().font_desc)
        width, _ = pango_layout.get_pixel_size()
        label.destroy()
        return width

    def _get_best_column_width(self, colnum, samples):
        """Determine a reasonable column width for the given column.

        :param int colnum: Index of column
        :param int samples: Number of rows to use to determine best width
        :return: optimal column width
        :rtype: int
        """
        label = '  %s  ' % self.model.columns[colnum]['display']
        layout = self.create_pango_layout(label)
        label_width = layout.get_pixel_size()[0]
        lengths = set()
        model = self.get_model()
        for row in samples:
            value = model.get_formatted_value(row[colnum], colnum)
            if isinstance(value, basestring):
                lines = value.splitlines()
                if lines:
                    value = lines[0]
                del lines
                try:
                    layout = self.create_pango_layout('  %s  ' % value)
                except TypeError:
                    # NOTE: unescaped hex data can cause an error like this:
                    # TypeError: Gtk.Widget.create_pango_layout() argument 1
                    #   must be string without null bytes, not unicode
                    layout = self.create_pango_layout('')
                lengths.add(layout.get_pixel_size()[0])
        if lengths:
            max_length = max(lengths)
        else:
            max_length = 1
        width = max_length
        if width < self.MIN_WIDTH:
            width = self.MIN_WIDTH
            if width < label_width:
                width = label_width + 20
        elif width > self.MAX_WIDTH:
            width = self.MAX_WIDTH
        return width


class DataGridModel(GenericTreeModel):

    """Underlying model for data grid view.

    This is a ``TreeModel`` class for representing data from a persistent data
    store such as a SQLite database table.

    :param data_source: Persistent data source to populate model
    :type data_source: :class:`datagrid_gtk3.db.sqlite.SQLiteDataSource`
    :param get_media_callback: Function to retrieve media file
    :type get_media_callback: callable
    :param decode_fallback: Callable for converting objects to
        strings in case `unicode(obj)` fails.
    :type decode_fallback: callable
    :param str encoding_hint: Encoding to use for rendering strings

    It may be  a question of changing parent class(es) and changing eg.
    ``on_get_flags`` to ``do_get_flags`` etc.

    """

    __gsignals__ = {
        'data-loaded': (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    MIN_TIMESTAMP = 0  # 1970
    MAX_TIMESTAMP = 2147485547  # 2038

    def __init__(self, data_source, get_media_callback, decode_fallback,
                 encoding_hint='utf-8'):
        """Set up model."""
        super(DataGridModel, self).__init__()
        self.data_source = data_source
        self.get_media_callback = get_media_callback
        self.decode_fallback = decode_fallback
        self.columns = self.data_source.columns
        self.datetime_columns = []
        self.column_types = []
        for column in self.columns:
            if column['transform'] == 'datetime':
                self.datetime_columns.append(column)
            self.column_types.append(column['type'])
        self.display_columns = self.data_source.get_selected_columns()
        self.encoding_hint = encoding_hint
        self.selected_cells = list()

        self.rows = None
        self.total_recs = None

    def refresh(self, params):
        """Refresh the model from the data source.

        :param dict params: dict of params used for filtering/sorting/etc.
        """
        self.data_source.load(params)
        self.rows = self.data_source.rows
        self.total_recs = self.data_source.total_recs
        self.emit('data-loaded', self.total_recs)

    def add_rows(self, params):
        """Add rows to the model from a new page of data and update the view.

        :param dict params: dict of params used for filtering/sorting/etc.
        :return: True if update took place, False if not
        :rtype: bool
        """
        path = (len(self.rows) - 1,)
        itr = self.get_iter(path)
        self.data_source.load(params)
        if not self.data_source.rows:
            return False

        for row in self.data_source.rows:
            self.rows.append(row)
            self.row_inserted(path, itr)
        return True

    def update_data_source(self, column, value, ids):
        """Update the model's persistent data source for given records.

        Currently only used for updating "__selected" column.

        Note that the function that uses this must call ``row_changed`` or
        reset grid in order to see changes.

        :param str column: Name of column to update
        :param value: Update value
        :type value: str or int
        :param list ids: List of primary keys of records to update
        """
        param = {column: value}
        self.data_source.update(param, ids)

    def get_formatted_value(self, value, column_index):
        """Get the value to display in the cell.

        :param value: Value from data source
        :type value: str or int or None
        :param int column_index: Index of the column containing the value
        :return: formatted value
        :rtype: unicode or int or bool or None
        """
        col_dict = self.columns[column_index]
        if col_dict['transform'] is None:
            if value is None:
                value = '<NULL>'
                return value

            if isinstance(value, str):
                value = unicode(value, self.encoding_hint, 'replace')
            else:
                try:
                    value = unicode(value)
                except UnicodeDecodeError:
                    value = self.decode_fallback(value)
            value = value.splitlines()
            if value:
                # don't show more than GRID_LABEL_MAX_LENGTH chars in treeview;
                #   helps with performance
                # print value, GRID_LABEL_MAX_LENGTH
                if len(value[0]) > GRID_LABEL_MAX_LENGTH:
                    value = (
                        '%s [...]' % (
                            value[0][:GRID_LABEL_MAX_LENGTH]
                        )
                    )
                else:
                    value = ' '.join(value)
            else:
                value = ''

        elif col_dict['transform'] == 'boolean':
            if col_dict['name'] != '__selected':
                value = self._boolean_transform(value)
            else:
                if value == 1:
                    return True

                # 0 or null
                return False

        elif col_dict['transform'] == 'image':
            if value:
                value = self._image_transform(value)
            else:
                return NO_IMAGE_PIXBUF

        elif col_dict['transform'] == 'datetime':
            if value:
                value = self._datetime_transform(value)
            else:
                return ''

        # FIXME: At the end, if the string is in unicode, it needs to be
        # converted to str or else gtk won't display it on the treeview.
        # Maybe we should handle this better above?
        if isinstance(value, unicode):
            value = str(value.encode(self.encoding_hint))

        return value

    def set_value(self, itr, column, value):
        """Set the value in the model and update the data source with it.

        :param itr: ``TreeIter`` object representing the current row
        :type itr: :class:`Gtk.TreeIter`
        :param int column: Column index for value
        :param value: Update the row/column to this value
        :type value: str or int or bool or None
        """
        path = self.get_path(itr)[0]
        self.rows[path][column] = value
        id_ = self.get_value(itr, 1)
        self.update_data_source(
            self.columns[column]['name'], value, [int(id_)])
        self.row_changed(path, itr)

    ###
    # Transforms
    ###

    def _boolean_transform(self, value):
        """Transform boolean values to a stock image indicating True or False.

        :param bool value: True or False
        """
        img = Gtk.Image()
        if value:
            icon = Gtk.STOCK_YES
        else:
            # NOTE: should be STOCK_NO but looks crappy in Lubuntu
            icon = Gtk.STOCK_CANCEL
        pixbuf = img.render_icon(icon, Gtk.IconSize.MENU)
        return pixbuf

    def _image_transform(self, value):
        """Render a thumbnail of an image for given path.

        :param str value: Path to image file.
        """
        is_image = False
        if value.startswith('file://'):
            # TODO: ensure performance not affected by scaling images
            #   with large recordsets, use file_ = 'icons/image.png' if so
            # TODO: refactor image scaling to its own utility function
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(
                    self.get_media_callback(value[7:])
                )
                orig_width = pixbuf.get_width()
                orig_height = pixbuf.get_height()
                width = int(float(24 * orig_width) / orig_height)
                pic = pixbuf.scale_simple(width, 24, GdkPixbuf.InterpType.BILINEAR)
                is_image = True
            except GLib.GError:
                is_image = False
        if not is_image:
            file_ = 'icons/binary.png'
            pic = GdkPixbuf.Pixbuf.new_from_file(
                self.get_media_callback(file_)
            )
        return pic

    def _datetime_transform(self, value):
        """Transform timestamps to ISO 8601 date format.

        :param int value: Unix timestamp
        """
        timestamp = value
        #  If timestamp value is -1, the actual data is None.
        if timestamp == -1:
            return ''
        # TODO: ??? When is timestamp ever -2?
        if timestamp == -2:
            return ''

        if timestamp < self.MIN_TIMESTAMP:
            return value
        if timestamp > self.MAX_TIMESTAMP:
            # might be milliseconds
            try:
                dt = datetime.utcfromtimestamp(timestamp / 1000)
            except ValueError:
                # Last try, microseconds
                try:
                    dt = datetime.utcfromtimestamp(timestamp / 1000000)
                except ValueError:
                    return timestamp
        else:
            try:
                dt = datetime.utcfromtimestamp(timestamp)
            except ValueError:
                return timestamp

        iso = dt.isoformat()
        return iso

    ###
    # Required implementations for GenericTreeModel
    ###

    def on_get_flags(self):
        """Return the GtkTreeModelFlags for this particular type of model."""
        return Gtk.TreeModelFlags.LIST_ONLY

    def on_get_n_columns(self):
        """Return the number of columns in the model."""
        return len(self.columns)

    def on_get_column_type(self, index):
        """Return the type of a column in the model."""
        if self.columns[index]["name"] == "__selected":
            return bool
        else:
            if self.columns[index]['transform'] in ['boolean', 'image']:
                return GdkPixbuf.Pixbuf

            return str
            # NOTE: int/long column types cannot display None/null values
            #   so just use str for everything except pixbufs instead of
            #   self.column_types[index]

    def on_get_path(self, rowref):
        """Return the tree path (a tuple of indices) for a particular node."""
        return (rowref,)

    def on_get_iter(self, path):
        """Return the node corresponding to the given path (node is path)."""
        if path[0] < len(self.rows):
            return path[0]

        return None

    def on_get_value(self, rowref, column):
        """Return the value stored in a particular column for the node."""
        raw = self.rows[rowref][column]
        val = self.get_formatted_value(raw, column)
        return val

    def on_iter_next(self, rowref):
        """Return the next node at this level of the tree."""
        if rowref + 1 < len(self.rows):
            return rowref + 1

        return None

    def on_iter_children(self, rowref):
        """Return the first child of this node."""
        return 0

    def on_iter_has_child(self, rowref):
        """Return true if this node has children."""
        return False

    def on_iter_n_children(self, rowref):
        """Return the number of children of this node."""
        return len(self.rows)

    def on_iter_nth_child(self, parent, n):
        """Return the nth child of this node."""
        return n

    def on_iter_parent(self, child):
        """Return the parent of this node."""
        return None

    ###
    # END Required implementations for GenericTreeModel
    ###
