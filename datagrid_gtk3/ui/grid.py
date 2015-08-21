"""Module containing classes for datagrid MVC implementation."""

import base64
import contextlib
import datetime
import itertools
import logging
import os

from gi.repository import (
    GLib,
    GObject,
    Gdk,
    GdkPixbuf,
    Gtk,
    Pango,
)
from pygtkcompat.generictreemodel import GenericTreeModel

from datagrid_gtk3.ui.popupcal import DateEntry
from datagrid_gtk3.ui.uifile import UIFile
from datagrid_gtk3.utils.dateutils import normalize_timestamp
from datagrid_gtk3.utils.imageutils import ImageCacheManager
from datagrid_gtk3.utils.transformations import get_transformer

_MEDIA_FILES = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    os.pardir,
    "data",
    "media"
)

logger = logging.getLogger(__name__)
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

# Used to represent "no option selected" on filters. We use this instead of
# None as it can be a valid value for filtering.
NO_FILTER_OPTION = object()


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
     VIEW_FLAT,
     VIEW_ICON) = range(3)

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
        combo = self._get_view_options()
        if combo is not None:
            vbox.pack_start(combo, expand=False, fill=False,
                            padding=self.OPTIONS_PADDING)

        if not isinstance(self._controller.view, DataGridIconView):
            if combo is not None:
                vbox.pack_start(
                    Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
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
        iters = {}
        model = Gtk.ListStore(str, int)

        iters[self.VIEW_TREE] = model.append(("Tree View", self.VIEW_TREE))

        if self._controller.model.flat_column_idx is not None:
            iters[self.VIEW_FLAT] = model.append(("Flat View", self.VIEW_FLAT))

        if any(c['transform'] == 'image'
               for c in self._controller.model.columns):
            iters[self.VIEW_ICON] = model.append(("Icon View", self.VIEW_ICON))

        # Avoid displaying the combo if there's only one option
        if len(iters) == 1:
            return None

        combo = Gtk.ComboBox()
        combo.set_model(model)
        renderer = Gtk.CellRendererText()
        combo.pack_start(renderer, True)
        combo.add_attribute(renderer, 'text', 0)

        if isinstance(self._controller.view, DataGridView):
            if self._controller.model.active_params.get('flat', False):
                combo.set_active_iter(iters[self.VIEW_FLAT])
            else:
                combo.set_active_iter(iters[self.VIEW_TREE])
        elif isinstance(self._controller.view, DataGridIconView):
            combo.set_active_iter(iters[self.VIEW_ICON])
        else:
            raise AssertionError("Unknown view type %r" % (
                self._controller.view, ))

        combo.connect('changed', self.on_combo_view_changed)
        return combo

    def _get_visibility_options(self):
        """Construct the switches based on the actual model columns."""
        model = self._controller.model
        hidden_columns = model.hidden_columns

        for column in model.columns:
            if column['name'] in hidden_columns:
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

    def on_combo_view_changed(self, widget):
        """Handle changes on the view combo.

        Emit 'view-changed' for the given view.

        :param widget: the combobox that received the event
        :type widget: :class:`Gtk.ComboBox`
        """
        model = widget.get_model()
        value = model[widget.get_active()][1]
        self.emit('view-changed', value)
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

    def __init__(self, container, data_source, selected_record_callback=None,
                 activated_icon_callback=None, activated_row_callback=None,
                 has_checkboxes=True, decode_fallback=None,
                 get_full_path=None):
        """Setup UI controls and load initial data view."""
        self.extra_filter_widgets = {}
        self.container = container

        self.decode_fallback = decode_fallback if decode_fallback else repr
        self.get_full_path = get_full_path
        self.selected_record_callback = selected_record_callback
        self.activated_icon_callback = activated_icon_callback
        self.activated_row_callback = activated_row_callback

        self.vscroll = container.grid_scrolledwindow.get_vadjustment()
        self.vscroll.connect_after('value-changed', self.on_scrolled)

        self.tree_view = DataGridView(None, has_checkboxes=has_checkboxes)
        self.icon_view = DataGridIconView(None, has_checkboxes=has_checkboxes)

        self.tree_view.connect('cursor-changed',
                               self.on_treeview_cursor_changed)
        self.tree_view.connect('row-activated',
                               self.on_treeview_row_activated)
        self.icon_view.connect('selection-changed',
                               self.on_iconview_selection_changed)
        self.icon_view.connect('item-activated',
                               self.on_iconview_item_activated)
        self.tree_view.connect('row-expanded',
                               self.on_tree_view_row_expanded)
        self.tree_view.connect('row-collapsed',
                               self.on_tree_view_row_collapsed)

        # The treview will be the default view
        self.view = self.tree_view
        self.container.grid_scrolledwindow.add(self.view)

        cm = ImageCacheManager.get_default()
        cm.connect('image-loaded', self.on_image_cache_manager_image_loaded)

        # select columns toggle button
        self.options_popup = OptionsPopup(
            self.container.togglebutton_options, self)
        self.options_popup.connect('column-visibility-changed',
                                   self.on_popup_column_visibility_changed)
        self.options_popup.connect('view-changed', self.on_popup_view_changed)

        # date range widgets
        icon_theme = Gtk.IconTheme.get_default()
        for icon in ['calendar', 'stock_calendar']:
            if icon_theme.has_icon(icon):
                break
        else:
            # Should never happen, just a precaution
            raise Exception("No suitable calendar icon found on theme")

        for image in [self.container.image_start_date,
                      self.container.image_end_date]:
            image.set_from_icon_name(icon, Gtk.IconSize.BUTTON)

        self.date_start = DateEntry(self.container.window,
                                    DateEntry.TYPE_START)
        self.date_start.set_editable(False)
        self.date_start.set_sensitive(False)
        self.date_start.connect('date_changed', self.on_date_change, 'start')
        # FIXME: ^^ use hyphen in signal name
        self.container.vbox_start_date.pack_start(
            self.date_start, expand=False, fill=True, padding=0)
        self.date_end = DateEntry(self.container.window,
                                  DateEntry.TYPE_END)
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

    ###
    # Public
    ###

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

        liststore_date_cols = Gtk.ListStore(str, str, str)
        if self.model.datetime_columns:
            self.date_start.set_sensitive(True)
            self.date_end.set_sensitive(True)

        for column in self.model.datetime_columns:
            liststore_date_cols.append(
                (column['name'], column['display'], column['transform']))

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
            self.container.filters_separator,
        )
        if len(liststore_date_cols) == 0:
            for widget in widgets:
                widget.hide()
        else:
            combox_date_cols.set_active(0)
            for widget in widgets:
                widget.show()

        self._refresh_view()
        data_source.connect('rows-changed', self.on_data_source_rows_changed)

    def add_options_filter(self, attr, options, add_empty_option=True):
        """Add optional options filter for attr.

        :param str attr: the attr that will be filtered
        :param iterable options: the options that will be displayed
            on the filter as a tuple with (label, option).
            The label will be displayed as on the combo and the
            option will be used to generate the WHERE clause
        :param bool add_empty_option: if we should add an empty
            option as the first option in the combo. Its label will
            be the label of the column in question and selecting
            it will be the same as not filtering by that attr.
        :returns: the newly created combobox
        :rtype: :class:`Gtk.ComboBox`
        """
        for col_dict in self.model.columns:
            if col_dict['name'] == attr:
                label = col_dict['display']
                break
        else:
            raise ValueError

        model = Gtk.ListStore(str, object)
        if add_empty_option:
            model.append((label, NO_FILTER_OPTION))
        for option in options:
            model.append(option)

        combo = Gtk.ComboBox()
        combo.set_model(model)
        renderer = Gtk.CellRendererText()
        combo.pack_start(renderer, True)
        combo.add_attribute(renderer, 'text', 0)
        combo.set_active(0)
        combo.set_id_column(0)

        combo.connect('changed', self.on_filter_changed, attr)

        self.extra_filter_widgets[attr] = combo
        self.container.extra_filters.pack_start(
            combo, expand=False, fill=False, padding=0)
        self.container.extra_filters.show_all()
        # Make sure this separator is visible. It may have been hidden
        # if we don't have any datetime columns.
        self.container.filters_separator.show()

        return combo

    def set_selected_row_by_id(self, row_id,
                               scroll_to_row=True, callback=None):
        """Set the selected row by id.

        :param int row_id: The id of the row to set as the selected one
        :param bool scroll_to_row: If we should scroll to that row,
            putting it in the center of the window
        :param callable callback: A callback to call after the
            rows has been loaded
        """
        row = self.model.get_row_by_id(row_id, load_rows=True)
        if row is None:
            logger.warning("No row found with id %s", row_id)
            if callback is not None:
                assert callable(callback)
                callback()
            return

        path = Gtk.TreePath(row.path)
        self.view.set_cursor(path)


        def _callback():
            """Timeout callback."""
            if scroll_to_row:
                with self.view.block_draw():
                    if self.view is self.tree_view:
                        self.view.scroll_to_cell(path, None, True, 0.5, 0.0)
                    elif self.view is self.icon_view:
                        self.view.scroll_to_path(path, True, 0.5, 0.0)

            if callback is not None:
                assert callable(callback)
                GObject.idle_add(callback)

        # Acording to the documentation, PRIORITY_HIGH_IDLE + 20 is
        # used by redrawing operations so PRIORITY_HIGH_IDLE + 25
        # should be enought to make sure we call callback just after
        # the widget finishes redrawing itself.
        GObject.timeout_add(100, _callback,
                            priority=GLib.PRIORITY_HIGH_IDLE + 25)

    ###
    # Callbacks
    ###

    def on_scrolled(self, vadj):
        """Load new records upon scroll to end of visible rows.

        :param vadj: Adjustment widget associated with vertical scrollbar
        :type vadj: :class:`Gtk.Adjustment`
        """
        scrolled_to_bottom = (
            vadj.get_value() == (vadj.get_upper() - vadj.get_page_size()) or
            vadj.get_page_size() == vadj.get_upper())

        if scrolled_to_bottom:
            self.model.add_rows()

        self._set_visible_range()

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

        self.model.data_source.set_visible_columns(
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
            self.tree_view.set_model(None)
            self.model.image_max_size = 100.0
            self.model.image_draw_border = True
        elif new_view in [OptionsPopup.VIEW_TREE, OptionsPopup.VIEW_FLAT]:
            # Changing view from/to flat will make expanded_ids have no meaning
            self.tree_view.expanded_ids.clear()
            self.view = self.tree_view
            self.icon_view.set_model(None)
            self.model.image_max_size = 24.0
            self.model.image_draw_border = False
        else:
            raise AssertionError("Unrecognized option %r" % (new_view, ))

        # We want flat for flat and iconview, and only if we really have
        # a flat column.
        self.model.active_params['flat'] = (
            self.model.flat_column_idx is not None and
            new_view in [OptionsPopup.VIEW_FLAT, OptionsPopup.VIEW_ICON])

        child = self.container.grid_scrolledwindow.get_child()
        self.container.grid_scrolledwindow.remove(child)
        self.container.grid_scrolledwindow.add(self.view)
        self.view.show_all()

        self._refresh_view()
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
                model[row_iterator][self.model.id_column_idx])
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
                model[row_iterator][self.model.id_column_idx])
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
            self.model[row_iterator][self.model.id_column_idx])
        self.activated_icon_callback(record, view.pixbuf_column)

    def on_treeview_row_activated(self, view, path, column):
        """Handle row-activated signal on the treeview.

        Run the optional :obj:`.activated_row_callback` when
        a row gets activated.

        :param view: The treeview containing the row
        :type view: :class:`Gtk.TreeView`
        :param path: the activated path
        :type path: :class:`Gtk.TreePath`
        :param column: the column that was activated on the row
        :type column: class:`Gtk.TreeViewColumn`

        """
        if self.activated_row_callback is None:
            return

        row = self.model[self.model.get_iter(path)]
        selected_id = row[self.model.id_column_idx]
        record = self.model.data_source.get_single_record(selected_id)
        self.activated_row_callback(record)

    def on_tree_view_row_expanded(self, treeview, iter_, path):
        """Handle row-expanded events.

        Make sure visible range will be updated on the model.

        :param treeview: the treeview that had one of its rows expanded
        :type treeview: :class:`Gtk.TreeView`
        :param iter_: the iter pointing to the expanded row
        :type iter_: :class:`Gtk.TreeIter`
        :param path: the path pointing to the expanded row
        :type path: :class:`Gtk.TreePath`
        """
        GObject.idle_add(self._set_visible_range)

    def on_tree_view_row_collapsed(self, treeview, iter_, path):
        """Handle row-collapsed events.

        Make sure visible range will be updated on the model.

        :param treeview: the treeview that had one of its rows collapsed
        :type treeview: :class:`Gtk.TreeView`
        :param iter_: the iter pointing to the collapsed row
        :type iter_: :class:`Gtk.TreeIter`
        :param path: the path pointing to the collapsed row
        :type path: :class:`Gtk.TreePath`
        """
        GObject.idle_add(self._set_visible_range)

    def on_image_cache_manager_image_loaded(self, cm):
        """Handle image-loaded event for image cache manager.

        When an image finishes loading, queue a redraw to make sure
        the image will be loaded.

        :param cm: the cache manager that emited the event
        :type cm: :class: `datagrid_gtk3.utils.imageutils.ImageCacheManager`
        """
        self.view.queue_draw()

    def on_filter_changed(self, combo, attr):
        """Handle selection changed on filter comboboxes.

        :param combo: the combo that received the signal
        :type combo: :class:`Gtk.ComboBox`
        :param str attr: the name of the attr to filter
        """
        model = combo.get_model()
        value = model[combo.get_active()][1]

        if value is NO_FILTER_OPTION:
            remove_keys = [attr]
            update_dict = None
        else:
            remove_keys = None
            update_dict = {
                attr: {
                    'operator': 'is' if value is None else '=',
                    'param': value,
                }
            }

        self._refresh_view(update_dict=update_dict, remove_keys=remove_keys)

    def on_data_source_rows_changed(self, data_source, params, ids):
        """Handle data_source rows-changed signal.

        When a row gets updated on data source, make sure to reflect
        them on the view, without requiring to do an extra query for that.

        :param data_source: The data source which emitted the signal
        :type data_source: `datagrid_gtk3.db.DataSource`
        :param params: A dict of params that got updated, mapped as
            ``column_name: new_value``
        :type params: dict
        :param ids: The row ids that got updated
        :type ids: [int]
        """
        params_idx = [
            (self.model.data_source.columns_idx[k], v)
            for k, v in params.iteritems()]
        rows = (row
                for id_, row in self.model.row_id_mapper.iteritems()
                if ids is None or id_ in ids)

        for row in rows:
            for idx, value in params_idx:
                row.data[idx] = value

            path = Gtk.TreePath(row.path)
            self.model.row_changed(path, self.model.get_iter(row.path))
            # Even if we call `view.queue_draw` here, it would only be updated
            # when it got focused. By setting refresh_draw to True, it will
            # force it to refresh the values when the view gets visible on the
            # screen, even if it is not focused atm.
            self.view.refresh_draw = True

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
        initial = datetime.datetime(1970, 1, 1)

        start_date = self.date_start.get_date()
        start_timestamp = start_date and (start_date - initial).total_seconds()
        end_date = self.date_end.get_date()
        end_timestamp = end_date and (end_date - initial).total_seconds()

        active_date_column = self.container.combobox_date_columns.get_active()
        model_date_columns = self.container.combobox_date_columns.get_model()
        # clear all params from previous date column range select
        remove_columns = [column[0] for column in model_date_columns]
        # FIXME: Why this is comming as -1 on exampledata for Employee?
        active_date_column = max(active_date_column, 0)
        column = model_date_columns[active_date_column][0]
        transform = model_date_columns[active_date_column][2]

        # Normalize the timestamp so the search is accurate
        if start_timestamp:
            start_timestamp = normalize_timestamp(
                start_timestamp, transform, inverse=True)
        if end_timestamp:
            end_timestamp = normalize_timestamp(
                end_timestamp, transform, inverse=True)

        if start_timestamp is not None and end_timestamp is not None:
            operator = 'range'
            param = (start_timestamp, end_timestamp)
        elif start_timestamp is not None:
            operator = '>='
            param = start_timestamp
        elif end_timestamp is not None:
            operator = '<='
            param = end_timestamp
        else:
            operator = None
            param = None

        update_dict = {}
        if operator is not None:
            update_dict[column] = {
                'operator': operator,
                'param': param,
            }

        self._refresh_view(update_dict, remove_columns)

    ###
    # Private
    ###

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

        # This will speed up loading the views. Images will be loaded
        # after when _set_visible_range executes.
        self.model.visible_range = ((-1, ), (-1, ))
        self.view.refresh()
        GObject.idle_add(self._set_visible_range)

    def _set_visible_range(self):
        """Update model with current view's visible range."""
        visible_range = self.view.get_visible_range()
        if visible_range is None:
            return

        self.model.visible_range = (
            tuple(visible_range[0]), tuple(visible_range[1]))

        self.view.queue_draw()


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
        self.connect('row-expanded', self.on_row_expanded)
        self.connect('row-collapsed', self.on_row_collapsed)

        # FIXME: Ideally, we should pass model directly to treeview and get
        # it from self.get_model instead of here. We would need to refresh
        # it first though
        self.model = model
        self.check_btn_toggle_all = None
        self.check_btn_toggled_id = None
        self.set_rules_hint(True)
        self.active_sort_column = None
        self.active_sort_column_order = None

        self.expanded_ids = set()
        self._all_expanded = False
        self._block_all_expanded = False

        self.refresh_draw = False
        self._block_draw = False

    ###
    # Public
    ###

    @contextlib.contextmanager
    def block_draw(self):
        """Block the drawing of this widget.

        While inside this context, this widget will not be draw.
        """
        self._block_draw = True
        yield
        self._block_draw = False
        self.queue_draw()

    def do_draw(self, cr):
        """Do the drawing of this widget.

        :param cr: The cairo context context
        :type cr: :class:`cairo.Context`
        """
        if self._block_draw:
            return
        if self.refresh_draw:
            GObject.idle_add(self.queue_draw)
            self.refresh_draw = False
        return Gtk.TreeView.do_draw(self, cr)

    def refresh(self):
        """Refresh the model results."""
        self.set_model(None)
        self.model.refresh()
        self.set_model(self.model)

        for col in self.get_columns()[:]:
            self.remove_column(col)

        self._setup_columns()

        # After refreshing the model, some rows may not be present anymore.
        # Let self.expanded_ids be constructed again by the events bellow
        expanded_ids = self.expanded_ids.copy()
        self.expanded_ids.clear()

        # FIXME: This is very optimized, but on some situations (e.g. all paths
        # are expanded and the user changed the sort column), this would make
        # everything be loaded at the same time. Is there anything we can do
        # regarding this issue?
        for row_id in expanded_ids:
            row = self.model.get_row_by_id(row_id, load_rows=True)
            if row is None:
                continue
            self.expand_to_path(Gtk.TreePath(row.path))

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

    def on_row_expanded(self, treeview, iter_, path):
        """Handle row-expanded events.

        Keep track of which rows are currently expanded

        :param treeview: the treeview that had one of its rows expanded
        :type treeview: :class:`Gtk.TreeView`
        :param iter_: the iter pointing to the expanded row
        :type iter_: class:`Gtk.TreeIter`
        :param path: the path pointing to the expanded row
        :type path: :class:`Gtk.TreePath`
        """
        row_id = self.model.get_value(iter_, self.model.id_column_idx)
        self.expanded_ids.add(row_id)

    def on_row_collapsed(self, treeview, iter_, path):
        """Handle row-collapsed events.

        Keep track of which rows are currently expanded

        :param treeview: the treeview that had one of its rows collapsed
        :type treeview: :class:`Gtk.TreeView`
        :param iter_: the iter pointing to the collapsed row
        :type iter_: class:`Gtk.TreeIter`
        :param path: the path pointing to the collapsed row
        :type path: :class:`Gtk.TreePath`
        """
        self.expanded_ids.discard(
            self.model.get_value(iter_, self.model.id_column_idx))

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
        for col in self.get_columns():
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
        self.model.update_data_source(
            self.model.data_source.SELECTED_COLUMN, val, ids)

        self.refresh()

    ###
    # Private
    ###

    def _setup_columns(self):
        """Configure the column widgets in the view."""
        if self.has_checkboxes:
            toggle_cell = Gtk.CellRendererToggle()
            toggle_cell.connect('toggled', self.on_toggle,
                                self.model.data_source.selected_column_idx)
            col = Gtk.TreeViewColumn(
                '', toggle_cell,
                active=self.model.data_source.selected_column_idx)

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

        hidden_columns = self.model.hidden_columns
        samples = list(itertools.islice(
            (r.data for r in self.model.iter_rows()), self.SAMPLE_SIZE))
        for column_index, column in enumerate(self.model.columns):
            item = column['name']
            display = item in self.model.display_columns
            if display and column['name'] not in hidden_columns:
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
                width = self._get_pango_string_width(lbl) + 14
                col.set_fixed_width(
                    self._get_best_column_width(column_index, samples))
                col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                col.set_expand(column['expand'])
                if item == self.active_sort_column:
                    # When the column is expanded, leave a little more
                    # space for the sort indicator
                    width += self._get_pango_string_width(
                        u" \u25BC".encode('utf-8'))
                    col.set_sort_indicator(True)
                    col.set_sort_order(self.active_sort_column_order)
                col.set_min_width(width)
                self.append_column(col)

        self.set_headers_clickable(True)
        self._update_toggle_check_btn_activity()

    def _update_toggle_check_btn_activity(self):
        """Update the "selected" treeview column's checkbox activity.

        This will update the checkbox activity based on the selected
        rows on the model.
        """
        if self.check_btn_toggle_all is None:
            return

        selected_idx = self.model.data_source.selected_column_idx
        all_selected = all(row[selected_idx] for row in self.model)
        any_selected = any(row[selected_idx] for row in self.model)

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
        if model.data_source.selected_column_idx:
            self._is_checked = model.get_value(
                iter_, model.data_source.selected_column_idx)


