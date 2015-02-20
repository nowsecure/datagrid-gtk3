"""SQLite database backend."""
import logging
import sqlite3
import struct
from contextlib import closing

from sqlalchemy import (
    Column,
    MetaData,
    Table,
    create_engine,
    inspect,
)
from sqlalchemy.exc import DatabaseError

from datagrid_gtk3.db import DataSource

logger = logging.getLogger(__name__)


class Node(list):

    """A list that can hold data.

    Just like a simple list, but one can set/get its data
    from :obj:`.data`.

    :param object data: the data that will be stored in this node
    """

    def __init__(self, data=None):
        super(Node, self).__init__()
        self.data = data


class SQLiteDataSource(DataSource):

    """SQLite data source especially for use with a `Gtk.TreeModel`.

    Provides a SQLite backend for providing data to a
    :class:`datagrid_gtk3.ui.grid.DataGridModel` instance, which is
    a GTK `TreeModel`.

    Optional table configuration example::

        [
            ('ID', (int, None)),
            ('Title', (str, None)),
            ('Date', (long, 'datetime')),
            ('Thumbnail', (buffer, 'image'))
        ]

    :param str db_file: path to SQLite database file
    :param str table: name of table in SQLite db
    :param str update_table: table to perform update operations on, eg.
        if the table being SELECTed is actually a view
    :param list config: list of table configuration tuples including display
        names, data types, transforms, etc.
    :param bool ensure_selected_column: Whether to ensure the presence of
        the __selected column.
    :param bool display_all: Whether or not all columns should be displayed.
    :param str query: Full custom query to be used instead of the table name.
    """

    MAX_RECS = 100
    SQLITE_PY_TYPES = {
        'INT': long,
        'INTEGER': long,
        'LONG': long,
        'TEXT': str,
        'REAL': float,
        'BLOB': str
    }
    ID_COLUMN = 'rowid'
    PARENT_ID_COLUMN = None

    def __init__(self, db_file, table=None, update_table=None, config=None,
                 ensure_selected_column=True, display_all=False, query=None):
        """Process database column info."""
        assert table or query  # either table or query must be given
        self.db_file = db_file
        self.table = table if table else "__CustomQueryTempView"
        self.query = query
        if query:
            logger.debug("Custom SQL: %s", query)
        self._ensure_selected_column = ensure_selected_column
        self.display_all = display_all
        if update_table is not None:
            self.update_table = update_table
        else:
            self.update_table = table
        self.config = config
        self.rows = None
        self._id_column_idx = None
        self._parent_column_idx = None
        self.columns = self.get_columns()
        column_names = ['"%s"' % col['name'] for col in self.columns]
        self.column_name_str = ', '.join(column_names)
        self.total_recs = None

    def load(self, params=None):
        """Execute SQL ``SELECT`` and populate ``rows`` attribute.

        Loads a maximum of ``MAX_RECS`` records at a time.

        ``params`` dict example::

            {
                'desc': False,
                'order_by': 'title',
                'where': {
                    'date': {
                        'operator': 'range',
                        'param': (0, 1403845140)
                    },
                    'search': {
                        'operator': '=',
                        'param': 'Google'}
                    }
                }
            }

        :param dict params: dict of various parameters from which to construct
            additional SQL clauses eg. ``WHERE``, ``ORDER BY``, etc.
        """
        first_access = True
        last_page = False
        offset = 0
        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.row_factory = lambda cursor, row: list(row)
            # ^^ make result lists mutable so we can change values in
            # the GTK TreeModel that uses this datasource.
            conn.create_function('rank', 1, rank)
            # TODO: ^^ only if search term in params
            with closing(conn.cursor()) as cursor:
                self._ensure_temp_view(cursor)
                bindings = []
                where_sql = ''
                order_sql = ''
                # FIXME: We probably should return rows in this function
                # instead of setting it to self.rows and having datagrid to
                # access it after.
                self.rows = Node()
                if params:
                    # construct WHERE clause
                    if 'where' in params:
                        where_sql, bindings = self._get_where_clause(
                            self.table, params['where'])
                    # construct ORDER BY clause
                    if 'order_by' in params:
                        order_sql = order_sql + ' ORDER BY "%s"' % \
                            params['order_by']
                        if 'desc' in params:
                            if params['desc'] is True:
                                order_sql = order_sql + ' DESC'
                    # determine OFFSET value for paging
                    if 'page' in params:
                        first_access = False
                        if params['page']:
                            offset = params['page'] * self.MAX_RECS
                            if offset >= self.total_recs:
                                # at end of total records, return no records
                                #   for paging
                                last_page = True
                if not last_page:
                    # FIXME: How to properly do lazy loading in this case?
                    if self.PARENT_ID_COLUMN:
                        def get_results(parent):
                            operator = 'is' if parent is None else '='
                            if where_sql:
                                parent_where = '%s AND %s %s ?' % (
                                    where_sql, operator, self.PARENT_ID_COLUMN)
                            else:
                                parent_where = ' WHERE %s %s ? ' % (
                                    self.PARENT_ID_COLUMN, operator)
                            sql = 'SELECT %s FROM %s %s %s' % (
                                self.column_name_str, self.table,
                                parent_where, order_sql)

                            bindings_ = bindings + [parent]
                            logger.debug('SQL: %s, %s', sql, bindings_)
                            # FIXME: If would be better to do:
                            #     for row in cursor.execute(sql, bindings_):
                            #         yield row
                            # But for that we would need different cursors
                            cursor.execute(sql, bindings_)
                            return cursor.fetchall()

                        def build_tree(parent, parent_id):
                            for row in get_results(parent_id):
                                node = Node(data=row)
                                parent.append(node)
                                build_tree(node, row[self._id_column_idx])

                        build_tree(self.rows, None)
                    else:
                        sql = 'SELECT %s FROM %s %s %s LIMIT %d OFFSET %d' % (
                            self.column_name_str, self.table, where_sql,
                            order_sql, self.MAX_RECS, offset)
                        logger.debug('SQL: %s, %s', sql, bindings)
                        for row in cursor.execute(sql, bindings):
                            self.rows.append(Node(data=row))

                if first_access:
                    # set the total record count the only the first time the
                    # record set is requested
                    sql = 'SELECT COUNT(*) FROM %s %s' % (
                        self.table, where_sql)
                    cursor.execute(sql, bindings)
                    self.total_recs = int(cursor.fetchone()[0])

    def update(self, params, ids=None):
        """Update the recordset with a SQL ``UPDATE`` statement.

        Typically used to update the ``__selected`` column indicating
        selected records.

        If `ids` is None, will update the entire table.

        :param dict params: keys corresponding to DB columns + values to update
        :param list ids: database primary keys to use for updating
        """
        with closing(sqlite3.connect(self.db_file)) as conn:
            with closing(conn.cursor()) as cursor:
                update_sql_list = []
                for key, value in params.iteritems():
                    if isinstance(value, bool):
                        value = int(value)
                    elif isinstance(value, basestring):
                        value = "'%s'" % value
                    update_sql_list.append('%s=%s' % (key, value))
                update_sql_str = ', '.join(update_sql_list)
                if ids is not None:
                    for id_ in ids:
                        sql = 'UPDATE %s SET %s WHERE %s = ?' % (
                            self.update_table, update_sql_str, self.ID_COLUMN)
                        cursor.execute(sql, (str(id_),))
                else:
                    sql = 'UPDATE %s SET %s' % (
                        self.update_table, update_sql_str)
                    cursor.execute(sql)
                conn.commit()

    def get_all_record_ids(self, params=None):
        """Get all the record primary keys for given params.

        :param dict params: params from which to construct SQL ``WHERE`` clause
        :return: primary key ids
        :rtype: list
        """
        bindings = []
        where_sql = ''
        # construct WHERE clause
        if params is not None:
            if 'where' in params:
                where_sql, bindings = self._get_where_clause(
                    self.table, params['where'])
        sql = 'SELECT %s FROM %s %s' % (self.ID_COLUMN, self.table, where_sql)
        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.create_function('rank', 1, rank)
            # TODO: ^^ create this function only if search term in params
            with closing(conn.cursor()) as cursor:
                self._ensure_temp_view(cursor)
                cursor.execute(sql, bindings)
                results = [row[0] for row in cursor.fetchall()]
        return results

    def get_single_record(self, record_id, table=None):
        """Get single record from database for display in preview pane.

        :param int record_id: required record number to be retrieved
        :param str table: optional string table name to retrieve from if not
            class default table
        :return: row of data
        :rtype: tuple
        """
        if table is None:
            table = self.table
        sql_statement = 'SELECT * FROM %s WHERE %s = ?' % (
            table, self.ID_COLUMN
        )
        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.row_factory = sqlite3.Row  # Access columns by name
            with closing(conn.cursor()) as cursor:
                self._ensure_temp_view(cursor)
                cursor.execute(sql_statement, (str(record_id),))
                data = cursor.fetchone()
            # TODO log error if more than one
        return data

    def get_selected_columns(self):
        """Get selected columns info from DB.

        :returns: list of column names
        :rtype: list or None
        """
        result = self.select(
            self.db_file,
            '_selected_columns',
            None,
            {'tablename': {'param': self.table, 'operator': '='}}
        )
        if not result:
            return None

        return result[0][1].split(',')
        # ^^ 2nd column of returned row; first column is table name

    def update_selected_columns(self, columns):
        """Update the ``_selected_columns`` table.

        Updates the table in the DB that stores info about which columns have
        been selected.  This is used to exclude unwanted columns from a report.

        :param list columns: list of column names to display
        """
        with closing(sqlite3.connect(self.db_file)) as conn:
            with closing(conn.cursor()) as cursor:
                create_sql = (
                    'CREATE TABLE IF NOT EXISTS _selected_columns '
                    '(tablename TEXT, columns TEXT)'
                )
                cursor.execute(create_sql)
                if not columns:
                    update_sql = (
                        'DELETE FROM _selected_columns WHERE tablename=?'
                    )
                    params = (self.table,)
                else:
                    select_sql = (
                        'SELECT * FROM _selected_columns WHERE tablename=?'
                    )
                    cursor.execute(select_sql, (self.table,))
                    row = cursor.fetchone()
                    if not row:
                        update_sql = (
                            'INSERT INTO _selected_columns '
                            '(tablename, columns) VALUES (?, ?)'
                        )
                        params = (self.table, ','.join(columns))
                    else:
                        update_sql = (
                            'UPDATE _selected_columns '
                            'SET columns=? WHERE tablename=?'
                        )
                        params = (','.join(columns), self.table)
                cursor.execute(update_sql, params)
                conn.commit()

    @classmethod
    def select(cls, db_file, table, columns=None, where=None):
        """Select records from given db and table given columns and criteria.

        :param str db_file: path to SQLite database file
        :param str table: name of table in SQLite db
        :param list columns: list of columns to SELECT from
        :param dict where: dict of parameters to build ``WHERE`` clause
        """
        # TODO: make this an instance method to avoid having to pass db_file?
        where_sql = ''
        where_params = []
        if columns:
            columns = ', '.join(columns)
        else:
            columns = '*'
        if where is not None:
            where_sql, where_params = \
                cls._get_where_clause(table, where)
        sql = 'SELECT %s FROM %s %s' % (columns, table, where_sql)
        logger.debug(sql)
        with closing(sqlite3.connect(db_file)) as conn:
            conn.row_factory = sqlite3.Row  # Access columns by name
            with closing(conn.cursor()) as cursor:
                try:
                    cursor.execute(sql, where_params)
                except sqlite3.OperationalError as err:
                    logger.warn(str(err))
                    data = []
                else:
                    data = cursor.fetchall()
        return data

    @classmethod
    def _get_where_clause(cls, table, where_params):
        """Construct a SQL ``WHERE`` clause.

        A typical ``where_params`` dict might look like this::

            {'search': {'operator': '=', 'param': 'Google'}}

        .. NOTE:: ``search`` is a special key used for full-text searches

        :param dict where_params: parameters to build ``WHERE`` clause
        :return: SQL ``WHERE`` clause, and parameters to use in clause
        :rtype: tuple
        """
        sql_clauses = []
        params = []
        for key, value in where_params.iteritems():
            dic = value
            if key == 'search':
                # full-text search
                # TODO: make this generic, not specific to vE implementation
                if dic['param']:
                    sql = '(%s IN (%s)' % (
                        cls.ID_COLUMN,
                        'SELECT %(id)s FROM '
                        '(SELECT rank(matchinfo(%(table)s)) AS r, %(id)s'
                        ' FROM  %(table)s WHERE %(table)s MATCH ?)'
                        ' WHERE r > 0 ORDER BY r DESC)' % {
                            "id": cls.ID_COLUMN,
                            "table": table + '_search'
                        }
                    )
                    sql_clauses.append(sql)
                    params.append(dic['param'])
            elif dic['operator'] == 'range':
                sql = '(%(col)s >= ? AND %(col)s <= ?)' % {'col': key}
                sql_clauses.append(sql)
                params.append(dic['param'][0])
                params.append(dic['param'][1])
            else:
                sql = '(%s %s ?)' % (key, dic['operator'])
                sql_clauses.append(sql)
                params.append(dic['param'])

        if not sql_clauses:
            return ('', [])

        if len(sql_clauses) > 1:
            sql = 'WHERE %s' % (' AND '.join(sql_clauses))
        else:
            sql = 'WHERE %s' % sql_clauses[0]
        return (sql, params)

    def _ensure_temp_view(self, cursor):
        """If a custom query is defined, temporary view using that query
        is used in place of a table name.
        This makes sure that temporary view exists if required.

        :param cursor: Cursor for the session where the view might be needed.
        """
        if self.query:
            # create a temporary view for collecting column info
            cursor.execute('CREATE TEMP VIEW IF NOT EXISTS %s AS %s' % (
                self.table, self.query
            ))

    def get_columns(self):
        """Return a list of column information dicts.

        Queries either the database ``PRAGMA`` for column information or
        uses the config information passed into the constructor.

        Column dict example::

            {
                'transform': None,
                'type': str,
                'name': 'title',
                'display': 'Title'
            }

        :return: a list of column information dicts
        :rtype: list
        """
        cols = []
        with closing(sqlite3.connect(self.db_file)) as conn:
            with closing(conn.cursor()) as cursor:
                self._ensure_temp_view(cursor)
                table_info_query = 'PRAGMA table_info(%s)' % self.table
                cursor.execute(table_info_query)
                rows = cursor.fetchall()
                has_selected = False
                counter = 0
                for i, row in enumerate(rows):
                    col_defined = False
                    col_name = row[1]
                    if self.config is not None:
                        if col_name not in [self.ID_COLUMN, '__selected']:
                            display_name, (data_type, transform) = \
                                self.config[counter]
                            col_defined = True
                            counter += 1
                    if not col_defined:
                        display_name = row[1]
                        data_type = self.SQLITE_PY_TYPES.get(row[2].upper(), str)
                        transform = None  # TODO: eg. buffer
                    col_dict = {
                        'name': col_name,
                        'display': display_name,
                        'type': data_type,
                        'transform': transform
                    }

                    if col_name == self.ID_COLUMN:
                        self._id_column_idx = i
                    if col_name == self.PARENT_ID_COLUMN:
                        self._parent_column_idx = i

                    if row[1] == '__selected':
                        col_dict['transform'] = 'boolean'
                        cols.insert(0, col_dict)
                        has_selected = True
                    else:
                        cols.append(col_dict)
                if self._ensure_selected_column and not has_selected:
                    alter_sql = 'ALTER TABLE %s ADD __selected INTEGER' % (
                        self.update_table)
                    cursor.execute(alter_sql)
                    conn.commit()
                    col_dict = {
                        'name': '__selected',
                        'display': '__selected',
                        'type': int,
                        'transform': 'boolean'
                    }
                    cols.insert(0, col_dict)
                    has_selected = True

                # If __selected column is present, it was inserted on position
                # 0, so we need to increase the id/parent columns by 1
                if has_selected and self._id_column_idx is not None:
                    self._id_column_idx += 1
                if has_selected and self._parent_column_idx is not None:
                    self._parent_column_idx += 1

        return cols


