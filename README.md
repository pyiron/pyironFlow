# pyironFlow

# Visual Programming Interface
The visual programmming interface `pyironflow` or `PyironFlow` is a gui skin based on [ReactFlow](https://reactflow.dev/) that currently works on top of `pyiron_workflow`. Theoretically, one could currently pack `pyiron_base` jobs into nodes for execution. The gui could also be extended to pack the workflow graph (extracted from the gui using `get_workflow()`) into a `pyiron_base` job for execution. An existing code-based workflow graph can be packed into the gui using `PyironFlow([wf])` where wf is the existing graph.

## Example of a multiscale simulation

### Problem definition:
![Gui1](https://github.com/user-attachments/assets/cce60750-6eb4-4e16-8fca-af192017da25)

### Constructing the workflow:
![Gui2](https://github.com/user-attachments/assets/3228734b-7ff5-4512-b965-ff8c6d10103a)

### Execution:
![Gui3](https://github.com/user-attachments/assets/34e43a83-c5bf-44ce-8aea-cd1d30f2b14d)

### Viewing source code:
![Gui4](https://github.com/user-attachments/assets/04c35f35-e850-4f5d-a511-ae35642e7d3c)

### Visualization of FEM meshes using PyVista:
![Gui5](https://github.com/user-attachments/assets/653d0bfd-92fe-4188-b8bd-e04a8f8fa8da)

### Atomistic sub-workflow:
![Gui6](https://github.com/user-attachments/assets/c4a85724-ce4e-4383-8c47-64c181281fe6)

### Continuum sub-workflow:
![Gui7](https://github.com/user-attachments/assets/42b617d4-303d-405a-b057-eebcc94089f4)

## Planned/desired/in-development features

- Dynamically add nodes from the notebook to the node library (currently being polished by Julius Mittler)
- Dynamically make macros from the gui using a box selection and add them to the node library (currently in development by Julius Mittler)
- Automatic positioning of nodes in a nice way on (re-)instantiation (current positioning is passable, but room for improvement exists)
- Caching based on a hash-based storage. Currently caching does not work at all in the gui since the workflow graph is reinstantiated everytime there's a change in the gui. This could be theoretically fixed by comparing the dictionary of the existing workflow to the new dictionary from the gui. But this would be a painstaking process and easily broken. A better way would be to work with a hash-based storage which would reload outputs when the inputs of a node have not changed. However this would have to be implemented in `pyiron_workflow` and not in the gui side of things.
- Edit the source code of nodes from within the gui. Maybe something that uses the [FileReader](https://stackoverflow.com/questions/51272255/how-to-use-filereader-in-react) api. Need to look into this further.

See the demo.ipynb jupyter notebook for  brief discussion of the key ideas, the link to pyiron_workflows and a few toy application of the xyflow project.

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/pyiron/pyironFlow/HEAD?labpath=pyironflow_demo.ipynb)
