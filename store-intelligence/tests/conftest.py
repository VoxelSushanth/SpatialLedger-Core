import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)
