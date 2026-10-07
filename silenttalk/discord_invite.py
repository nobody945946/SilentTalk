import discord

BOT_PERMISSIONS = discord.Permissions(
    view_channel=True,
    connect=True,
    speak=True,
    send_messages=True,
    read_message_history=True,
    add_reactions=True,
    create_public_threads=True,
    send_messages_in_threads=True,
)


def invite_url(application_id: int) -> str:
    """The link a server admin opens to add the bot (or, opened again, to
    give a bot already there what BOT_PERMISSIONS has gained since)."""
    return discord.utils.oauth_url(
        application_id, permissions=BOT_PERMISSIONS, scopes=("bot",)
    )
