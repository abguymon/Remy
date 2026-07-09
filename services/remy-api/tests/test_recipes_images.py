"""Image pipeline: download → re-encode → store, plus graceful failure."""

import io

import httpx
from PIL import Image

from remy_api.recipes import images


def _png_bytes(size=(2000, 1500), color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_store_image_bytes_reencodes_and_caps_dimensions():
    stored = images.store_image_bytes("recipe-1", _png_bytes())
    assert stored is not None
    with Image.open(stored) as img:
        assert img.format == "JPEG"
        assert max(img.size) <= 1024  # thumbnailed down from 2000px


def test_store_image_bytes_rejects_non_image():
    assert images.store_image_bytes("recipe-bad", b"not an image at all") is None


async def test_download_recipe_image_happy_path():
    png = _png_bytes(size=(800, 600))

    def handler(request):
        return httpx.Response(200, content=png, headers={"Content-Type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stored = await images.download_recipe_image("recipe-2", "https://example.com/x.png", client=client)
    assert stored is not None
    assert images.image_path_for("recipe-2").exists()


async def test_download_recipe_image_missing_url_is_none():
    assert await images.download_recipe_image("recipe-3", None) is None


async def test_download_recipe_image_http_error_is_none_not_raise():
    def handler(request):
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stored = await images.download_recipe_image("recipe-4", "https://example.com/x.png", client=client)
    assert stored is None


def test_delete_recipe_image_is_idempotent():
    images.store_image_bytes("recipe-5", _png_bytes(size=(100, 100)))
    assert images.image_path_for("recipe-5").exists()
    images.delete_recipe_image("recipe-5")
    assert not images.image_path_for("recipe-5").exists()
    images.delete_recipe_image("recipe-5")  # no error the second time
