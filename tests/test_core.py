"""Run with:  python -m pytest -q"""
import json

from postlens.ai.retrieval import BM25, build_chunks, select_context
from postlens.anonymize import replace_ranges, scrub
from postlens.scraper.facebook import is_single_post, normalize_url
from postlens.scraper.graphql_parser import GraphQLCollector


def test_scrub_removes_contact_details():
    t = scrub("mail me at jane.doe@example.com or call +880 1712-345678, see facebook.com/jane.doe.77 @rahim")
    assert "example.com" not in t and "1712" not in t and "jane.doe.77" not in t and "rahim" not in t
    assert "[email]" in t and "[phone]" in t and "[profile link]" in t and "@user" in t


def test_scrub_keeps_years_and_prices():
    assert scrub("Sale in 2026, only 1000 BDT") == "Sale in 2026, only 1000 BDT"


def test_replace_ranges_utf16_offsets():
    # "😀 " is 3 UTF-16 units; the tagged name starts at utf16 offset 3
    assert replace_ranges("😀 John Smith thanks", [(3, 10)]) == "😀 @user thanks"


def test_url_helpers():
    assert normalize_url("m.facebook.com/SomePage") == "https://www.facebook.com/SomePage"
    assert is_single_post("https://www.facebook.com/SomePage/posts/pfbid0abc")
    assert not is_single_post("https://www.facebook.com/SomePage")


def test_graphql_collector_story_and_comment_without_authors():
    doc = {"data": {"node": {
        "__typename": "Story", "post_id": "111", "id": "S:111",
        "actors": [{"__typename": "User", "name": "Secret Name"}],
        "comet_sections": {
            "content": {"story": {"message": {"text": "Hello Dhaka with Ali Khan",
                                              "ranges": [{"offset": 17, "length": 8, "entity": {"__typename": "User"}}]}}},
            "metadata": [{"story": {"creation_time": 1760000000,
                                    "url": "https://www.facebook.com/page/posts/111"}}],
        },
        "feedback": {"reaction_count": {"count": 42}, "total_comment_count": 3},
        "interesting_top_level_comments": [{"comment": {
            "__typename": "Comment", "legacy_fbid": "c1", "created_time": 1760000100, "depth": 0,
            "author": {"name": "Another Secret"},
            "body": {"text": "Great post", "ranges": []}}}],
    }}}
    c = GraphQLCollector()
    c.feed("for (;;);" + json.dumps(doc))
    [s] = c.story_list()
    assert s["text"] == "Hello Dhaka with @user"
    assert s["created_at"] == 1760000000 and s["reactions"] == 42
    assert s["url"].endswith("/posts/111")
    [cm] = c.comments.values()
    assert cm["text"] == "Great post"
    assert c.comment_story[cm["ext_key"]] == "111"
    dumped = json.dumps([s, cm])
    assert "Secret" not in dumped


def test_retrieval_prefers_relevant_chunk():
    posts = [
        {"id": 1, "text": "New shoes arrived", "created_at": None, "reactions": 1,
         "comments": [{"text": "love the shoes"}]},
        {"id": 2, "text": "Delivery update", "created_at": None, "reactions": 1,
         "comments": [{"text": "delivery was late again"}] * 3},
    ]
    chunks = build_chunks(posts)
    scores = BM25([c["text"] for c in chunks]).scores("late delivery")
    assert scores[1] > scores[0]
    ctx, used, complete = select_context("late delivery", posts, budget_chars=len(chunks[1]["text"]) + 5)
    assert used == [2] and not complete
