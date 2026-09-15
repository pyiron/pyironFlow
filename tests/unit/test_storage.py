import contextlib
import os
import pathlib
import pickle
import shutil
import tempfile
import threading
import unittest

import bagofholding as boh
import flowrep as fr
import pyiron_workflow as pwf
from pyiron_workflow import execution

from pyironflow import storage


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("out")
def boom(x: float) -> float:
    raise RuntimeError("boom")


def _finished_run():
    wf = pwf.Workflow("saved")
    wf.n1 = pwf.node(relu)
    wf.set_inputs_to_unconnected_child_input()
    wf.set_outputs_to_unconnected_child_output()
    return wf.run(n1__x=1.0)


def _failed_run():
    wf = pwf.Workflow("failed")
    wf.n1 = pwf.node(boom)
    wf.set_inputs_to_unconnected_child_input()
    wf.set_outputs_to_unconnected_child_output()
    caught = []
    config = execution.RunConfig(
        exception_hooks=[lambda _dir, run, _err: caught.append(run)]
    )
    with contextlib.suppress(RuntimeError):
        wf.run(config, n1__x=1.0)
    return caught[0]


def _load(path, fmt):
    if fmt is storage.RunFormat.PICKLE:
        with path.open("rb") as f:
            return pickle.load(f)
    return boh.H5Bag(str(path)).load()


class _TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class TestResolvePath(_TempDirCase):
    def setUp(self):
        super().setUp()
        previous = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, previous)

    def test_a_relative_path_resolves_against_the_cwd(self):
        self.assertEqual(
            self.tmp / "a" / "b.json", storage.resolve_path("a/b", ".json")
        )

    def test_parent_references_are_resolved(self):
        self.assertEqual(
            self.tmp.parent / "up.json", storage.resolve_path("../up", ".json")
        )

    def test_an_existing_matching_extension_is_kept(self):
        self.assertEqual(self.tmp / "b.json", storage.resolve_path("b.json", ".json"))

    def test_another_suffix_still_gets_the_extension(self):
        self.assertEqual(self.tmp / "run.v2.h5", storage.resolve_path("run.v2", ".h5"))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(self.tmp / "b.json", storage.resolve_path("  b  ", ".json"))

    def test_home_is_expanded(self):
        self.assertEqual(
            pathlib.Path("~/x.json").expanduser().resolve(),
            storage.resolve_path("~/x", ".json"),
        )

    def test_an_absolute_path_is_kept(self):
        target = self.tmp / "abs" / "c.pckl"
        self.assertEqual(target, storage.resolve_path(str(target), ".pckl"))

    def test_a_blank_path_is_refused(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.resolve_path("   ", ".json")
        self.assertIn("Enter a file path", str(caught.exception))


class TestCheckWritable(_TempDirCase):
    def test_a_new_file_in_an_existing_directory_is_fine(self):
        storage.check_writable(self.tmp / "new.json", False, False)

    def test_an_existing_file_is_refused_without_overwrite(self):
        target = self.tmp / "there.json"
        target.write_text("{}")
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(target, False, False)
        self.assertIn("Overwrite existing", str(caught.exception))

    def test_an_existing_file_is_fine_with_overwrite(self):
        target = self.tmp / "there.json"
        target.write_text("{}")
        storage.check_writable(target, False, True)

    def test_a_directory_is_refused(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(self.tmp, True, True)
        self.assertIn("is a directory", str(caught.exception))

    def test_a_missing_directory_is_refused_without_create_dirs(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(self.tmp / "no" / "x.json", False, False)
        self.assertIn("Create missing directories", str(caught.exception))

    def test_a_missing_directory_is_fine_with_create_dirs_and_nothing_is_made(self):
        storage.check_writable(self.tmp / "no" / "x.json", True, False)
        self.assertFalse((self.tmp / "no").exists())

    def test_a_file_in_the_way_of_the_directories_is_refused(self):
        (self.tmp / "blocker").write_text("")
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(self.tmp / "blocker" / "x.json", True, True)
        self.assertIn("is a file", str(caught.exception))


class TestRunFormat(unittest.TestCase):
    def test_extensions(self):
        self.assertEqual(".pckl", storage.RunFormat.PICKLE.extension)
        self.assertEqual(".h5", storage.RunFormat.H5.extension)


class TestSaveRun(_TempDirCase):
    def test_a_finished_run_round_trips(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"finished{fmt.extension}"
                storage.save_run(_finished_run(), path, fmt, False, False)
                self.assertEqual({"n1__signal": 1.0}, dict(_load(path, fmt).outputs))

    def test_a_failed_run_round_trips(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"failed{fmt.extension}"
                storage.save_run(_failed_run(), path, fmt, False, False)
                self.assertEqual(execution.RunStatus.FAILED, _load(path, fmt).status)

    def test_missing_directories_are_created_on_request(self):
        path = self.tmp / "deep" / "er" / "run.pckl"
        storage.save_run(_finished_run(), path, storage.RunFormat.PICKLE, True, False)
        self.assertTrue(path.is_file())

    def test_an_existing_file_is_kept_without_overwrite(self):
        path = self.tmp / "run.pckl"
        path.write_bytes(b"keep")
        with self.assertRaises(storage.StorageError):
            storage.save_run(
                _finished_run(), path, storage.RunFormat.PICKLE, False, False
            )
        self.assertEqual(b"keep", path.read_bytes())

    def test_overwrite_replaces_the_file(self):
        path = self.tmp / "run.pckl"
        storage.save_run(_finished_run(), path, storage.RunFormat.PICKLE, False, False)
        storage.save_run(_failed_run(), path, storage.RunFormat.PICKLE, False, True)
        self.assertEqual(
            execution.RunStatus.FAILED, _load(path, storage.RunFormat.PICKLE).status
        )

    def test_a_failed_serialization_leaves_no_file(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                run = _finished_run()
                run.run_dir = threading.Lock()  # cannot be pickled or bagged
                with self.assertRaises(storage.StorageError) as caught:
                    storage.save_run(
                        run, self.tmp / f"bad{fmt.extension}", fmt, False, False
                    )
                self.assertIsInstance(caught.exception.__cause__, TypeError)
                self.assertEqual([], list(self.tmp.iterdir()))


if __name__ == "__main__":
    unittest.main()
