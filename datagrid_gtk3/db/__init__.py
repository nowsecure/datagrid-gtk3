"""Database package.

Modules that provide interaction with persistent data stores via database
backends (eg. SQLite)

"""

from gi.repository import GObject


class Node(list):

    """A list that can hold data.

    Just like a simple list, but one can set/get its data
    from :obj:`.data`.

    :param object data: the data that will be stored in this node
    :param int children_len: the number of the children that will
        be loaded lazely at some point
    """

    def __init__(self, data=None, children_len=0):
        super(Node, self).__init__()

        self.data = data
        self.children_len = children_len
        self.path = None

    def is_children_loaded(self, recursive=False):
        """Check if this node's children is loaded

        :param bool recursive: wheather to ask each child if their
            children is loaded (and their child too and so on) too.
        :returns: `True` if children is loaded, otherwise `False`
        :rtype: bool
        """
        loaded = len(self) == self.children_len
        if recursive:
            loaded = (loaded and
                      all(c.is_children_loaded(recursive=True) for c in self))
        return loaded


class DataSource(GObject.GObject):
    """Base class for data sources."""

    ID_COLUMN = 'rowid'
    SELECTED_COLUMN = '__selected'
    PARENT_ID_COLUMN = None
    CHILDREN_LEN_COLUMN = None
    FLAT_COLUMN = None

    def __init__(self):
        super(DataSource, self).__init__()
        self.columns = []
        self.total_recs = 0
        self.display_all = True
        self.id_column_idx = None
        self.parent_column_idx = None
        self.children_len_column_idx = None
        self.flat_column_idx = None
        self.selected_column_idx = None

    def get_visible_columns(self):
        return []

    def load(self, params=None):
        return Node()

    def update_selected_columns(self, columns):
        pass

    def get_all_record_ids(self, params=None):
        return []

    def get_single_record(self, record_id, table=None):
        return tuple()

    def update(self, params, ids=None):
        pass


class EmptyDataSource(DataSource):
    """Data source that can be used when an empty data grid is required."""

    __gsignals__ = {
        'rows-changed': (GObject.SignalFlags.RUN_LAST, None, (object, object)),
    }
