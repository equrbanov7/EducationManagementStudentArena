"""Optional read-only group identity providers; shared kernel imports no app."""

_PROVIDERS = []


def register_alias_provider(provider):
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def canonical_aliases(groups):
    groups = list(groups)
    result = {}
    for provider in _PROVIDERS:
        result.update(provider(groups))
    return result
