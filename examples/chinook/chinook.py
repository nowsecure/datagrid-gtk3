#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Datagrid example using chinook database."""

import logging
import os
import sys

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import (
    GObject,
    Gtk,
)

try:
    import datagrid_gtk3
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                    os.path.pardir, os.path.pardir))
from datagrid_gtk3.utils import (
    setup_logging_to_stdout,
    setup_gtk_show_rules_hint,
)
from datagrid_gtk3.ui.grid import (
    DataGridContainer,
    DataGridController,
)
from datagrid_gtk3.db.sqlite import SQLiteDataSource
from datagrid_gtk3.db import EmptyDataSource

logger = logging.getLogger(__name__)


# TODO: Add config for all tables
_EXAMPLE_DATABASES = {
    'album': None,
    'artist': None,
    'employee': [
        {
            'column': 'LastName',
            'type': 'str',
        },
        {
            'column': 'FirstName',
            'type': 'str',
        },
        {
            'column': 'Title',
            'type': 'str',
        },
        {
            'column': 'ReportsTo',
            'type': 'long',
        },
        {
            'column': 'BirthDate',
            'type': 'long',
            'encoding': 'timestamp'
        },
        {
            'column': 'HireDate',
            'type': 'long',
            'encoding': 'timestamp',
        },
        {
            'column': 'Address',
            'type': 'str'
        },
        {
            'column': 'City',
            'type': 'str'
        },
        {
            'column': 'State',
            'type': 'str'
        },
        {
            'column': 'Country',
            'type': 'str'
        },
        {
            'column': 'PostalCode',
            'type': 'str'
        },
        {
            'column': 'Phone',
            'type': 'str'
        },
        {
            'column': 'Fax',
            'type': 'str'
        },
        {
            'column': 'Email',
            'type': 'str'
        }
    ],
    'genre': None,
    'track': None,
}


def main():
    """Example usage of the datagrid_gtk3 package."""
    logger.info("Starting a datagrid_gtk3 example.")

    db_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), 'chinook.sqlite')

    win = Gtk.Window()
    datagrid_container = DataGridContainer(win)
    controller = DataGridController(datagrid_container,
                                    EmptyDataSource(),
                                    has_checkboxes=False)
    datagrid_container.grid_vbox.reparent(win)

    win.set_default_size(600, 400)
    win.connect("delete-event", lambda *args: Gtk.main_quit())
    win.show()

    tables = Gtk.Window()
    tables.set_title("Choose a table")

    table_list = Gtk.TreeView()
    column = Gtk.TreeViewColumn("")
    table_list.append_column(column)
    cell = Gtk.CellRendererText()
    column.pack_start(cell, True)
    column.add_attribute(cell, 'text', 0)

    table_store = Gtk.ListStore(str, object)
    for database, config in _EXAMPLE_DATABASES.iteritems():
        table_store.append([database, config])
    table_list.set_model(table_store)

    def select_table(selection):
        model, iterator = selection.get_selected()
        if iterator:
            table_name, config = model[iterator]
            controller.bind_datasource(SQLiteDataSource(
                db_path, table_name, config=config,
                ensure_selected_column=False, display_all=True,
                persist_columns_visibility=False
            ))
    table_list.get_selection().connect("changed", select_table)

    tables.add(table_list)
    tables.set_default_size(300, 400)
    GObject.idle_add(tables.show_all)

    try:
        Gtk.main()
    except KeyboardInterrupt:
        Gtk.main_quit()


if __name__ == '__main__':
    setup_logging_to_stdout()
    setup_gtk_show_rules_hint()
    main()
