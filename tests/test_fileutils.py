from yas_filetool.utils.fileutils import unique_target, _sha256


def test_unique_target_free(tmp_path):
    p = tmp_path / "photo.jpg"
    assert unique_target(p) == p


def test_unique_target_collision(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"x")
    assert unique_target(p) == tmp_path / "photo_1.jpg"


def test_sha256(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello")
    assert _sha256(p) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
