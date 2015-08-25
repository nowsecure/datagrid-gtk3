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


def replace_non_printable(string_):
    """Replace non-printable characters on the string with a replacement.

    Use the unicode replacement character (U+FFFD), instead of the
    non-printable ones.

    :param string_: The string to replace the characters from
    :type string_: str
    :rtype: str
    """
    return ''.join(c if is_printable(c) else u"\uFFFD" for c in string_)
