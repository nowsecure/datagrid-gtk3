"""String utilities."""


def is_printable(char):
    """Determines whether a character can be displayed directly.

    Used for testing if some content should be treated as text or binary.

    :param char: Character to be tested
    :type char: str
    :rtype: bool
    """
    char_code = ord(char)
    return (char_code >= 32) or (9 <= char_code <= 13)


def strip_non_printable(string_):
    """Remove non-printable characters from the string.

    :param string_: The string to remove the characters from
    :type string_: str
    :rtype: str
    """
    return ''.join(c for c in string_ if is_printable(c))
