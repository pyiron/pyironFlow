from __future__ import annotations

# Define functions needed to construct and utilize a hash based database for node storage
# Could/should be later moved to pyiron_workflows

from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean
from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.engine import reflection

from datetime import datetime
from pathlib import Path

# from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dataclasses import dataclass

import sqlalchemy
import hashlib
import json
import pickle
import pandas as pd
import os
import sys


def compute_hash_value(input_dict, length=256):
    """
    Converts a dictionary into a hash.

    This function converts a dictionary into a JSON object to ensure a
    consistent hash and hashes it using SHA-256 by default but can be
    adjusted for SHA-512 or MD5.

    Parameters:
    input_dict (dict): The dictionary to convert into a hash.
    length (int, optional): The desired length of the hash, either
                             128, 256 (default), or 512.

    Returns:
    str: The hexadecimal representation of the hash of the dictionary,
         matching the specified length.
    """

    # Convert dictionary to JSON object to ensure consistent hash
    jsonified_dict = json.dumps(input_dict, sort_keys=True)

    # Create a new hash object based on specified length
    if length == 256:
        hasher = hashlib.sha256()
    elif length == 512:
        hasher = hashlib.sha512()
    elif length == 128:
        hasher = hashlib.md5()
    else:
        raise ValueError("Length must be either 128, 256, or 512.")

    # Update the hash object with the bytes of the JSON object
    hasher.update(jsonified_dict.encode("utf-8"))

    # Return the hexadecimal representation of the hash
    hash_value = hasher.hexdigest()
    # print('hash: ', hash_value, input_dict)
    return hash_value


Base = declarative_base()


class Node(Base):
    __tablename__ = "node"

    node_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    hash_value = Column(String)
    lib_path = Column(String)
    creation_date = Column(DateTime, default=datetime.utcnow)
    # creation_date = Column(DateTime, default=datetime.now(datetime.UTC))
    # data = Column(JSON)
    inputs = Column(JSON)
    outputs = Column(JSON)
    output_ready = Column(Boolean)
    file_path = Column(String)

    def __init__(self, name, input_dict, path, length=256):
        """
        Initializes a Node object with a name, input dictionary, hash, file path,
        and creation date.

        The function hashes the input dictionary and stores both the dictionary and its hash,
        and the file path where further data is stored. The `node_id` and `creation_date`
        are auto-generated.

        Parameters:
        name (str): The name of the node.
        input_dict (dict): The dictionary to convert into a hash.
        path (str): The path where further data is stored.
        length (int, optional): The desired length of the hash, either 128, 256 (default), or 512.
        """

        self.name = name
        self.hash_value = compute_hash_value(input_dict, length=length)
        # print('Node_init: ', input_dict)
        self.lib_path = path  # str(Path(path).resolve())
        # self.data = input_dict['inputs']
        self.inputs = input_dict["inputs"]
        self.output_ready = False
        self.file_path = ""


@dataclass
class Database:
    """
    Data class that represents a Database.

    Attributes:
    Session (sqlalchemy.orm.sessionmaker): The sessionmaker object that creates session.
    Node (Base): The SQLAlchemy Base object that represents a node.
    """

    Session: any
    Node: any


def create_nodes_table(db_url="postgresql://localhost/joerg", echo=False):
    """
    Creates a nodess table in the database.

    This function creates a SQLAlchemy engine with the provided database URL,
    sets up a sessionmaker with this engine, ensures the nodes table is
    created, and returns a Database object with the sessionmaker and the Node class.

    Parameters:
    db_url (str, optional): The database URL. Defaults to 'postgresql://localhost/joerg'.
    echo (bool, optional): If true, the engine will log all statements
                           as well as a repr() of their parameter lists to the engines logger.
                           Defaults to False.

    Returns:
    Database: a Database object with two attributes: a configured "Session" class and the "Node" class.
    """

    # Create engine
    engine = create_engine(db_url, echo=echo)

    # Create a configured "Session" class
    Session = sessionmaker(bind=engine)

    # Create table
    Node.__table__.create(bind=engine, checkfirst=True)

    # Return Database class with Session and Node classes
    return Database(Session, Node)


