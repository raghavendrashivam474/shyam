"""Foundation unit test verifying package structure and metadata."""

import shyam


def test_package_version():
    """Verify that package version is defined and adheres to current milestone target."""
    assert hasattr(shyam, "__version__")
    assert shyam.__version__ == "0.15.0"