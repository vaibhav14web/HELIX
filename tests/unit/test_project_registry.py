from foundation.project_registry.project_registry import ProjectRegistry


def test_project_registry_helix_seed():
    registry = ProjectRegistry()
    helix = registry.resolve_project("helix")
    assert helix is not None
    assert "HELIX" in helix.name
    assert "Python" in helix.languages


def test_project_registry_list():
    registry = ProjectRegistry()
    projects = registry.list_projects()
    assert len(projects) >= 1
