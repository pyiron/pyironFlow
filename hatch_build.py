"""
Hatch build hook: build the JS bundle exactly as locked in package-lock.json.

We home-brew a build function to avoid the `npm install` in hatch-jupyter-builder's
`npm_builder`; we want `npm ci` to ensure that the build artefact stays consistent
with our tracked `package-lock.json`. In this way, the built artefact distributed on
the release CI is the same one tested against in the test CI.
"""

import pathlib
import shutil
import subprocess

from hatchling.builders.hooks.plugin import interface

BUNDLE = pathlib.Path("pyironflow", "static", "widget.js")


class NpmCiBuildHook(interface.BuildHookInterface):
    """Run `npm ci && npm run build` unless the bundle already exists."""

    def initialize(self, version, build_data):
        root = pathlib.Path(self.root)
        bundle = root / BUNDLE
        if bundle.exists():
            self.app.display_info(f"Found {BUNDLE}; skipping JS build")
            return

        npm = shutil.which("npm")  # resolves npm.cmd on Windows
        if npm is None:
            raise RuntimeError(
                "npm not found; install nodejs (see .ci_support/environment.yml)"
            )

        for args in (["ci"], ["run", "build"]):
            subprocess.run([npm, *args], cwd=root, check=True)

        if not bundle.exists():
            raise RuntimeError(f"JS build did not produce {BUNDLE}")
