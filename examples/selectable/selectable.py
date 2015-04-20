#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Datagrid example using an example database with selectable rows."""

import logging
import os
import sys

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

try:
    import datagrid_gtk3
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                    os.path.pardir, os.path.pardir))
from datagrid_gtk3.utils import (
    setup_logging_to_stdout,
    setup_gtk_show_rules_hint,
)
from datagrid_gtk3.db.sqlite import SQLiteDataSource
from datagrid_gtk3.ui.grid import (
    DataGridContainer,
    DataGridController,
)

logger = logging.getLogger(__name__)


if __name__ == '__main__':
    setup_logging_to_stdout()
    setup_gtk_show_rules_hint()

    logger.info("Starting a datagrid_gtk3 example.")

    path = os.path.join(os.path.dirname(os.path.realpath(__file__)))
    db_path = os.path.join(path, 'selectable.sqlite')

    data_source = SQLiteDataSource(
        db_path, 'fruits', ensure_selected_column=True)

    win = Gtk.Window()

    datagrid_container = DataGridContainer(win)
    controller = DataGridController(
        datagrid_container, data_source, has_checkboxes=True)
    datagrid_container.grid_vbox.reparent(win)

    win.set_default_size(600, 400)
    win.connect("delete-event", lambda *args: Gtk.main_quit())
    win.show()

    try:
        Gtk.main()
    except KeyboardInterrupt:
        Gtk.main_quit()
