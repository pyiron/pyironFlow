from __future__ import annotations

# introduce node dataclass object to serialize and deserialize nodes
import pyiron_nodes.development.hash_based_storage as hs

from dataclasses import dataclass, field, fields
import dataclasses
from typing import Optional, Union
import json


@dataclass()
class ObjectAsData:
    lib_path: str = ""
    input_dict: dict = field(default_factory=dict)
    output_dict: dict = field(
        default_factory=dict
    )  # provide also an option for executed nodes
    __dataclass_name__: Optional[str] = None

    # hash_value: add .__hash__() function to node
    def to_json(self, path: Optional[Union[str, object]] = None):
        """
        Converts the dataclass instance to a JSON string.

        If path is None, returns the JSON string. If path is a string,
        writes the JSON string to a file at that path. If path is a file-like
        object, writes the JSON string to that file.

        Parameters:
        path (str or file-like object, optional): The path or file to
        write the JSON string to.

        Returns:
        str: If path is None, returns the JSON string.
        """
        json_str = json.dumps(self, cls=DataCustomEncoder)

        if path is None:
            return json_str

        if isinstance(path, str):
            with open(path, "w") as f:
                f.write(json_str)
        else:
            path.write(json_str)

    @classmethod
    def from_json(cls, json_str_or_file: Union[str, object]):
        """
        Creates an instance of ObjectsData from a JSON string or file.

        Parameters:
        json_str_or_file (str or file-like object): The JSON string
        or file to parse.

        Returns:
        MyDataClass: The created MyDataClass instance.
        """
        if isinstance(json_str_or_file, str):
            json_dict = json.loads(json_str_or_file)
        else:
            json_dict = json.load(json_str_or_file)

        # return json_dict
        return cls(**json_dict)


class DataCustomEncoder(json.JSONEncoder):
    def default(self, obj):
        print("json encoder: ", type(obj), dataclasses.is_dataclass(obj))
        if dataclasses.is_dataclass(obj):
            result = dataclasses.asdict(obj)
            if "input_dict" in result:
                for k, v in result["input_dict"].items():
                    print("input dict k: ", k, is_dataclass(v), is_pyiron_node(v))
            path_lib = get_import_path(obj)
            print("path_lib ", path_lib, len(result["output_dict"].keys()))
            if path_lib is not None:
                result["__dataclass_name__"] = get_import_path(obj)
            if len(result["output_dict"].keys()) == 0:
                del result["output_dict"]
            return result
        return super().default(obj)


def node_to_data(node, keep_input_as_node_data=True):
    data = ObjectAsData()
    data.lib_path = get_import_path(node)

    inp_nodes = hs.get_all_connected_input_nodes(node)
    for k, v in node.inputs.to_dict()["channels"].items():
        if keep_input_as_node_data and (k in inp_nodes.keys()):
            data.input_dict[k] = node_to_data(inp_nodes[k])
        else:
            data.input_dict[k] = node.inputs[k].value
    if node.outputs.ready:
        for k, v in node.outputs.to_dict()["channels"].items():
            print("out: ", k)
            data.output_dict[k] = obj_to_data(v).to_json()
    return data


def data_to_node(data):
    new_node = get_object_from_path(data.lib_path)()
    for k, v in new_node.inputs.to_dict()["channels"].items():
        # print (k, v)
        v = data.input_dict[k]
        if isinstance(v, ObjectAsData):
            new_node.inputs[k] = data_to_node(v)
        else:
            new_node.inputs[k] = v
    return new_node


def dataclass_to_data(obj):
    data = ObjectAsData()
    data.lib_path = get_import_path(obj)
    for field in fields(obj):
        # print("field: ", field, field.name)
        v = getattr(obj, field.name)
        if is_dataclass(v):
            data.input_dict[field.name] = dataclass_to_data(v)
        else:
            data.input_dict[field.name] = v
    return data


import importlib


