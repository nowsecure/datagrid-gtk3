
Usage
=====

The basic usage scenario looks like this:

.. code-block:: python

    win = Gtk.Window()

    data_source = SQLiteDataSource(db_path, table_name)
    datagrid_container = DataGridContainer(win)
    controller = DataGridController(datagrid_container, data_source)
    datagrid_container.grid_vbox.reparent(win)

    win.show()


For more advanced usages see the example applications in the "examples" folder.