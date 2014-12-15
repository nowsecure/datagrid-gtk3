=====
Usage
=====

.. code-block:: python

    import gtk

    from datagrid-gtk2.ui.grid import DataGridContainer, DataGridController
    from datagrid-gtk2.db.sqlite import SQLiteDataSource

    win = gtk.Window()
    datagrid_container = DataGridContainer(win)
    datagrid_source = SQLiteDataSource(
        '/path/to/sqlite.db',
        'table_name',
        # optional table config list arg
    )
    datagrid_controller = DataGridController(datagrid_container, datagrid_source)
    win.add(datagrid_container.vpaned_grid)
    win.show_all()
    gtk.main()


Usage in place of viaextract-main.ui.datagrid
=============================================

When instantiating a `DataGridController`, pass the following functions
as the optional `file_getter` and `tostring_fallback` arguments to get
equivalent behavior:

.. code-block:: python

    from viaextract.util import get_media_file
    from viacore_utils.packages import magic

    def magic_fallback(obj):
        return magic.from_buffer(str(obj))

    DataGridController(container, source,
                       decode_fallback=magic_fallback,
                       get_full_path=get_media_file)

To make the `SQLiteDataSource` have equivalent behavior, use a subclass of it
with an overridden ID_COLUMN attribute:

.. code-block:: python

    from datagrid-gtk2.db.sqlite import SQLiteDataSource

    class vE_SQLiteDataSource(SQLiteDataSource):
        ID_COLUMN = '__viaextract_id'