def rank(matchinfo):
    """Rank full-text search results.

    :param matchinfo: defined as returning 32-bit unsigned integers in
      machine byte order (http://www.sqlite.org/fts3.html#matchinfo)
      and struct defaults to machine byte order.
    """
    matchinfo = struct.unpack('I' * (len(matchinfo) / 4), matchinfo)
    iterator = iter(matchinfo[2:])
    return sum(x[0] for x in zip(iterator, iterator, iterator) if x[1])


class Database(object):

    """Generic database object.

    This class is subclassed to provide additional functionality specific to
    artifacts and/or documents.

    :param db_filename: Path to the sqlite database file
    :type db_filename: str

    """

    def __init__(self, db_filename):
        """Connect to database and create session object."""
        self.db_filename = db_filename
        self.engine = create_engine(
            'sqlite:///{}'.format(db_filename),
            connect_args={'check_same_thread': False},
        )
        self.connection = None
        self.metadata = MetaData(bind=self.engine)

    def connect(self):
        """Create connection."""
        logger.debug('Connecting to SQLite database: %s', self.db_filename)
        self.connection = self.engine.connect()

    def disconnect(self):
        """Close connection."""
        assert not self.connection.closed
        logger.debug(
            'Disconnecting from SQLite database: %s', self.db_filename)
        self.connection.close()

    def __enter__(self):
        """Connect on entering context."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Disconnect on exiting context."""
        self.disconnect()

    def __getitem__(self, table_name):
        """Get table object in database.

        :param table_name: Name of the table
        :type table_name: str
        :return: Table object that can be used in queries
        :rtype: sqlalchemy.schema.Table

        """
        table = self.metadata.tables.get(table_name)
        if table is None:
            table = Table(table_name, self.metadata, autoload=True)
        return table

    def run_quick_check(self):
        """Check database integrity.

        Some files, especially those files created after carving, might not
        contain completely valid data.

        """
        try:
            result = self.connection.execute('PRAGMA quick_check;')
        except DatabaseError:
            return False

        passed = result.fetchone()[0] == 'ok'
        if not passed:
            logger.warning('Integrity check failure: %s', self.db_filename)
        return passed

    def reflect(self):
        """Get table metadata through reflection.

        sqlalchemy already provides a reflect method, but it will stop at the
        first failure, while this method will try to get as much as possible.

        """
        inspector = inspect(self.engine)
        for table_name in inspector.get_table_names():
            columns = []
            for column_data in inspector.get_columns(table_name):
                # Rename 'type' to 'type_' to create column object
                column_type = column_data.pop('type', None)
                column_data['type_'] = column_type
                columns.append(Column(**column_data))
            Table(table_name, self.metadata, *columns)
