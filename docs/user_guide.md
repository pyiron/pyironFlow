# pyironflow
The visual programming interface `pyironflow` is a gui skin based on [ReactFlow](https://reactflow.dev/) that works on top of [pyiron_workflow](https://github.com/pyiron/pyiron_workflow).

### Table of Contents <a name="toc"></a>
1. [Installing pyironflow](#installing_pyironflow)
2. [Launching pyironflow](#launching_pyironflow)
   1. [Node library](#node_library)
4. [Basic usage](#basic_usage)
   1. [Viewing](#viewing_usage)
   2. [Running](#running_usage)
   3. [Modifying](#modifying_usage)
   4. [Saving/Loading](#data_usage)
5. [Warnings](#warnings)
6. [For Developers](#node_developers)
   1. [Hints for GUI data input](#dev_hints)
   2. [Installation](#dev_install)
   3. [Developing the JS](#dev_js)

## Installing-pyironflow <a name="installing_pyironflow"></a>
A package of `pyironflow` is available on PyPI and [conda-forge](https://anaconda.org/conda-forge/pyironflow). This can be installed using:
```
conda install -c conda-forge pyironflow   # recommended
pip install pyironflow                    # also available from PyPI
```

The `pyironflow` gui is intended to be used inside a Jupyter notebook, was additionally recommend installing [jupyterlab](https://anaconda.org/conda-forge/jupyterlab):
```
conda install -c conda-forge jupyterlab
```

## Launching pyironflow <a name="launching_pyironflow"></a>
It is recommended to use `pyironflow` in a jupyterlab or notebook instance launched from a terminal. Launching them from code editors such Visual Studio Code and PyCharm may cause unexpected behavior and rendering errors. To launch `pyironflow`, the following code should be executed in jupyter:
```
from pyironflow.pyironflow import PyironFlow
pf = PyironFlow()
pf.gui
```

It can also be launched with one or more [`pyiron_workflow.Workflow`](https://github.com/pyiron/pyiron_workflow) instances:
```
pf = PyironFlow([wf])
```

The widget consists of a set of control and information panels on the left, and a set of workflow graph tabs on the right.
You can adjust the relative sizes of these portions by clicking and dragging the vertical bar dividing them.

### Setting the Node library <a name="node_library"></a>

The "Node Library" tab lets you add new nodes to your workflow.
It automatically scrapes python files and finds anything that is marked as a node (e.g. decorated by a `@flowrep.workflow` or `@flowrep.atomic` decorator), or that might possibly be interpreted as one (e.g., any standard python function definition).
By default, the GUI tries to import a module named `pyiron_nodes` and will use that, as a source for scraping, but otherwise will use the current working directory or any directory you specify with the `root_path` argument:
```
pf = PyironFlow([wf], root_path='../some_other_directory')
```

This path will be added to your python path for the lifetime of the GUI (if it isn't part of your `sys.path` already).

- Click on orange folder or green file icons to expand the folder/file
- `flowrep`-decorated atomic, dataclass, and workflow definitions are shown with red wireframe, green table, and blue process symbols, respectively
- `pyiron_workflow`-decorated function (aka atomic) and macro (aka workflow) definitions are similarly shown in red wireframe or blue process symbols
- All remaining class and function definitions are shown with a grey symbol -- these may or may not parse to nodes, but clicking on them will _attempt_ to make an atomic node out of the definition
  - This allows you to immediately leverage many python packages that know nothing about pyiron workflows!
- Click on any of these node items to add it to the workflow area

_Note_: The refresh button updates the nodes in the library reflecting any new nodes. However, nodes already in the workflow will not be automatically refreshed. 

## Basic usage <a name="basic_usage"></a>

### Viewing <a name="viewing_usage"></a>
- Use the mouse wheel to zoom in and out.
- Hold left-click in an empty area and move the mouse to pan.
- Left-click on a node, hold and move the mouse to move a node around.
- Click on "Reset Layout" in the bottom-right of the workflow viewport to automatically rearrange nodes.
- Click on a node and press "Info" to open the "Node Info" panel on that node: its most recent output and its source code. While "Node Info" is open, it follows whichever single node is selected.
- Hovering over the label of a node's port will display a tooltip with the data type of the port.

### Running <a name="running_usage"></a>

- Click on "Run" in the top of the workflow viewport to run all nodes in the workflow tab.
- Click on a node and press "Pull" to execute the node and all **upstream nodes** that connect to it. The output of the whole pulled subgraph is shown in "Global Output", and the "Node Info" panel opens on this node's own output.
- Fields marked with an asterisk (*) require an input from the user in the form of GUI data input or an incoming graph edge.
- The square box next to the name of the node indicates the execution status of the node once the execution has finished:
  - White is for nodes not yet executed
  - Green is for nodes that have been successfully executed and cache has been activated
  - Blue is for nodes that have been successfully executed and cache has not been activated, or has been manually reset with an active cache
  - Red is for failed nodes

### Modifying <a name="modifying_usage"></a>

- Open the "Node Library" and click on nodes to add them to the graph.
- Set input data by interacting with text-editable fields, check-boxes, and drop-down menus (available where the input port has a JSONable type hint).
  - The keyword "None" is reserved for the value `None` (python `NoneType`). Entering this in a text field will always be parsed as `None`.
- Control the flow of data by clicking and dragging from one node's output port to another node's input port to form a new data-flow edge.
- Delete existing nodes or edges by clicking on them to select them, and then pressing "backspace" on the keyboard to delete.

### Saving/Loading <a name="data_usage"></a>
- "Export" sends the active workflow's `flowrep` recipe to JSON.
- "Import" opens a new workflow in a new tab based on a `flowrep` recipe loaded from JSON.
- "Save" sends the last run `pyiron_workflow.schemas.Run` output to a file, either pickle bytes or a bagofholding hdf5 file
- A workflow in the gui can be exported out within your jupyter notebook scope using: `wf_gui = pf.get_workflow()`. This new object behaves like a conventional `pyiron_workflow` object.


## Warnings <a name="warnings"></a>

- Currently, if files in the node library are updated while the GUI is running, the kernel has to be restarted to use the new nodes listed when the "refresh" button is pressed
- The "Node Library" will scrape _all_ possible `def` and `class` declarations in order to let you scrape nodes from packages that know nothing about graph-based workflows, but these are not guaranteed to be parsable; un-parsable declarations will complain when you try to add them to the workflow.
- Triggering a run with "Run" or "Pull" will monopolize the python process, but not the GUI; e.g. if you start a "Run", then use the GUI to delete a node, first the run will complete, _then_ the deletion will be processed.

## For Developers <a name="node_developers"></a>

### Hints for GUI data input <a name="dev_hints"></a>

Nodes hinted as `flowrep.schemase.JSONABLE` types get exposed as user-typable input right in the GUI, where

```python
JSONABLE = typing.TypeAliasType(
    "JSONABLE",
    "dict[str, JSONABLE] | list[JSONABLE] | str | int | float | bool | None",
)
```

In addition to this, if you hint some `Literal[{something jsonable}] | Literal[{something else jsonable}] | ...`, you'll get a drop-down choice menu in the GUI.


### Installation <a name="dev_install"></a>

- Clone the repository to your file system
- Install dependencies into your environment, e.g. from `.ci_support/environment.yml`
  - This includes the JS toolchain: Node.js `>=24.21.0,<25` with npm 11. These ranges are declared in `package.json` under `engines`, and `.npmrc` sets `engine-strict=true`, so `npm` refuses to run with any other version
- Run `./.dev-build.sh --clean` to completely rebuild the JS bundle, reinstalling JS dependencies exactly as locked in `package-lock.json`
- Launch a jupyter notebook and make sure the clone of `pyironflow` is the one in your `sys.path`, and use `pyironflow` as usual
- For live JS development, run `./.dev-build.sh --watch` and start Jupyter with `ANYWIDGET_HMR=1` so rebuilt bundles hot-reload without a kernel restart. This requires `watchfiles` (included in the `dev` extra: `pip install -e ".[dev]"`)

### Developing the JS <a name="dev_js"></a>

#### How the JS bundle is built  <a name="dev_js_build"></a>

- `pyironflow/static/{{widget/splitter}.{js/css}}` are a build artefacts and are not tracked by git.
- The hatch build hook in `hatch_build.py` runs `npm ci && npm run build` whenever a Python build (`pip install .`, `pip install -e .`, `hatchling build`) finds no existing bundle. `npm ci` installs exactly what is in `package-lock.json` and fails if it disagrees with `package.json`.
- If a bundle already exists, the hook keeps it and does not rebuild. A local `pip install .` will therefore ship whatever is in `pyironflow/static/`, stale or not; run `./.dev-build.sh` (or `--clean`) first if you have changed JS sources or dependencies.
- CI and releases start from a clean checkout, so they always build from the lockfile. The sdist ships the built bundle, so downstream builds from the sdist (e.g. conda-forge) reuse it rather than rebuilding.

#### Updating JS dependencies  <a name="dev_js_udpate"></a>

- `./.dev-build.sh --update` upgrades packages within the ranges in `package.json` and rewrites `package-lock.json`.
- For major-version bumps, edit the ranges in `package.json` (or run `npx npm-check-updates -u`), then run `./.dev-build.sh`.
- The plain `./.dev-build.sh` uses `npm install`, which may also rewrite `package-lock.json` if `package.json` changed; `--clean` uses `npm ci` and never touches the lockfile.
- Test, then commit `package.json` and `package-lock.json` together. CI and releases install exactly what is in the lockfile, so never delete it to "get the latest"; use `--update` instead.
- To change the Node.js version, update `engines` in `package.json` and the `nodejs` pins in `.ci_support/*.yml` together; a mismatch fails every build.