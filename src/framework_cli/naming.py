import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectNames:
    project_name: str
    project_slug: str
    package_name: str


def derive_names(name: str) -> ProjectNames:
    """Derive a directory slug and Python package name from a human project name."""
    lowered = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    package = slug.replace("-", "_")
    return ProjectNames(
        project_name=name.strip(),
        project_slug=slug,
        package_name=package,
    )