def add_node_dict_to_db(db, inputs, name="", path=".", length=256):
    """
    Adds a dictionary as a new Node to a database.

    Parameters:
    db (Database): The Database object, which includes the Session and Node classes.
    name (str): The name of the Node.
    inputs (dict): The dictionary to convert into a hash and store as data.
    path (str): The path where further data is stored.
    length (int): The desired length of the hash.


    Returns:
    Node:  The Node object that was added to the database.
    """

    # Start session
    session = db.Session()

    # Create new node, without providing node_id
    new_node = db.Node(name=name, input_dict=inputs, path=path, length=length)

    # Check if a node with this hash exists
    exists = (
        session.query(db.Node).filter_by(hash_value=new_node.hash_value).scalar()
        is not None
    )

    # If the node does not exist, add it to the session
    if not exists:
        # Add new node to session
        session.add(new_node)

        # Commit session
        session.commit()

    # Close session
    session.close()

    # If the node was added, return it; otherwise return None
    # return new_node if not exists else None
    return exists


def edit_node_dict_in_db(
    db,
    node_id,
    inputs=None,
    outputs=None,
    name=None,
    lib_path=None,
    output_ready=None,
    file_path=None,
):
    """
    Edits the attributes of a Node in a database.

    Parameters:
    db (Database): The Database object, which includes the Session and Node classes.
    node_id (int): The db id of the node to be updated.
    name (str): The new name of the Node.
    inputs (dict): The new dictionary to convert into a hash and store as data.
    lib_path (str): The new path where further data is stored.
    output_ready (bool): Flag determines if the node's output is ready.
    file_path (str): path to node storage file ('' if no file has been stored)

    Returns:
    Node: The Node object that was updated in the database.
    """

    # Start session
    session = db.Session()

    # Get the node to update
    node_to_update = session.query(db.Node).filter_by(node_id=node_id).first()

    # If the node exists, update its attributes and commit the session
    if node_to_update:
        if name is not None:
            node_to_update.name = name
        if inputs is not None:
            node_to_update.inputs = inputs
        if outputs is not None:
            node_to_update.outputs = outputs
        if lib_path is not None:
            node_to_update.lib_path = lib_path
        if output_ready is not None:
            node_to_update.output_ready = output_ready
        if file_path is not None:
            node_to_update.file_path = str(file_path)

        # Commit session
        session.commit()

    # Close session
    session.close()

    # If the node was updated, return it; otherwise return None
    return node_to_update if node_to_update else None


def remove_nodes_from_db(db, indices=None, verbose=False):
    """
    Deletes selected/named rows in the nodes table.

    Args:
        db (Database): A Database instance containing the Session and Node classes.
        indices (list): Optional. List of indices to delete. If None, deletes all rows.
        verbose (bool): If True, prints out messages about what the function does.

    Returns:
        Database: The original Database instance passed in.
    """
    # Extract Session and Node classes from Database instance
    # Session = db.Session
    Node = db.Node

    # Start a new session
    session = db.Session()

    ids_to_delete = []

    if indices is None:
        # Delete all rows
        session.query(Node).delete()
        message = "All rows deleted. TODO: Delete all files!"
    else:
        # Check if provided indices exist in the database
        for index in indices:
            node = session.get(
                Node, int(index)
            )  # using session.get instead of query.get
            if node is None:
                if verbose:
                    print(f"Row with id {index} does not exist.")
            else:
                print("file path: ", node.file_path)
                remove_directory_if_contains_file(node.file_path)
                ids_to_delete.append(int(index))

        # Delete only the existing rows with the provided indices
        for index in ids_to_delete:
            session.query(Node).filter(Node.node_id == int(index)).delete(
                synchronize_session="fetch"
            )
            session.expire_all()  # synchronize the session
        message = f"Rows with ids {ids_to_delete} deleted."

    session.commit()

    session.close()

    if verbose:
        print(message)

    return db


