#!/usr/bin/env python3
"""
library_explorer_server.py
MCP Server that exposes library exploration tools for aerosandbox.

Tools:
- list_scoped_classes: List all relevant classes with summaries
- list_scoped_functions: List all relevant functions with signatures and summaries
- get_docstring: Get docstring and signature for a class/function/method
- get_methods: Get all methods and parameters for a class
"""

import os
import sys
import importlib
import inspect
from typing import Optional, List, Dict

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("library-explorer")

# Configuration - paths to trace outputs
TRACES_DIR = os.path.dirname(__file__)


# ============================================================================
# Helper Functions (from get_docstring.py and get_methods.py)
# ============================================================================

def get_object_from_path(full_path: str):
    """
    Given a full dotted path, import and return the object.
    """
    parts = full_path.split('.')
    
    for i in range(len(parts), 0, -1):
        module_path = '.'.join(parts[:i])
        attr_path = parts[i:]
        
        try:
            module = importlib.import_module(module_path)
            obj = module
            for attr in attr_path:
                obj = getattr(obj, attr)
            return obj
        except (ImportError, ModuleNotFoundError):
            continue
        except AttributeError:
            continue
    
    raise ImportError(f"Could not resolve path: {full_path}")


def get_signature_string(obj) -> Optional[str]:
    """Get signature as a string."""
    try:
        sig = inspect.signature(obj)
        return str(sig)
    except (ValueError, TypeError):
        return None


def get_docstring_summary(obj, max_lines: Optional[int] = None) -> str:
    """Get docstring summary with optional line limit."""
    docstring = inspect.getdoc(obj)
    
    if not docstring:
        return ""
    
    if max_lines is None or max_lines == 0:
        return docstring
    
    lines = docstring.split('\n')
    if max_lines > 0:
        lines = lines[:max_lines]
    else:
        lines = lines[:max_lines]
    
    return '\n'.join(lines)


def get_class_parameters(cls) -> List[str]:
    """Get list of class parameters from __init__ signature."""
    try:
        init_method = getattr(cls, '__init__', None)
        if init_method is None:
            return []
        
        sig = inspect.signature(init_method)
        params = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            params.append(param_name)
        
        return params
    except (ValueError, TypeError):
        return []


def get_class_methods_dict(cls, include_private: bool = False) -> Dict[str, callable]:
    """Get dictionary of method name -> method object for a class."""
    methods = {}
    
    for name, obj in inspect.getmembers(cls):
        if not include_private and name.startswith('_'):
            continue
        if inspect.ismethod(obj) or inspect.isfunction(obj):
            methods[name] = obj
    
    return methods


# ============================================================================
# Tools
# ============================================================================

@mcp.tool()
def get_docstring(
    full_path: str,
    max_lines: int = 0,
    include_signature: bool = True
) -> dict:
    """
    Get the docstring and signature of an aerosandbox class, function, or method.
    
    Args:
        full_path: Full dotted path (e.g., "aerosandbox.geometry.wing.Wing" or 
                   "aerosandbox.Atmosphere.density")
        max_lines: Number of docstring lines to return (0 = full docstring,
                   positive = first N lines, negative = remove last N lines)
        include_signature: Whether to include the function/method signature
    
    Returns:
        Dictionary with path, name, signature (optional), and docstring
    """
    try:
        obj = get_object_from_path(full_path)
        
        result = {
            "path": full_path,
            "name": full_path.split('.')[-1]
        }
        
        # Signature
        if include_signature:
            sig = get_signature_string(obj)
            if sig:
                result["signature"] = sig
        
        # Docstring
        docstring = get_docstring_summary(obj, max_lines if max_lines != 0 else None)
        result["docstring"] = docstring if docstring else None
        
        return result
    
    except (ImportError, AttributeError) as e:
        return {"error": f"Could not resolve '{full_path}': {e}"}


