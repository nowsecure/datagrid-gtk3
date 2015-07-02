"""Data transformation utilities test cases."""

import unittest

from datagrid_gtk3.utils.transformations import degree_decimal_str_transform


class DegreeDecimalStrTransformTest(unittest.TestCase):

    """Degree decimal string transformation test case."""

    def test_no_basestring(self):
        """AssertionError raised when no basestring value is passed."""
        self.assertRaises(AssertionError, degree_decimal_str_transform, 0)
        self.assertRaises(AssertionError, degree_decimal_str_transform, 1.23)
        self.assertRaises(AssertionError, degree_decimal_str_transform, True)

    def test_no_digit(self):
        """AssertionError raised when other characters than digits."""
        self.assertRaises(AssertionError, degree_decimal_str_transform, '.')
        self.assertRaises(AssertionError, degree_decimal_str_transform, '+')
        self.assertRaises(AssertionError, degree_decimal_str_transform, '-')

    def test_length(self):
        """AssertionError when more characters than expected passed."""
        self.assertRaises(
            AssertionError, degree_decimal_str_transform, '123456789')

    def test_point_insertion(self):
        """Decimal point is inserted in the expected location."""
        self.assertEqual(
            degree_decimal_str_transform('12345678'),
            '12.345678',
        )
        self.assertEqual(
            degree_decimal_str_transform('1234567'),
            '1.234567',
        )
        self.assertEqual(
            degree_decimal_str_transform('123456'),
            '0.123456',
        )
        self.assertEqual(
            degree_decimal_str_transform('12345'),
            '0.012345',
        )
