# -*- coding: utf-8 -*-

"""Date utilities test cases."""

import datetime
import unittest

from datagrid_gtk3.utils.dateutils import (
    InvalidDateFormat,
    parse_string,
)


class DateUtilsTest(unittest.TestCase):

    """Tests for :mod:`datagrid.utils.dateutils`."""

    def test_parse_string_valid(self):
        """Parse string should generate datetime for valid inputs."""
        for date_str, date in [
                ('4/10/2015', datetime.datetime(2015, 4, 10)),
                ('4/10/2015 04:20', datetime.datetime(2015, 4, 10, 4, 20)),
                ('2-Jun-2013', datetime.datetime(2013, 6, 2)),
                ('2-Jun-2013 06:48:15',
                 datetime.datetime(2013, 6, 2, 6, 48, 15)),
                ('Tue, 10 Apr 2001 15:51:24',
                 datetime.datetime(2001, 4, 10, 15, 51, 24))]:
            self.assertEqual(parse_string(date_str), date)

    def test_parse_string_invalid(self):
        """InvalidDateFormat should be raised for invalid inputs."""
        for invalid_str in [
                'non-valid-string',
                '10/50/2010',
                '50/10/2015',
                '10/10/2010 25:10']:
            with self.assertRaises(InvalidDateFormat):
                parse_string(invalid_str)
