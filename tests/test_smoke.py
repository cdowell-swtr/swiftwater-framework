import framework_cli


def test_package_has_version():
    assert isinstance(framework_cli.__version__, str)
    assert framework_cli.__version__
