from container import build_container

_container = None

async def make_graph(config: dict = None):
    global _container
    if _container is None:
        _container = await build_container()
    return _container.query_graph