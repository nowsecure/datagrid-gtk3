"""Data grid MVC package.

Usage::

    from gi.repository import Gtk
    from datagrid_gtk3.ui.grid import DataGridContainer, DataGridController
    from datagrid_gtk3.db.sqlite import SQLiteDataSource
    win = Gtk.Window()
    datagrid_container = DataGridContainer(win)
    datagrid_source = SQLiteDataSource(
        '/path/to/sqlite.db',
        'table_name',
        # optional table config list arg
    )
    datagrid_controller = DataGridController(datagrid_container, datagrid_source)
    win.add(datagrid_container.vpaned_grid)
    win.show_all()

"""
