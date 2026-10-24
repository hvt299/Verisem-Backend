from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class BlogCategory(str, Enum):
    INTERVIEW = "interview"
    CV_WRITING = "cv_writing"
    CAREER_PATH = "career_path"
    HR_CORNER = "hr_corner"
    AI_TECH = "ai_tech"
    MARKET_INSIGHTS = "market_insights"

class BlogAuthor(BaseModel):
    name: str = Field(default="Ban Biên Tập Verisem", description="Tên tác giả")
    avatar_url: Optional[str] = Field(default=None, description="Ảnh đại diện tác giả")
    role: str = Field(default="Chuyên gia Nhân sự & AI", description="Chức danh hoặc chuyên môn")
    bio: Optional[str] = Field(default="Đội ngũ nghiên cứu và cố vấn tuyển dụng ứng dụng trí tuệ nhân tạo của Verisem.", description="Tiểu sử tóm tắt")

class BlogCreate(BaseModel):
    title: str = Field(..., description="Tiêu đề bài viết")
    category: BlogCategory = Field(..., description="Danh mục bài viết")
    thumbnail_url: str = Field(..., description="Ảnh bìa bài viết")
    banner_url: Optional[str] = Field(default=None, description="Ảnh banner lớn đầu trang bài viết")
    gallery_images: List[str] = Field(default_factory=list, description="Bộ sưu tập hình ảnh đính kèm bài viết (Gallery)")
    content_html: str = Field(..., description="Nội dung bài viết (HTML/Rich Text)")
    summary: Optional[str] = Field(default=None, description="Đoạn trích dẫn tóm tắt bài viết (Meta description/Excerpt)")
    tags: List[str] = Field(default_factory=list, description="Danh sách từ khóa / thẻ tag liên quan")
    is_featured: bool = Field(default=False, description="Đánh dấu bài viết tiêu điểm ghim nổi bật")
    is_hot: bool = Field(default=False, description="Đánh dấu bài viết xu hướng thịnh hành")
    key_takeaways: List[str] = Field(default_factory=list, description="Các điểm mấu chốt/ghi nhớ nhanh từ bài viết")
    target_audience: Optional[str] = Field(default="all", description="Đối tượng độc giả (all, applicant, hr)")
    author_name: str = Field(default="Ban Biên Tập", description="Tên tác giả (tương thích backward)")
    author_avatar: Optional[str] = Field(default=None, description="Ảnh đại diện tác giả")
    author_role: Optional[str] = Field(default="Ban Biên Tập Verisem", description="Chức danh tác giả")
    author_bio: Optional[str] = Field(default=None, description="Tiểu sử tác giả")
    likes_count: int = Field(default=0, description="Số lượt thích bài viết")
    shares_count: int = Field(default=0, description="Số lượt chia sẻ")
    is_published: bool = Field(default=True, description="Đăng ngay hay lưu nháp")

class BlogUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[BlogCategory] = None
    thumbnail_url: Optional[str] = None
    banner_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    content_html: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    is_featured: Optional[bool] = None
    is_hot: Optional[bool] = None
    key_takeaways: Optional[List[str]] = None
    target_audience: Optional[str] = None
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None
    author_role: Optional[str] = None
    author_bio: Optional[str] = None
    likes_count: Optional[int] = None
    shares_count: Optional[int] = None
    is_published: Optional[bool] = None