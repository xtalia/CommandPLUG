"""Minimal schema fixture for offline CI; real Hermes schemas are used when installed."""
import sys
import types


def install():
    schemas = {
        'read_file': {'type': 'object', 'properties': {
            'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 1},
            'limit': {'type': 'integer', 'maximum': 2000}}, 'required': ['path']},
        'search_files': {'type': 'object', 'properties': {
            'pattern': {'type': 'string'}, 'target': {'type': 'string', 'enum': ['content', 'files']},
            'limit': {'type': 'integer'}, 'offset': {'type': 'integer'},
            'context': {'type': 'integer'}}, 'required': ['pattern']},
        'terminal': {'type': 'object', 'properties': {
            'command': {'type': 'string'}, 'timeout': {'type': 'integer', 'minimum': 1}}, 'required': ['command']},
        'web_extract': {'type': 'object', 'properties': {
            'urls': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 5},
            'char_limit': {'type': 'integer', 'minimum': 2000}}, 'required': ['urls']},
    }
    registry = types.SimpleNamespace(definition_for=lambda name: (
        {'type': 'function', 'function': {'name': name, 'parameters': schemas[name]}}
        if name in schemas else None))
    tools = types.ModuleType('tools')
    tools.__path__ = []
    registry_module = types.ModuleType('tools.registry')
    registry_module.registry = registry
    sys.modules['tools'] = tools
    sys.modules['tools.registry'] = registry_module
