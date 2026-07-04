from datetime import datetime, timezone

from services.apify.instagram_timeline import compute_timeline_analytics, normalize_apify_post


def test_normalize_apify_post_published_at():
    row = {
        "shortCode": "ABC123",
        "postUrl": "https://www.instagram.com/reel/ABC123/",
        "publishedAt": "2026-03-21T14:13:00.000Z",
        "likesCount": 10,
        "commentsCount": 2,
        "type": "reel",
        "accessStatus": "success",
    }
    post = normalize_apify_post(row)
    assert post is not None
    assert post["weekday_label"] == "Sat"
    assert post["hour_utc"] == 14


def test_compute_timeline_analytics_counts_days():
    posts = [
        {
            "published_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "published_date": "2026-01-01",
            "weekday": 3,
            "weekday_label": "Thu",
            "hour_utc": 10,
        },
        {
            "published_at": datetime(2026, 1, 8, 20, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "published_date": "2026-01-08",
            "weekday": 3,
            "weekday_label": "Thu",
            "hour_utc": 20,
        },
    ]
    analytics = compute_timeline_analytics(posts)
    assert analytics["posts_count"] == 2
    assert analytics["most_popular"]["weekday_label"] == "Thu"
    assert analytics["day_counts"][3]["count"] == 2
