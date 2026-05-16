def concatenate_strings(
    str1: str,
    str2: str,
    separator: str = ""
) -> str:
    """
    Concatenate two strings with an optional separator.

    Concatenates the provided strings and inserts the separator between them.
    If no separator is provided, the strings are joined directly.

    Args:
        str1 (str): First input string.
        str2 (str): Second input string.
        separator (str, optional): String to insert between concatenated parts.
            Defaults to an empty string.

    Returns:
        str: The concatenated result with separator inserted.
    """
    return str1 + separator + str2