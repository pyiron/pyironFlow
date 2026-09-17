import typing
import unittest

import flowrep as fr

from pyironflow import entry


class TestEntryKind(unittest.TestCase):
    def test_kinds(self):
        cases = [
            (bool, entry.EntryKind.CHECKBOX),
            (typing.Literal["a", "b"], entry.EntryKind.DROPDOWN),
            (typing.Literal["a"] | typing.Literal[1], entry.EntryKind.DROPDOWN),
            (str, entry.EntryKind.TEXT),
            (int, entry.EntryKind.TEXT),
            (float, entry.EntryKind.TEXT),
            (int | str, entry.EntryKind.TEXT),
            (bool | int, entry.EntryKind.TEXT),
            (bool | None, entry.EntryKind.TEXT),
            (list[list[int]], entry.EntryKind.TEXT),
            (dict[str, float], entry.EntryKind.TEXT),
            (list, entry.EntryKind.TEXT),
            (dict, entry.EntryKind.TEXT),
            (fr.schemas.JSONABLE, entry.EntryKind.TEXT),
            (typing.Annotated[int, "units"], entry.EntryKind.TEXT),
            (typing.Literal["a"] | None, entry.EntryKind.TEXT),
            (None, entry.EntryKind.NONE),
            (typing.Any, entry.EntryKind.NONE),
            (tuple[int, int], entry.EntryKind.NONE),
            (set[str], entry.EntryKind.NONE),
            (dict[int, str], entry.EntryKind.NONE),
            (unittest.TestCase, entry.EntryKind.NONE),
        ]
        for hint, expected in cases:
            with self.subTest(hint=hint):
                self.assertEqual(expected, entry.entry_kind(hint))

    def test_options_are_rendered_members(self):
        self.assertEqual(["'a'", "1"], entry.options(typing.Literal["a", 1]))

    def test_options_of_a_non_literal_are_none(self):
        self.assertIsNone(entry.options(int))


class TestParse(unittest.TestCase):
    def test_accepted(self):
        cases = [
            ("42", int | str, 42),
            ("'42'", int | str, "42"),
            ("hello", int | str, "hello"),
            ("hello", str, "hello"),
            ("'42'", str, "'42'"),
            ("None", int | None, None),
            ("True", bool, True),
            ("True", bool | int, True),
            ("1", bool | int, 1),
            ("2", float, 2.0),
            ("[[1, 2], [3, 4, 5]]", list[list[int]], [[1, 2], [3, 4, 5]]),
            ("[1, 2,]", list[int], [1, 2]),
            ("{'a': 1}", dict[str, float], {"a": 1.0}),
            ("[1, 'a', None]", list, [1, "a", None]),
            ("'a'", typing.Literal["a", 1], "a"),
            ("3", typing.Annotated[int, "units"], 3),
            ("[1, 2", int | str, "[1, 2"),
            ("hello world", int | str, "hello world"),
        ]
        for text, hint, expected in cases:
            with self.subTest(text=text, hint=hint):
                parsed = entry.parse(text, hint)
                self.assertEqual(expected, parsed)
                self.assertIs(type(expected), type(parsed))

    def test_rejected(self):
        cases = [
            ("2.0", int | str),  # a valid literal that does not fit
            ("hello", int),  # unparseable and str is not admitted
            ("[1, 2", list[int]),  # unparseable and str is not admitted
            ("[[True]]", list[list[int]]),
            ("True", int),
            ("2.0", int),
            ("{1: 2}", dict[str, int]),
            ("[1, (2,)]", list),  # a tuple is not JSONABLE
            ("True", typing.Literal["a", 1]),  # strict pydantic would give 1
            ("1e400", float),  # inf cannot survive the JSON trip
        ]
        for text, hint in cases:
            with (
                self.subTest(text=text, hint=hint),
                self.assertRaises(entry.EntryError),
            ):
                entry.parse(text, hint)

    def test_the_error_message_suggests_quoting_when_str_is_admitted(self):
        with self.assertRaises(entry.EntryError) as caught:
            entry.parse("2.0", int | str)
        self.assertIn("Quote it", str(caught.exception))


class TestCoerce(unittest.TestCase):
    def test_promotes_an_int_to_a_float(self):
        self.assertEqual(2.0, entry.coerce(2, float))

    def test_rejects_a_value_that_no_longer_fits(self):
        with self.assertRaises(entry.EntryError):
            entry.coerce("42", int)

    def test_rejects_a_bool_for_an_int(self):
        with self.assertRaises(entry.EntryError):
            entry.coerce(True, int)


class TestRender(unittest.TestCase):
    def test_a_str_hint_renders_verbatim(self):
        self.assertEqual("[not a list]", entry.render("[not a list]", str))

    def test_other_hints_render_as_python_literals(self):
        self.assertEqual("'42'", entry.render("42", int | str))
        self.assertEqual("2.0", entry.render(2.0, float))
        self.assertEqual("None", entry.render(None, int | None))

    def test_round_trip(self):
        cases = [
            ([[1, 2], [3]], list[list[int]]),
            ({"a": [1.5, None]}, dict[str, fr.schemas.JSONABLE]),
            (0.1 + 0.2, float),
            (1e-20, float),
            ('she said "hi"\n', str),
            ("it's", int | str),
            (True, bool),
            (None, int | None),
            (42, int | str),
            ("42", int | str),
        ]
        for value, hint in cases:
            with self.subTest(value=value, hint=hint):
                parsed = entry.parse(entry.render(value, hint), hint)
                self.assertEqual(value, parsed)
                self.assertIs(type(value), type(parsed))
