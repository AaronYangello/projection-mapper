import threading

from projection_show.render.preview import PreviewEncoder, encode_preview


def test_preview_encoder_publishes_jpeg_off_thread():
    published = []
    ready = threading.Event()

    def publish(data):
        published.append((threading.current_thread().name, data))
        ready.set()

    encoder = PreviewEncoder(publish)
    try:
        assert encoder.submit((2, 2), bytes([255, 0, 0] * 4))
        assert ready.wait(1)
        stats = encoder.snapshot()
        assert stats["submitted_total"] == stats["encoded_total"] == 1
        assert published[0][0] == "preview-jpeg-encoder"
        assert published[0][1][:2] == b"\xff\xd8"
    finally:
        encoder.close()


def test_encode_preview_returns_jpeg():
    assert encode_preview((1, 1), bytes([0, 0, 0]))[:2] == b"\xff\xd8"
