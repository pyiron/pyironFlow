from ipytree import Tree, Node
from pathlib import Path
import ast

from dataclasses import dataclass


# Note: available icons and types in ipytree
# - style_values = ["warning", "danger", "success", "info", "default"]
# - icons: https://fontawesome.com/v5/search?q=node&o=r (version 5) appears to work


@dataclass
class FunctionNode:
    name: str
    path: str | Path


def get_subpath_remove_ext(path, subpath_start):
    if subpath_start in path.parts:
        start_index = path.parts.index(subpath_start)
        subpath = Path(*path.parts[start_index:])
        subpath_no_ext = subpath.with_suffix('')
        return subpath_no_ext
    else:
        return "The subpath start was not found in the path."


class TreeView:
    def __init__(self, root_path='../pyiron_nodes/node_library', flow_widget=None, log=None):
        """
        This function generates and returns a tree view of nodes starting from the
        root_path directory.

        Params:
        ------
        root_path : str or Path, optional
            The root directory path from which the tree starts.
            Defaults to '../pyiron_nodes/node_library'.

        Return:
        ------
        tree : Tree object
            A tree view object with nodes added to it.
        """
        import copy

        self.path = copy.copy(root_path)
        if isinstance(self.path, str):
            self.path = Path(root_path)

        self.flow_widget = flow_widget
        self.log = log  # logging widget

        self.gui = Tree(stripes=True)
        self.add_nodes(self.gui, parent_node=self.path)

    def handle_click(self, event):
        """
        This function handles click events by adding nodes to the selected object
        if it does not already have any nodes.

        Params:
        ------
        event : dict
            A dictionary representing the event object.

        Note:
        The event object should include the owner of the event (the object that was clicked),
        and the owner should have a 'nodes' property (a list of nodes) and a 'path' property (the path to the node).
        """
        selected_node = event['owner']
        if selected_node.icon == 'codepen':
            selected_node.on_click(selected_node)
        elif (len(selected_node.nodes)) == 0:
            self.add_nodes(selected_node, selected_node.path)

    def on_click(self, node):
        path = get_subpath_remove_ext(node.path.path, 'node_library') / node.path.name
        path_str = str(path).replace('/', '.')
        if self.flow_widget is not None:
            self.flow_widget.add_node(str(path_str), node.path.name)
            self.log.append_stdout(f'on_click.add_node ({str(path_str)}, {node.path.name}) \n')

    def add_nodes(self, tree, parent_node):
        """
        This function adds child nodes to a parent node in a tree. It assumes the input
        is an Abstract Syntax Tree (AST). It creates new nodes based on the attributes
        of the parent node, updates icon style based on the type of node and finally
        adds child nodes to the parent.

        Params:
        ------
        tree : ast
            The Abstract Syntax Tree

        parent_node : Node object
            The node of the AST to which child nodes must be added

        """

        for node in self.list_nodes(parent_node):
            name_lst = node.name.split('.')
            if len(name_lst) > 1:
                if 'py' == name_lst[-1]:
                    node_tree = Node(name_lst[0])
                    node_tree.icon = 'archive'  # 'file'
                    node_tree.icon_style = 'success'
                else:
                    continue
            else:
                node_tree = Node(node.name)
                if isinstance(node, FunctionNode):
                    node_tree.icon = 'codepen'  # 'file-code' # 'code'
                    node_tree.icon_style = 'danger'
                else:
                    node_tree.icon = 'folder'  # 'info', 'copy', 'archive'
                    node_tree.icon_style = 'warning'

            node_tree.path = node
            tree.add_node(node_tree)
            if self.on_click is not None:
                node_tree.on_click = self.on_click

            node_tree.observe(self.handle_click, 'selected')

    def list_nodes(self, node: Path):
        """
        Return a list of child directories and python files of a given Path' node'.
        Child directories and python files starting with '.' or '_' are excluded.

        Parameters:
        node (Path): A directory or a python file.

        Returns:
        nodes (List[Path]): List of child directories and python files. For python file 'node',
          list_pyiron_nodes(node) is called and the paths are added.
        """
        node_path = node

        nodes = []
        if node.is_dir():
            for child in node_path.iterdir():
                if child.is_dir() and not child.name.startswith('.') and not child.name.startswith('_'):
                    nodes.append(child)

            for child in node_path.glob('*.py'):
                if not child.name.startswith('.') and not child.name.startswith('_'):
                    nodes.append(child)

        elif node.is_file():
            for child in self.list_pyiron_nodes(node):
                nodes.append(child)

        return nodes

    @staticmethod
    def list_pyiron_nodes(my_python_file):
        """
        This function reads a Python code file and looks for any assignments
        to a list variable named 'nodes'. It then creates FunctionNode objects
        for each element in this list and returns all FunctionNodes in a list.

        Params:
        ------
        my_python_file : str
            Path to the python file to be analysed

        Returns:
        -------
        nodes : list of FunctionNode
            List of FunctionNodes extracted from the Python file
        """
        nodes = []
        with open(my_python_file, "r") as source:
            tree = ast.parse(source.read())

            for stmt in tree.body:
                if (isinstance(stmt, ast.Assign) and
                        len(stmt.targets) == 1 and
                        isinstance(stmt.targets[0], ast.Name) and
                        stmt.targets[0].id == 'nodes'):

                    for n in stmt.value.elts:
                        func_node = FunctionNode(name=n.id,
                                                 path=Path(my_python_file))
                        nodes.append(func_node)

        return nodes