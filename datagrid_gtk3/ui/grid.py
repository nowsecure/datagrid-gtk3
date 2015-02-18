"""Module containing classes for datagrid MVC implementation."""
import base64
import os
from datetime import datetime

from gi.repository import (
    GObject,
    GdkPixbuf,
    Gtk,
    Gdk,
    Pango,
)
from pygtkcompat.generictreemodel import GenericTreeModel
from PIL import Image

from datagrid_gtk3.ui import popupcal
from datagrid_gtk3.ui.uifile import UIFile
from datagrid_gtk3.utils import imageutils

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
_no_image_loader.close()
# A trivial 1px transparent png to be used on CellRendererPixbuf when there's
# no data there. Due to possible bug on gtk, passing None to it will make it
# repeat the lastest value read in a row for that column
NO_IMAGE_PIXBUF = _no_image_loader.get_pixbuf()


class OptionsPopup(Gtk.Window):

    """Popup to select which columns should be displayed on datagrid.

    :param toggle_btn: the toggle button responsible for popping this up
    :type toggle_btn: :class:`Gtk.ToggleButton`
    :param controller: the datagrid controller
    :type controller: :class:`DataGridController`
    """

    OPTIONS_PADDING = 5
    MAX_HEIGHT = 500

    (VIEW_TREE,
     VIEW_ICON) = range(2)

    __gsignals__ = {
        'column-visibility-changed': (GObject.SignalFlags.RUN_FIRST,
                                      None, (str, bool)),
        'view-changed': (GObject.SignalFlags.RUN_FIRST, None, (int, ))
    }

    def __init__(self, toggle_btn, controller, *args, **kwargs):
        self._toggle_btn = toggle_btn
        self._toggled_id = self._toggle_btn.connect(
            'toggled', self.on_toggle_button_toggled)
        self._controller = controller

        super(OptionsPopup, self).__init__(
            Gtk.WindowType.POPUP, *args, **kwargs)

        self.connect('button-press-event', self.on_button_press_event)
        self.connect('key-press-event', self.on_key_press_event)

        self._scrolled_window = Gtk.ScrolledWindow(
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            hscrollbar_policy=Gtk.PolicyType.NEVER)

        alignment = Gtk.Alignment()
        alignment.set_padding(5, 5, 5, 5)
        alignment.add(self._scrolled_window)

        self.add(alignment)

    ##
    # Public
    ##

    def popup(self):
        """Show the popup.

        This will show the popup and allow the user to change
        the columns visibility.
        """
        if not self._toggle_btn.get_realized():
            return

        child = self._scrolled_window.get_child()
        if child:
            self._scrolled_window.remove(child)

        vbox = Gtk.VBox()
        for switch in self._get_view_options():
            vbox.pack_start(switch, expand=False, fill=False,
                            padding=self.OPTIONS_PADDING)

        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                        expand=True, fill=True, padding=self.OPTIONS_PADDING)

        for switch in self._get_visibility_options():
            vbox.pack_start(switch, expand=False, fill=False,
                            padding=self.OPTIONS_PADDING)

        self._scrolled_window.add(vbox)

        toplevel = self._toggle_btn.get_toplevel().get_toplevel()
        if isinstance(toplevel, (Gtk.Window, Gtk.Dialog)):
            group = toplevel.get_group()
            if group:
                group.add_window(self)

        x, y = self._get_position()
        self.move(x, y)
        self.show_all()

        allocation = vbox.get_allocation()
        height = min(allocation.height + 2 * self.OPTIONS_PADDING,
                     self.MAX_HEIGHT)
        self.set_size_request(-1, height)

        if not self._popup_grab_window():
            self.popdown()

    def popdown(self):
        """Hide the popup."""
        if not self._toggle_btn.get_realized():
            return

        # Make sure the toggle button is unset when popping down.
        with self._toggle_btn.handler_block(self._toggled_id):
            self._toggle_btn.set_active(False)

        self.grab_remove()
        self.hide()

    ##
    # Private
    ##

    def _popup_grab_window(self):
        """Grab pointer and keyboard on this window.

        By grabbing the pointer and the keyboard, we will be able to
        intercept key-press and button-press events.
        """
        window = self.get_window()
        grab_status = Gdk.pointer_grab(
            window, True,
            (Gdk.EventMask.BUTTON_PRESS_MASK |
             Gdk.EventMask.BUTTON_RELEASE_MASK |
             Gdk.EventMask.POINTER_MOTION_MASK),
            None, None, 0L)
        if grab_status == Gdk.GrabStatus.SUCCESS:
            if Gdk.keyboard_grab(window, True, 0L) != Gdk.GrabStatus.SUCCESS:
                display = window.get_display()
                display.pointer_ungrab(0L)
                return False

        self.grab_add()
        return True

    def _get_position(self):
        """Get the position to show this popup."""
        allocation = self._toggle_btn.get_allocation()
        window = self._toggle_btn.get_window()

        if self._toggle_btn.get_has_window():
            x_coord = 0
            y_coord = 0
        else:
            x_coord = allocation.x
            y_coord = allocation.y

        x, y = window.get_root_coords(x_coord, y_coord)

        return x, y + allocation.height

    def _get_view_options(self):
        """Build view options for datagrid."""
        tv_radio = Gtk.RadioButton(label='Tree View')
        yield tv_radio

        iv_radio = Gtk.RadioButton(label='Icon View', group=tv_radio)
        # We can only change to icon view if we have at least one column
        # with 'image' transformation.
        iv_radio.set_sensitive(
            any(c['transform'] == 'image'
                for c in self._controller.model.columns))

        is_iconview = isinstance(self._controller.view, DataGridIconView)
        iv_radio.set_active(is_iconview)
        tv_radio.connect('toggled', self.on_treeview_radio_toggled)
        yield iv_radio

    def _get_visibility_options(self):
        """Construct the switches based on the actual model columns."""
        model = self._controller.model
        if model.display_columns is None:
            model.display_columns = set(
                column['name']
                for column in model.columns
                if not column['name'].startswith('__')
            )

        for column in model.columns:
            if column['name'].startswith('__'):
                continue

            switch = Gtk.Switch()
            label = Gtk.Label(column['display'])
            switch.set_active(column['name'] in model.display_columns)

            hbox = Gtk.HBox(spacing=5)
            hbox.pack_start(switch, expand=False, fill=True, padding=0)
            hbox.pack_start(label, expand=True, fill=True, padding=0)

            switch.connect(
                'notify::active',
                self.on_column_switch_notify_active, column['name'])

            yield hbox

    ##
    # Callbacks
    ##

    def on_key_press_event(self, window, event):
        """Handle key press events.

        Popdown when the user presses Esc.
        """
        if event.get_keyval()[1] == Gdk.KEY_Escape:
            self.popdown()
            return True
        return False

    def on_button_press_event(self, window, event):
        """Handle button press events.

        Popdown when the user clicks on an area outside this window.
        """
        event_rect = Gdk.Rectangle()
        event_rect.x, event_rect.y = event.get_root_coords()
        event_rect.width = 1
        event_rect.height = 1

        allocation = self.get_allocation()
        window_rect = Gdk.Rectangle()
        window_rect.x, window_rect.y = self._get_position()
        window_rect.width = allocation.width
        window_rect.height = allocation.height

        intersection = Gdk.rectangle_intersect(
            event_rect, window_rect)
        # if the click was outside this window, hide it
        if not intersection[0]:
            self.popdown()

    def on_treeview_radio_toggled(self, widget):
        """Handle changes on the views radio.

        Emit 'view-changed' when the radio selection changes
        """
        self.emit('view-changed',
                  self.VIEW_TREE if widget.get_active() else self.VIEW_ICON)
        self.popdown()

    def on_toggle_button_toggled(self, widget):
        """Show switch list of columns to display.

        :param widget: the ToggleButton that launches the list
        :type widget: :class:`Gtk.ToggleButton`
        """
        if widget.get_active():
            self.popup()
        else:
            self.popdown()

    def on_column_switch_notify_active(self, widget, p_spec, name):
        """Set the list of columns to display based on column checkboxes.

        :param widget: checkbox widget for selected/deselected column
        :type widget: :class:`Gtk.Switch`
        :param str name: name of the column to add/remove from list
        """
        self.emit('column-visibility-changed', name, widget.get_active())


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

    """UI controls to manipulate datagrid model/view.

    :param container: ``UIFile`` instance providing ``Gtk.Box`` and
        access to GTK widgets for controller
    :type container: :class:`DataGridContainer`
    :param data_source: Database backend instance
    :type data_source: :class:`datagrid_gtk3.db.sqlite.SQLiteDataSource`
    :param selected_record_callback:
        Callback to call when a record is selected in the grid
    :type selected_record_callback: `callable`
    :param selected_record_callback:
        Callback to call when an icon is activated on `DataGridIconView`
    :type selected_record_callback: `callable`
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
                 activated_icon_callback=None, has_checkboxes=True,
                 decode_fallback=None, get_full_path=None):
        """Setup UI controls and load initial data view."""
        if decode_fallback is None:
            decode_fallback = default_decode_fallback
        if get_full_path is None:
            get_full_path = default_get_full_path

        self.container = container

        self.decode_fallback = decode_fallback
        self.get_full_path = get_full_path
        self.selected_record_callback = selected_record_callback
        self.activated_icon_callback = activated_icon_callback

        vscroll = container.grid_scrolledwindow.get_vadjustment()
        vscroll.connect('value-changed', self.on_scrolled)

        self.tree_view = DataGridView(None, has_checkboxes=has_checkboxes)
        self.icon_view = DataGridIconView(None, has_checkboxes=has_checkboxes)

        self.tree_view.connect('cursor-changed',
                               self.on_treeview_cursor_changed)
        self.icon_view.connect('selection-changed',
                               self.on_iconview_selection_changed)
        self.icon_view.connect('item-activated',
                               self.on_iconview_item_activated)

        # The treview will be the default view
        self.view = self.tree_view
        self.container.grid_scrolledwindow.add(self.view)

        # select columns toggle button
        options_popup = OptionsPopup(
            self.container.togglebutton_options, self)
        options_popup.connect('column-visibility-changed',
                              self.on_popup_column_visibility_changed)
        options_popup.connect('view-changed', self.on_popup_view_changed)

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
        self.container.entry_search.connect(
            'search-changed', self.on_search_clicked)

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
        for view in [self.tree_view, self.icon_view]:
            view.model = self.model

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

        # Hide date column selection if there can be no choice
        if len(liststore_date_cols) < 2:
            combox_date_cols.hide()
            self.container.date_column_label.hide()
        else:
            # They might have been hidden on a previous bind call.
            combox_date_cols.show()
            self.container.date_column_label.show()

        # If the are no date columns, hide the date range controls as well
        widgets = (
            self.container.image_start_date,
            self.container.vbox_start_date,
            self.container.label_date_to,
            self.container.image_end_date,
            self.container.vbox_end_date,
            self.container.vseparator2
        )
        if len(liststore_date_cols) == 0:
            for widget in widgets:
                widget.hide()
        else:
            for widget in widgets:
                widget.show()

        self.view.refresh()

    ###
    # Callbacks
    ###

    def on_scrolled(self, vadj):
        """Load new records upon scroll to end of visible rows.

        :param vadj: Adjustment widget associated with vertical scrollbar
        :type vadj: :class:`Gtk.Adjustment`
        """
        # We don't need the visible_range optimization for treeview
        if self.view is self.icon_view:
            self.model.visible_range = self.view.get_visible_range()
        else:
            self.model.visible_range = None

        scrolled_to_bottom = (
            vadj.get_value() == (vadj.get_upper() - vadj.get_page_size()) or
            vadj.get_page_size() == vadj.get_upper())

        if scrolled_to_bottom:
            self.model.add_rows()

        return False

    def on_popup_column_visibility_changed(self, popup, name, value):
        """Set the list of columns to display based on column checkboxes.

        :param popup: the columns popup
        :type popup: :class:`OptionsPopup`
        :param str name: the name of the columns
        : param bool value: the new column visibility
        """
        if value:
            self.model.display_columns.add(name)
        else:
            self.model.display_columns.discard(name)

        self.model.data_source.update_selected_columns(
            self.model.display_columns)
        self.view.refresh()

    def on_popup_view_changed(self, popup, new_view):
        """Set the actual view based on the options popup option.

        :param popup: the columns popup
        :type popup: :class:`OptionsPopup`
        :param int new_view: either :attr:`OptionsPopup.VIEW_TREE` or
            :attr:`OptionsPopup.VIEW_ICON`
        """
        if new_view == OptionsPopup.VIEW_ICON:
            self.view = self.icon_view
            self.model.image_max_size = 100.0
            self.model.image_draw_border = True
        elif new_view == OptionsPopup.VIEW_TREE:
            self.view = self.tree_view
            self.model.image_max_size = 24.0
            self.model.image_draw_border = False
        else:
            raise AssertionError("Unrecognized option %r" % (new_view, ))

        child = self.container.grid_scrolledwindow.get_child()
        self.container.grid_scrolledwindow.remove(child)
        self.container.grid_scrolledwindow.add(self.view)
        self.view.show_all()

        self.view.refresh()
        # FIXME: Is there a way to keep the selection after the view was
        # refreshed? The actual selected paths are not guaranteed to be the
        # same, so how can we get them again?
        if self.selected_record_callback:
            self.selected_record_callback(None)

    def on_treeview_cursor_changed(self, view):
        """Get the data for a selected record and run optional callback.

        :param view: The treeview containing the row
        :type view: Gtk.TreeView

        """
        selection = view.get_selection()
        model, row_iterator = selection.get_selected()
        if row_iterator and self.selected_record_callback:
            record = self.model.data_source.get_single_record(
                model[row_iterator][1])
            self.selected_record_callback(record)
        elif self.selected_record_callback:
            self.selected_record_callback(None)

    def on_iconview_selection_changed(self, view):
        """Get the data for a selected record and run optional callback.

        :param view: The icon view containing the selected record
        :type view: :class:`Gtk.IconView`
        """
        selections = view.get_selected_items()
        row_iterator = selections and self.model.get_iter(selections[0])
        if row_iterator and self.selected_record_callback:
            model = view.get_model()
            record = self.model.data_source.get_single_record(
                model[row_iterator][1])
            self.selected_record_callback(record)
        elif self.selected_record_callback:
            self.selected_record_callback(None)

    def on_iconview_item_activated(self, view, path):
        """Get the data the activated record and run optional callback.

        :param view: The icon view containing the selected record
        :type view: :class:`Gtk.IconView`
        :param path: the activated path
        """
        if not path or not self.activated_icon_callback:
            return

        row_iterator = view.model.get_iter(path)
        record = self.model.data_source.get_single_record(
            self.model[row_iterator][1])
        # Why is the pixbuf column on view.pixbuf_column -1 position in this rec?
        self.activated_icon_callback(record, view.pixbuf_column - 1)

    def on_data_loaded(self, model, total_recs):
        """Update the total records label.

        :param model: Current datagrid model
        :type model: :class:`DataGridModel`
        :param int total_recs: Total records for current query

        """
        self.container.label_num_recs.set_markup(
            '<small>%d records</small>' % total_recs
        )

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

    def _refresh_view(self, update_dict=None, remove_keys=None):
        """Reload the grid with any filter/sort parameters.

        :param dict update_dict: Any ``where`` parameters with which to update
            the currently active parameters
        :param remove_keys: List of keys to delete from ``where`` parameters
        :type remove_keys: list

        """
        where_dict = self.model.active_params.setdefault('where', {})

        if remove_keys:
            for key in remove_keys:
                where_dict.pop(key, None)

        where_dict.update(update_dict or {})

        # If in the end the dict was/became empty, remove it from active_params
        if not where_dict:
            del self.model.active_params['where']

        self.view.refresh()


class DataGridView(Gtk.TreeView):

    """A ``Gtk.TreeView`` for displaying data from a ``DataGridModel``.

    :param model: The model providing the tabular data for the grid
    :type model: :class:`DataGridModel`
    :keyword bool has_checkboxes: Whether record rows have a checkbox

    """

    has_checkboxes = GObject.property(type=bool, default=True)

    # Column widths
    MIN_WIDTH = 40
    MAX_WIDTH = 400
    SAMPLE_SIZE = 50

    def __init__(self, model, **kwargs):
        super(DataGridView, self).__init__(**kwargs)

        self.connect_after('notify::model', self.after_notify_model)

        # FIXME: Ideally, we should pass model directly to treeview and get
        # it from self.get_model instead of here. We would need to refresh
        # it first though
        self.model = model
        self.tv_columns = []
        self.check_btn_toggle_all = None
        self.check_btn_toggled_id = None
        self.set_rules_hint(True)
        self.active_sort_column = None
        self.active_sort_column_order = None

    ###
    # Public
    ###

    def refresh(self):
        """Refresh the model results."""
        self.set_model(None)
        self.model.refresh()
        self.set_model(self.model)

        for col in self.get_columns()[:]:
            self.remove_column(col)

        self._setup_columns()

    ###
    # Callbacks
    ###

    def after_notify_model(self, treeview, p_spec):
        """Track model modification on the treeview.

        Aftwe the model of this treeview has changed, we need
        to update some connections, like the 'row-changed'

        :param treeview: the treeview that had its model modified
        :type treeview: `Gtk.TreeView`
        """
        model = treeview.get_model()
        if model is None:
            return

        model.connect('row-changed', self.on_model_row_changed)

    def on_model_row_changed(self, model, path, iter_):
        """Track row changes on model.

        :param model: this treeview's model
        :type model: :class:`DataGridModel`
        :param path: the path to the changed row
        :type path: :class:`Gtk.TreePath`
        :param iter_: the iter to the changed row
        :type iter_: :class:`Gtk.TreeIter`
        """
        self._update_toggle_check_btn_activity()

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
        self.model.active_params.update({'order_by': column, 'desc': desc})
        self.refresh()

    def on_select_all_column_clicked(self, check_btn):
        """Select all records in current recordset and update model/view.

        :param check_btn: The check button inside the treeview column header
        :type: :class:`Gtk.CheckButton`

        """
        val = check_btn.get_active()

        where_params = {}
        if 'where' in self.model.active_params:
            where_params['where'] = self.model.active_params['where']

        ids = self.model.data_source.get_all_record_ids(where_params)
        self.model.update_data_source('__selected', val, ids)

        self.refresh()

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

            check_btn = Gtk.CheckButton()
            col.set_widget(check_btn)
            check_btn.show()

            self.check_btn_toggled_id = check_btn.connect(
                "toggled", self.on_select_all_column_clicked)

            # Mimic toggle on checkbutton since it won't receive the click.
            # This will work when clicking directly on the checkbutton or on
            # the header button itself.
            col.connect(
                'clicked',
                lambda tvc: check_btn.set_active(not check_btn.get_active()))

            self.check_btn_toggle_all = check_btn
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
        self._update_toggle_check_btn_activity()

    def _update_toggle_check_btn_activity(self):
        """Update the "selected" treeview column's checkbox activity.

        This will update the checkbox activity based on the selected
        rows on the model.
        """
        if self.check_btn_toggle_all is None:
            return

        all_selected = all(row[0] for row in self.model)
        any_selected = any(row[0] for row in self.model)

        with self.check_btn_toggle_all.handler_block(
                self.check_btn_toggled_id):
            self.check_btn_toggle_all.set_active(all_selected)
            self.check_btn_toggle_all.set_inconsistent(
                not all_selected and any_selected)

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
            value = model.get_formatted_value(row[colnum], colnum,
                                              visible=False)
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


class DataGridCellAreaRenderer(Gtk.CellAreaBox):

    """A cell area renderer with a check box in it."""

    # 16 is the default size, as defined here:
    # https://git.gnome.org/browse/gtk+/tree/gtk/gtkcheckbutton.c
    CHECK_BUTTON_DEFAULT_SIZE = 16
    CHECK_BUTTON_OFFSET = 6

    def __init__(self, *args, **kwargs):
        super(DataGridCellAreaRenderer, self).__init__(*args, **kwargs)

        checkbutton = Gtk.CheckButton()
        value = GObject.Value(GObject.TYPE_INT)
        checkbutton.style_get_property('indicator-size', value)
        self._checkbutton_size = (value.get_int() or
                                  self.CHECK_BUTTON_DEFAULT_SIZE)

        self._is_checked = False

    ###
    # Public
    ###

    def get_checkbutton_area(self, cell_area):
        """Get the area to draw the checkbox on the cell area.

        :param cell_area: the cell area rectangle
        :type cell_area: `cairo.Rectangle`
        :returns: a tuple with the area as (x, y, width, height)
        :rtype: `tuple`
        """
        pos_x = cell_area.x + self.CHECK_BUTTON_OFFSET
        pos_y = (cell_area.y + cell_area.height -
                 (self._checkbutton_size + self.CHECK_BUTTON_OFFSET))
        return pos_x, pos_y, self._checkbutton_size, self._checkbutton_size

    ###
    # Virtual overrides
    ###

    def do_render(self, ctx, widget, cr, background_area,
                  cell_area, flags, paint_focus):
        """Render the checkbox on the cell area.

        :param ctx: the cell area context
        :type ctx: `Gtk.CellAreaContext`
        :param widget: the widget that we are rendering on
        :type widget: `DataGridIconView`
        :param cr: the context to render with
        :type cr: `cairo.Context`
        :param background_area: the widget relative coordinates from
            the area's background
        :type background_area: `cairo.Rectangle`
        :param cell_area: the widget relative coordinates from area
        :type cell_area: `cairo.Rectangle`
        :param flags: the cell renderer state for the area in this row
        :type flags: `Gtk.CellRendererState`
        :param paint_focus: wheather the area should paint focus on
            focused cells for focused rows or not
        :type paint_focus: `bool`
        """
        # For some reason, can't use super here
        Gtk.CellAreaBox.do_render(
            self, ctx, widget, cr, background_area,
            cell_area, flags, paint_focus)

        if not widget.has_checkboxes:
            return

        style_context = widget.get_style_context()
        style_context.save()
        style_context.add_class(Gtk.STYLE_CLASS_CHECK)

        if self._is_checked:
            # CHECKED is the right flag to use, but it's only available on
            # gtk 3.14+. For older versions, we use ACTIVE alone, since
            # setting it together with existing flags would break its drawing
            if hasattr(Gtk.StateFlags, 'CHECKED'):
                style_context.set_state(style_context.get_state() |
                                        Gtk.StateFlags.CHECKED)
            else:
                style_context.set_state(Gtk.StateFlags.ACTIVE)

        Gtk.render_check(widget.get_style_context(), cr,
                         *self.get_checkbutton_area(cell_area))

        style_context.restore()

    def do_apply_attributes(self, model, iter_, *args):
        """Render the checkbox on the cell area.

        :param model: the model to pull values from
        :type model: `DataGridModel`
        :param iter_: the iter to apply values from
        :type iter_: `Gtk.TreeIter`
        """
        # For some reason, can't use super here
        Gtk.CellAreaBox.do_apply_attributes(self, model, iter_, *args)
        self._is_checked = model.get_value(iter_, 0)


class DataGridIconView(Gtk.IconView):

    """A ``Gtk.IconView`` for displaying data from a ``DataGridModel``.

    :param model: The model providing the tabular data for the grid
    :type model: :class:`DataGridModel`
    :keyword bool has_checkboxes: Whether record rows have a checkbox

    """

    has_checkboxes = GObject.property(type=bool, default=True)

    def __init__(self, model, **kwargs):
        if not 'cell_area' in kwargs:
            kwargs['cell_area'] = DataGridCellAreaRenderer()

        super(DataGridIconView, self).__init__(**kwargs)

        self.pixbuf_column = None
        # FIXME: Ideally, we should pass model directly to treeview and get
        # it from self.get_model instead of here. We would need to refresh
        # it first though
        self.model = model

        self.connect('button-release-event', self.on_button_release_event)
        self.connect('key-press-event', self.on_key_press_event)

    ###
    # Public
    ###

    def refresh(self):
        """Refresh the model results."""
        self.set_model(None)
        self.model.refresh()
        self.set_model(self.model)

        for column_index, column in enumerate(self.model.columns):
            # FIXME: Can we have more than one column with image transform?
            if column['transform'] == 'image':
                self.pixbuf_column = column_index
                self.set_pixbuf_column(self.pixbuf_column)
                break

    ##
    # Callbacks
    ##

    def on_key_press_event(self, window, event):
        """Handle key press events.

        Toggle the check button when pressing 'Space'
        """
        # We don't want 'item-activated' signal to be fired on Space, even
        # if we don't have checkboxes visible. Space should be used
        # to toggle the checkboxes only
        space_pressed = event.get_keyval()[1] == Gdk.KEY_space
        if not space_pressed:
            return False

        if not self.has_checkboxes:
            return space_pressed

        selections = self.get_selected_items()
        if not selections:
            return space_pressed

        self._toggle_path(selections[0])
        return True

    def on_button_release_event(self, window, event):
        """Handle button press events.

        Toggle the check button if we clicked on it.
        """
        if not self.has_checkboxes:
            return False

        coords = event.get_coords()
        path = self.get_path_at_pos(*coords)
        if not path:
            return False

        success, cell_rect = self.get_cell_rect(path, None)
        cell_area = self.get_property('cell_area')

        event_rect = Gdk.Rectangle()
        event_rect.x, event_rect.y = coords
        event_rect.width = 1
        event_rect.height = 1

        check_rect = Gdk.Rectangle()
        (x, y,
         check_rect.width,
         check_rect.height) = cell_area.get_checkbutton_area(cell_rect)

        # x and y needs to be converted to bin window coords
        (check_rect.x,
         check_rect.y) = self.convert_widget_to_bin_window_coords(x, y)

        # For some reason, we also need to consider the item padding
        check_rect.x += self.get_item_padding()
        check_rect.y -= self.get_item_padding()

        intersection = Gdk.rectangle_intersect(event_rect, check_rect)
        if intersection[0]:
            self._toggle_path(path)
            return True

        return False

    ###
    # Private
    ###

    def _toggle_path(self, path):
        """Toggle the '__selected' value for the given path on model.

        :param path: the path to toggle
        :type itr: :class:`Gtk.TreePath`
        """
        iter_ = self.model.get_iter(path)
        val = self.model.get_value(iter_, 0)
        # FIXME: Gtk.IconView has some problems working with huge models.
        # It would invalidate everything on row changed, as can be seem here:
        # https://git.gnome.org/browse/gtk+/tree/gtk/gtkiconview.c
        # Atm we will avoid row-changed and just call queue_redraw which
        # will be a lot faster! We should try to find a better solution
        self.model.set_value(iter_, 0, not val, emit_event=False)
        self.queue_draw()


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

    image_max_size = GObject.property(type=float, default=24.0)
    image_draw_border = GObject.property(type=bool, default=False)

    IMAGE_PREFIX = 'file://'
    IMAGE_BORDER_SIZE = 6
    IMAGE_SHADOW_SIZE = 6
    IMAGE_SHADOW_OFFSET = 2
    MIN_TIMESTAMP = 0  # 1970
    MAX_TIMESTAMP = 2147485547  # 2038

    def __init__(self, data_source, get_media_callback, decode_fallback,
                 encoding_hint='utf-8'):
        """Set up model."""
        super(DataGridModel, self).__init__()

        self._fallback_images = {}
        self.visible_range = None
        self.active_params = {}
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
        self.display_columns = None
        self.encoding_hint = encoding_hint
        self.selected_cells = list()

        self.rows = None
        self.total_recs = None

    def refresh(self):
        """Refresh the model from the data source."""
        if 'page' in self.active_params:
            del self.active_params['page']

        self.data_source.load(self.active_params)
        self.rows = self.data_source.rows
        self.total_recs = self.data_source.total_recs
        self.emit('data-loaded', self.total_recs)

    def add_rows(self):
        """Add rows to the model from a new page of data and update the view.

        :return: True if update took place, False if not
        :rtype: bool
        """
        self.active_params['page'] = self.active_params.get('page', 0) + 1

        path = (len(self.rows) - 1,)
        itr = self.get_iter(path)
        self.data_source.load(self.active_params)
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

    def get_formatted_value(self, value, column_index, visible=True):
        """Get the value to display in the cell.

        :param value: Value from data source
        :type value: str or int or None
        :param int column_index: Index of the column containing the value
        :param bool visible: If the value is visible on the view or not.
            Some transformations (i.e. image) will do some optimizations
            if the value is not visible
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
                value = self._image_transform(value, visible=visible)
            else:
                return NO_IMAGE_PIXBUF

        elif col_dict['transform'] == 'datetime':
            if value:
                value = self._datetime_transform(value)
            else:
                return ''
        else:
            # If no transformation is required, at least convert the value to
            # str as required by CellRendererText
            value = str(value) if value is not None else ''

        # At the end, if value is unicode, it needs to be converted to
        # an utf-8 encoded str or it won't be rendered in the treeview.
        if isinstance(value, unicode):
            value = value.encode('utf-8')

        return value

    def set_value(self, itr, column, value, emit_event=True):
        """Set the value in the model and update the data source with it.

        :param itr: ``TreeIter`` object representing the current row
        :type itr: :class:`Gtk.TreeIter`
        :param int column: Column index for value
        :param value: Update the row/column to this value
        :type value: str or int or bool or None
        :param bool emit_event: if we should call :meth:`.row_changed`.
            Be sure to know what you are doing before passind `False` here
        """
        path = self.get_path(itr)[0]
        self.rows[path][column] = value
        id_ = self.get_value(itr, 1)
        self.update_data_source(
            self.columns[column]['name'], value, [int(id_)])
        if emit_event:
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

    def _image_transform(self, value, visible=True):
        """Render a thumbnail of an image for given path.

        :param str value: Path to image file.
        """
        if not visible:
            key = (self.image_draw_border, self.image_max_size)
            fallback = self._fallback_images.get(key)
            if not fallback:
                fallback = self._get_pixbuf()
                self._fallback_images[key] = fallback
            return fallback

        is_image = False
        if value.startswith(self.IMAGE_PREFIX):
            # TODO: ensure performance not affected by scaling images
            #   with large recordsets, use file_ = 'icons/image.png' if so
            # TODO: refactor image scaling to its own utility function
            filename = value[len(self.IMAGE_PREFIX):]
        else:
            filename = None

        return self._get_pixbuf(filename)

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

    def _get_pixbuf(self, path=None):
        """Resize the image if needed to fit :obj:`.image_max_size`.

        :param str image: the image path or `None` to use a fallback image
        :returns: the resized pixbuf
        :rtype: :class:`GdkPixbuf.Pixbuf`
        """
        fallback = self.get_media_callback('icons/image.png')
        path = path or fallback

        try:
            image = Image.open(path)
            image.load()
        except IOError:
            # If the image is damaged for some reason, use fallback
            image = Image.open(fallback)

        image.thumbnail(
            (self.image_max_size, self.image_max_size), Image.BICUBIC)

        square_side = self.image_max_size
        if self.image_draw_border:
            image = imageutils.add_border(
                image, border_size=self.IMAGE_BORDER_SIZE)
            image = imageutils.add_drop_shadow(
                image, border_size=self.IMAGE_SHADOW_SIZE,
                offset=(self.IMAGE_SHADOW_OFFSET, self.IMAGE_SHADOW_OFFSET))

            square_side += self.IMAGE_BORDER_SIZE * 2
            square_side += self.IMAGE_SHADOW_SIZE * 2
            square_side += self.IMAGE_SHADOW_OFFSET

        pixbuf = imageutils.image2pixbuf(image)
        width = pixbuf.get_width()
        height = pixbuf.get_height()

        # Make sure the image is on the center of the image_max_size
        square_pic = GdkPixbuf.Pixbuf.new(
            GdkPixbuf.Colorspace.RGB, True, pixbuf.get_bits_per_sample(),
            square_side, square_side)
        # Fill with transparent white
        square_pic.fill(0xffffff00)

        dest_x = (square_side - width) / 2
        dest_y = (square_side - height) / 2

        pixbuf.copy_area(
            0, 0, width, height, square_pic, dest_x, dest_y)

        return square_pic

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
        if self.visible_range:
            visible = self.visible_range[0][0] <= rowref <= self.visible_range[1][0]
        else:
            visible = True

        raw = self.rows[rowref][column]
        val = self.get_formatted_value(raw, column, visible=visible)
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
