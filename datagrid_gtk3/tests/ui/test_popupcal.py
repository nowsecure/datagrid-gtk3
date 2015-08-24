"""Popupcal tests."""

import datetime
import unittest

from gi.repository import Gtk
import mock

from datagrid_gtk3.ui.popupcal import DateEntry


class FakeDialog(object):

    """Object mimicing Gtk.Dialog's api."""

    def __init__(self, retval, *args):
        """Initialize the FakeDialog object."""
        self._retval = retval
        self.vbox = Gtk.VBox()

    def run(self):
        """Mimic the run method."""
        return self._retval

    def set_decorated(self, value):
        """Stub set_decorated method."""
        pass

    def add_button(self, label, response):
        """Mimic fake_button method."""
        return Gtk.Button(label)

    def destroy(self):
        """Stub destroy method."""
        pass

    def get_action_area(self):
        """Mimic get_action_area method."""
        class FakeActionArea(object):
            def reorder_child(self, btn, order):
                pass
        return FakeActionArea()


class DateEntryTest(unittest.TestCase):

    """Tests for :class:`datagrid_gtk3.ui.popupcal.DateEntry`."""

    def setUp(self):
        """Setup widget for testing."""
        self._entry = DateEntry(Gtk.Window(), DateEntry.TYPE_START)

    def test_set_date(self):
        """set_date should set the text for the widget based on the format."""
        self.assertEqual(self._entry.get_property('text'), '')

        self._entry.set_date(datetime.datetime(2015, 8, 10))
        self.assertEqual(self._entry.get_property('text'), '10-Aug-2015 00:00')

        self._entry.set_date(datetime.datetime(2015, 8, 12, 15, 20))
        self.assertEqual(self._entry.get_property('text'), '12-Aug-2015 15:20')

        self._entry.set_date(None)
        self.assertEqual(self._entry.get_property('text'), '')

    def test_get_date(self):
        """get_date should return a datetime based on the text on the entry."""
        self._entry.set_property('text', '')
        self.assertIsNone(self._entry.get_date())

        self._entry.set_property('text', '10-Aug-2015 00:00')
        self.assertEqual(self._entry.get_date(),
                         datetime.datetime(2015, 8, 10))

        self._entry.set_property('text', '12-Aug-2015 15:20')
        self.assertEqual(self._entry.get_date(),
                         datetime.datetime(2015, 8, 12, 15, 20))

    def test_set_text(self):
        """set_text should set the text for the widget based on the format."""
        self.assertEqual(self._entry.get_property('text'), '')

        self._entry.set_text('2-Jun-2013 06:48')
        self.assertEqual(self._entry.get_date(),
                         datetime.datetime(2013, 6, 2, 6, 48))
        self.assertEqual(self._entry.get_property('text'), '2-Jun-2013 06:48')

        self._entry.set_text('02/10/2015')
        self.assertEqual(self._entry.get_date(),
                         datetime.datetime(2015, 2, 10))
        self.assertEqual(self._entry.get_property('text'), '10-Feb-2015 00:00')

    def test_get_text(self):
        """get_text should return a formated date based on the format."""
        self.assertEqual(self._entry.get_property('text'), '')

        self._entry.set_date(datetime.datetime(2015, 8, 10))
        self.assertEqual(self._entry.get_text(), '10-Aug-2015 00:00')

        self._entry.set_date(datetime.datetime(2015, 8, 12, 15, 20))
        self.assertEqual(self._entry.get_text(), '12-Aug-2015 15:20')

    def test_popup_response_ok(self):
        """DatePicker should change the date on entry on response ok."""
        self._entry.set_date(datetime.datetime(2015, 1, 2, 10, 20))

        with mock.patch('datagrid_gtk3.ui.popupcal.Gtk.Dialog') as dialog:
            fake_dialog = FakeDialog(Gtk.ResponseType.OK)
            dialog.return_value = fake_dialog

            with mock.patch.object(self._entry, 'get_date') as get_date:
                # Entry will use the actual date to populate the date picker
                get_date.return_value = datetime.datetime(2010, 2, 3)
                self._entry._popup_picker()
            self.assertEqual(self._entry.get_date(),
                             datetime.datetime(2010, 2, 3))

    def test_popup_response_clear(self):
        """DatePicker should clear the date on entry on response clear."""
        self._entry.set_date(datetime.datetime(2015, 1, 2, 10, 20))

        with mock.patch('datagrid_gtk3.ui.popupcal.Gtk.Dialog') as dialog:
            fake_dialog = FakeDialog(99)
            dialog.return_value = fake_dialog

            self.assertEqual(self._entry.get_date(),
                             datetime.datetime(2015, 1, 2, 10, 20))
            self._entry._popup_picker()
            self.assertIsNone(self._entry.get_date())
