# -*- coding: utf-8 -*-

"""Filebrowser example definitions."""

import os

from sqlalchemy import (
    Column,
    INTEGER,
    TEXT,
    Table,
)

from datagrid_gtk3.db.sqlite import SQLiteDataSource, Database


class FileBrowserDB(Database):

    """Files database generation."""

    TABLENAME = 'files'
    COLUMNS = [
        ('__fullpath', TEXT),
        ('__parent', TEXT),
        ('basename', TEXT),
        ('flatname', TEXT),
        ('preview', TEXT),
        ('size', INTEGER)]

    def __init__(self, db_filepath):
        """Initialize FileBrowserDB object."""
        super(FileBrowserDB, self).__init__(db_filepath)

        self._table_def = Table(
            self.TABLENAME, self.metadata,
            *[Column(name, col) for name, col in self.COLUMNS])

    ###
    # Public
    ###

    def load_path(self, path):
        """Load path inside the database table.

        :param str path: the directory path to load
        """
        with self:
            if self._table_def.exists():
                self._table_def.drop()
            self._table_def.create()

            # Filenames with non-ascii character will be represented as
            # utf-8 encoded strings. We need to convert them to unicode.
            conv = lambda s: unicode(s, encoding='utf-8')
            rows = []
            for i, (root, dirs, files) in enumerate(os.walk(path)):
                root = root.rstrip(os.path.sep)

                if i == 0:
                    file_parent = None
                else:
                    file_parent = root
                    dir_parent = os.path.dirname(root)
                    if os.path.samefile(os.path.dirname(root), path):
                        dir_parent = None
                    rows.append({
                        '__fullpath': conv(root),
                        '__parent': dir_parent and conv(dir_parent),
                        'basename': conv(os.path.basename(root)),
                        'flatname': None,
                        'preview': None,
                        'size': None,
                    })
                for file_ in files:
                    file_path = os.path.join(root, file_)
                    rows.append({
                        '__fullpath': conv(file_path),
                        '__parent': file_parent and conv(file_parent),
                        'basename': conv(file_),
                        'flatname': conv(os.path.relpath(file_path, path)),
                        'preview': u'file://' + conv(file_path),
                        'size': int(os.path.getsize(file_path)),
                    })

            # If rows was empty, calling the above would make a tuple of null
            # values to be inserted. Probably a bug on sqlalchemy.
            if rows:
                insert_query = self._table_def.insert()
                self.connection.execute(insert_query, rows)


class FileBrowserDataSource(SQLiteDataSource):

    """SQLiteDataSource to use with filebrowser database."""

    ID_COLUMN = '__fullpath'
    PARENT_ID_COLUMN = '__parent'
    FLAT_COLUMN = 'flatname'