def get_node_by_hash(db, hash_value):
    """
    Queries a database for a node with a specific hash value.

    Parameters:
    db (Database): The Database object, which includes the Session and Node classes.
    hash_value (str): The hash value to query for.

    Returns:
    dict: The corresponding database row as a dict if the node with the given hash exists. None otherwise.
    """

    # Start a session
    session = db.Session()

    # Query for the node
    node = session.query(db.Node).filter_by(hash_value=hash_value).first()

    # Close the session
    session.close()

    # Declare result variable
    result = None

    # If the node is found, convert it into a dictionary
    if node:
        result = {
            c.key: getattr(node, c.key)
            for c in sqlalchemy.inspect(node).mapper.column_attrs
        }

    return result


def list_table(db):
    """
    Get all data in the 'node' database table as a pandas DataFrame.

    Parameters:
    db (Database): The Database object, which includes the Session and Node classes.

    Returns:
    DataFrame: The entire 'node' database table as a pandas DataFrame.
    """

    # Start session
    session = db.Session()

    # Run SELECT * FROM node
    df = pd.read_sql(session.query(db.Node).statement, session.bind)

    return df


def drop_table(db, table_name):
    """
    Deletes a table from a database.

    Parameters:
    db (Database): Database data class that contains Session as sessionmaker and Node as SQLAlchemy Base object.
    table_name (str): The name of the table to be deleted.
    """

    engine = db.Session().get_bind()

    base = declarative_base()
    metadata = MetaData()
    metadata.reflect(bind=engine)
    table = metadata.tables[table_name]
    if table is not None:
        base.metadata.drop_all(engine, [table], checkfirst=True)


def db_query_dict(db, column="inputs", **kwargs):
    # Extract Session and Node classes from Database instance
    # Session = db.Session
    # Node = db.Node

    # Start a new session
    session = db.Session()

    # Convert kwargs values to strings
    kwargs = {k: str(v) for k, v in kwargs.items()}

    # Start building the SQL query
    query_text = "SELECT * FROM node WHERE "

    # Add conditions for each key-value pair
    for key, value in kwargs.items():
        query_text += f"{column} ->> '{key}' = '{value}' AND "

    # Remove trailing "AND "
    query_text = query_text[:-4]

    # Execute the query
    query = text(query_text)
    result = session.execute(query)

    data = result.fetchall()
    if data:
        # Convert result to a pandas DataFrame
        df = pd.DataFrame(data)
        df.columns = result.keys()
    else:
        df = pd.DataFrame()  # empty DataFrame

    session.close()

    # return the DataFrame
    return df


def transform_data_column(df):
    """
    Transforms the 'inputs' column of the DataFrame into separate columns.

    Args:
        df (DataFrame): A pandas DataFrame containing the id and data columns.

    Returns:
        DataFrame: A pandas DataFrame where each key in the 'inputs' column is a separate column.
    """
    # Transform 'inputs' column into a DataFrame
    data_df = pd.json_normalize(df["inputs"])

    # Concatenate original DataFrame (minus 'inputs' column) with the new DataFrame
    df = pd.concat([df.drop("inputs", axis=1), data_df], axis=1)

    return df


def list_column_names(db, table_name):
    """
    Returns a list of column names from a specific table in a database.

    Parameters:
    db (Database): Database data class that must contain Session as sessionmaker and Node as SQLAlchemy Base object.
    table_name (str): The name of the table.

    Returns:
    list: A list of column names in the specified table.
    """

    # create a temporary session to get the engine
    session = db.Session()
    engine = session.bind

    # initialize inspector
    insp = reflection.Inspector.from_engine(engine)

    # get table columns
    columns = insp.get_columns(table_name)

    # close session
    session.close()

    # return list of column names
    return [column["name"] for column in columns]


