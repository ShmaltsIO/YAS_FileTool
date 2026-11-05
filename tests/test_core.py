import imagehash
from PIL import Image
from yas_filetool.core import group_duplicates


def _hashes(path, color):
    img = Image.new("RGB", (100, 100), color=color)
    return (imagehash.phash(img, hash_size=16),
            imagehash.dhash(img, hash_size=16))


def test_identical_images_grouped(tmp_path):
    f1, f2 = tmp_path / "a.jpg", tmp_path / "b.jpg"
    f1.touch(); f2.touch()
    h = _hashes(f1, "red")
    groups, _ = group_duplicates({f1: h, f2: h}, verify=False)
    assert len(groups) == 1
    assert set(groups[0]) == {f1, f2}


def _hashes_split():
    img = Image.new("RGB", (100, 100), "white")
    for x in range(50):
        for y in range(100):
            img.putpixel((x, y), (0, 0, 0))
    return (imagehash.phash(img, hash_size=16),
            imagehash.dhash(img, hash_size=16))


def _hashes_stripes():
    img = Image.new("RGB", (100, 100), "white")
    for y in range(0, 100, 10):
        for x in range(100):
            for dy in range(5):
                img.putpixel((x, y + dy), (0, 0, 0))
    return (imagehash.phash(img, hash_size=16),
            imagehash.dhash(img, hash_size=16))


def test_different_images_not_grouped(tmp_path):
    f1, f2 = tmp_path / "split.jpg", tmp_path / "stripes.jpg"
    f1.touch(); f2.touch()
    groups, _ = group_duplicates(
        {f1: _hashes_split(), f2: _hashes_stripes()},
        verify=False,
    )
    assert groups == []
