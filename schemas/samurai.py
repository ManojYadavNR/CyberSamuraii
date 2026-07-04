from pydantic import BaseModel, Field


class InstagramCommentsRequest(BaseModel):
    url: str = Field(..., description="Instagram post or reel URL")
    results_limit: int = Field(15, ge=1, le=100)
    include_replies: bool = True


class InstagramCommentReply(BaseModel):
    id: str | None = None
    username: str | None = None
    text: str = ""
    like_count: int | None = None
    timestamp: str | None = None
    profile_url: str | None = None
    comment_url: str | None = None
    replies_count: int | None = None
    replies: list["InstagramCommentReply"] = Field(default_factory=list)


class InstagramCommentsResponse(BaseModel):
    success: bool
    post_url: str | None = None
    results_limit: int | None = None
    count: int = 0
    comments: list[InstagramCommentReply] = Field(default_factory=list)
    error: str | None = None


InstagramCommentReply.model_rebuild()


class CommentOnPost(BaseModel):
    text: str = ""
    timestamp: str | None = None
    like_count: int | None = None
    comment_url: str | None = None
    is_reply: bool = False


class CommenterPostGroup(BaseModel):
    post_url: str
    shortcode: str | None = None
    post_type: str | None = None
    post_owner_username: str | None = None
    total_comments_on_post: int | None = None
    comment_count: int = 0
    comments: list[CommentOnPost] = Field(default_factory=list)


class TopCommenter(BaseModel):
    username: str
    comment_count: int
    top_level_count: int = 0
    reply_count: int = 0
    posts_count: int
    total_likes: int = 0
    profile_url: str | None = None
    profile_pic_url: str | None = None
    is_verified: bool = False
    by_post: list[CommenterPostGroup] = Field(default_factory=list)


class PostCommentStats(BaseModel):
    post_url: str
    shortcode: str | None = None
    post_type: str | None = None
    post_owner_username: str | None = None
    total_comments_on_post: int | None = None
    comments_scraped: int = 0
    replies_scraped: int = 0
    unique_commenters: int = 0


class InstagramTopCommentersRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1)
    profile_username: str | None = None
    results_limit: int = Field(15, ge=1, le=100)
    include_replies: bool = True
    top_n: int = Field(10, ge=1, le=50)


class InstagramTopCommentersResponse(BaseModel):
    success: bool
    post_urls: list[str] = Field(default_factory=list)
    results_limit: int | None = None
    posts_analyzed: int = 0
    total_comments: int = 0
    unique_commenters: int = 0
    post_stats: list[PostCommentStats] = Field(default_factory=list)
    top_commenters: list[TopCommenter] = Field(default_factory=list)
    error: str | None = None


class InstagramTimelineRequest(BaseModel):
    username: str = Field(..., description="Instagram username or profile URL")
    results_limit: int = Field(20, ge=1, le=100)
    skip_pinned: bool = False
    data_detail_level: str = Field("basicData", pattern="^(basicData|detailedData)$")


class TimelinePost(BaseModel):
    shortcode: str | None = None
    post_url: str | None = None
    type: str | None = None
    caption: str = ""
    published_at: str | None = None
    published_date: str | None = None
    weekday: int | None = None
    weekday_label: str | None = None
    hour_utc: int | None = None
    minute_utc: int | None = None
    likes_count: int | None = None
    comments_count: int | None = None
    views_count: int | None = None
    engagement_score: float | None = None
    owner_username: str | None = None


class InstagramTimelineResponse(BaseModel):
    success: bool
    profile_username: str | None = None
    target_url: str | None = None
    results_limit: int | None = None
    posts: list[TimelinePost] = Field(default_factory=list)
    analytics: dict = Field(default_factory=dict)
    error: str | None = None
