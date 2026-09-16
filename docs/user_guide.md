# pyironflow
The visual programmming interface `pyironflow` is a gui skin based on [ReactFlow](https://reactflow.dev/) that works on top of [pyiron_workflow](https://github.com/pyiron/pyiron_workflow).

### Table of Contents
1. [Installing pyironflow](#installing_pyironflow)
2. [Launching pyironflow](#launching_pyironflow)
3. [Node library](#node_library)
4. [Basic usage](#basic_usage)
5. [Global features](#other_features)
6. [Node status](#node_status)
7. [Known bugs](#known_bugs)
8. [Type hints for node developers](#node_devel)
9. [Installation for module developers](#dev_install)

## Installing-pyironflow <a name="installing_pyironflow"></a>
A package of `pyironflow` is available in [conda-forge](https://anaconda.org/conda-forge/pyironflow). This can be installed using:
```
conda install -c conda-forge pyironflow
```

In addition, it is also recommened to install [jupyterlab](https://anaconda.org/conda-forge/jupyterlab):
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

It can also be launched with some preset workflows:
```
pf = PyironFlow([wf])
```
where `wf` is a worklfow initially created using [pyiron_workflow](https://github.com/pyiron/pyiron_workflow).

The widget automatically resizes to fit the screen. The ratio between the widths of the wokflow viewport and the accordion (with node library, output and log) can be changed using:
```
pf = PyironFlow([wf], flow_widget_ratio=0.75) # default flow_widget_ratio=0.85
```

If the nodes are in a folder named "pyiron_nodes" anywhere in the current folder or in a subfolder, they will be automatically listed in the nodes library.
A different path to the node library (e.g., `../some_other_directoy/pyiron_nodes/`) can be set, when instantiating the GUI: 

```
pf = PyironFlow([wf], root_path='../some_other_directory')
```

This path will be added to your python path for the lifetime of the GUI (if it isn't part of your `sys.path` already).

## Node library <a name="node_library"></a>

The node library path is scraped for python files, and the node library is populated using class and function definitions found therein.

- Click on orange folder or green file icons to expand the folder/file
- `flowrep`-decorated atomic, dataclass, and workflow definitions are shown with red wireframe, green table, and blue process symbols, respectively
- `pyiron_workflow`-decorated function (aka atomic) and macro (aka workflow) definitions are similarly shown in red wireframe or blue process symbols
- All remaining class and function definitions are shown with a grey symbol -- these may or may not parse to nodes, but clicking on them will _attempt_ to make an atomic node out of the definition
  - This allows you to immediately leverage many python packages that know nothing about pyiron workflows!
- Click on any of these node items to add it to the workflow area


- The refresh button updates the nodes in the library reflecting any new nodes. However, nodes already in the workflow will not be automatically refreshed. 

## Basic usage <a name="basic_usage"></a>
- Use the mouse wheel to zoom in and out.
- Hold left-click in an empty area and move the mouse to pan.
- Left-click on a node, hold and move the mouse to move a node around.

- Click on a node and press "Pull" to execute the node and all **upstream nodes** that connect to it. The output displayed is of this node.
- Click on an output port of a node and drag the line to a valid input port of another node to form a data-flow channel. If an input port of a node has both an incoming data channel and an editable field input, the data channel will be given priority.
- Select a node or an edge by clicking on it, and then press "backspace" on the keyboard to delete.
- Right-clicking on a node open the context menu with buttons:
  - "View Ouptut" shows the current output of the node without running it.
  - "View Source" shows the souce code behind the nodes.

- Change values in the editable fields and press "Pull" to see updated results.
- Hovering over the label of a port will display a tooltip with the data type of the port.
- The keyword "None" is reserved for the value `None` (python `NoneType`). Entering this in a text field will always be parsed as `None`.
- Fields marked with an asterisk (*) require an input from the user in the form of some interaction.

## Global features <a name="other_features"></a>
- Click on "Reset Layout" in the bottom-right of the workflow viewport to automatically rearrange nodes.
- Click on "Run" in the top of the workflow viewport to run all nodes in the workflow tab.
<!---
- Hold shift+left-click and drag around nodes and edges to select them. Then click on "Create Macro" (top-right) to create a node with a sub-workflow (a macro). The created macro will appear in the node library in a green box with the name assigned to it (default: custom_macro). Click on it to make it appear in the workflow viewport.
-->
- "Export" sends the workflow's `flowrep` recipe to JSON
- "Import" opens a new workflow in a new tab based on a `flowrep` recipe loaded from JSON
- "Save" sends the last run `pyiron_workflow.schemas.Run` output to a file, either pickle bytes or a bagofholding hdf5 file
- A workflow in the gui can be exported out within your jupyter notebook scope using: `wf_gui = pf.get_workflow()`. This new object behaves like a conventional `pyiron_workflow` object.

## Node status <a name="node_status"></a>
- The square box next to the name of the node indicates the execution status of the node:
  - White is for nodes not yet executed
  - Green is for nodes that have been successfully executed and cache has been activated
  - Blue is for nodes that have been successfully executed and cache has not been activated, or has been manually reset with an active cache
  - Red is for failed nodes
- Currently, the statuses are only updated after the execution.

## Known bugs <a name="known_bugs"></a>

- Currently, if files in the node library are updated while the GUI is running, the kernel has to be restarted to use the new nodes listed when the "refresh" button is pressed

## Input type hints for node developers <a name="node_devel"></a>

Nodes hinted as `flowrep.schemase.JSONABLE` types get exposed as user-typable input right in the GUI, where

```python
JSONABLE = typing.TypeAliasType(
    "JSONABLE",
    "dict[str, JSONABLE] | list[JSONABLE] | str | int | float | bool | None",
)
```

In addition to this, if you hint some `Literal[{something jsonable}] | Literal[{something else jsonable}] | ...`, you'll get a drop-down choice menu in the GUI.


## Installation for module developers <a name="dev_install"></a>
- Clone the repository to your file system
- Install dependecies into a conda environment:\
`conda install -c conda-forge pyiron_workflow jupyterlab nodejs esbuild anywidget ipytree` as of 26.02.2025
- Install npm packages in the folder that has been cloned (the name of the folder would be "pyironFlow"):\
`npm install @anywidget/react@0.0.7 @xyflow/react@12.3.5 elkjs@0.9.3 react@18.3.1 react-dom@18.3.1`
- Run the following command in the same folder:\
`esbuild js/widget.jsx --minify --format=esm --bundle --outdir=pyironflow/static`
- Launch a jupyter notebook from the same folder and import the pyironflow module as [usual](#launching_pyironflow).
