import re
from typing import Protocol


class SlugCollection(Protocol):
    def find_one(self, filter: dict):
        ...


_slug_pattern = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _slug_pattern.sub("-", value.lower()).strip("-")
    return slug or "link"


def unique_slug(collection: SlugCollection, base_slug: str) -> str:
    root = slugify(base_slug)
    slug = root
    suffix = 2

    while collection.find_one({"slug": slug}):
        slug = f"{root}-{suffix}"
        suffix += 1

    return slug
