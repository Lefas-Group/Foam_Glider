#!/usr/bin/env python3
"""
get_docstring.py
Retrieve docstrings and signatures from aerosandbox classes, functions, and methods
using runtime introspection.
"""

import importlib
import inspect
from typing import Optional, Tuple


def get_object_from_path(full_path: str):
    """
    Given a full dotted path, import and return the object.
    
    Args:
        full_path: e.g., "aerosandbox.dynamics.point_mass.point_2D.speed_gamma.DynamicsPointMass2DSpeedGamma"
        
    Returns:
        The resolved object (class, function, or method)
        
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


def get_signature(obj) -> Optional[str]:
    """
    Get the signature of a callable object.
    
    Args:
        obj: A class, function, or method
        
    Returns:
        String representation of the signature, or None if not available
    """
    try:
        sig = inspect.signature(obj)
        return str(sig)
    except (ValueError, TypeError):
        # Some built-in functions don't have inspectable signatures
        return None


def get_docstring(
    full_path: str,
    max_lines: Optional[int] = None,
    include_signature: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """
    Get the docstring and optionally signature of an aerosandbox object.
    
    Args:
        full_path: Full dotted path to the class/function/method
        max_lines: 
            - None or 0: return full docstring
            - Positive int: return first N lines
            - Negative int: remove last N lines
        include_signature: Whether to also return the signature
        
    Returns:
        Tuple of (docstring, signature) where either may be None
    """
    obj = get_object_from_path(full_path)
    
    # Get docstring
    docstring = inspect.getdoc(obj)
    
    if docstring and max_lines is not None and max_lines != 0:
        lines = docstring.split('\n')
        if max_lines > 0:
            lines = lines[:max_lines]
        else:  # negative
            lines = lines[:max_lines]  # Python slice handles negative correctly
        docstring = '\n'.join(lines)
    
    # Get signature
    signature = None
    if include_signature:
        signature = get_signature(obj)
    
    return docstring, signature


def format_output(
    full_path: str,
    docstring: Optional[str],
    signature: Optional[str],
    show_path: bool = True
) -> str:
    """
    Format the output for display.
    """
    lines = []
    
    if show_path:
        # Extract just the name
        name = full_path.split('.')[-1]
        lines.append(f"=== {name} ===")
        lines.append(f"Path: {full_path}")
        lines.append("")
    
    if signature is not None:
        name = full_path.split('.')[-1]
        lines.append(f"Signature: {name}{signature}")
        lines.append("")
    
    if docstring:
        lines.append("Docstring:")
        lines.append("-" * 40)
        lines.append(docstring)
    elif docstring is None:
        lines.append("(No docstring available)")
    
    return '\n'.join(lines)


def inspect_member(
    full_path: str,
    max_lines: Optional[int] = None,
    include_signature: bool = True,
    include_docstring: bool = True,
    show_path: bool = True
) -> str:
    """
    Main function to inspect an aerosandbox member.
    
    Args:
        full_path: Full dotted path (e.g., "aerosandbox.geometry.wing.Wing")
        max_lines: 
            - None or 0: return full docstring
            - Positive int: return first N lines
            - Negative int: remove last N lines
        include_signature: Whether to include the signature
        include_docstring: Whether to include the docstring
        show_path: Whether to show the full path in output
        
    Returns:
        Formatted string with the requested information
    """
    try:
        docstring, signature = get_docstring(
            full_path, 
            max_lines=max_lines if include_docstring else None,
            include_signature=include_signature
        )
        
        if not include_docstring:
            docstring = None
        
        return format_output(full_path, docstring, signature, show_path)
    
    except (ImportError, AttributeError) as e:
        return f"Error: Could not resolve '{full_path}': {e}"


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Get docstrings and signatures from aerosandbox objects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python get_docstring.py aerosandbox.geometry.wing.Wing
  python get_docstring.py aerosandbox.library.aerodynamics.viscous.Cf_flat_plate --lines 5
  python get_docstring.py aerosandbox.Opti --lines -2  # Remove last 2 lines
  python get_docstring.py aerosandbox.Airplane --signature-only
  python get_docstring.py aerosandbox.Atmosphere.density --no-signature
        """
    )
    
    parser.add_argument(
        'path',
        help="Full dotted path to the class/function/method"
    )
    parser.add_argument(
        '-l', '--lines',
        type=int,
        default=None,
        help="Number of docstring lines (negative to remove from end)"
    )
    parser.add_argument(
        '-s', '--signature-only',
        action='store_true',
        help="Only show signature, no docstring"
    )
    parser.add_argument(
        '-d', '--docstring-only',
        action='store_true',
        help="Only show docstring, no signature"
    )
    parser.add_argument(
        '--no-signature',
        action='store_true',
        help="Exclude signature from output"
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help="Minimal output (no path header)"
    )
    
    args = parser.parse_args()
    
    # Determine what to include
    include_signature = not args.no_signature and not args.docstring_only
    include_docstring = not args.signature_only
    
    result = inspect_member(
        args.path,
        max_lines=args.lines,
        include_signature=include_signature,
        include_docstring=include_docstring,
        show_path=not args.quiet
    )
    
    print(result)


if __name__ == "__main__":
    main()