def extract_node_input(node, db):
    """
    This function extracts input from a pyiron_workflow node object as a dictionary.

    Arguments:
    node -- the pyiron_workflow node object from which to extract the input

    Returns:
    A dictionary where each key-value pair is the name of a channel and its corresponding value.
    """

    inp_node_dict = get_all_connected_input_nodes(node)
    # print(inp_node_dict.keys())

    ic = node.inputs.to_dict()["channels"]
    input_dict = dict()
    for k, v in ic.items():
        # print(k)
        if k in inp_node_dict:
            inp_node = inp_node_dict[k]
            input_dict[k] = "hash_" + get_node_hash(inp_node, db)
            save_node(inp_node, db, file_output=False)
        else:
            input_dict[k] = v["value"]
    return input_dict


def extract_node_output(node, as_string=True):
    """
    This function extracts input from a pyiron_workflow node object as a dictionary.

    Arguments:
    node -- the pyiron_workflow node object from which to extract the input

    Returns:
    A dictionary where each key-value pair is the name of a channel and its corresponding value.
    """

    # from pyiron_workflow.channels import NotData

    output_dict = dict()
    for k in node.outputs.channel_dict.keys():
        val = node.outputs[k].value
        if hasattr(val, "_serialize"):
            # convert dataclass objects into nested dictionaries that can be jsonified
            # TODO: dataclasses should be serializable and node-like, so that they can be imported
            # print ('extract_output_serialize: ')
            val = val._serialize(str(val))
        elif as_string:
            val = str(val)
        # if isinstance(val, NotData):
        #     val = 'NotData'
        elif hasattr(val, "keys"):
            # assumption: val object behaves like a dict
            val = dict(val)

        output_dict[k] = val
    return output_dict


def extract_unique_identifier(node):
    """
    This function creates a unique identifier for a given node. In a first approach the unique identifier is created
    by combining the package identifier and label of the node. More elaborate schemas taking into account the function
    code may be considered later.

    Arguments:
    node -- the node object for which to create the unique identifier

    Returns:
    A string representing the unique identifier for the node.
    """
    return str(node.package_identifier) + "." + str(node.label)


def get_node_storage_path(node):
    node_storage_path = extract_unique_identifier(node).replace(".", "/")
    return node_storage_path


def extract_node_dictionary(node, db):
    """
    This function creates a dictionary from a given node. The dictionary combines the output of
    'extract_node_input' and 'create_unique_identifier'.

    Arguments:
    node -- the node object from which to create the dictionary

    Returns:
    A dictionary that contains node inputs and a unique identifier for the node.
    """
    node_input = extract_node_input(node, db)
    node_id = extract_unique_identifier(node)

    return {"inputs": node_input, "node_identifier": node_id}


def create_node(node_lib_path):
    """
    This function creates the node from the Workflow.create object
    specified by the node_lib_path.

    Arguments:
    node_lib_path -- a string in the form 'attr1.attr2....attrn', where each attr is an attribute
                   of the object or one of its nested attributes

    Returns:
    The node as given by the node_lib_path.
    """
    # Initial object is Workflow.create
    from pyiron_workflow import Workflow

    obj = Workflow.create

    # Split the string into individual attributes
    attrs = node_lib_path.split(".")

    # Access the nested attributes
    for attr in attrs:
        if callable(obj):
            obj = obj()
        obj = getattr(obj, attr)

    # if the final attribute is callable, call and return the result
    return obj() if callable(obj) else obj


def add_node_to_db(node, db):
    """
    Add node instance to database. Different node inputs (based on hashing it) will result in different database
    entries.

    Arguments:
    node -- the node object to add to the database
    db -- the database to which we want to add the node metadata

    Returns:
    None.
    """

    # extract input + node identifier dictionary from node
    node_dic = extract_node_dictionary(node, db)
    # print('add: ', node_dic)

    # Convert node_identifier to a path format by replacing '.' with '/'
    path_format = node_dic["node_identifier"].replace(".", "/")

    # Add the node's metadata to the database
    exists = add_node_dict_to_db(db, inputs=node_dic, path=path_format)

    # # if node instance is not yet in db save it as file (make sure that output exists)
    # if not exists:
    #     # check if node output is available/ready
    #     if not node.outputs.ready:
    #         node.pull()

    return exists


