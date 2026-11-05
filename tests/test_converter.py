from yas_filetool.converter import build_jobs


def test_convert_jpg_to_png(tmp_photos):
    jobs = build_jobs(
        folders=[str(tmp_photos)],
        recursive=False,
        mapping={".jpg": ".png"},
        overwrite=False,
        move_dir=None,
        unify_target=None,
    )
    assert len(jobs) == 1
    assert jobs[0].src.name == "a.jpg"
    assert jobs[0].dst.name == "a.png"
    assert jobs[0].action == "convert"
    assert jobs[0].overwrite is False


def test_same_format_skipped(tmp_photos):
    jobs = build_jobs(
        folders=[str(tmp_photos)],
        recursive=False,
        mapping={".png": ".png"},   # тот же формат
        overwrite=False,
        move_dir=None,
        unify_target=None,
    )
    assert jobs == []   # ничего не делаем
