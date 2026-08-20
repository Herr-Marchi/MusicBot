from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from discord import Guild, Interaction, Member, VoiceClient, app_commands
from discord.ext import commands

from music_bot.adapters.inbound.discord.cogs.base import BaseCog
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies
from music_bot.adapters.inbound.discord.helpers import InteractionContext, begin_interaction
from music_bot.application.contracts.commands.music import PlayPlaylistCommand
from music_bot.application.contracts.results.music import PlayPlaylistResult
from music_bot.application.orchestration.playlists import PlaylistDetail
from music_bot.application.ports.playlists import PlaylistData, PlaylistTrackData
from music_bot.domain.playlists.models import PlaylistAccess

type AccessChoice = Literal["private", "public"]


class PlaylistCog(BaseCog, name="Playlist"):
    playlist_group = app_commands.Group(name="playlist", description="Manage playlists")

    def __init__(self, bot: commands.Bot, deps: DiscordDependencies) -> None:
        super().__init__(bot)
        self.deps: DiscordDependencies = deps

    async def _autocomplete_editable(
        self, interaction: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        playlists: Sequence[PlaylistData] = await self.deps.playlist_service.list_editable(
            user_id=interaction.user.id
        )
        return self._choices(playlists, current, guild=interaction.guild)

    async def _autocomplete_readable(
        self, interaction: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        playlists: Sequence[PlaylistData] = await self.deps.playlist_service.list_readable(
            user_id=interaction.user.id
        )
        return self._choices(playlists, current, guild=interaction.guild)

    @staticmethod
    def _choices(
        playlists: Sequence[PlaylistData],
        current: str,
        *,
        guild: Guild | None,
    ) -> list[app_commands.Choice[str]]:
        needle: str = current.lower()
        matches: list[PlaylistData] = [p for p in playlists if needle in p.title.lower()]
        choices: list[app_commands.Choice[str]] = []
        for playlist in matches[:25]:
            owner: Member | None = (
                guild.get_member(playlist.owner_id) if guild is not None else None
            )
            owner_label: str = owner.display_name if owner is not None else "unknown"
            label: str = f"{playlist.title} — {owner_label}"[:100]
            choices.append(app_commands.Choice(name=label, value=playlist.id))
        return choices

    @playlist_group.command(name="create", description="Create a new playlist")
    @app_commands.describe(title="Playlist title", access="Who can see and play this playlist")
    async def create(
        self,
        interaction: Interaction,
        title: str,
        access: AccessChoice,
    ) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        playlist: PlaylistData = await self.deps.playlist_service.create(
            owner_id=ctx.member.id,
            owner_username=ctx.member.name,
            title=title,
            access=PlaylistAccess(access),
        )
        await ctx.responder.success(f"Created playlist **{playlist.title}**.")

    @playlist_group.command(name="rename", description="Rename one of your playlists")
    @app_commands.describe(playlist="Playlist to rename", title="New title")
    @app_commands.autocomplete(playlist=_autocomplete_editable)
    async def rename(self, interaction: Interaction, playlist: str, title: str) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        updated: PlaylistData = await self.deps.playlist_service.rename(
            playlist_id=playlist,
            requested_by=ctx.member.id,
            title=title,
        )
        await ctx.responder.success(f"Renamed to **{updated.title}**.")

    @playlist_group.command(name="visibility", description="Change who can see a playlist")
    @app_commands.describe(playlist="Playlist to update", access="New visibility")
    @app_commands.autocomplete(playlist=_autocomplete_editable)
    async def visibility(
        self,
        interaction: Interaction,
        playlist: str,
        access: AccessChoice,
    ) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        updated: PlaylistData = await self.deps.playlist_service.set_access(
            playlist_id=playlist,
            requested_by=ctx.member.id,
            access=PlaylistAccess(access),
        )
        await ctx.responder.success(f"**{updated.title}** is now {updated.access.value}.")

    @playlist_group.command(name="delete", description="Delete one of your playlists")
    @app_commands.describe(playlist="Playlist to delete")
    @app_commands.autocomplete(playlist=_autocomplete_editable)
    async def delete(self, interaction: Interaction, playlist: str) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        await self.deps.playlist_service.delete(playlist_id=playlist, requested_by=ctx.member.id)
        await ctx.responder.success("Playlist deleted.")

    @playlist_group.command(name="mine", description="Show your playlists")
    async def list_mine(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        playlists: Sequence[PlaylistData] = await self.deps.playlist_service.list_editable(
            user_id=ctx.member.id
        )
        if not playlists:
            await ctx.responder.info("You don't have any playlists yet.")
            return

        lines: list[str] = [f"**{p.title}** — {p.access.value}" for p in playlists]
        await ctx.responder.info("\n".join(lines), title=f"Your playlists · {len(playlists)}")

    @playlist_group.command(name="show", description="Show a playlist's tracks")
    @app_commands.describe(playlist="Playlist to show")
    @app_commands.autocomplete(playlist=_autocomplete_readable)
    async def show(self, interaction: Interaction, playlist: str) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        detail: PlaylistDetail = await self.deps.playlist_service.get(
            playlist_id=playlist, requested_by=ctx.member.id
        )

        lines: list[str] = [
            f"{track.position + 1}. **{track.track.title}**" for track in detail.tracks
        ]
        body: str = "\n".join(lines) if lines else "This playlist is empty."
        await ctx.responder.info(
            body, title=f"{detail.playlist.title} · {len(detail.tracks)} track(s)"
        )

    @playlist_group.command(name="add", description="Add a track to a playlist, searched by name")
    @app_commands.describe(
        playlist="Playlist to add to",
        query="Song name, artist, or other search text — not a link",
    )
    @app_commands.autocomplete(playlist=_autocomplete_editable)
    async def add(self, interaction: Interaction, playlist: str, query: str) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        track: PlaylistTrackData = await self.deps.playlist_service.add_track(
            playlist_id=playlist,
            requested_by=ctx.member.id,
            url=query,
        )
        await ctx.responder.success(f"Added **{track.track.title}** to the playlist.")

    @playlist_group.command(name="remove", description="Remove a track from a playlist")
    @app_commands.describe(
        playlist="Playlist to remove from",
        position="Track position as shown in /playlist show",
    )
    @app_commands.autocomplete(playlist=_autocomplete_editable)
    async def remove(
        self,
        interaction: Interaction,
        playlist: str,
        position: app_commands.Range[int, 1],
    ) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        await self.deps.playlist_service.remove_track(
            playlist_id=playlist,
            requested_by=ctx.member.id,
            position=position - 1,
        )
        await ctx.responder.success("Track removed.")

    @playlist_group.command(name="play", description="Play all tracks from a playlist")
    @app_commands.describe(playlist="Playlist to play")
    @app_commands.autocomplete(playlist=_autocomplete_readable)
    async def play(self, interaction: Interaction, playlist: str) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        detail: PlaylistDetail = await self.deps.playlist_service.get(
            playlist_id=playlist, requested_by=ctx.member.id
        )
        if not detail.tracks:
            await ctx.responder.info("This playlist has no tracks.")
            return

        voice_client: VoiceClient = await self.deps.voice_manager.connect(
            guild=ctx.guild, member=ctx.member
        )

        outcome: PlayPlaylistResult = await self.deps.playback_manager.execute(
            PlayPlaylistCommand(
                guild_id=ctx.guild.id,
                requested_by=ctx.member.id,
                urls=[track.track.url for track in detail.tracks],
            )
        )

        await ctx.responder.success(f"Queued {outcome.queued_count} track(s) from the playlist.")
        if outcome.started_playing:
            await ctx.responder.announce(
                f"Playlist **{detail.playlist.title}**",
                channel=voice_client.channel,
                title="Now playing",
            )
