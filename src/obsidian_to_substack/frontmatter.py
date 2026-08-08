"""Parse YAML frontmatter from Obsidian Markdown files."""

import re
import logging

import yaml

logger = logging.getLogger(__name__)

FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and return (metadata, body).

    If no frontmatter is found or YAML is malformed, returns ({}, text).
    """
    match = FRONTMATTER_PATTERN.match(text)
    if match is None:
        return {}, text

    yaml_block = match.group(1)
    body = text[match.end():]

    try:
        metadata = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        logger.warning("Malformed YAML frontmatter, treating as body text: %s", exc)
        return {}, text

    if not isinstance(metadata, dict):
        logger.warning("Frontmatter parsed to non-dict type (%s), ignoring", type(metadata).__name__)
        return {}, text

    return metadata, body
