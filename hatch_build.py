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

BUNDLES = tuple(
    pathlib.Path("pyironflow", "static", name) for name in ("widget.js", "splitter.js")
)


class NpmCiBuildHook(interface.BuildHookInterface):
    """Run `npm ci && npm run build` unless the bundles already exist."""

    def initialize(self, version, build_data):
        root = pathlib.Path(self.root)
        if all((root / bundle).exists() for bundle in BUNDLES):
            self.app.display_info(
                f"Found {', '.join(map(str, BUNDLES))}; skipping JS build"
            )
            return

        npm = shutil.which("npm")  # resolves npm.cmd on Windows
        if npm is None:
            raise RuntimeError(
                "npm not found; install nodejs (see .ci_support/environment.yml)"
            )

        for args in (["ci"], ["run", "build"]):
            subprocess.run([npm, *args], cwd=root, check=True)

        missing = [str(bundle) for bundle in BUNDLES if not (root / bundle).exists()]
        if missing:
            raise RuntimeError(f"JS build did not produce {', '.join(missing)}")
