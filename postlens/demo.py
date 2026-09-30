"""A small made-up dataset so people can try the app (and the AI) without
connecting Facebook. All text is invented for demonstration."""
from __future__ import annotations

import random
import time

from . import db
from .anonymize import key

POSTS = [
    ("We're excited to announce our new delivery service now covers all of Dhaka! Orders above 1000 BDT ship free. 🚚",
     ["Finally! Been waiting for this", "Does it cover Savar too?", "Free shipping is a great move",
      "Last order took 5 days, hope this is faster", "@user look at this", "Great news, will order tonight",
      "What about Chattogram?", "Delivery charge was the only reason I didn't order before"]),
    ("Our customer support hours are changing. From next week we'll be available 9am–11pm every day.",
     ["Thank you, late night support helps a lot", "Please add live chat on the website",
      "Called yesterday and nobody answered", "Good improvement", "Will support be available on Friday?"]),
    ("Flash sale this weekend: 30% off all skincare products. Limited stock!",
     ["Is the sunscreen included?", "Prices went up last month, so 30% off is just the old price",
      "Ordered 3 items already 😍", "Website crashed during the last sale, please fix it",
      "Is this for original products?", "Love the moisturizer, buying again", "Stock ran out in 10 minutes last time",
      "Please restock the vitamin C serum", "Why no cash on delivery for sale items?"]),
    ("We heard your feedback about late deliveries. We've added two new warehouses and hired 40 more riders.",
     ["Appreciate the transparency", "My last two orders were on time, good job", "Still waiting for order from last week",
      "Hope it lasts", "Rider was very polite", "Packaging was damaged on my last order"]),
    ("Which product should we bring back next? Comment below!",
     ["The rose water toner!", "Vitamin C serum please", "Aloe gel", "Rose water toner, it was the best",
      "Charcoal face wash", "Vitamin C serum 100%", "Please bring back the travel size bottles",
      "Rose water toner!!", "Lip balm pack"]),
    ("Meet our team! Our warehouse staff work around the clock to get your orders packed with care. ❤️",
     ["Respect to the team", "Hardworking people", "Pay them well!", "Nice to see the faces behind the brand"]),
]


def create_demo() -> int:
    ds = db.create_dataset("https://www.facebook.com/example-demo-page", 30)
    db.update_dataset(ds, title="Demo Store (sample data)")
    now = time.time()
    rnd = random.Random(7)
    for i, (text, comments) in enumerate(POSTS):
        created = now - (i * 4 + 1) * 86400 - rnd.randint(0, 40000)
        pid = db.upsert_post(ds, {
            "ext_key": key("demo", i), "text": text, "created_at": created,
            "reactions": rnd.randint(40, 900), "shares": rnd.randint(0, 60),
            "comment_total": len(comments) + rnd.randint(0, 12),
        })
        db.add_comments(pid, [
            {"ext_key": key("demo-c", i, j), "text": c, "created_at": created + rnd.randint(300, 200000),
             "reactions": rnd.randint(0, 25), "is_reply": j % 5 == 4}
            for j, c in enumerate(comments)
        ])
    from .ai import index
    index.build_index(ds)
    db.update_dataset(ds, status="done", finished_at=time.time())
    return ds
