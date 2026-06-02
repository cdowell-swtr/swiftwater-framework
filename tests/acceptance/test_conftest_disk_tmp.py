def test_disk_tmp_is_not_under_ram_tmp(disk_tmp):
    assert disk_tmp.exists()
    # The whole point: the dir must NOT live under the RAM-backed /tmp tmpfs.
    assert not str(disk_tmp).startswith("/tmp/"), f"{disk_tmp} is under RAM-backed /tmp"
