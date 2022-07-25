
__classes_to_export__ = {
    "kw_condition.backend.KiwoomOpenApiPlus": [
        "KiwoomOpenApiPlus"
    ]
}

__module_for_each_class_to_export__ = {
    name: module
    for module in __classes_to_export__
    for name in __classes_to_export__[module]
}

__all__ = [
    "KiwoomOpenApiPlus"
]


# lazily import classes on attribute access
# https://www.python.org/dev/peps/pep-0562/
def __getattr__(name):
    if name in __all__:
        if name in __module_for_each_class_to_export__:
            module_name = __module_for_each_class_to_export__[name]
            import importlib

            module = importlib.import_module(module_name)
            print( module_name, module)
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
