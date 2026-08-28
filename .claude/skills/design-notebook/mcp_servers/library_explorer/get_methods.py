#!/usr/bin/env python3
"""
get_methods.py
Retrieve all methods and parameters from a class using runtime introspection.
"""

import importlib
import inspect
from typing import Optional, List, Dict


def get_object_from_path(full_path: str):
    """
    Given a full dotted path, import and return the object.
    
    Args:
        full_path: e.g., "aerosandbox.geometry.wing.Wing"
        
    Returns:
        The resolved object (class)
        
    Raises:
        ImportError, AttributeError if the path cannot be resolved
    """
    parts = full_path.split('.')
    
    # Try progressively shorter module paths
    for i in range(len(parts), 0, -1):
        module_path = '.'.join(parts[:i])
        attr_path = parts[i:]
        
        try:
            module = importlib.import_module(module_path)
            
            # Navigate to the attribute
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
    """
    Get docstring summary with optional line limit.
    
    Args:
        obj: Object to get docstring from
        max_lines: None for full, positive for first N lines, negative to remove last N
    """
    docstring = inspect.getdoc(obj)
    
    if not docstring:
        return ""
    
    if max_lines is None or max_lines == 0:
        return docstring
    
    lines = docstring.split('\n')
    if max_lines > 0:
        lines = lines[:max_lines]
    else:  # negative
        lines = lines[:max_lines]
    
    return '\n'.join(lines)


def get_class_parameters(cls) -> List[str]:
    """
    Get list of class parameters from __init__ signature.
    
    Returns list of parameter names (excluding 'self').
    """
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


def get_class_methods(cls, include_private: bool = False) -> Dict[str, callable]:
    """
    Get dictionary of method name -> method object for a class.
    
    Args:
        cls: The class to inspect
        include_private: Whether to include private methods (starting with _)
        
    Returns:
        Dict mapping method name to method object
    """
    methods = {}
    
    for name, obj in inspect.getmembers(cls):
        if not include_private and name.startswith('_'):
            continue
        if inspect.ismethod(obj) or inspect.isfunction(obj):
            methods[name] = obj
    
    return methods


def format_method_info(
    method_name: str,
    method_obj: callable,
    docstring_lines: Optional[int] = 2,
    include_signature: bool = True
) -> str:
    """
    Format information about a single method.
    
    Args:
        method_name: Name of the method
        method_obj: The method object
        docstring_lines: Number of docstring lines to include
        include_signature: Whether to include the signature
        
    Returns:
        Formatted string
    """
    lines = []
    
    # Method name with signature
    if include_signature:
        sig = get_signature_string(method_obj)
        if sig:
            lines.append(f"{method_name}{sig}")
        else:
            lines.append(method_name)
    else:
        lines.append(method_name)
    
    # Docstring
    if docstring_lines is not None:
        docstring = get_docstring_summary(method_obj, docstring_lines)
        if docstring:
            for line in docstring.split('\n'):
                lines.append(f"  {line}")
    
    return '\n'.join(lines)


