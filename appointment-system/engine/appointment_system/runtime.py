"""Verify this whole contained copy once, then bind its own immutable identity."""
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def contained_release():
    path=Path(__file__).absolute()
    if any(value.is_symlink() for value in (path,*path.parents)):
        raise ValueError('Contained package links are forbidden.')
    root=path.parents[2]
    from tools.install.package import verify
    return root,verify(root)['content_digest']

def create_application(project_file,environment):
    root,digest=contained_release()
    path=Path(project_file).absolute()
    if (path!=root.parent/'appointment-settings/project.json'
        or any(value.is_symlink() for value in (path,*path.parents))):
        raise ValueError('This package requires its own project settings.')
    from .configuration import load
    load(path)
    # Provider modules are imported only after the process identity is bound.
    from .hosting import create_hosted_application
    return create_hosted_application(environment,release_digest=digest)
