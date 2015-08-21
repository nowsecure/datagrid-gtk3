"""Popup calendar widget module."""

import datetime
import os

from gi.repository import (
    GObject,
    Gdk,
    Gtk,
)

from datagrid_gtk3.ui.uifile import UIFile
from datagrid_gtk3.utils import dateutils


class _DatePicker(UIFile):

    """Date picker widget."""

    UI_FNAME = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'glade', 'popupcal.glade')

    def __init__(self):
        """Initialize the _DatePicker object."""
        super(_DatePicker, self).__init__(self.UI_FNAME)

        for widget in [self.hours, self.minutes]:
            widget.connect('output', self._on_spinbutton_output)

    ###
    # Public
    ###

    def set_datetime(self, date):
        """Set the date and time for this widget.

        :param date: The date to use to set this widget's values
        :type date: datetime.datetime
        """
        self.calendar.select_month(date.month - 1, date.year)
        self.calendar.select_day(date.day)
        self.hours.set_value(date.hour)
        self.minutes.set_value(date.minute)

    def get_datetime(self):
        """Get the actual selected date and time.

        :rtype: datetime.datetime
        """
        (year, month, day) = self.calendar.get_date()
        hours = self.hours.get_value_as_int()
        minutes = self.minutes.get_value_as_int()
        return datetime.datetime(year, month + 1, day, hours, minutes)

    ###
    # Callbacks
    ###

    def _on_spinbutton_output(self, widget):
        """Override spinbutton output signal.

        We want to make sure that leading zeroes are displayed on the widget.

        :param widget: The spinbutton that emitted the signal
        :type widget: :class:`Gtk.SpinButton`
        """
        widget.set_text('%02d' % (widget.get_value_as_int(), ))
        return True


class DateEntry(Gtk.Entry):

    """Clickable text box that launches a calendar for populating with a date.

    :param parent_window: Main window of the application
    :type parent_window: class:`Gtk.Window`

    """

    __gsignals__ = dict(
        date_changed=(GObject.SignalFlags.RUN_FIRST, None, ()))

    (TYPE_NOW,
     TYPE_START,
     TYPE_END) = range(3)

    DEFAULT_DATE_FORMAT = '%e-%b-%Y %H:%M'

    def __init__(self, parent_window, type_):
        """Set up widget."""
        super(DateEntry, self).__init__()

        self.connect('focus_out_event', self.on_focus_out_event)
        self.connect('button_press_event', self.on_button_press_event)
        self.connect('activate', lambda widget: widget.get_toplevel()
                     .child_focus(Gtk.DirectionType.TAB_FORWARD))
        assert parent_window, 'Parent window needed'
        self.type_ = type_
        self.parent_window = parent_window
        self.set_width_chars(15)
        self.calendar_dialog = False

    ###
    # Private
    ###

    def _popup_picker(self):
        """Display the calendar dialog."""
        self.calendar_dialog = True
        dialog = Gtk.Dialog(
            None, self.parent_window,
            Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OK, Gtk.ResponseType.OK)
        )

        date = self.get_date()
        if date is None:
            date = datetime.datetime.now()
            if self.type_ == self.TYPE_START:
                date = date.replace(hour=0, minute=0)
            elif self.type_ == self.TYPE_END:
                date = date.replace(hour=23, minute=59)

        date_picker = _DatePicker()
        date_picker.date_picker_alignment.reparent(dialog.vbox)
        date_picker.set_datetime(date)
        dialog.set_decorated(False)

        response_clear = 99
        clear_btn = dialog.add_button('Clear', response_clear)
        action_area = dialog.get_action_area()
        action_area.reorder_child(clear_btn, 0)
        clear_btn.set_sensitive(bool(self.get_date()))

        calendar = date_picker.calendar
        response_day_selected = 98
        calendar.connect('day_selected_double_click',
                         lambda d: dialog.response(response_day_selected))

        result = dialog.run()
        if result in [Gtk.ResponseType.OK, response_day_selected]:
            self.set_date(date_picker.get_datetime())
        elif result == response_clear:
            self.set_date(None)

        dialog.destroy()
        self.calendar_dialog = False

    ###
    # Public
    ###

    def set_date(self, date):
        """Set the date for this widget.

        :param date: The date object to use
        :type date: datetime.datetime
        """
        old_date = self.get_date()
        date_str = date.strftime(self.DEFAULT_DATE_FORMAT) if date else ''
        super(DateEntry, self).set_text(date_str.strip())
        if date != old_date:
            self.emit('date_changed')

    def get_date(self, date_format=None):
        """Get the current date in the widget.

        :rtype: datetime.datetime
        """
        text = super(DateEntry, self).get_text()
        if not text:
            return None

        date = dateutils.parse_string(text)
        if self.type_ == self.TYPE_START:
            date = date.replace(second=0)
        elif self.type_ == self.TYPE_END:
            date = date.replace(second=59)

        return date

    def set_text(self, text):
        """Set the date in the widget as a text.

        :param str text: The text to be parsed and set on the widget
        :raises: :exc:`datagrid_gtk3.utils.dateutils.InvalidDateFormat`
            if the format is not recognized
        """
        self.set_date(dateutils.parse_string(text))

    def get_text(self):
        """Get the text currently in the date widget."""
        date = self.get_date()
        if not date:
            return ''
        return date.strftime(self.DEFAULT_DATE_FORMAT)

    def clear_date(self):
        """Clear the date widget."""
        super(DateEntry, self).set_text('')

    ###
    # Signal handler callbacks
    ###

    def on_button_press_event(self, _widget, event):
        """Signal handler to launch calendar widget.

        :param widget: the widget that called the event
        :type widget: class:`Gtk.Widget`
        :param event: button press event
        :type event: :class:`Gdk.Event`

        """
        if (event.button == Gdk.BUTTON_PRIMARY and
                event.type == Gdk.EventType.BUTTON_PRESS):
            self._popup_picker()
            return True
        else:
            return False

    def on_focus_out_event(self, _widget, _event):
        """Validate date when dialog gets out of focus.

        Display error dialog if it's not possible to parse date.

        :param _widget: The widget that emitted the focus_out_event signal
        :type _widget: Gtk.Entry
        :param _event: The event that triggered the signal
        :type _event: Gdk.Event

        """
        try:
            text = self.get_text()
        except Exception:
            valid = False
        else:
            valid = True

        if valid and not text:
            return

        if not valid and not self.calendar_dialog:
            dialog = Gtk.MessageDialog(
                self.parent_window,
                Gtk.DialogFlags.DESTROY_WITH_PARENT | Gtk.DialogFlags.MODAL,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.CANCEL,
                'Unknown date format\n%s' % (text))
            dialog.connect('response', self.on_dialog_response)
            dialog.show()

    def on_dialog_response(self, dialog, _response):
        """Close error message dialog and grab fous on main one.

        :param dialog: The dialog used to display an error message
        :type dialog: Gtk.Dialog
        :param _response: The dialog response code
        :type _response: Gtk.ResponseType.*

        """
        GObject.timeout_add(100, self.grab_focus)
        dialog.destroy()
