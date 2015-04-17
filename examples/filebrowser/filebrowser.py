#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Datagrid example using an filebrowser example database."""

import atexit
import logging
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from datagrid_gtk3.utils import (
    setup_logging_to_stdout,
    setup_gtk_show_rules_hint,
)
from datagrid_gtk3.ui.grid import (
    DataGridContainer,
    DataGridController,
)
from filebrowser_db import (
    FileBrowserDB,
    FileBrowserDataSource,
)

logger = logging.getLogger(__name__)


FILEBROWSER_CONFIG = [
    {
        'column': 'Parent',
        'type': 'str',
    },
    {
        'column': 'File',
        'type': 'str',
        'expand': True
    },
    {
        'column': 'File Path',
        'type': 'str',
        'expand': True
    },
    {
        'column': 'Preview',
        'type': 'str',
        'encoding': 'image',
        'expand': False,
    },
    {
        'column': 'Size',
        'type': 'long',
        'encoding': 'bytes',
    },
]


if __name__ == '__main__':
    setup_logging_to_stdout()
    setup_gtk_show_rules_hint()

    logger.info("Starting a datagrid_gtk3 example.")

    path = os.path.join(os.path.dirname(os.path.realpath(__file__)))
    db_path = os.path.join(path, 'filebrowser.sqlite')
    fdb = FileBrowserDB(db_path)
    fdb.load_path(os.path.join(path, 'examples'))

    atexit.register(lambda: os.remove(db_path))

    data_source = FileBrowserDataSource(
        db_path, FileBrowserDB.TABLENAME,
        config=FILEBROWSER_CONFIG, ensure_selected_column=False)

    win = Gtk.Window()

    datagrid_container = DataGridContainer(win)
    controller = DataGridController(
        datagrid_container, data_source, has_checkboxes=False)
    datagrid_container.grid_vbox.reparent(win)

    win.set_default_size(600, 400)
    win.connect("delete-event", lambda *args: Gtk.main_quit())
    win.show()

    try:
        Gtk.main()
    except KeyboardInterrupt:
        Gtk.main_quit()
