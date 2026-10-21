import pytest

from source_adapters import normalize_source_item, stable_source_id


def test_normalize_source_item_has_common_schema():
    item = normalize_source_item(
        platform="youtube",
        source_name="Example feed",
        title="  Example   video ",
        summary="A short summary",
        url="https://example.com/watch?id=1",
        published="2026-10-21",
        video_url="https://cdn.example.com/clip.mp4",
        source_id="video-1",
        media_type="video",
    )
    assert item["platform"] == "youtube"
    assert item["category"] == "youtube"
    assert item["title"] == "Example video"
    assert item["media_type"] == "video"
    assert item["rights_status"] == "unknown"
    assert len(item["source_id"]) == 64


def test_source_id_is_stable_for_same_source():
    first = stable_source_id("rss", "https://example.com/post", "abc")
    second = stable_source_id("rss", "https://different.example/post", "abc")
    assert first == second


@pytest.mark.parametrize("url", ["", "example.com/post", "file:///tmp/video.mp4", "ftp://example.com/a"])
def test_rejects_non_http_source_urls(url):
    with pytest.raises(ValueError):
        normalize_source_item(
            platform="rss",
            source_name="Feed",
            title="Title",
            summary="",
            url=url,
        )


def test_video_url_promotes_media_type_when_defaulted():
    item = normalize_source_item(
        platform="rss",
        source_name="Feed",
        title="Video",
        summary="",
        url="https://example.com/post",
        video_url="https://cdn.example.com/video.mp4",
    )
    assert item["media_type"] == "video"