def get_function_from_string(path: str):
    # Split a __class__ string into module and attribute
    parts = path.split(".")
    module_path = ".".join(parts[:-1])
    attribute_name = parts[-1]

    # Import the module
    module = importlib.import_module(module_path)

    # Get the attribute
    attribute = getattr(module, attribute_name)

    return attribute


def print_data(data, indent=0):
    ind_space = " " * indent
    str_print = f"{ind_space}node: {data.lib_path} \n"
    for k, v in data.input_dict.items():
        if isinstance(v, ObjectAsData):
            str_print += f" {ind_space}  {k}: {print_data(v, indent + 3)} \n"
        else:
            str_print += f" {ind_space}  {k}: {v} \n"

    return str_print


# The following functions to identify the constructing decorator are rather pragmatic solutions
# Should be replaced by a decorator attribute attached to the instance
def is_dataclass(obj):
    return hasattr(obj, "__dataclass_fields__")


def is_pyiron_node(obj):
    return hasattr(obj, "channel")


def is_numpy_array(obj):
    import numpy as np

    return isinstance(obj, np.ndarray)


def get_import_path(obj):
    module = obj.__module__ if hasattr(obj, "__module__") else obj.__class__.__module__
    name = obj.__name__ if hasattr(obj, "__name__") else obj.__class__.__name__
    path = f"{module}.{name}"
    if path == "numpy.ndarray":
        path = "numpy.array"
    return path


def get_args_from_node(node, keep_input_as_node_data=False):
    input_dict = dict()
    inp_nodes = hs.get_all_connected_input_nodes(node)
    for k, v in node.inputs.to_dict()["channels"].items():
        if keep_input_as_node_data and (k in inp_nodes.keys()):
            input_dict[k] = node_to_data(inp_nodes[k])
        else:
            input_dict[k] = node.inputs[k].value
    return input_dict


def get_outputs_from_node(node):
    output_dict = dict()
    if node.outputs.ready:
        for k in node.outputs.to_dict()["channels"].keys():
            v = node.outputs[k].value
            print("out: ", k, is_dataclass(v))
            if is_dataclass(v):
                output_dict[k] = obj_to_data(v).to_json()
            else:
                output_dict[k] = v

    return output_dict


def get_args_from_dataclass(instance, skip_default_values=True):
    arg_dict = dict()
    if hasattr(instance, "_skip_default_values"):
        skip_default_values = instance._skip_default_values

    for f in dataclasses.fields(instance):
        if not f.name.startswith(
            "_"
        ):  # private variables are for internal use (should not be changed by user)
            v = getattr(instance, f.name)
            is_not_default = True
            if skip_default_values:
                is_not_default = f.default != v
            if (
                is_not_default
            ):  # and not isinstance(f.default, dataclasses._MISSING_TYPE):
                if is_pyiron_node(v) or is_dataclass(v) or is_numpy_array(v):
                    arg_dict[f.name] = obj_to_data(v)
                else:
                    arg_dict[f.name] = v

    return arg_dict


def obj_to_data(obj, keep_input_as_node_data=True):
    data = ObjectAsData()
    data.lib_path = get_import_path(obj)

    if is_pyiron_node(obj):
        data.input_dict = get_args_from_node(
            obj, keep_input_as_node_data=keep_input_as_node_data
        )
        data.output_dict = get_outputs_from_node(obj)
    elif is_dataclass(obj):
        data.input_dict = get_args_from_dataclass(obj)
    elif is_numpy_array(obj):
        data.input_dict["array"] = obj.tolist()

    return data


def get_object_from_path(import_path):
    import importlib

    # Split the path into module and object part
    module_path, _, name = import_path.rpartition(".")
    # Import the module
    module = importlib.import_module(module_path)
    # Get the object
    object_from_path = getattr(module, name)
    return object_from_path


def data_to_obj(data):
    obj = get_object_from_path(import_path=data.lib_path)

    if is_dataclass(obj):
        result = obj(**data.input_dict)
    elif is_pyiron_node(obj):
        result = data_to_node(data)
    else:
        raise ValueError("Data must be either node or dataclass")

    return result
