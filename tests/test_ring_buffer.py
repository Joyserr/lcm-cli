"""RingBuffer tests."""

from lcm_cli.dashboard.ring_buffer import RingBuffer


def test_append_and_get_all():
    buf = RingBuffer(max_duration_sec=60)
    buf.append(1.0, {"speed": 10.0})
    buf.append(2.0, {"speed": 20.0})
    items = buf.get_all()
    assert len(items) == 2
    assert items[0] == (1.0, {"speed": 10.0})
    assert items[1] == (2.0, {"speed": 20.0})


def test_duration_eviction():
    buf = RingBuffer(max_duration_sec=5)
    buf.append(1.0, {"v": 1})
    buf.append(4.0, {"v": 2})
    buf.append(7.0, {"v": 3})  # 7 - 1 = 6 > 5, first entry evicted
    items = buf.get_all()
    assert len(items) == 2
    assert items[0][0] == 4.0


def test_get_range():
    buf = RingBuffer(max_duration_sec=60)
    for i in range(10):
        buf.append(float(i), {"v": i})
    items = buf.get_range(3.0, 7.0)
    assert all(3.0 <= ts <= 7.0 for ts, _ in items)
    assert len(items) == 5  # timestamps 3,4,5,6,7


def test_get_fields():
    buf = RingBuffer(max_duration_sec=60)
    buf.append(1.0, {"speed": 10, "accel": 1.5})
    buf.append(2.0, {"speed": 20, "accel": 2.5})
    result = buf.get_fields(["speed"])
    assert len(result["speed"]) == 2
    assert result["speed"][0] == (1.0, 10)
    assert result["speed"][1] == (2.0, 20)


def test_empty_buffer():
    buf = RingBuffer(max_duration_sec=60)
    assert buf.get_all() == []
    assert buf.get_range(0, 100) == []
    assert buf.get_fields(["x"]) == {"x": []}
