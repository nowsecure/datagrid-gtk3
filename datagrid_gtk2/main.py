# -*- coding: utf-8 -*-

"""Main module of the datagrid_gtk2 package, used to start an example."""

import logging
import sys
import os

import pygtk
pygtk.require('2.0')

import gtk

from ui.grid import DataGridContainer, DataGridController
from db.sqlite import SQLiteDataSource

logger = logging.getLogger(__name__)


def setup_logging():
    """Sets up logging to std out."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


def main():
    """Example usage of the datagrid-gtk2 package."""
    logger.info("Starting a datagrid-gtk2 example.")

    win = gtk.Window()

    datagrid_container = DataGridContainer(win)
    datagrid_source = SQLiteDataSource(
        os.path.join(os.path.dirname(os.path.realpath(__file__)),
                     os.path.pardir, 'example_data', 'chinook.sqlite'),
        'track',
        ensure_selected_column=False
    )
    controller = DataGridController(datagrid_container, datagrid_source,
                                    has_checkboxes=False)
    datagrid_container.grid_vbox.reparent(win)

    win.set_default_size(600, 400)
    win.connect("delete-event", lambda *args: gtk.main_quit())
    win.show_all()
    gtk.main()


if __name__ == '__main__':
    setup_logging()
    main()
