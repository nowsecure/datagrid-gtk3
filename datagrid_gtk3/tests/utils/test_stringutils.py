# -*- coding: utf-8 -*-

"""String utilities test cases."""

import string
import unittest

from datagrid_gtk3.utils.stringutils import (
    is_printable,
    replace_non_printable,
)


class StringUtilsTest(unittest.TestCase):

    """Tests for :mod:`datagrid.utils.stringutils`."""

    def test_printable(self):
        """Tests for :func:`datagrid.utils.stringutils.is_printable`."""
        for char in ['a', 'Z', '?', '\n']:
            self.assertTrue(is_printable(char))

        for char in string.whitespace:
            self.assertTrue(is_printable(char))

        # UTF-8 encoded non-ascii characters should be considered printable
        for char in u'žćčđš'.encode('utf-8'):
            self.assertTrue(is_printable(char))

        for char in [chr(0), chr(20), chr(30)]:
            self.assertFalse(is_printable(char))

    def test_replace_non_printable(self):
        """Test :func:`datagrid.utils.stringutils.replace_non_printable`."""
        self.assertEqual(
            replace_non_printable(
                "Some string\nWith\tsome %s non-printable, %s chars" % (
                    chr(20), chr(30))),
            u"Some string\nWith\tsome � non-printable, � chars")

        self.assertEqual(
            replace_non_printable(
                u"Ração %s para %s búfalos" % (chr(20), chr(30))),
            u"Ração � para � búfalos")
