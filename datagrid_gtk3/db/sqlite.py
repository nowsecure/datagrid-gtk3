"""SQLite database backend."""

import logging
import operator
import sqlite3
import struct
import weakref
from contextlib import closing

from gi.repository import GObject
from sqlalchemy import (
    Column,
    INTEGER,
    MetaData,
    Table,
    create_engine,
    inspect,
)
from sqlalchemy.exc import DatabaseError
from sqlalchemy.sql import (
    cast,
    alias,
    and_,
    collate,
    column,
    desc,
    func,
    or_,
    select,
    table as table_,
)

from datagrid_gtk3.db import DataSource, Node

logger = logging.getLogger(__name__)
_compile = lambda q: q.compile(compile_kwargs={"literal_binds": True}).string

_OPERATOR_MAPPER = {
    'is': operator.eq,
    '=': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '<=': operator.le,
    '>': operator.gt,
    '>=': operator.ge,
}


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
    :param bool persist_columns_visibility: Weather we should persist
        the columns visibility in the database.
    """

    __gsignals__ = {
        'rows-changed': (GObject.SignalFlags.RUN_LAST, None, (object, object)),
    }

    _DBS = weakref.WeakSet()

    MAX_RECS = 100
    SQLITE_PY_TYPES = {
        'INT': long,
        'INTEGER': long,
        'LONG': long,
        'TEXT': str,
        'REAL': float,
        'BLOB': str
    }

    STRING_PY_TYPES = {  # NOTE: ideally could use eval, but unsafe
        'int': int,
        'long': long,
        'str': str,
        'float': float,
        'buffer': buffer
    }

    def __init__(self, db_file, table=None, update_table=None, config=None,
                 ensure_selected_column=True,
                 display_all=False, query=None,
                 persist_columns_visibility=True):
        """Process database column info."""
        super(SQLiteDataSource, self).__init__()

        assert table or query  # either table or query must be given
        self.db_file = db_file
        self.table = table_(table if table else "__CustomQueryTempView")
        self.query = query
        if query:
            logger.debug("Custom SQL: %s", query)
        self._persist_columns_visibility = persist_columns_visibility
        self._ensure_selected_column = ensure_selected_column
        self.display_all = display_all
        # FIXME: Use sqlalchemy for queries using update_table
        if update_table is not None:
            self.update_table = update_table
        else:
            self.update_table = table
        self.config = config
        self.columns = self.get_columns()
        self.columns_idx = {
            col['name']: i for i, col in enumerate(self.columns)}

        for col in self.columns:
            self.table.append_column(column(col['name']))

        self.visible_columns_table = table_('__visible_columns')
        for col in ['tablename', 'columns']:
            self.visible_columns_table.append_column(column(col))

        with closing(sqlite3.connect(self.db_file)) as conn:
            with closing(conn.cursor()) as cursor:
                # FIXME: Maybe we should use a parameter to generate
                # search_table if it doesn't exist?
                search_table = self.table.name + '_search'
                cursor.execute('PRAGMA table_info(%s)' % (search_table, ))
                if cursor.fetchone():
                    self.search_table = search_table
                else:
                    self.search_table = None

                # Migrate old `_selected_columns` to `__visible_columns`
                cursor.execute('PRAGMA table_info(_selected_columns)')
                columns = {column_info[1] for column_info in cursor.fetchall()}
                if columns == {u'columns', u'tablename'}:
                    # `_selected_columns` exists and has the appropriate schema
                    cursor.execute('ALTER TABLE _selected_columns '
                                   'RENAME TO __visible_columns')
                    conn.commit()

        self.__class__._DBS.add(self)

    ###
    # Public
    ###

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
        rows = Node()
        # FIXME: Maybe we should use kwargs instead of params?
        params = params or {}

        # WHERE
        where = params.get('where', None)
        if where is not None:
            where = self._get_where_clause(where)

        # ORDER BY
        order_by = params.get('order_by', None)
        # Do a numeric ordering first, as suggested here
        # (http://stackoverflow.com/a/4204641), and then a case-insensitive one
        order_by = (order_by and
                    [self.table.columns[order_by] + 0,
                     collate(self.table.columns[order_by], 'NOCASE')])
        if order_by is not None and params.get('desc', False):
            order_by = [desc(col) for col in order_by]

        # OFFSET
        page = params.get('page', 0)
        offset = page * self.MAX_RECS
        # A little optimization to avoid doing more queries when we
        # already loaded everything
        if page > 0 and offset >= self.total_recs:
            return rows

        # Flat
        flat = params.get('flat', False)
        if flat:
            flat_where = operator.ne(
                self.table.columns[self.FLAT_COLUMN], None)
            where = and_(where, flat_where) if where is not None else flat_where  # noqa

        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.row_factory = lambda cursor, row: list(row)
            # ^^ make result lists mutable so we can change values in
            # the GTK TreeModel that uses this datasource.
            conn.create_function('rank', 1, rank)
            # TODO: ^^ only if search term in params
            with closing(conn.cursor()) as cursor:
                self._ensure_temp_view(cursor)

            if page == 0:
                # set the total record count the only the first time the
                # record set is requested
                res = self.select(
                    conn, self.table, [func.count(1)], where=where)
                self.total_recs = int(list(res)[0][0])

            if self.PARENT_ID_COLUMN and not flat:
                rows.extend(
                    self._load_tree_rows(
                        conn, where, order_by, params.get('parent_id', None)))
            else:
                query = self.select(
                    conn, self.table, self.table.columns, where=where,
                    limit=self.MAX_RECS, offset=offset, order_by=order_by)
                for row in query:
                    rows.append(Node(data=row))

        rows.children_len = len(rows)
        return rows

    def update(self, params, ids=None):
        """Update the recordset with a SQL ``UPDATE`` statement.

        Typically used to update the ``__selected`` column indicating
        selected records.

        If `ids` is None, will update the entire table.

        :param dict params: keys corresponding to DB columns + values to update
        :param list ids: database primary keys to use for updating
        """
        # FIXME: Use sqlalchemy to construct the queries here
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

        # Emit rows-changed for any other databases connected to the same
        # database and table. This is to allow any view using them
        # to update themselves with the changes done here.
        # The current object will not emit the event as it is the one who
        # made the update and thus, is assumed to know about the changes
        for db in self.__class__._DBS:
            if db is self:
                continue
            if (db.db_file, db.table.name) != (self.db_file, self.table.name):
                continue

            db.emit('rows-changed', params, ids)

    def get_all_record_ids(self, params=None):
        """Get all the record primary keys for given params.

        :param dict params: params from which to construct SQL ``WHERE`` clause
        :return: primary key ids
        :rtype: list
        """
        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.create_function('rank', 1, rank)
            # TODO: ^^ create this function only if search term in params
            where = params and params.get('where', None)
            if where is not None:
                where = self._get_where_clause(where)
            res = self.select(
                conn, self.table,
                [self.table.columns[self.ID_COLUMN]], where=where)

            return [row[0] for row in res]

    def get_single_record(self, record_id):
        """Get single record from database for display in preview pane.

        :param int record_id: required record number to be retrieved
        :return: row of data
        :rtype: tuple
        """
        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.row_factory = sqlite3.Row  # Access columns by name
            res = list(self.select(
                conn, self.table, self.table.columns,
                where=self.table.columns[self.ID_COLUMN] == record_id))

            # TODO log error if more than one
            return res[0]

    def get_visible_columns(self):
        """Get visible columns info from DB.

        :returns: list of column names
        :rtype: list or None
        """
        if not self._persist_columns_visibility:
            return None

        where = (self.visible_columns_table.columns['tablename'] ==
                 self.table.name)
        columns = [self.visible_columns_table.columns['columns']]

        with closing(sqlite3.connect(self.db_file)) as conn:
            conn.row_factory = sqlite3.Row  # Access columns by name
            try:
                result = list(
                    self.select(conn, self.visible_columns_table,
                                columns, where=where))
            except sqlite3.OperationalError as err:
                # FIXME: When will this happen?
                logger.warn(str(err))
                return None

        if not result:
            return None

        return result[0][0].split(',')

    def set_visible_columns(self, columns):
        """Update the *__visible_columns* table.

        Updates the table in the DB that stores info about which columns have
        been selected.  This is used to exclude unwanted columns from a report.

        :param list columns: list of column names to display
        """
        if not self._persist_columns_visibility:
            return

        with closing(sqlite3.connect(self.db_file)) as conn:
            with closing(conn.cursor()) as cursor:
                table = self.visible_columns_table.name
                cursor.execute(
                    'CREATE TABLE IF NOT EXISTS %s '
                    '(tablename TEXT PRIMARY KEY, columns TEXT)' % (table, ))
                cursor.execute(
                    'INSERT OR REPLACE INTO %s (tablename, columns) '
                    'VALUES (?, ?)' % (table, ),
                    (self.table.name, ','.join(columns)))
                conn.commit()

    def select(self, conn, table, columns=None, where=None,
               order_by=None, limit=None, offset=None):
        """Select records from given db and table given columns and criteria.

        :param str db_file: path to SQLite database file
        :param str table: name of table in SQLite db
        :param list columns: list of columns to SELECT from
        :param dict where: dict of parameters to build ``WHERE`` clause
        """
        columns = columns or table.columns
        sql = select(
            columns=columns, whereclause=where,
            from_obj=[table], order_by=order_by)
        sql_str = _compile(sql)

        # XXX: How to make sqlalchemy use limit/offset right? It is not
        # replacing the values on _compile
        if limit is not None:
            sql_str += '\nLIMIT %s' % (limit, )
        if offset is not None:
            sql_str += '\nOFFSET %s' % (offset, )

        logger.debug('SQL:\n%s', sql_str)
        with closing(conn.cursor()) as cursor:
            for row in cursor.execute(sql_str):
                yield row

    ###
    # Private
    ###

    def _get_where_clause(self, where_params):
        """Construct a SQL ``WHERE`` clause.

        A typical ``where_params`` dict might look like this::

            {'search': {'operator': '=', 'param': 'Google'}}

        .. NOTE:: ``search`` is a special key used for full-text searches

        :param dict where_params: parameters to build ``WHERE`` clause
        :return: SQL ``WHERE`` clause, and parameters to use in clause
        :rtype: tuple
        """
        sql_clauses = []
        for key, value in where_params.iteritems():
            if key == 'search':
                # full-text search
                if value['param'] and self.search_table is not None:
                    # XXX: This is to make MATCH be compiled direct here.
                    # We should build this query using sqlalchemy instead
                    match = column(self.search_table).match(value['param'])

                    sql = '(%s IN (%s)' % (
                        self.ID_COLUMN,
                        'SELECT %(id)s FROM '
                        '(SELECT rank(matchinfo(%(table)s)) AS r, %(id)s'
                        ' FROM  %(table)s WHERE %(match)s)'
                        ' WHERE r > 0 ORDER BY r DESC)' % {
                            "id": self.ID_COLUMN,
                            "table": self.search_table,
                            "match": _compile(match),
                        }
                    )
                    sql_clauses.append(sql)
                elif value['param']:
                    clauses = [col.like('%{}%'.format(value['param']))
                               for col in self.table.columns]
                    sql_clauses.append(or_(*clauses))
            elif value['operator'] == 'range':
                sql_clauses.append(
                    self.table.columns[key].between(*value['param']))
            else:
                clause = _OPERATOR_MAPPER[value['operator']](
                    self.table.columns[key], value['param'])
                sql_clauses.append(clause)

        return and_(*sql_clauses)

    def _ensure_temp_view(self, cursor):
        """If a custom query is defined, temporary view using that query
        is used in place of a table name.
        This makes sure that temporary view exists if required.

        :param cursor: Cursor for the session where the view might be needed.
        """
        if self.query:
            # create a temporary view for collecting column info
            cursor.execute('CREATE TEMP VIEW IF NOT EXISTS %s AS %s' % (
                self.table.name, self.query
            ))

    def _ensure_primary_key_column(self, conn):
        """Ensure that we know what is the primary key.

        :param conn: an open connection to the database
        """
        # FIXME: What to do when using temporary views?
        if self.query:
            return True

        with closing(conn.cursor()) as cursor:
            cursor.execute('PRAGMA table_info(%s)' % (self.table.name, ))
            rows = cursor.fetchall()

        row_names = [row[1] for row in rows]

        # First check if there's any row that matches self.ID_COLUMN
        if self.ID_COLUMN in row_names:
            return True

        # Then try to find any row that has its primary key flag set to True
        for row in rows:
            if row[5]:  # primary key
                self.ID_COLUMN = row[1]
                return True

        self.ID_COLUMN = '_rowid_'
        return False

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
            has_primary_key = self._ensure_primary_key_column(conn)

            with closing(conn.cursor()) as cursor:
                self._ensure_temp_view(cursor)
                table_info_query = 'PRAGMA table_info(%s)' % self.table.name
                cursor.execute(table_info_query)
                rows = cursor.fetchall()
                # If the table doesn't have a real primary key,
                # we will use its rowid, but it is not present on table_info
                if not has_primary_key:
                    rows.append(
                        (len(rows), self.ID_COLUMN, 'INTEGER', 0, '', 1))

                skip_config = [self.ID_COLUMN, self.SELECTED_COLUMN]
                has_selected = False
                counter = 0
                for i, row in enumerate(rows):
                    col_name = row[1]
                    if self.config is not None and col_name not in skip_config:
                        display_name = self.config[counter].get(
                            'alias', self.config[counter]['column'])
                        data_type = self.STRING_PY_TYPES[
                            self.config[counter]['type']]
                        transform = self.config[counter].get('encoding', None)
                        options = self.config[counter].get('encoding_options', None)
                        expand = self.config[counter].get('expand', False)
                        visible = self.config[counter].get('visible', True)
                        counter += 1
                    else:
                        display_name = row[1]
                        data_type = self.SQLITE_PY_TYPES.get(
                            row[2].upper(), str)
                        transform = None  # TODO: eg. buffer
                        options = None
                        expand = False
                        visible = True

                    col_dict = {
                        'name': col_name,
                        'display': display_name,
                        'type': data_type,
                        'transform': transform,
                        'transform_options': options,
                        'expand': expand,
                        'visible': visible,
                        'from_config': self.config is not None,
                    }

                    if col_name == self.ID_COLUMN:
                        self.id_column_idx = i
                    if col_name == self.PARENT_ID_COLUMN:
                        self.parent_column_idx = i
                    if col_name == self.CHILDREN_LEN_COLUMN:
                        self.children_len_column_idx = i
                    if col_name == self.FLAT_COLUMN:
                        self.flat_column_idx = i
                    if col_name == self.SELECTED_COLUMN:
                        self.selected_column_idx = i
                        has_selected = True
                        col_dict['transform'] = 'boolean'

                    cols.append(col_dict)

                if self._ensure_selected_column and not has_selected:
                    alter_sql = 'ALTER TABLE %s ADD %s INTEGER' % (
                        self.update_table, self.SELECTED_COLUMN)
                    cursor.execute(alter_sql)
                    conn.commit()
                    col_dict = {
                        'name': self.SELECTED_COLUMN,
                        'display': self.SELECTED_COLUMN,
                        'type': int,
                        'transform': 'boolean',
                        'transform_options': 'boolean',
                        'expand': False,
                        'visible': True,
                        'from_config': False,
                    }
                    self.selected_column_idx = len(cols)
                    cols.append(col_dict)

        return cols

    def _load_tree_rows(self, conn, where, order_by, parent_id):
        """Load rows as a tree."""
        if where is not None:
            # FIXME: If we have a where clause, we cant load the results lazily
            # because, we don't know if a row's children/grandchildren/etc will
            # match.  If this optimization (loading the leafs and the necessary
            # parents until the root) good enough?
            children = {}
            node_mapper = {}

            def load_rows(where_):
                query = self.select(
                    conn, self.table, columns=self.table.columns,
                    where=where_, order_by=order_by)
                for row in query:
                    row_id = row[self.id_column_idx]
                    if row_id in node_mapper:
                        continue

                    c_list = children.setdefault(
                        row[self.parent_column_idx], [])
                    node = Node(data=row)
                    c_list.append(node)
                    node_mapper[row_id] = node

            load_rows(where)
            if not children:
                return

            # Load parents incrementally until we are left with the root
            while children.keys() != [None]:
                parents_to_load = []
                for parent, c_list in children.items():
                    if parent is None:
                        continue

                    node = node_mapper.get(parent, None)
                    if node is None:
                        parents_to_load.append(parent)
                        continue

                    node.extend(c_list)
                    node.children_len = len(node)
                    del children[parent]

                if parents_to_load:
                    where = self.table.columns[self.ID_COLUMN].in_(
                        parents_to_load)
                    load_rows(where)

            for node in children[None]:
                yield node
        else:
            # If there's no where clause, we can load the results lazily
            where = self.table.columns[self.PARENT_ID_COLUMN] == parent_id

            if self.CHILDREN_LEN_COLUMN is None:
                count_table = alias(self.table, '__count')
                # We could use the comparison between the columns, but that would
                # make sqlalchemy add self.table in the FROM clause, which
                # would produce wrong results.
                count_where = '%s.%s = %s.%s' % (
                    count_table.name, self.PARENT_ID_COLUMN,
                    self.table.name, self.ID_COLUMN)
                count_select = select(
                    [func.count(1)],
                    whereclause=count_where, from_obj=[count_table])

                columns = self.table.columns.values()
                # We have to compile this here or else sqlalchemy would put
                # this inside the FROM part.
                columns.append('(%s)' % (_compile(count_select), ))
                extra_count_col = True
            else:
                columns = self.table.columns
                extra_count_col = False

            query = self.select(
                conn, self.table, columns=columns,
                where=where, order_by=order_by)

            for row in query:
                if extra_count_col:
                    children_len = row.pop(-1)
                else:
                    children_len = row[self.children_len_column_idx]

                yield Node(data=row, children_len=children_len)


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

    def reflect(self, table_name):
        """Get table metadata through reflection.

        sqlalchemy already provides a reflect method, but it will stop at the
        first failure, while this method will try to get as much as possible.

        """
        inspector = inspect(self.engine)
        columns = []
        for column_data in inspector.get_columns(table_name):
            # Rename 'type' to 'type_' to create column object
            column_type = column_data.pop('type', None)
            column_data['type_'] = column_type
            columns.append(Column(**column_data))

        return Table(table_name, self.metadata, *columns)
