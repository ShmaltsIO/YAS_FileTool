from yas_filetool.rename import build_plans, FilePlan, FolderPlan, check_conflicts


def test_numbering_with_prefix(tmp_photos):
    plans = build_plans(
        [(tmp_photos, tmp_photos)],
        use_folder_prefix=True,
        custom_prefix="",
        postfix="photo",
        add_subfolder_names=False,
    )
    names = sorted([fp.new_path.name for fp in plans[0].files])
    answer = sorted([
        "photos_photo_1.jpg",
        "photos_photo_2.png",
        "photos_photo_3.bmp",
    ])
    assert names == answer


def test_no_prefix_just_numbers(tmp_photos):
    plans = build_plans(
        [(tmp_photos, tmp_photos)],
        use_folder_prefix=False,
        custom_prefix="",
        postfix="",
        add_subfolder_names=False,
    )
    names = sorted(fp.new_path.name for fp in plans[0].files)
    assert names == ["1.jpg", "2.png", "3.bmp"]


def test_conflict_detected(tmp_path):
    # файл a.jpg переименовывается в blocker.jpg, но blocker.jpg уже есть
    # и НЕ участвует в операции (его нет в plan.files)
    a = tmp_path / "a.jpg"
    a.write_bytes(b"y")
    blocker = tmp_path / "blocker.jpg"
    blocker.write_bytes(b"x")

    plan = FolderPlan(tmp_path, [FilePlan(a, blocker)])
    errors = check_conflicts([plan])
    assert any("уже существует" in e for e in errors)


def test_no_conflict_when_target_is_part_of_plan(tmp_path):
    # a.jpg → b.jpg, b.jpg → c.jpg — двухпроходная замена справится
    a = tmp_path / "a.jpg"; a.write_bytes(b"a")
    b = tmp_path / "b.jpg"; b.write_bytes(b"b")
    plan = FolderPlan(tmp_path, [
        FilePlan(a, tmp_path / "b.jpg"),
        FilePlan(b, tmp_path / "c.jpg"),
    ])
    assert check_conflicts([plan]) == []
