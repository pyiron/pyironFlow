# pyironFlow

# Visual Programming Interface
The visual programmming interface `pyironflow` or `PyironFlow` is a gui skin based on [ReactFlow](https://reactflow.dev/) that currently works on top of `pyiron_workflow`. Theoretically, one could currently pack `pyiron_base` jobs into nodes for execution. The gui could also be extended to pack the workflow graph (extracted from the gui using `get_workflow()`) into a `pyiron_base` job for execution. An existing code-based workflow graph can be packed into the gui using `PyironFlow([wf])` where wf is the existing graph.

## Installation

`conda install -c conda-forge pyironflow`

Recommended to be used with JupyterLab: `conda install -c conda-forge jupyterlab`

## Example of a multiscale simulation

### Problem definition:
![atomistics_to_continuum](docs/_static/multiscale_pf_science.png)

### Constructing the workflow:
![select_nodes](docs/_static/multiscale_pf_node_select.png)

### Execution:
![view_output](docs/_static/multiscale_pf_view_output.png)

### Viewing source code:
![view_source](docs/_static/multiscale_pf_view_source.png)

### Visualization of FEM meshes using PyVista:
![visualize_mesh](docs/_static/multiscale_pf_visualize_mesh.png)

### Atomistic sub-workflow:
![atomistic_part](docs/_static/multiscale_pf_atomistic_workflow.png)

### Continuum sub-workflow:
![continuum_part](docs/_static/multiscale_pf_FEM_workflow.png)

## Planned/desired/in-development features

- Dynamically add nodes from the notebook to the node library (currently being polished by Julius Mittler)
- Dynamically make macros from the gui using a box selection and add them to the node library (currently in development by Julius Mittler)
- Automatic positioning of nodes in a nice way on (re-)instantiation (current positioning is passable, but room for improvement exists)
- Caching based on a hash-based storage. Currently caching does not work at all in the gui since the workflow graph is reinstantiated everytime there's a change in the gui. This could be theoretically fixed by comparing the dictionary of the existing workflow to the new dictionary from the gui. But this would be a painstaking process and easily broken. A better way would be to work with a hash-based storage which would reload outputs when the inputs of a node have not changed. However this would have to be implemented in `pyiron_workflow` and not in the gui side of things.
- Edit the source code of nodes from within the gui. Maybe something that uses the [FileReader](https://stackoverflow.com/questions/51272255/how-to-use-filereader-in-react) api. Need to look into this further.

See the demo.ipynb jupyter notebook for  brief discussion of the key ideas, the link to pyiron_workflows and a few toy application of the xyflow project.

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/pyiron/pyironFlow/HEAD?labpath=pyironflow_demo.ipynb)
