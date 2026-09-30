"""Everything that depends on Facebook's current page layout lives here.

Facebook changes its HTML often. When scraping breaks, this is the first file
to check. Text patterns are English; a Facebook account set to another
language will need these patterns translated (or switch the account's
language to English while scraping).
"""
import re

# ---- network ----
GRAPHQL_URL_PART = "/api/graphql"

# ---- links that point to a single post (not a page/feed) ----
SINGLE_POST_URL = re.compile(
    r"(/posts/|/permalink/|permalink\.php|story\.php|story_fbid=|/videos/|/reel/|/photo|/share/p/|/share/v/|/share/r/)",
    re.IGNORECASE,
)

# keys in GraphQL JSON that hold a post's permalink
POST_URL_KEYS = ("permalink_url", "url", "wwwURL")
POST_URL_HINT = re.compile(r"facebook\.com/.*(posts|permalink|story_fbid|videos|reel|photo)", re.IGNORECASE)

# ---- DOM fallback ----
ARTICLE = 'div[role="article"]'
POST_MESSAGE = 'div[data-ad-preview="message"], div[data-ad-comet-preview="message"]'
COMMENT_TEXT = 'div[dir="auto"]'
DIALOG = 'div[role="dialog"]'

# ---- buttons we click to reveal comments ----
SORT_BUTTON_TEXT = re.compile(r"^(Most relevant|Top comments|Newest|Most recent)$", re.IGNORECASE)
ALL_COMMENTS_TEXT = re.compile(r"^All comments", re.IGNORECASE)
MORE_COMMENTS_TEXT = re.compile(
    r"^(View more comments|View \d+ more comments?|See more comments|View previous comments|Load more comments)$",
    re.IGNORECASE,
)
MORE_REPLIES_TEXT = re.compile(r"^(View (all )?\d+ repl(y|ies)|\d+ repl(y|ies)|View \d+ more repl(y|ies))$", re.IGNORECASE)
SEE_MORE_TEXT = re.compile(r"^See more$", re.IGNORECASE)

# Things that mean "you can't see this"
LOGIN_WALL_HINTS = ("log in to facebook", "you must log in", "log into facebook")
CONTENT_UNAVAILABLE_HINTS = ("this content isn't available", "this page isn't available")
