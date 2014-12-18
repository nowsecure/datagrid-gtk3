"""Database package.

Modules that provide interaction with persistent data stores via database
backends (eg. SQLite)

"""


class EmptyDataSource:

    """Data source that can be used when an empty data grid is required.
    Also, an illustration of the data source's interface.
    """

    def __init__(self):
        self.rows = []
        self.columns = []
        self.column_name_str = ''
        self.total_recs = 0
        self.display_all = True

    def get_selected_columns(self):
        pass

    def load(self, params=None):
        pass

    def update_selected_columns(self, columns):
        pass

    def get_all_record_ids(self, params=None):
        return []

    def get_single_record(self, record_id, table=None):
        return tuple()

    def update(self, params, ids=None):
        pass
