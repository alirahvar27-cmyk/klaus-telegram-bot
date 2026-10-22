"""Helpers for keeping one forwarded media group together.

Telegram albums are represented by media_group_id. A forwarded album should be
processed as one logical post, never mixed with another forwarded post.
"""

def group_key(message):
    """Return a stable key for one incoming Telegram post/album."""
    media_group_id = message.get("media_group_id")
    if media_group_id:
        return "media_group:" + str(media_group_id)
    return "message:" + str(message.get("message_id", ""))


def append_group(groups, message):
    """Append a message to its own album bucket without mixing other groups."""
    key = group_key(message)
    groups.setdefault(key, []).append(message)
    return key
