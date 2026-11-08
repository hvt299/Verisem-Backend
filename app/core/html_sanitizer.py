from typing import Optional

import nh3

# Chỉ giữ các thẻ mà RichTextEditor (CKEditor) sinh ra, loại bỏ script, event handler, iframe, link javascript:
RICH_TEXT_TAGS = {"p", "br", "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s", "a", "ul", "ol", "li", "blockquote", "span"}
RICH_TEXT_ATTRIBUTES = {
    "a": {"href", "target"},
    "p": {"style"}, "h2": {"style"}, "h3": {"style"}, "h4": {"style"}, "li": {"style"},
}


def sanitize_rich_html(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return nh3.clean(
        value,
        tags=RICH_TEXT_TAGS,
        attributes=RICH_TEXT_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )
