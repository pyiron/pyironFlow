from ipytree import Tree, Node
from pathlib import Path
import ast

from dataclasses import dataclass

__author__ = "Joerg Neugebauer"
__copyright__ = (
    "Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - "
    "Computational Materials Design (CM) Department"
)
__version__ = "0.2"
__maintainer__ = ""
__email__ = ""
__status__ = "development"
__date__ = "Aug 1, 2024"


# Note: available icons and types in ipytree
# - style_values = ["warning", "danger", "success", "info", "default"]
# - icons: https://fontawesome.com/v5/search?q=node&o=r (version 5) appears to work


@dataclass
class FunctionNode:
    name: str
    path: str | Path


@dataclass
class DataClassNode:
    name: str
    path: str | Path


def get_rel_path_for_last_occurrence(path: Path, relpath_start: str) -> int:
    if relpath_start in path.parts:
        # Reverse the list and find the first (last in original list) occurrence
        reversed_parts = path.parts[::-1]  # this does not modify the original list
        last_occurrence = len(path.parts) - 1 - reversed_parts.index(relpath_start)

        rel_path = Path(*path.parts[last_occurrence:])
        rel_path_no_ext = rel_path.with_suffix('')
        return rel_path_no_ext


class TreeView:
    def __init__(self, root_path='../pyiron_nodes/pyiron_nodes', flow_widget=None, log=None):
        """
        This function generates and returns a tree view of nodes starting from the
        root_path directory.

        Params:
        ------
        root_path : str or Path, optional
            The root directory path from which the tree starts.
            Defaults to '../pyiron_nodes/pyiron_nodes'.

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
        # the following flag is needed since handle click sends two signals, the first repeats the last one from the
        # previous click
        self._handle_click_is_last_event = True

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
        if not self._handle_click_is_last_event:
            self._handle_click_is_last_event = True
            return None
        self._handle_click_is_last_event = False

        selected_node = event['owner']
        # self.log.append_stdout(f'handle_click ({selected_node.path}, {selected_node.name}) \n')

        if selected_node.icon in ['codepen', 'table']:
            selected_node.on_click(selected_node)
        elif (len(selected_node.nodes)) == 0:
            self.add_nodes(selected_node, selected_node.path)

    def on_click(self, node):
        # self.log.append_stdout(f'on_click.add_node_init ({node.path}, {node.path.name}) \n')
        path = get_rel_path_for_last_occurrence(node.path.path, 'pyiron_nodes') / node.path.name
        path_str = str(path).replace('/', '.')
        if self.flow_widget is not None:
            # self.log.append_stdout(f'on_click.add_node ({str(path_str)}, {node.path.name}) \n')
            self.flow_widget.add_node(str(path_str), node.path.name)

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
                elif isinstance(node, DataClassNode):
                    node_tree.icon = 'table'  # 'file-code' # 'code'
                    node_tree.icon_style = 'success'
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
    def list_pyiron_nodes(file_name, decorators=['as_function_node', 'as_macro_node', 'as_dataclass_node']):
        """
        This function reads a Python code file and looks for any assignments
        to a list variable named 'nodes'. It then creates FunctionNode objects
        for each element in this list and returns all FunctionNodes in a list.

        Params:
        ------
        file_name : str
            Path to the python file to be analysed

        Returns:
        -------
        nodes : list of FunctionNode
            List of FunctionNodes extracted from the Python file
        """
        with open(file_name, 'r') as file:
            tree = ast.parse(file.read())

        nodes = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    # check if decorator is a function call like @as_function_node()
                    if isinstance(decorator, ast.Call) and hasattr(decorator.func,
                                                                   'id') and decorator.func.id in decorators:
                        node_name = node.name
                        if isinstance(node, ast.ClassDef):
                            func_node = DataClassNode(name=node_name, path=Path(file_name))
                        else:
                            func_node = FunctionNode(name=node_name, path=Path(file_name))
                        nodes.append(func_node)
                    # check if decorator is a simple attribute like @as_function_node
                    elif hasattr(decorator, 'id') and decorator.id in decorators:
                        node_name = node.name
                        if isinstance(node, ast.ClassDef):
                            func_node = DataClassNode(name=node_name, path=Path(file_name))
                        else:
                            func_node = FunctionNode(name=node_name, path=Path(file_name))
                        nodes.append(func_node)

        return nodes
