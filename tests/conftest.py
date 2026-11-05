import pytest
from PIL import Image


@pytest.fixture
def tmp_photos(tmp_path):
    """Папка с тремя разноцветными картинками."""
    folder = tmp_path / "photos"
    folder.mkdir()
    for name, color in [("a.jpg", "red"), ("b.png", "green"), ("c.bmp", "blue")]:
        Image.new("RGB", (100, 100), color=color).save(folder / name)
    return folder