@mcp.tool()
def list_scoped_classes() -> dict:
    """
    List all classes available in relevant aerosandbox modules.
    
    Returns:
        Dictionary with list of class information (path, summary)
    """
    classes_file = os.path.join(TRACES_DIR, "scoped_classes.txt")
    
    if not os.path.exists(classes_file):
        return {"error": "scoped_classes.txt not found. Run generate_scoped_docs.py first."}
    
    classes = []
    current_class = None
    summary_lines = []
    
    with open(classes_file, 'r') as f:
        for line in f:
            line = line.rstrip()
            
            # Skip header lines
            if not line or line.startswith('Classes from') or line.startswith('===='):
                continue
            
            # New class entry (no leading whitespace)
            if line and not line.startswith(' '):
                if current_class:
                    current_class["summary"] = '\n'.join(summary_lines).strip()
                    classes.append(current_class)
                current_class = {"path": line}
                summary_lines = []
            
            # Summary or metadata lines (indented)
            elif line.startswith('  ') and current_class:
                # Stop collecting summary at Parameters or Methods
                if line.strip().startswith('Parameters:') or line.strip().startswith('Methods:'):
                    continue
                summary_lines.append(line.strip())
    
    if current_class:
        current_class["summary"] = '\n'.join(summary_lines).strip()
        classes.append(current_class)
    
    return {"classes": classes, "count": len(classes)}


@mcp.tool()
def list_scoped_functions() -> dict:
    """
    List all functions available in relevant aerosandbox modules.
    
    Returns:
        Dictionary with list of function information (path, signature, summary)
    """
    functions_file = os.path.join(TRACES_DIR, "scoped_functions.txt")
    
    if not os.path.exists(functions_file):
        return {"error": "scoped_functions.txt not found. Run generate_scoped_docs.py first."}
    
    functions = []
    current_function = None
    summary_lines = []
    
    with open(functions_file, 'r') as f:
        for line in f:
            line = line.rstrip()
            
            # Skip header lines and empty lines
            if not line or line.startswith('Functions from') or line.startswith('===='):
                continue
            
            # Function entries start with module path (no leading whitespace)
            if line and not line.startswith(' '):
                # Save previous function if any
                if current_function:
                    current_function["summary"] = '\n'.join(summary_lines).strip() if summary_lines else None
                    functions.append(current_function)
                
                # Parse new function
                if '(' in line:
                    paren_idx = line.index('(')
                    path = line[:paren_idx]
                    signature = line[paren_idx:]
                    current_function = {"path": path, "signature": signature}
                else:
                    current_function = {"path": line, "signature": None}
                summary_lines = []
            
            # Summary lines (indented)
            elif line.startswith('  ') and current_function:
                summary_lines.append(line.strip())
    
    # Don't forget the last function
    if current_function:
        current_function["summary"] = '\n'.join(summary_lines).strip() if summary_lines else None
        functions.append(current_function)
    
    return {"functions": functions, "count": len(functions)}


@mcp.tool()
def get_methods(
    full_path: str,
    docstring_lines: int = 2,
    include_signature: bool = True,
    include_private: bool = False
) -> dict:
    """
    Get all methods and parameters from an aerosandbox class.
    
    Args:
        full_path: Full dotted path to the class (e.g., "aerosandbox.geometry.wing.Wing")
        docstring_lines: Number of docstring lines per method (0 = full, positive = first N,
                         negative = remove last N)
        include_signature: Whether to include method signatures
        include_private: Whether to include private methods (starting with _)
    
    Returns:
        Dictionary with path, name, docstring, parameters, and methods list
    """
    try:
        cls = get_object_from_path(full_path)
        
        if not inspect.isclass(cls):
            return {"error": f"'{full_path}' is not a class"}
        
        result = {
            "path": full_path,
            "name": full_path.split('.')[-1]
        }
        
        # Class docstring
        class_doc = get_docstring_summary(cls, docstring_lines if docstring_lines != 0 else None)
        result["docstring"] = class_doc if class_doc else None
        
        # Parameters
        params = get_class_parameters(cls)
        result["parameters"] = params
        
        # Methods
        methods = get_class_methods_dict(cls, include_private)
        methods_list = []
        
        for method_name in sorted(methods.keys()):
            method_obj = methods[method_name]
            method_info = {"name": method_name}
            
            # Signature
            if include_signature:
                sig = get_signature_string(method_obj)
                if sig:
                    method_info["signature"] = sig
            
            # Docstring
            if docstring_lines != 0:
                doc = get_docstring_summary(
                    method_obj, 
                    docstring_lines if docstring_lines > 0 else None
                )
                method_info["docstring"] = doc if doc else None
            
            methods_list.append(method_info)
        
        result["methods"] = methods_list
        
        return result
    
    except (ImportError, AttributeError) as e:
        return {"error": f"Could not resolve '{full_path}': {e}"}


# ============================================================================
# Main
# ============================================================================

def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