def save_node(
    node, db, file_output=None, db_output=None, node_pull=True, json_size_limit=1000
):  # , node_id):
    """
    This function stores a node by setting its storage_directory attribute to a certain path.
    An additional directory is added to this path, named with the given database ID.

    Arguments:
    node -- the node object to be stored
    db -- the database dataclass object
    db_id -- the ID of the database where the node data is stored
    file_output -- if True save node in file
    db_output -- if True save output in db.Node.outputs

    Returns:
       True if successful
    """

    path = get_node_storage_path(node)
    node_id = get_node_db_id(node, db)
    if node_id is None:
        add_node_to_db(node, db)
        node_id = get_node_db_id(node, db)

    if node_pull:
        run = node.pull
    else:
        run = node.run

    json_size = get_json_size(extract_node_output(node))
    if file_output is None:
        if json_size > json_size_limit:
            file_output = True
            if db_output is None:
                db_output = False
        else:
            file_output = False
            if db_output is None:
                db_output = True

    if file_output:
        # print('save: node_id: ', node_id)
        # Create a Path object and add the database id as a new directory
        file_path = Path(path) / str(node_id)

        # Set the node's storage_directory path
        node.storage_directory.path = file_path
        if not node.outputs.ready:
            run()

        edit_node_dict_in_db(
            db, node_id, output_ready=node.outputs.ready, file_path=file_path
        )
        node_to_pickle(node, file_path, db)
        # node.save()
    if db_output:
        if not node.outputs.ready:
            run()

        # as_string=False would be preferred but returns objects that cannot be json-ified
        edit_node_dict_in_db(
            db,
            node_id,
            output_ready=node.outputs.ready,
            outputs=extract_node_output(node, as_string=True),
        )

    return node_id


def get_json_size(obj):
    """
    Get the size of a Python object when stored as JSON.

    Parameters:
    obj (Python object): The Python object to be sized.

    Returns:
    int: The size of the object in bytes when stored as JSON.
    """

    # Convert the object to a JSON string
    json_str = json.dumps(obj)

    # Encode the JSON string to bytes
    json_bytes = json_str.encode("utf-8")

    # Return the number of bytes
    return sys.getsizeof(json_bytes)


def node_to_pickle(node, file_path, verbose=False):
    """
    Serialize node to pickle.

    Parameters:
    node (Node): The Node object to extract data from.
    file_path (str): The path to the location where the pickle file should be written.

    Returns:
    None
    """

    # Create directories if they do not exist
    os.makedirs(file_path, exist_ok=True)

    # Define the path to the project.json file
    file_path = os.path.join(file_path, "project.pkl")

    # Write the data to the JSON file
    with open(file_path, "wb") as file:
        pickle.dump(node, file)

    if verbose:
        print(f"Node written to {file_path}")
    return True


def load_node_from_pickle(node, file_path, db=None, verbose=False):
    """
    Loads input and output data from a JSON file into a Node object.

    Parameters:
    node (Node): The Node object to load data into.
    file_path (str): The path to the location of the JSON file.

    Returns:
    None
    """

    # import numpy as np

    # Define the path to the project.json file
    file_path = os.path.join(file_path, "project.pkl")

    # Open the JSON file and load the data
    with open(file_path, "rb") as file:
        node = pickle.load(file)

    if verbose:
        print(f"Data loaded into node from {file_path}")

    return node


def node_to_json(node, file_path, db, verbose=False):
    """
    Extracts input and output data from a node and writes it to a JSON file.

    Parameters:
    node (Node): The Node object to extract data from.
    file_path (str): The path to the location where the JSON file should be written.

    Returns:
    None
    """

    # Create directories if they do not exist
    os.makedirs(file_path, exist_ok=True)

    # Extract input and output data from the node as dictionaries
    data = {
        "inputs": extract_node_input(node, db),  # node.inputs.to_dict(),
        "outputs": node.outputs.to_dict(),
    }

    # Define the path to the project.json file
    json_file_path = os.path.join(file_path, "project.json")

    # Write the data to the JSON file
    with open(json_file_path, "w") as json_file:
        json.dump(data, json_file)

    if verbose:
        print(f"Data written to {json_file_path}")
    return True


