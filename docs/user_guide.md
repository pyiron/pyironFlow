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
A different path to the node library (e.g., `../some_other_directoy/pyiron_nodes/`) can be set, using: 
```
import sys
sys.path.append('../some_other_directory')
```
Then the nodes from within the folder named "pyiron_nodes" will be listed.

## Node library <a name="node_library"></a>
- Click on an item with a green icon in the node library to display nodes within a file in the pyiron_nodes folder.
- Click on a node (red icon) to make it appear in the workflow area of the widget.
- The refresh button is deactivated by default. It can be reactivated using:
```
pf = PyironFlow([wf], reload_node_library=True)
```
- The refresh button updates the nodes in the library reflecting any new nodes. However, nodes already in the workflow will not be automatically refreshed. 

## Basic usage <a name="basic_usage"></a>
- Use the mouse wheel to zoom in and out.
- Hold left-click in an empty area and move the mouse to pan.
- Left-click on a node, hold and move the mouse to move a node around.
- Click on a node and press "Pull" to execute the node and all **upstream nodes** that connect to it. The output displayed is of this node.
- Click on a node and press "Push" to execute the node and all **downstream nodes** that connect to it. The output displayed is of this node.
- Pressing "Pull" or "Push" again on a node without changing any of the inputs will show the cached result of the node (unless the node is defined not to use the cache in the code - `use_cache=False` in the decorator).
- Click on a node and press "Reset" to clear the cache of the node. This needs to be done whenever there was an error in connecting nodes and is later rectified.
- Change values in the editable fields and press "Pull" or "Push" to see updated results, or press "Reset" to re-run the node without changing inputs. Nodes which have been defined to not use the cache in the code (`use_cache=False` in the decorator) will always be re-run.
- Click on an output port of a node and drag the line to a valid input port of another node to form a data-flow channel. If an input port of a node has both an incoming data channel and an editable field input, the data channel will be given priority.
- Select a node or an edge by clicking on it, and then press "backspace" on the keyboard to delete.
- Right-clicking on a node open the context menu with buttons:
  - "View Ouptut" shows the current output of the node without running it.
  - "View Source" shows the souce code behind the nodes.

## Global features <a name="other_features"></a>
- Click on "Reset Layout" in the bottom-right of the workflow viewport to automatically rearrange nodes.
- Click on "Run" in the top-right of the workflow viewport to run all nodes in the workflow viewport.
<!---
- Hold shift+left-click and drag around nodes and edges to select them. Then click on "Create Macro" (top-right) to create a node with a sub-workflow (a macro). The created macro will appear in the node library in a green box with the name assigned to it (default: custom_macro). Click on it to make it appear in the workflow viewport.
-->
- "Save" creates a save folder in the current folder with the workflow name. "Load" will load the workflow from this folder. "Delete" will delete this folder. 
- A workflow in the gui can be exported out using: `wf_gui = pf.get_workflow()`. This new object behaves like a conventional `pyiron_workflow` object.

## Node status <a name="node_status"></a>
- The square box next to the name of the node indicates the execution status of the node:
  - White is for nodes not yet executed
  - Green is for nodes that have been successfully executed and cache has been activated
  - Blue is for nodes that have been successfully executed and cache has not been activated, or has been manually reset with an active cache
  - Red is for failed nodes
- Currently, the statuses are only updated after the execution.

## Known bugs <a name="known_bugs"></a>
- Nodes and edges can sometimes disappear. Open a different file in the notebook (by clicking on the folder icon on the top-left) and then reopen this file to make the nodes/edges reappear.
- Sometimes, clicking on an output port to start forming a data channel will not cause a line to appear. The solution to this is the same as the previous bug.
- It may be needed to click on nodes, edges and node-library items twice to activate them.
- The "Create Macro" functionality is still under development and has been temporarily deactivated.
- Currently, the kernel has to be restarted to use the new nodes listed when the "refresh" button is pressed. This will be fixed in an update.

## Input type hints for node developers <a name="node_devel"></a>
The following type (**primitive**) hints defined in the node functions result in interactive fields for users to specify inputs in the input ports:
- `str`: gives a text field
- `int`: gives a text field
- `float`: gives a text field
- `bool`: gives a checkbox
- `Literal`: gives a drop down menu
- Other types, called **non-primitive** (e.g., `list`, `numpy.array`, custom objects etc.), do not result in interactive fields. Only a dot appears which can be used to connect with upstream output ports.

If `Union` of types are used (also "`|`"), then the following apply:
- `Union` between non-primitive and any one of `str`, `int`, `float` result in a text field and is parsed according to the primitive if entered.
- `Union` between `int` and `float` (and other non-primitives) will be parsed according to the following example:
  - 123 will be parsed as an `int` 123
  - 123.0 will be parsed as an `int` 123
  - 123.8 will be parsed as a `float` 123.8
- `Union` between `int` and `str` (and other non-primitives) will be parsed according to the following example:
  - 123 will be parsed as an `int` 123
  - 123.0 will be parsed as an `int` 123
  - 123.8 will be parsed as an `int` 123
  - "foo" will be parsed as an `str` "foo"
- `Union` between `int` and `float` (and other non-primitives) will be parsed according to the following example:
  - 123 will be parsed as a `float` 123.0
  - 123.0 will be parsed as an `float` 123.0
  - 123.8 will be parsed as an `float` 123.8
  - "foo" will be parsed as an `str` "foo"
- `Union` between `int`, `float` and `str` (and other non-primitives) will be parsed according to the following example:
  - 123 will be parsed as a `int` 123
  - 123.0 will be parsed as an `int` 123
  - 123.8 will be parsed as an `float` 123.8
  - "foo" will be parsed as an `str` "foo"
- `typing.Optional` can be used to create a `Union` with `NoneType` and `int`, `float`, `str` and other non-primitives
- `Union` between `bool` and any other type (including `NoneType` even when defined with `typing.Optional`) is **not** supported and will throw an error in the jupyter log
- `Union` between `Literal` and any other type (including `NoneType` even when defined with `typing.Optional`) is **not** supported and will throw an error in the jupyter log
- `Union` consisting of only non-primitive types results in a dot for the input port

## Installation for module developers <a name="dev_install"></a>
- Clone the repository to your file system
- Install dependecies into a conda environment:\
`conda install -c conda-forge pyiron_workflow jupyterlab nodejs esbuild anywidget ipytree` as of 26.02.2025
- Install npm packages in the folder that has been cloned (the name of the folder would be "pyironFlow"):\
`npm install @anywidget/react@0.0.7 @xyflow/react@12.3.5 elkjs@0.9.3 react@18.3.1 react-dom@18.3.1`
- Run the following command in the same folder:\
`esbuild js/widget.jsx --minify --format=esm --bundle --outdir=pyironflow/static`
- Launch a jupyter notebook from the same folder and import the pyironflow module as [usual](#launching_pyironflow).
