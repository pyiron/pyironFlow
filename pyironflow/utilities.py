def get_import_path(obj):
    module = obj.__module__ if hasattr(obj, "__module__") else obj.__class__.__module__
    # name = obj.__name__ if hasattr(obj, "__name__") else obj.__class__.__name__
    name = obj.__qualname__ if "__qualname__" in dir(obj) else obj.__class__.__qualname__
    path = f"{module}.{name}"
    if path == "numpy.ndarray":
        path = "numpy.array"
    return path