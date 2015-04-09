"""Datagrid utilies package."""

import logging
import sys

from gi.repository import Gtk, Gdk


def setup_logging_to_stdout():
    """Sets up logging to std out."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


def setup_gtk_show_rules_hint(base_color='base_color'):
    """Modify gtk theme to display rules hinting.

    Different from gtk2, gtk3 rules hinting is only displayed if the
    theme implements it. This is a way to override that.

    :param base_color: the theme base color, if different from the default
    """
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data("""
        GtkTreeView row:nth-child(even) {
            background-color: shade(@%s, 1.0);
        }
        GtkTreeView row:nth-child(odd) {
            background-color: shade(@%s, 0.95);
        }
    """ % (base_color, base_color))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