class DataGridIconView(Gtk.IconView):

    """A ``Gtk.IconView`` for displaying data from a ``DataGridModel``.

    :param model: The model providing the tabular data for the grid
    :type model: :class:`DataGridModel`
    :keyword bool has_checkboxes: Whether record rows have a checkbox

    """

    has_checkboxes = GObject.property(type=bool, default=True)

    def __init__(self, model, **kwargs):
        if 'cell_area' not in kwargs:
            kwargs['cell_area'] = DataGridCellAreaRenderer()

        super(DataGridIconView, self).__init__(**kwargs)

        self._button_press_time = 0
        self._button_press_scroll = None
        self._button_press_path = None

        self.pixbuf_column = None
        # FIXME: Ideally, we should pass model directly to treeview and get
        # it from self.get_model instead of here. We would need to refresh
        # it first though
        self.model = model

        self.connect('button-release-event', self.on_button_release_event)
        self.connect('key-press-event', self.on_key_press_event)

        self.refresh_draw = False
        self._block_draw = False

    ###
    # Public
    ###

    @contextlib.contextmanager
    def block_draw(self):
        """Block the drawing of this widget.

        While inside this context, this widget will not be draw.
        """
        self._block_draw = True
        yield
        self._block_draw = False
        self.queue_draw()

    def do_draw(self, cr):
        """Do the drawing of this widget.

        :param cr: The cairo context context
        :type cr: :class:`cairo.Context`
        """
        if self._block_draw:
            return
        if self.refresh_draw:
            GObject.idle_add(self.queue_draw)
            self.refresh_draw = False
        return Gtk.IconView.do_draw(self, cr)

    def refresh(self):
        """Refresh the model results."""
        self.set_model(None)
        self.model.refresh()
        self.set_model(self.model)

        if self.model.flat_column_idx is not None:
            # When defining a text column, we need to set a max width or
            # it will expand the rows to fit the longest string.
            self.set_item_width(100)
            self.set_text_column(self.model.flat_column_idx)

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
        coords = event.get_coords()
        path = self.get_path_at_pos(*coords)
        if not path:
            return False

        # If we have checkboxes, check if the click was on it. If it was,
        # we will need to toggle its state.
        if self.has_checkboxes:
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

        # FIXME: This is to workaround a problem that, if the item's height is
        # greater than the available space (and thus, it is cropped), double
        # clicking it will make the scroll move but not activate it.
        # We check if the scroll is really different to avoid activating the
        # item twice when the item is not cropped.
        # Note: Gtk considers a double click if the first event happened
        # with a difference of a quarter of second from the other.
        event_time = event.get_time()
        scroll = self.get_vadjustment().get_value()
        if (path == self._button_press_path and
                event_time - self._button_press_time <= 250 and
                scroll != self._button_press_scroll):
            self._button_press_time = 0
            self._button_press_scroll = None
            self._button_press_path = None
            self.item_activated(path)
            return True

        self._button_press_scroll = scroll
        self._button_press_time = event_time
        self._button_press_path = path

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
        selected_idx = self.model.data_source.selected_column_idx
        val = self.model.get_value(iter_, selected_idx)
        # FIXME: Gtk.IconView has some problems working with huge models.
        # It would invalidate everything on row changed, as can be seem here:
        # https://git.gnome.org/browse/gtk+/tree/gtk/gtkiconview.c
        # Atm we will avoid row-changed and just call queue_redraw which
        # will be a lot faster! We should try to find a better solution
        self.model.set_value(iter_, selected_idx, not val,
                             emit_event=False)
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
    image_load_on_thread = GObject.property(type=bool, default=True)

    STRING_MAX_LENGTH = 100
    IMAGE_PREFIX = 'file://'

    def __init__(self, data_source, get_media_callback, decode_fallback,
                 encoding_hint='utf-8'):
        """Set up model."""
        super(DataGridModel, self).__init__()

        self._invisible_images = {}
        self._fallback_images = {}
        self.visible_range = None
        self.active_params = {'flat': False}
        self.data_source = data_source
        self.get_media_callback = get_media_callback
        self.decode_fallback = decode_fallback
        self.columns = self.data_source.columns
        self.datetime_columns = []
        self.column_types = []
        for column in self.columns:
            transform = column['transform']
            if transform is None:
                continue
            if transform.startswith('timestamp'):
                self.datetime_columns.append(column)
            self.column_types.append(column['type'])

        selected_columns = self.data_source.get_visible_columns()
        if selected_columns is not None:
            self.display_columns = set(selected_columns)
        else:
            self.display_columns = {
                col['name'] for col in self.columns
                if col['visible'] and not col['name'].startswith('__')}

        self.encoding_hint = encoding_hint
        self.selected_cells = list()

        self.row_id_mapper = {}
        self.id_column_idx = None
        self.parent_column_idx = None
        self.flat_column_idx = None
        self.rows = None
        self.total_recs = None

    @property
    def hidden_columns(self):
        """A set of columns names that should not be displayed on the view."""
        hidden = {self.data_source.SELECTED_COLUMN}
        if not self.data_source.display_all:
            hidden.add(self.data_source.ID_COLUMN)
            hidden.add(self.data_source.PARENT_ID_COLUMN)
            if not self.active_params.get('flat', False):
                hidden.add(self.data_source.FLAT_COLUMN)
        return hidden

    def refresh(self):
        """Refresh the model from the data source."""
        if 'page' in self.active_params:
            del self.active_params['page']
        if 'parent_id' in self.active_params:
            del self.active_params['parent_id']

        self.row_id_mapper.clear()
        self.rows = self.data_source.load(self.active_params)
        self.rows.path = ()

        self.id_column_idx = self.data_source.id_column_idx
        self.parent_column_idx = self.data_source.parent_column_idx
        self.flat_column_idx = self.data_source.flat_column_idx
        self.total_recs = self.data_source.total_recs

        if self.id_column_idx is not None:
            for i, row in enumerate(self.rows):
                row.path = (i, )
                self.row_id_mapper[row.data[self.id_column_idx]] = row

        self.emit('data-loaded', self.total_recs)

    def add_rows(self, parent_node=None):
        """Add rows to the model from a new page of data and update the view.

        :return: True if update took place, False if not
        :rtype: bool
        """
        is_tree = (self.parent_column_idx is not None and
                   not self.active_params.get('flat', False))
        # When the data is hierarchical, all the root data was already loaded,
        # except in a flat view, where data is being lazy loaded.
        if is_tree and parent_node is None:
            return False

        if parent_node is None:
            parent_id = None
            parent_row = self.rows
            path_offset = self.rows[-1].path[-1] + 1
            # We are not using pages for hierarchical data
            self.active_params['page'] = self.active_params.get('page', 0) + 1
        else:
            parent_id = parent_node.data[self.id_column_idx]
            parent_row = parent_node
            path_offset = 0

        self.active_params['parent_id'] = parent_id
        rows = self.data_source.load(self.active_params)
        if not len(rows):
            return False

        for i, row in enumerate(rows):
            row.path = parent_row.path + (path_offset + i, )
            self.row_id_mapper[row.data[self.id_column_idx]] = row
            parent_row.append(row)

            # Non-hierarchical data need this to call self.row_inserted
            # so the treemodel will know about the new rows.
            # For hierarchical, those paths/iters already exists, they
            # are just lazy-loaded when neede (i.e. when expanding the parent)
            if not is_tree:
                parent_row.children_len += 1
                path = Gtk.TreePath(row.path)
                self.row_inserted(path, self.create_tree_iter(row.path))

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
        col_name = col_dict['name']

        # Defaults to string transformer if None
        transformer_name = col_dict['transform'] or 'string'
        transformer = get_transformer(transformer_name)
        transformer_kwargs = {}

        # Only enforce value type if the config was provided. Otherwise,
        # we would just be spamming a lot of obvious warnings (we got the type
        # from introspecting the database and for sqlite, it has a high
        # probability of not being an exact match in python).
        if (col_dict['from_config'] and
                value is not None and 'type' in col_dict):
            # Try enforcing value type
            value = self._enforce_value_type(value, col_dict['type'])

        if transformer is None:
            logger.warning("No transformer found for %s", transformer_name)
            return value

        if (transformer_name == 'boolean' and
                col_name == self.data_source.SELECTED_COLUMN):
            # __selected is an exception to the boolean transformation.
            # It requires a bool value and not a pixbuf
            return bool(value)
        elif transformer_name == 'image':
            transformer_kwargs.update(dict(
                size=self.image_max_size,
                draw_border=self.image_draw_border,
                load_on_thread=self.image_load_on_thread,
                draft=True,
            ))

            # If no value, use an invisible image as a placeholder
            if not value:
                invisible_img = self._invisible_images.get(self.image_max_size)
                if not invisible_img:
                    invisible_img = NO_IMAGE_PIXBUF.scale_simple(
                        self.image_max_size, self.image_max_size,
                        GdkPixbuf.InterpType.NEAREST)
                    self._invisible_images[self.image_max_size] = invisible_img
                return invisible_img

            if isinstance(value, buffer):
                # FIXME: Support buffer in the future. Atm, set visible to
                # False so a fallback image will be returned bellow
                logger.warn('Buffered images are still not supported')
                visible = False

            # When not visible on the iconview, use an already generated
            # fallback image (that has the same dimensions as the real
            # image should have) to improve loading time.
            if not visible:
                key = (self.image_draw_border, self.image_max_size)
                fallback = self._fallback_images.get(key)
                if not fallback:
                    fallback = transformer(None, **transformer_kwargs)
                    self._fallback_images[key] = fallback
                return fallback

            if value.startswith(self.IMAGE_PREFIX):
                value = value[len(self.IMAGE_PREFIX):]

            if not value:
                # Force fallback in this case
                value = None
            elif not os.path.isabs(value):
                if self.get_media_callback is None:
                    logger.warning(
                        "Don't know how to access the relative path '%s'. "
                        "Try passing get_full_path to controller.", value)
                    value = None
                else:
                    value = self.get_media_callback(value)
        elif transformer_name in ['string', 'html']:
            transformer_kwargs.update(dict(
                max_length=self.STRING_MAX_LENGTH, oneline=True,
                decode_fallback=self.decode_fallback,
            ))

        custom_options = col_dict.get('transform_options')
        if custom_options:
            transformer_kwargs['options'] = custom_options

        return transformer(value, **transformer_kwargs)

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
        path = self.get_path(itr)
        # path and iter are the same in this model.
        row = self._get_row_by_path(path)
        row.data[column] = value
        id_ = self.get_value(itr, self.id_column_idx)
        self.update_data_source(
            self.columns[column]['name'], value, [int(id_)])
        if emit_event:
            self.row_changed(path, itr)

    def iter_rows(self, load_rows=False):
        """Iterate over the rows of the model.

        This will iterate using a depth-first algorithm. That means that,
        on a hierarchy like this::

            A
              B
                E
              C
                F
                  G
                  H
              D

        This would generate an iteration like::

            [ A, B, E, C, F, G, H, D ]

        :param bool load_rows: if we should load rows from the
            datasource during the iteration. When using this, be sure
            to use lazy iteration and stop when you found what you needed.
        :returns: an iterator for the rows
        :rtype: generator
        """
        def _iter_children_aux(parent):
            for row in parent:
                if load_rows:
                    self._ensure_children_is_loaded(row)
                yield row
                for inner_row in _iter_children_aux(row):
                    yield inner_row

        for row in _iter_children_aux(self.rows):
            yield row

        if load_rows:
            rows_len = len(self.rows)
            while self.add_rows():
                for row in _iter_children_aux(self.rows[rows_len:]):
                    yield row
                rows_len = len(self.rows)

    def get_row_by_id(self, row_id, load_rows=False):
        """Get a row given its id

        Note that this will load the data from the source until the
        row is found, meaning that everything will be loaded on the
        worst case (i.e. the row is not present)

        :param object row_id: the id of the row
        :returns: the row or ``None`` if it wasn't found
        :rtype: :class:`datagrid_gtk3.db.sqlite.Node`
        """
        if row_id in self.row_id_mapper:
            return self.row_id_mapper[row_id]

        for row in self.iter_rows(load_rows=load_rows):
            # Although we could check row, trying self.row_id_mapper has a
            # chance of needing less iterations (and thus, less loading from
            # sqlite) since after loading all children of A, we can find them
            # on self.row_id_mapper without having to load their children too
            if row_id in self.row_id_mapper:
                return self.row_id_mapper[row_id]

    ###
    # Private
    ###

    def _enforce_value_type(self, value, type_):
        # FIXME: Some configurations are indicating the images as buffer,
        # but really are storing the file path. This can be removed
        # when those places are fixed.
        if type_ == buffer and isinstance(value, basestring):
            return value

        # Don't try to convert str=>unicode and unicode=>str
        type_check = basestring if type_ in [str, unicode] else type_
        if not isinstance(value, type_check):
            try:
                value = type_(value)
            except (ValueError, TypeError):
                logger.warn('Could not enforce type "%s" for "%r"',
                            type_.__name__, value)

        return value

    def _ensure_children_is_loaded(self, row):
        if not row.is_children_loaded():
            self.add_rows(row)

    def _get_row_by_path(self, iter_):
        def get_row_by_iter_aux(iter_aux, rows):
            self._ensure_children_is_loaded(rows)
            if len(iter_aux) == 1:
                row = rows[iter_aux[0]]
                return row
            return get_row_by_iter_aux(iter_aux[1:], rows[iter_aux[0]])

        return get_row_by_iter_aux(iter_, self.rows)

    ###
    # Required implementations for GenericTreeModel
    ###

    def on_get_flags(self):
        """Return the GtkTreeModelFlags for this particular type of model."""
        return Gtk.TreeModelFlags.ITERS_PERSIST

    def on_get_n_columns(self):
        """Return the number of columns in the model."""
        return len(self.columns)

    def on_get_column_type(self, index):
        """Return the type of a column in the model."""
        if self.columns[index]["name"] == self.data_source.SELECTED_COLUMN:
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
        return tuple(rowref)

    def on_get_iter(self, path):
        """Return the node corresponding to the given path (node is path)."""
        try:
            # row and path are the same in this model. We just need
            # to make sure that the iter is valid
            self._get_row_by_path(path)
        except IndexError:
            return None
        else:
            return tuple(path)

    def on_get_value(self, rowref, column):
        """Return the value stored in a particular column for the node."""
        if self.visible_range:
            visible = self.visible_range[0] <= rowref <= self.visible_range[1]
        else:
            visible = True

        row = self._get_row_by_path(rowref)
        raw = row.data[column]
        # Don't format value for id and parent columns. They are not displayed
        # on the grid and we may need their full values to get their records
        # (e.g. when the id is a string column)
        if column in [self.id_column_idx, self.parent_column_idx]:
            return raw
        else:
            return self.get_formatted_value(raw, column, visible=visible)

    def on_iter_next(self, rowref):
        """Return the next node at this level of the tree."""
        if rowref is None:
            return None

        # root node
        if len(rowref) == 1:
            rows = self.rows
            next_value = (rowref[0] + 1, )
        else:
            parentref = rowref[:-1]
            rows = self._get_row_by_path(parentref)
            next_value = parentref + (rowref[-1] + 1, )

        if not next_value[-1] < rows.children_len:
            return None

        return next_value

    def on_iter_children(self, rowref):
        """Return the first child of this node."""
        if rowref is None:
            return (0, )

        parent_row = self._get_row_by_path(rowref)
        if not parent_row.children_len:
            return None

        return rowref + (0, )

    def on_iter_has_child(self, rowref):
        """Return true if this node has children."""
        row = self._get_row_by_path(rowref)
        return row.children_len > 0

    def on_iter_n_children(self, rowref):
        """Return the number of children of this node."""
        if rowref is None:
            return len(self.rows)

        row = self._get_row_by_path(rowref)
        return row.children_len

    def on_iter_nth_child(self, parent, n):
        """Return the nth child of this node."""
        if parent is None:
            parent = ()
            rows = self.rows
        else:
            rows = self._get_row_by_path(parent)

        if not 0 <= n < rows.children_len:
            return None

        return parent + (n, )

    def on_iter_parent(self, child):
        """Return the parent of this node."""
        if len(child) == 1:
            return None

        return child[:-1]

    ###
    # END Required implementations for GenericTreeModel
    ###
