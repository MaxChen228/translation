import asyncio

import pytest

from app.core import http_client

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture(autouse=True)
async def reset_httpx_client():
    # Ensure clean state before/after each test
    await http_client.close_http_client()
    yield
    await http_client.close_http_client()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_get_http_client_requires_initialization():
    with pytest.raises(RuntimeError):
        http_client.get_http_client()


@pytest.mark.anyio
async def test_init_returns_singleton_instance():
    first = await http_client.init_http_client()
    second = await http_client.init_http_client()
    assert first is second
    assert http_client.get_http_client() is first


@pytest.mark.anyio
async def test_init_is_thread_safe():
    results = await asyncio.gather(
        http_client.init_http_client(),
        http_client.init_http_client(),
        http_client.init_http_client(),
    )
    assert results[0] is results[1] is results[2]


@pytest.mark.anyio
async def test_close_resets_singleton():
    client = await http_client.init_http_client()
    await http_client.close_http_client()
    with pytest.raises(RuntimeError):
        http_client.get_http_client()
    new_client = await http_client.init_http_client()
    assert new_client is not client
