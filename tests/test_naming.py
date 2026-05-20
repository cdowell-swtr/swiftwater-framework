from framework_cli.naming import ProjectNames, derive_names


def test_simple_name():
    names = derive_names("My App")
    assert names == ProjectNames(
        project_name="My App",
        project_slug="my-app",
        package_name="my_app",
    )


def test_name_with_punctuation_and_extra_spaces():
    names = derive_names("  Cool!! Service 2  ")
    assert names.project_name == "Cool!! Service 2"
    assert names.project_slug == "cool-service-2"
    assert names.package_name == "cool_service_2"


def test_already_slug_like():
    names = derive_names("data-pipeline")
    assert names.project_slug == "data-pipeline"
    assert names.package_name == "data_pipeline"


def test_blank_input_returns_empty_slug():
    # Contract: the pure deriver does not validate; it returns empty strings for
    # blank input. Rejecting empty/invalid names is the CLI's responsibility.
    names = derive_names("   ")
    assert names.project_slug == ""
    assert names.package_name == ""
