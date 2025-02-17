from pyiron_workflow.type_hinting import type_hint_to_tuple
import typing
import warnings

def get_import_path(obj):
    module = obj.__module__ if hasattr(obj, "__module__") else obj.__class__.__module__
    # name = obj.__name__ if hasattr(obj, "__name__") else obj.__class__.__name__
    name = obj.__name__ if "__name__" in dir(obj) else obj.__class__.__name__
    qualname = obj.__qualname__ if "__qualname__" in dir(obj) else obj.__class__.__qualname__

    warnings.simplefilter('error', UserWarning)
    if qualname != name:
        warnings.warn("Node __name__ does not match __qualname__ which may lead to unexpected behavior. To avoid this, ensure the node is NOT nested inside subclasses within the module.")

    path = f"{module}.{name}"
    if path == "numpy.ndarray":
        path = "numpy.array"
    return path

def get_input_types_from_hint(node_input: dict):

    new_type = ""

    for listed_type in list(type_hint_to_tuple(node_input.type_hint)):
        if listed_type == None:
            listed_type = type(None)
        if listed_type.__name__ != "NoneType":
            new_type = new_type + listed_type.__name__ + "|"

    new_type = new_type[:-1]    

    for listed_type in list(type_hint_to_tuple(node_input.type_hint)):
        if listed_type == None:
            listed_type = type(None)
        if listed_type.__name__ == "NoneType":
            if new_type != "":
                new_type = ": Optional[" + new_type + "]"

    return new_type

def create_macro(wf = dict, name = str, root_path='../pyiron_nodes/pyiron_nodes'):

    imports = list("")
    var_def = ""

    file = open(root_path + '/' + name + '.py', 'w')

    for i, (k, v) in enumerate(wf.children.items()):
        rest, n = get_import_path(v).rsplit('.', 1)
        new_import = "    from " + rest + " import " + n
        imports.append(new_import)
        list_inputs = list(v.inputs.channel_dict.keys())

        for j in list(v.inputs):
            if ((v.label + "__" + j.label) in list(wf.inputs.channel_dict.keys())):
                if str(j) == ("NOT_DATA" or "None"):
                    value = "None"
                elif type(j.value) == str:
                    value = "'" + j.value + "'"
                else:
                    value = str(j.value)
                var_def = var_def + v.label + "_" + j.label + get_input_types_from_hint(j)+ " = " + value + ", "

    var_def = var_def[:-2]    

    count = 0
    new_list = list("")
    for ic, (out, inp) in enumerate(wf.graph_as_dict["edges"]["data"].keys()):
        out_node, out_port = out.split('/')[2].split('.')
        inp_node, inp_port = inp.split('/')[2].split('.')
        new_list.append([out_node, inp_node, inp_port])


    file.write(
'''from pyiron_workflow import as_function_node, as_macro_node
from typing import Optional

@as_macro_node()
def ''' + name + '''(self, ''' + var_def + '''):
''')
    for j in imports:
        file.write(j + "\n")

    for i, (k, v) in enumerate(wf.children.items()):
        rest, n = get_import_path(v).rsplit('.', 1)
        file.write("    self." + v.label + " = " +  n + "()\n") 
    
    for i, (k, v) in enumerate(wf.children.items()):
        rest, n = get_import_path(v).rsplit('.', 1)
    
        node_def =""
    
        for j in list(wf.inputs.channel_dict.keys()):
            node_label, input_label =j.rsplit('__', 1)
            if v.label == node_label: 
                node_def = node_def + input_label + " = " + node_label + "_" + input_label+ ", "
        
        for p in new_list:
            if v.label == p[1]:
                node_def = node_def + p[2] + " = self."+ p[0] + ", "
        node_def = node_def[:-2]
        file.write("    self." + v.label + ".set_input_values" + "(" + node_def + ")\n") 
    

    rest, n = list(wf.outputs.channel_dict.keys())[0].rsplit('__', 1)
    file.write("    return self." + rest)
    print("\nSuccessfully created macro: " + root_path + '/' + name + '.py')
    file.close()

    return