def load_data_from_json(node, file_path, db, verbose=False):
    """
    Loads input and output data from a JSON file into a Node object.

    Parameters:
    node (Node): The Node object to load data into.
    file_path (str): The path to the location of the JSON file.

    Returns:
    json data
    """

    # import numpy as np

    # Define the path to the project.json file
    json_file_path = os.path.join(file_path, "project.json")

    # Open the JSON file and load the data
    with open(json_file_path, "r") as json_file:
        data = json.load(json_file)

    return data


def load_node_from_json(node, file_path, db, verbose=False):
    """
    Loads input and output data from a JSON file into a Node object.

    Parameters:
    node (Node): The Node object to load data into.
    file_path (str): The path to the location of the JSON file.

    Returns:
    None
    """

    # import numpy as np

    # Define the path to the project.json file
    json_file_path = os.path.join(file_path, "project.json")

    # Open the JSON file and load the data
    with open(json_file_path, "r") as json_file:
        data = json.load(json_file)

    # Load the inputs and outputs into the node
    #     for key, value in data['inputs']['channels'].items():
    #         node.inputs[key] = eval_db_value(value['value'], db)
    set_node_input(node, data["inputs"], db)

    for key, value in data["outputs"]["channels"].items():
        # val = value['value'].replace('array', 'np.array')
        # node.outputs[key] = eval(val)
        val = eval_db_value(value["value"], db)
        node.outputs[key] = val

    if verbose:
        print(f"Data loaded into node from {json_file_path}")

    return node


def get_node_hash(node, db, hash_length=256):
    hash_value = compute_hash_value(
        extract_node_dictionary(node, db), length=hash_length
    )
    return hash_value


def get_node_db_id(node, db):
    session = db.Session()
    hash_value = get_node_hash(node, db)

    q = session.query(db.Node).filter(db.Node.hash_value == hash_value).all()
    # alternative solution (fster by about a factor 2 but less pythonic)
    # query = f"SELECT * FROM node WHERE hash_value = '{hash}'"
    # result = session.execute(text(query)).fetchall()
    # result[0][0]

    if len(q) == 0:
        node_id = None
    elif len(q) == 1:
        node_id = q[0].node_id
    else:
        raise ValueError(f"Error: Multiple nodes with identical hash: {len(q)}")
    return node_id


def process_query_result(q):
    """
    Processes the result of a query.

    Parameters:
    q (list): The result of a SQLAlchemy query.

    Returns:
    None if list is empty, the list if it contains one element, raises an error otherwise.
    """

    query_len = len(q)
    assert query_len <= 1, "Query result should not contain more than one element."

    q_out = None if query_len == 0 else q[0]

    return q_out


def eval_db_value(value, db):
    """
    Evaluates a value from the database. If the value is a hash, retrieve the corresponding node.

    Parameters:
    value (str): The value to evaluate. If it's a hash, it should start with 'hash_'.
    db (Database): The Database object, which includes the necessary functions to retrieve nodes.

    Returns:
    Node or Python object: The Node object if the value is a hash, otherwise the evaluated value.
    """

    # Check if the value is a hash
    if value.startswith("hash_"):
        # Extract the hash value by removing the prefix
        hash_value = value[5:]

        # Get a dictionary using the hash value
        node_dict = get_node_by_hash(db, hash_value)

        # Extract the node_id
        node_id = node_dict["node_id"]

        # Retrieve the Node using the node_id
        new_node = get_node_from_db_id(node_id, db)

        val = new_node
    elif value.startswith("array"):
        import numpy as np

        val = value.replace("array", "np.array")
    else:
        # If the value is not a hash, simply evaluate it
        try:
            from pyiron_nodes.atomistic.property.elastic import DataStructureContainer

            val = eval(value)
        except Exception as e:
            print("eval exception: ", e, value)
            val = None
    return val


