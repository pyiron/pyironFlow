# pyironflow
The visual programmming interface `pyironflow` is a gui skin based on [ReactFlow](https://reactflow.dev/) that works on top of [pyiron_workflow](https://github.com/pyiron/pyiron_workflow).

### Table of Contents
1. [Installing pyironflow](#installing_pyironflow)
2. [Launching pyironflow](#launching_pyironflow)
3. [Node library](#node_library)
4. [Basic usage](#basic_usage)
5. [Other features](#other_features)
6. [Node status](#node_status)
7. [Known bugs](#known_bugs)
8. [Installation for developers](#dev_install)

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

In order to resize the widgets to fit your screen better, the following can be used to launch `pyironflow`:
```
from pyironflow.pyironflow import GUILayout
gui_layout = GUILayout()
gui_layout.flow_widget_height = 700 # Change this value to adjust the height of the workflow area of the widget
gui_layout.flow_widget_width = 1000 # Change this value to adjust the width of the workflow area of the widget
gui_layout.output_widget_width = 500 # # Change this value to adjust the width of the output/node-library/log on the left
pf = PyironFlow([wf], gui_layout=gui_layout)
```

The path to the node library (a folder with the name "pyiron_nodes") can be set, e.g., using:
```
pf = PyironFlow([wf], root_path='./pyiron_nodes' gui_layout=gui_layout)
```

## Node library <a name="node_library"></a>
- Click on an item with a green icon in the node library to display nodes within a file in the pyiron_nodes folder.
- Click on a node (red icon) to make it appear in the workflow area of the widget.
- The refresh button updates the nodes in the library reflecting any changes to the underlying code. However, nodes already in the workflow viewport will not be automatically refreshed.

## Basic usage <a name="basic_usage"></a>
- Use the mouse wheel to zoom in and out.
- Hold left-click in an empty area and move the mouse to pan.
- Right-click will open the jupyter drop down menu for the cell and currrently has no functionality in the app.
- Click on a node and press "Run" to execute the node and all upstream nodes that connect to it.
- Left-click on a node, hold and move the mouse to move a node around.
- Click on a node and press "Source" to view the source code of the function behind the node.
- Change values in the editable fields and press "Run" to see updated results.
- Click on an output port of a node and drag the line to a valid input port of another node to form a data-flow channel. If an input port of a node has both an incoming data channel and an editable field input, the data channel will be given priority.
- Select a node or an edge by clicking on it, and then press "backspace" on the keyboard to delete.

## Other features <a name="other_features"></a>
- Click on "Reset Layout" in the bottom-right of the workflow viewport to automatically rearrange nodes.
- Click on "Run Workflow" in the top-right of the workflow viewport to run all nodes in the workflow viewport.
- Hold shift+left-click and drag around nodes and edges to select them. Then click on "Create Macro" (top-right) to create a node with a sub-workflow (a macro). The created macro will appear in the node library in a green box with the name assigned to it (default: custom_macro). Click on it to make it appear in the workflow viewport.
- "Save workflow" creates a save folder in the current folder with a suffix `-save` attached to the end of the workflow name. "Delete workflow" will delete this folder.
- A workflow in the gui can be exported out using: `wf_gui = pf.get_workflow()`. This new object behaves like a conventional `pyiron_workflow` object.

## Node status <a name="node_status"></a>
- The square box next to the name of the node indicates the execution status of the node:
  - White is for nodes not yet executed
  - Green is for nodes that have been successfully executed
  - Red is for failed nodes
- Currently, the statuses are only updated after the execution.

## Known bugs <a name="known_bugs"></a>
- Nodes and edges can sometimes disappear. Open a different file in the notebook (by clicking on the folder icon on the top-left) and then reopen this file to make the nodes/edges reappear.
- Sometimes, clicking on an output port to start forming a data channel will not cause a line to appear. The solution to this is the same as the previous issue.
- It may be needed to click on nodes, edges and node-library items twice to activate them.
- The "Create Macro" functionality is still under development and may throw unexpted errors (e.g. * is already the label for a child) even with a valid selection. Reinstantiate the widget in such cases.
- Resizing the widget using GUILayout() sometimes takes a couple of attempts to reflect changes

## Installation for developers <a name="dev_install"></a>
- Clone the repository to your file system
- Install dependecies into a conda environment:\
`conda install -c conda-forge pyiron_workflow jupyterlab nodejs esbuild anywidget ipytree` as of 26.02.2025
- Install npm packages in the folder that has been cloned (the name of the folder would be "pyironFlow"):\
`npm install @anywidget/react@0.0.7 @xyflow/react@12.3.5 elkjs@0.9.3 react@18.3.1 react-dom@18.3.1`
- Run the following command in the same folder:\
`esbuild js/widget.jsx --minify --format=esm --bundle --outdir=pyironflow/static`
- Launch a jupyter notebook from the same folder and import the pyironflow module as [usual](#launching_pyironflow).
