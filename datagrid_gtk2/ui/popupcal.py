"""Popup calendar widget module."""
import time

import gobject
import gtk


class InvalidDate(Exception):

    """Invalid date custom exception class.

    :param str date: the invalid date string to put in the message

    """

    def __init__(self, date):
        """Set exception message."""
        super(InvalidDate, self).__init__()
        self.message = 'Invalid date "%s".' % (date)

    def __str__(self):
        """Set str representation of class to exception message."""
        return self.message


class DateEntry(gtk.Entry):

    """Clickable text box that launches a calendar for populating with a date.

    :param parent_window: Main window of the application
    :type parent_window: class:`gtk.Window`

    """

    __gsignals__ = dict(
        date_changed=(gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ()))

    DEFAULT_DATE_FORMAT = '%e-%b-%Y'

    # Different data formats used to try to parse a text date
    DATE_FORMATS = (
        '%Y-%m-%d %H:%M:%S',
        '%d-%m-%Y',
        '%d-%b-%Y',
        '%d-%B-%Y',
        '%d-%m-%y',
        '%d-%b-%y',
        '%d-%B-%y',
        '%Y-%m-%d',
        '%Y-%b-%d',
        '%Y-%B-%d',
        '%d/%m/%Y',
        '%d/%b/%Y',
        '%d/%B/%Y',
        '%d/%m/%y',
        '%d/%b/%y',
        '%d/%B/%y',
        '%Y/%m/%d',
        '%Y/%b/%d',
        '%Y/%B/%d'
    )

    def __init__(self, parent_window):
        """Set up widget."""
        super(DateEntry, self).__init__()
        self.connect('focus_out_event', self.on_focus_out_event)
        self.connect('button_press_event', self.on_button_press_event)
        self.connect('activate', lambda widget: widget.get_toplevel()
                     .child_focus(gtk.DIR_TAB_FORWARD))
        assert parent_window, 'Parent window needed'
        self.parent_window = parent_window
        self.set_width_chars(11)

        self.calendar_dialog = False
        self.timestamp = None

    def popup_calendar(self):
        """Display the calendar dialog."""
        self.calendar_dialog = True
        dialog = gtk.Dialog(
            None, self.parent_window,
            gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
             gtk.STOCK_OK, gtk.RESPONSE_OK)
        )
        # self.dialog.set_position(gtk.WIN_POS_MOUSE)
        calendar = gtk.Calendar()
        dialog.vbox.pack_start(calendar, expand=True, fill=True, padding=0)
        dialog.set_decorated(False)
        dialog.action_area.hide()
        calendar.connect('day_selected_double_click',
                         self.on_day_selected, dialog)
        timestamp = self.timestamp
        if timestamp is None:
            timestamp = time.localtime()
        if timestamp:
            calendar.select_month(timestamp[1] - 1, timestamp[0])
            calendar.select_day(timestamp[2])
        dialog.show_all()
        result = dialog.run()
        if result == gtk.RESPONSE_OK:
            self.on_day_selected(calendar, dialog)
        else:
            dialog.destroy()
        self.calendar_dialog = False

    def set_today(self):
        """Set widget to today's date."""
        # round the current time into a date
        timestamp = time.strptime(
            time.strftime('%d-%b-%Y', time.localtime()), '%d-%b-%Y')
        self.check_for_signal(timestamp)
        super(DateEntry, self).set_text(self.get_date())

    def set_date(self, date, date_format=None):
        """Set the date in the widget.

        :param str date: date string
        :param str date_format: date format string
        :raises ValueError: if format is None

        """
        if date is None or len(date.strip()) == 0:
            self.check_for_signal(None)
            super(DateEntry, self).set_text('')
            return
        if date_format is None:
            date_format = self.check_formats(date)
        else:
            self.timestamp = time.strptime(date, date_format)
            super(DateEntry, self).set_text(self.get_date())
        if date_format is None:
            raise ValueError('Unknown date format - %s' % (date))

    def get_date(self, date_format=None):
        """Get the date currently in widget.

        :param str date_format: date format string
        :return: formatted date time
        :rtype: str

        """
        # check if the widget has the focus
        if self.is_focus():
            # the widget has the focus
            # we need to check if the current text is OK
            text = super(DateEntry, self).get_text()
            if len(text) > 0:
                timestamp = self.check_formats(text)
                if not timestamp:
                    raise InvalidDate(text)
            else:
                return None
        if self.timestamp is None:
            return None
        if date_format is None:
            date_format = self.DEFAULT_DATE_FORMAT
        return time.strftime(date_format, self.timestamp)

    def check_for_signal(self, current):
        """Emit date changed signal if changed."""
        if current != self.timestamp:
            self.timestamp = current
            self.emit('date_changed')

    def check_formats(self, text):
        """Ensure valid date format string is being used (?).

        :param str text: the text of the date string
        """
        # try multple formats for converting to a timestamp
        try:
            timestamp = time.strptime(text, self.DEFAULT_DATE_FORMAT)
        except ValueError:
            # Ignore parsing errors
            pass
        else:
            super(DateEntry, self).set_text(
                time.strftime(self.DEFAULT_DATE_FORMAT, timestamp))
            self.check_for_signal(timestamp)
            return timestamp

        for date_format in self.DATE_FORMATS:
            try:
                timestamp = time.strptime(text, date_format)
            except ValueError:
                # Ignore parsing errors
                pass
            else:
                super(DateEntry, self).set_text(
                    time.strftime(self.DEFAULT_DATE_FORMAT, timestamp))
                self.check_for_signal(timestamp)
                return timestamp
        return None

    def set_text(self, _text):
        """Disallow use of ``set_text``.

        :raises AttributeError: if method is used
        """
        raise AttributeError('Use set_date()')

    def get_text(self):
        """Get the text currently in the date widget."""
        return self.get_date()

    def clear_date(self):
        """Clear the date widget."""
        super(DateEntry, self).set_text('')
        self.timestamp = None

    ###
    # Signal handler callbacks
    ###

    def on_button_press_event(self, _widget, event):
        """Signal handler to launch calendar widget.

        :param widget: the widget that called the event
        :type widget: class:`gtk.Widget`
        :param event: button press event
        :type event: :class:`gtk.gdk.Event`

        """
        if event.button == 1 and event.type == gtk.gdk.BUTTON_PRESS:
            text = super(DateEntry, self).get_text()
            if text is None or len(text.strip()) == 0:
                # we don't want to emit a signal as the popup will do so when
                # needed
                self.timestamp = None
            self.popup_calendar()
            return True
        else:
            return False

    def on_focus_out_event(self, _widget, _event):
        """Validate date when dialog gets out of focus.

        Display error dialog if it's not possible to parse date.

        :param _widget: The widget that emitted the focus_out_event signal
        :type _widget: gtk.Entry
        :param _event: The event that triggered the signal
        :type _event: gtk.gdk.Event

        """
        text = super(DateEntry, self).get_text()
        if text is None or len(text.strip()) == 0:
            self.check_for_signal(None)
            return

        timestamp = self.check_formats(text)
        if timestamp is None and not self.calendar_dialog:
            dialog = gtk.MessageDialog(
                self.parent_window,
                gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_MODAL,
                gtk.MESSAGE_ERROR,
                gtk.BUTTONS_CANCEL,
                'Unknown date format\n%s' % (text))
            dialog.connect('response', self.on_dialog_response)
            dialog.show()

    def on_day_selected(self, widget, dialog):
        """Update text when day is selected or OK button in dialog is clicked.

        :param widget: The calendar in which the date was selected
        :type widget: gtk.Calendar
        :param dialog: A dialog that is used to display the calendar widget
        :type dialog: gtk.Dialog

        """
        (year, month, day) = widget.get_date()
        current = time.strptime(
            '%d-%d-%d' % (year, month + 1, day), '%Y-%m-%d')
        super(DateEntry, self).set_text(
            time.strftime(self.DEFAULT_DATE_FORMAT, current))
        self.check_for_signal(current)
        dialog.destroy()

    def on_dialog_response(self, dialog, _response):
        """Close error message dialog and grab fous on main one.

        :param dialog: The dialog used to display an error message
        :type dialog: gtk.Dialog
        :param _response: The dialog response code
        :type _response: gtk.RESPONSE_*

        """
        gobject.timeout_add(100, self.grab_focus)
        dialog.destroy()