def get_dict_from_db_id(node_id, db):
    session = db.Session()

    # Check if a node with this node_id exists
    q = session.query(db.Node).filter_by(node_id=node_id).scalar()
    return q


def get_node_from_db_id(node_id, db, data_only=False):
    session = db.Session()

    # Check if a node with this node_id exists
    q = session.query(db.Node).filter_by(node_id=node_id).scalar()

    node = None
    if q is not None:
        # print('query: ', q.node_id, q.hash_value)
        lib_path = q.lib_path

        # print('path: ', node_lib_path)
        if not lib_path.startswith("None"):
            # node class defined in library
            node_lib_path = ".".join(lib_path.split("/")[1:])
            node = create_node(node_lib_path)

            if q.file_path != "":
                file_path = Path(q.file_path)

                # Set the node's storage_directory path
                # node.storage_directory.path = file_path
                # node.load()
                # if data_only:
                #     # mainly for debugging to analyze the json data
                #     node = load_data_from_json(node, file_path, db)
                # else:
                node = load_node_from_pickle(node, file_path)
            else:
                # load input from database
                # print('q: ', q)
                node = set_node_input(node, q.inputs, db)
                if q.outputs is not None:
                    node = set_node_output(node, q, db)
        else:
            # Node class definition exists only locally
            print(
                f"NodeTable(id={node_id}): Save your node class in a pyiron_nodes and/or register it!"
            )
            node = None

    return node


def remove_directory_if_contains_file(dir_path, filename="project.h5"):
    """
    Removes a directory if it contains a specific file and no other files or directories.

    Parameters:
    dir_path (str): The path to the directory.
    filename (str): The name of the file to check for. Default is 'parameter.h5'.

    Returns:
    None
    """

    file_path = os.path.join(dir_path, filename)

    # Check if the specified file is in the directory
    if os.path.exists(file_path):
        # Get list of all files and directories in dir_path
        directory_contents = os.listdir(dir_path)

        # Remove the file
        os.remove(file_path)

        # Check if there are no other files or directories in dir_path
        if len(directory_contents) == 1:
            # Delete the directory
            os.rmdir(dir_path)
        else:
            print(f"The directory {dir_path} contains other files or directories.")

    else:
        print(f"The directory {dir_path} does not contain the file {filename}.")


def set_node_input(node, q, db):
    data = q
    for key, value in data.items():
        node.inputs[key] = eval_db_value(value, db)

    return node


def set_node_output(node, q, db):
    data = q.outputs
    for key, value in data.items():
        node.outputs[key] = eval_db_value(value, db)

    return node


def run_node(node, db, verbose=False):
    node_id = get_node_db_id(node, db)
    if node_id is None:
        # node instance not yet in db
        new_node = node  # TODO implement .copy()
        out = new_node.run()
        save_node(node, db)
    else:
        new_node = get_node_from_db_id(node_id, db)
        if verbose:
            print(f"node with id={node_id} is loaded rather than recomputed")

    return new_node


def get_all_connected_input_nodes(node):
    """
    Returns a dictionary with the Node objects that are connected to all input channels of a given node.

    Parameters:
    node (Node): The Node object to inspect.

    Returns:
    dict: A dictionary where the key is the name of the input channel, and the value is the Node object connected to it.
    """

    from pyiron_workflow.topology import get_nodes_in_data_tree

    # Get channel_dict dictionary containing all input channels
    channel_dict = node.inputs.channel_dict

    # Get the nodes in the data tree of the given node
    nodes_in_data_tree = get_nodes_in_data_tree(node)

    connected_nodes = {}

    # Iterate over each input channel
    for channel_name, input_channel in channel_dict.items():
        connections, connected = (
            input_channel.to_dict()["connections"],
            input_channel.to_dict()["connected"],
        )

        # Check if the input channel is connected
        if connected:
            # Iterate over the connections and the nodes in the data tree
            for connection in connections:
                for node_in_data_tree in nodes_in_data_tree:
                    # Compare function names of nodes in the data tree with connection
                    # print (node_in_data_tree.__class__.__name__)
                    # print (connection.split('.')[0])
                    if node_in_data_tree.__class__.__name__ == connection.split(".")[0]:
                        connected_nodes[channel_name] = node_in_data_tree

    return connected_nodes