def inspect_class_methods(
    full_path: str,
    docstring_lines: Optional[int] = 2,
    include_signature: bool = True,
    include_private: bool = False,
    include_parameters: bool = True,
    show_header: bool = True
) -> str:
    """
    Main function to inspect all methods of a class.
    
    Args:
        full_path: Full dotted path to the class (e.g., "aerosandbox.geometry.wing.Wing")
        docstring_lines: 
            - None or 0: full docstring
            - Positive int: first N lines
            - Negative int: remove last N lines
        include_signature: Whether to include method signatures
        include_private: Whether to include private methods
        include_parameters: Whether to show class parameters
        show_header: Whether to show header with class name
        
    Returns:
        Formatted string with all method information
    """
    try:
        cls = get_object_from_path(full_path)
        
        if not inspect.isclass(cls):
            return f"Error: '{full_path}' is not a class"
        
        output_lines = []
        
        # Header
        if show_header:
            class_name = full_path.split('.')[-1]
            output_lines.append("=" * 80)
            output_lines.append(f"Class: {class_name}")
            output_lines.append(f"Full path: {full_path}")
            output_lines.append("=" * 80)
            output_lines.append("")
            
            # Class docstring
            class_docstring = get_docstring_summary(cls, docstring_lines)
            if class_docstring:
                output_lines.append("Class description:")
                for line in class_docstring.split('\n'):
                    output_lines.append(f"  {line}")
                output_lines.append("")
        
        # Parameters
        if include_parameters:
            params = get_class_parameters(cls)
            if params:
                output_lines.append("Parameters:")
                output_lines.append("-" * 40)
                for param in params:
                    output_lines.append(f"  - {param}")
                output_lines.append("")
        
        # Methods
        methods = get_class_methods(cls, include_private)
        if methods:
            output_lines.append(f"Methods ({len(methods)} total):")
            output_lines.append("-" * 40)
            
            for method_name in sorted(methods.keys()):
                method_obj = methods[method_name]
                method_info = format_method_info(
                    method_name,
                    method_obj,
                    docstring_lines,
                    include_signature
                )
                output_lines.append(method_info)
                output_lines.append("")
        else:
            output_lines.append("(No public methods found)")
        
        return '\n'.join(output_lines)
    
    except (ImportError, AttributeError) as e:
        return f"Error: Could not resolve '{full_path}': {e}"


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Get all methods and parameters from a class",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full inspection with 2-line docstrings (default)
  python get_methods.py aerosandbox.geometry.wing.Wing
  
  # Show only method names (no signatures or docstrings)
  python get_methods.py aerosandbox.Airplane --no-signature --no-docstrings
  
  # Full docstrings
  python get_methods.py aerosandbox.Opti --lines 0
  
  # First line only
  python get_methods.py aerosandbox.Atmosphere --lines 1
  
  # Include private methods
  python get_methods.py aerosandbox.Wing --include-private
  
  # Parameters only
  python get_methods.py aerosandbox.Airplane --parameters-only
        """
    )
    
    parser.add_argument(
        'path',
        help="Full dotted path to the class"
    )
    parser.add_argument(
        '-l', '--lines',
        type=int,
        default=2,
        help="Number of docstring lines (0=full, negative to remove from end, default: 2)"
    )
    parser.add_argument(
        '--no-signature',
        action='store_true',
        help="Don't show method signatures"
    )
    parser.add_argument(
        '--no-docstrings',
        action='store_true',
        help="Don't show docstrings"
    )
    parser.add_argument(
        '--include-private',
        action='store_true',
        help="Include private methods (starting with _)"
    )
    parser.add_argument(
        '--no-parameters',
        action='store_true',
        help="Don't show class parameters"
    )
    parser.add_argument(
        '--parameters-only',
        action='store_true',
        help="Only show parameters, not methods"
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help="Minimal output (no header)"
    )
    
    args = parser.parse_args()
    
    # Handle docstring setting
    if args.no_docstrings:
        docstring_lines = None
    else:
        docstring_lines = args.lines if args.lines != 0 else None
    
    # Parameters only mode
    if args.parameters_only:
        try:
            cls = get_object_from_path(args.path)
            if not inspect.isclass(cls):
                print(f"Error: '{args.path}' is not a class")
                return
            
            params = get_class_parameters(cls)
            if params:
                class_name = args.path.split('.')[-1]
                if not args.quiet:
                    print(f"{class_name} parameters:")
                for param in params:
                    print(f"  {param}")
            else:
                print("(No parameters found)")
        except Exception as e:
            print(f"Error: {e}")
        return
    
    result = inspect_class_methods(
        args.path,
        docstring_lines=docstring_lines,
        include_signature=not args.no_signature,
        include_private=args.include_private,
        include_parameters=not args.no_parameters,
        show_header=not args.quiet
    )
    
    print(result)


if __name__ == "__main__":
    main()
