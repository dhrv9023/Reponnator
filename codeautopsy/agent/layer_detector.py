"""
agent/layer_detector.py — Architectural Layer Detection

Detects which architectural layer a function belongs to based on file path and name.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LAYER_SIGNALS


def detect_layer(qualified_name: str, file_path: str) -> str:
    """
    Determines which architectural layer a function belongs to
    based on its file path and qualified name.
    
    Args:
        qualified_name: e.g., "UserService.get_user"
        file_path: e.g., "src/services/user_service.py"
    
    Returns:
        Layer name: "entry", "service", "repository", "model", "utility",
                   "config", "middleware", "controller", "external", "unknown"
    """
    path_lower = file_path.lower() if file_path else ""
    name_lower = qualified_name.lower()
    
    # Check each layer's signals
    for layer, signals in LAYER_SIGNALS.items():
        for signal in signals:
            if signal in path_lower or signal in name_lower:
                return layer
    
    # Heuristics if no signal matched
    if "test" in path_lower or "spec" in path_lower:
        return "test"
    
    if "__init__" in path_lower:
        return "module_init"
    
    if is_private_function(qualified_name):
        return "utility"
    
    return "unknown"


def is_private_function(qualified_name: str) -> bool:
    """
    Check if function is private (starts with _ or __).
    
    Args:
        qualified_name: e.g., "_helper_function" or "Class._private_method"
    
    Returns:
        True if private
    """
    # Get the last part (function name)
    parts = qualified_name.split(".")
    if not parts:
        return False
    
    last_part = parts[-1]
    return last_part.startswith("_")


def is_cross_layer_node(from_layer: str, to_layer: str) -> bool:
    """
    Returns True if a call crosses architectural layer boundary.
    
    Some layer transitions are expected (service→repository).
    Others are violations (repository→service = bad).
    
    Args:
        from_layer: Caller's layer
        to_layer: Callee's layer
    
    Returns:
        True if this is a cross-layer call
    """
    # Same layer = not cross-layer
    if from_layer == to_layer:
        return False
    
    # Expected transitions (not considered violations)
    expected_transitions = {
        ("entry", "controller"),
        ("entry", "service"),
        ("controller", "service"),
        ("service", "repository"),
        ("service", "model"),
        ("repository", "model"),
        ("controller", "model"),
    }
    
    # Utility and config can be called from anywhere
    if to_layer in ["utility", "config", "middleware"]:
        return False
    
    # Check if this transition is expected
    transition = (from_layer, to_layer)
    if transition in expected_transitions:
        return False
    
    # All other transitions are cross-layer
    return True


def get_layer_description(layer: str) -> str:
    """
    Get a human-readable description of a layer.
    
    Args:
        layer: Layer name
    
    Returns:
        Description string
    """
    descriptions = {
        "entry": "Entry point (main, CLI, server startup)",
        "controller": "Controller/Handler (HTTP endpoints, routes)",
        "service": "Service/Business Logic",
        "repository": "Repository/Data Access",
        "model": "Model/Entity/Schema",
        "utility": "Utility/Helper functions",
        "config": "Configuration",
        "middleware": "Middleware/Interceptor",
        "external": "External/Unresolved",
        "test": "Test code",
        "module_init": "Module initialization",
        "unknown": "Unknown layer"
    }
    return descriptions.get(layer, "Unknown layer")


# Test function
if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("UserService.get_user", "src/services/user_service.py", "service"),
        ("User", "src/models/user.py", "model"),
        ("UserRepository.find_by_id", "src/repositories/user_repository.py", "repository"),
        ("main", "main.py", "entry"),
        ("app.run", "app.py", "entry"),
        ("UserController.get_user", "src/controllers/user_controller.py", "controller"),
        ("_helper_function", "src/utils/helpers.py", "utility"),
        ("Config.load", "src/config.py", "config"),
        ("AuthMiddleware.process", "src/middleware/auth.py", "middleware"),
        ("unknown_function", "src/unknown.py", "unknown"),
    ]
    
    print("Testing layer detection...")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for qualified_name, file_path, expected_layer in test_cases:
        detected_layer = detect_layer(qualified_name, file_path)
        status = "✓" if detected_layer == expected_layer else "✗"
        
        if detected_layer == expected_layer:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {qualified_name:40} → {detected_layer:15} (expected: {expected_layer})")
    
    print("=" * 60)
    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    
    # Test cross-layer detection
    print("\nTesting cross-layer detection...")
    print("=" * 60)
    
    cross_layer_tests = [
        ("service", "repository", False),  # Expected transition
        ("repository", "service", True),   # Violation
        ("service", "utility", False),     # Utility can be called from anywhere
        ("entry", "service", False),       # Expected
        ("model", "service", True),        # Violation (model shouldn't call service)
    ]
    
    for from_layer, to_layer, expected_cross in cross_layer_tests:
        is_cross = is_cross_layer_node(from_layer, to_layer)
        status = "✓" if is_cross == expected_cross else "✗"
        print(f"{status} {from_layer:15} → {to_layer:15} cross={is_cross} (expected: {expected_cross})")
    
    print("\n✓ Layer detector tests complete!")
