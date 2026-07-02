"""Instagram public feed API normalization for Samurai."""

from samurai.main import build_instagram_json_payload, enrich_posts_from_user_feed, normalize_feed_item


def test_normalize_feed_item_photo_post():
    item = {
        "code": "BSOpAWyBnBc",
        "pk": "1481301671820030044",
        "media_type": 1,
        "product_type": "feed",
        "like_count": 6,
        "comment_count": 0,
        "taken_at": 1490804941,
        "image_versions2": {
            "candidates": [{"url": "https://cdn.example/photo.jpg"}],
        },
    }
    post = normalize_feed_item(item)
    assert post["shortcode"] == "BSOpAWyBnBc"
    assert post["type"] == "Image"
    assert post["is_video"] is False
    assert post["display_url"] == "https://cdn.example/photo.jpg"
    assert post["url"] == "https://www.instagram.com/p/BSOpAWyBnBc/"


def test_build_instagram_json_payload_splits_posts_and_reels():
    profile = {
        "username": "demo",
        "posts": [
            {
                "shortcode": "PHOTO111",
                "url": "https://www.instagram.com/p/PHOTO111/",
                "type": "Image",
                "is_video": False,
                "display_url": "https://cdn.example/photo.jpg",
                "media": [{"kind": "image", "url": "https://cdn.example/photo.jpg"}],
            },
            {
                "shortcode": "REEL222",
                "url": "https://www.instagram.com/reel/REEL222/",
                "type": "Reel",
                "is_video": True,
                "display_url": "https://cdn.example/thumb.jpg",
                "video_url": "https://cdn.example/video.mp4",
                "media": [{"kind": "video", "url": "https://cdn.example/video.mp4"}],
            },
        ],
        "comments_available": False,
    }
    payload = build_instagram_json_payload(profile)
    assert len(payload["recent_posts"]) == 1
    assert payload["recent_posts"][0]["shortcode"] == "PHOTO111"
    assert len(payload["reels"]) == 1
    assert payload["reels"][0]["shortcode"] == "REEL222"


def test_enrich_posts_from_user_feed_backfills_timeline(monkeypatch):
    from samurai import main as samurai_main

    profile = {
        "username": "demo",
        "id": "12345",
        "media_count": 1,
        "posts": [],
        "source": "profile_page",
    }
    monkeypatch.setattr(
        samurai_main,
        "fetch_user_media_feed",
        lambda session, user_id, username: [
            {
                "shortcode": "PHOTO111",
                "url": "https://www.instagram.com/p/PHOTO111/",
                "type": "Image",
                "is_video": False,
                "display_url": "https://cdn.example/photo.jpg",
                "media": [],
            }
        ],
    )
    enrich_posts_from_user_feed(profile, session=None)
    assert len(profile["posts"]) == 1
    assert profile["source"] == "public_feed_api"