# function to convert stringified DataClass into nested dictionary
# pragmatic solution to serialize objects too complex for json etc.
# should work for conventional DataClass objects that have no extra built in functionality


def _bracketed_split(string, delimiter, strip_brackets=False):
    """Split a string by the delimiter unless it is inside brackets.
    e.g.
        list(bracketed_split('abc,(def,ghi),jkl', delimiter=',')) == ['abc', '(def,ghi)', 'jkl']
    """

    openers = "[{(<"
    closers = "]})>"
    opener_to_closer = dict(zip(openers, closers))
    opening_bracket = dict()
    current_string = ""
    depth = 0
    for c in string:
        if c in openers:
            depth += 1
            opening_bracket[depth] = c
            if strip_brackets and depth == 1:
                continue
        elif c in closers:
            assert (
                depth > 0
            ), f"You exited more brackets that we have entered in string {string}"
            assert (
                c == opener_to_closer[opening_bracket[depth]]
            ), f"Closing bracket {c} did not match opening bracket {opening_bracket[depth]} in string {string}"
            depth -= 1
            if strip_brackets and depth == 0:
                continue
        if depth == 0 and c == delimiter:
            yield current_string
            current_string = ""
        else:
            current_string += c
    assert depth == 0, f"You did not close all brackets in string {string}"
    yield current_string


def _split_func_and_args(input_string):
    func_name = ""
    args = ""
    bracket_counter = 0

    for i, char in enumerate(input_string):
        if char == "(":
            if bracket_counter == 0:
                func_name = input_string[:i].strip()
            bracket_counter += 1

        if char == ")":
            bracket_counter -= 1

        if bracket_counter > 0 or (bracket_counter == 0 and char == ")"):
            args += char

    args = args[1:-1]  # remove first '(' and last ‘)‘
    if "array" in func_name:
        # print ('func_array: ', func_name)
        return None
    if "[" in func_name:
        # print('func_array: ', func_name)
        return None

        # print ('func: ', func_name)

    return args


def _strip_args(input_string):
    inp_str = _split_func_and_args(input_string)
    if inp_str is None:
        return None
    return [s for s in _bracketed_split(inp_str, delimiter=",")]


def str_to_dict(input_string):
    """
    Convert stringified DataClass instances into nested python dictionary

    Example:
        input_string2 = 'my_obj(k1=1, k2=my_obj2(k11=1, k22=2), k3=my_obj3(k21=1, k22=array([[1,2], [2,3]])), k4=array([[(1,2)], [2,3]]), k5=[[(1, 2), (1, 2)]])'
        str_to_dict(input_string2)
    """
    arg_dict = dict()
    if _strip_args(input_string) is None:
        # print ('input_str: ', input_string)
        return input_string

    for arg in _strip_args(input_string):
        if "=" not in arg:
            # print(arg)
            return None
        key, val = arg.split("=", 1)
        key = key.strip()
        if not key.startswith("_"):
            if "(" in arg:
                arg_dict[key] = str_to_dict(val)
            else:
                arg_dict[key] = eval(val)

    return arg_dict


def clone_node_with_inputs(node):
    """
    Clone a node, keeping the same inputs but resetting the outputs.

    This function creates a new node with the same inputs as the given node but resets the outputs.

    Parameters:
    node: The node to clone. It should have 'package_identifier', 'label', and 'inputs' attributes.

    Returns:
    A new node with the same inputs as the given node, but with outputs reset.
    """
    lib_path = ".".join(node.package_identifier.split(".")[1:])
    node_lib_path = ".".join([lib_path, node.label])
    new_node = create_node(node_lib_path)
    for k, v in node.inputs.to_dict()["channels"].items():
        new_node.inputs[k] = node.inputs[k].value
    return new_node
