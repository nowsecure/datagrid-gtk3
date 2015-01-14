"""User interface file handling classes."""
from collections import defaultdict

from gi.repository import Gtk


class UIFile(object):

    """Load user interface file and provide additonal features.

    :param ui_filename: Name pointing to the user interface file
    :type ui_filename: str

    Additional features provided are as follows:

    * Connect callbacks methods from ui file
    * Attribute access to widgets in the ui file through
      ``Gtk.Builder.get_object()``
    * Helper methods to connect/disconnect all signal handlers to
      other objects. This is useful for dialogs that are destroyed,
      but connected to signals of other objects that remain alive. This
      is important because otherwise a reference to the callback
      methods is kept and, in fact, those callbacks are executed even
      after the dialog has been destroyed.
    """

    def __init__(self, ui_filename):
        """Open user interface file and connect widgets to callback methods."""
        builder = Gtk.Builder()
        builder.add_from_file(ui_filename)
        builder.connect_signals(self)
        setattr(self, 'builder', builder)

        # Keep a record of all handlers to disconnect them later if needed
        self._handler_ids = defaultdict(list)

    def __getattr__(self, name):
        """Look for widgets in builder object as attributes.

        :param name: Attribute name
        :type name: str
        :returns: Widget
        :rtype: ``Gtk.Widget`` (any of its subclasses)
        :raises:
            ``AtributeError`` when the attribute definition is not found in the
            ui file
        """
        obj = self.builder.get_object(name)

        if obj is None:
            raise AttributeError(name)

        return obj

    def connect_signal(self, obj, signal, handler, *args):
        """Connect signal handler and keep a record of its id.

        The id of the handlers is used to disconnect it on destroy

        :param obj: Object that will emit the signal
        :type obj: ``GObject.GObject``
        :param signal: Signal name
        :type signal: str
        :param handler: Callback to be executed when the signal is emitted
        :type handler: callable
        :param args: Additional arguments required by the signal
        :type args: iterable
        """
        handler_id = obj.connect(signal, handler, *args)
        self._handler_ids[obj].append(handler_id)
        return handler_id

    def disconnect_all_signals(self):
        """Disconnect all handlers."""
        for obj, handler_ids in self._handler_ids.iteritems():
            for handler_id in handler_ids:
                if obj.handler_is_connected(handler_id):
                    obj.disconnect(handler_id)


class SignalBlocker:

    """Block widget signals connected to a callback.

    :param widget: Widget that will emit the signal
    :type widget: ``GObject.GObject``
    :param callback: Function to block
    :type callback: callable

    """

    def __init__(self, widget, callback):
        """Keep a reference to widget and callback.

        Those references are required later when using the signal blocker as a
        context manager.

        """
        self.widget = widget
        self.callback = callback

    def __enter__(self):
        """Block sighnal handler for a given widget."""
        self.widget.handler_block_by_func(self.callback)

    def __exit__(self, type, value, traceback):
        """Unblock sighnal handler for a given widget."""
        self.widget.handler_unblock_by_func(self.callback)
        return False
