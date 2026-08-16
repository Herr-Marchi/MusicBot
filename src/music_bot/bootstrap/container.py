from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass

from discord import Intents
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.adapters.inbound.discord.bot import MusicBot
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies
from music_bot.adapters.inbound.discord.voice_manager import DiscordVoiceManager
from music_bot.adapters.outbound.discord_player import DiscordGuildPlayerFactory
from music_bot.adapters.outbound.postgres import (
    PostgresTrackCatalog,
    create_engine,
    create_session_factory,
)
from music_bot.adapters.outbound.redis import RedisGuildPlaybackRepository, create_redis_client
from music_bot.adapters.outbound.yt_dlp import YtDlpTrackSource
from music_bot.application.orchestration.music import (
    GuildPlaybackActorManager,
    GuildPlaybackActorRegistry,
)
from music_bot.application.orchestration.track_metadata_resolver import (
    CatalogBackedTrackMetadataResolver,
)
from music_bot.application.ports.music import GuildPlaybackRepository
from music_bot.application.ports.music_player import GuildPlayerFactory
from music_bot.application.ports.track_catalog import TrackCatalog
from music_bot.application.ports.track_source import TrackMetadataResolver, TrackSource

from .settings import Settings


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    postgres_engine: AsyncEngine
    redis_client: Redis
    playback_repository: GuildPlaybackRepository
    track_source: TrackSource
    playback_manager: GuildPlaybackActorManager
    discord_bot: MusicBot
    _exit_stack: AsyncExitStack

    @classmethod
    def create(cls, *, settings: Settings) -> Container:
        postgres_engine: AsyncEngine = cls._create_postgres_engine(settings=settings)
        postgres_session_factory: async_sessionmaker[AsyncSession] = (
            cls._create_postgres_session_factory(engine=postgres_engine)
        )

        redis_client: Redis = cls._create_redis_client(settings=settings)
        playback_repository: GuildPlaybackRepository = cls._create_playback_repository(
            client=redis_client,
            settings=settings,
        )
        track_source: TrackSource = cls._create_track_source()
        track_catalog: TrackCatalog = cls._create_track_catalog(
            session_factory=postgres_session_factory
        )
        catalog_backed_metadata_resolver: TrackMetadataResolver = (
            cls._create_catalog_backed_metadata_resolver(inner=track_source, catalog=track_catalog)
        )

        voice_client_lookup: VoiceClientLookup = cls._create_voice_client_lookup()
        voice_manager: DiscordVoiceManager = cls._create_voice_manager(lookup=voice_client_lookup)
        player_factory: GuildPlayerFactory = cls._create_player_factory(
            voice_client_lookup=voice_client_lookup,
            stream_resolver=track_source,
        )
        playback_actors: GuildPlaybackActorRegistry = cls._create_playback_actors(
            playback_repository=playback_repository,
            player_factory=player_factory,
            metadata_resolver=catalog_backed_metadata_resolver,
        )
        playback_manager: GuildPlaybackActorManager = cls._create_playback_manager(
            playback_actors=playback_actors
        )
        discord_dependencies: DiscordDependencies = cls._create_discord_dependencies(
            playback_manager=playback_manager,
            voice_manager=voice_manager,
        )
        discord_bot: MusicBot = cls._create_discord_bot(
            settings=settings,
            dependencies=discord_dependencies,
            voice_client_lookup=voice_client_lookup,
        )
        exit_stack: AsyncExitStack = cls._create_exit_stack(
            postgres_engine=postgres_engine,
            redis_client=redis_client,
            playback_manager=playback_manager,
            discord_bot=discord_bot,
        )

        return cls(
            settings=settings,
            postgres_engine=postgres_engine,
            redis_client=redis_client,
            playback_repository=playback_repository,
            track_source=track_source,
            playback_manager=playback_manager,
            discord_bot=discord_bot,
            _exit_stack=exit_stack,
        )

    @staticmethod
    def _create_postgres_engine(*, settings: Settings) -> AsyncEngine:
        return create_engine(database_url=str(settings.database_url))

    @staticmethod
    def _create_postgres_session_factory(
        *, engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        return create_session_factory(engine=engine)

    @staticmethod
    def _create_redis_client(*, settings: Settings) -> Redis:
        return create_redis_client(database_url=str(settings.redis_url))

    @staticmethod
    def _create_playback_repository(
        *,
        client: Redis,
        settings: Settings,
    ) -> RedisGuildPlaybackRepository:
        return RedisGuildPlaybackRepository(
            client=client,
            ttl_seconds=settings.redis_playback_ttl_seconds,
        )

    @staticmethod
    def _create_voice_client_lookup() -> VoiceClientLookup:
        return VoiceClientLookup()

    @staticmethod
    def _create_voice_manager(*, lookup: VoiceClientLookup) -> DiscordVoiceManager:
        return DiscordVoiceManager(lookup=lookup)

    @staticmethod
    def _create_track_source() -> YtDlpTrackSource:
        return YtDlpTrackSource()

    @staticmethod
    def _create_track_catalog(
        *, session_factory: async_sessionmaker[AsyncSession]
    ) -> PostgresTrackCatalog:
        return PostgresTrackCatalog(session_factory=session_factory)

    @staticmethod
    def _create_catalog_backed_metadata_resolver(
        *,
        inner: TrackMetadataResolver,
        catalog: TrackCatalog,
    ) -> CatalogBackedTrackMetadataResolver:
        return CatalogBackedTrackMetadataResolver(inner=inner, catalog=catalog)

    @staticmethod
    def _create_player_factory(
        *,
        voice_client_lookup: VoiceClientLookup,
        stream_resolver: TrackSource,
    ) -> DiscordGuildPlayerFactory:
        return DiscordGuildPlayerFactory(
            stream_resolver=stream_resolver,
            voice_client_lookup=voice_client_lookup,
        )

    @staticmethod
    def _create_playback_actors(
        *,
        playback_repository: GuildPlaybackRepository,
        player_factory: GuildPlayerFactory,
        metadata_resolver: TrackMetadataResolver,
    ) -> GuildPlaybackActorRegistry:
        return GuildPlaybackActorRegistry(
            playback_repository=playback_repository,
            player_factory=player_factory,
            metadata_resolver=metadata_resolver,
        )

    @staticmethod
    def _create_playback_manager(
        *,
        playback_actors: GuildPlaybackActorRegistry,
    ) -> GuildPlaybackActorManager:
        return GuildPlaybackActorManager(actors=playback_actors)

    @staticmethod
    def _create_discord_dependencies(
        *,
        playback_manager: GuildPlaybackActorManager,
        voice_manager: DiscordVoiceManager,
    ) -> DiscordDependencies:
        return DiscordDependencies(
            voice_manager=voice_manager,
            playback_manager=playback_manager,
        )

    @staticmethod
    def _create_discord_bot(
        *,
        settings: Settings,
        dependencies: DiscordDependencies,
        voice_client_lookup: VoiceClientLookup,
    ) -> MusicBot:
        return MusicBot(
            intents=Intents.default(),
            dependencies=dependencies,
            voice_client_lookup=voice_client_lookup,
            dev_guild_id=settings.discord_guild_id,
        )

    @staticmethod
    def _create_exit_stack(
        *,
        postgres_engine: AsyncEngine,
        redis_client: Redis,
        playback_manager: GuildPlaybackActorManager,
        discord_bot: MusicBot,
    ) -> AsyncExitStack:
        exit_stack: AsyncExitStack = AsyncExitStack()
        exit_stack.push_async_callback(postgres_engine.dispose)
        exit_stack.push_async_callback(redis_client.aclose)
        exit_stack.push_async_callback(playback_manager.shutdown)
        exit_stack.push_async_callback(discord_bot.close)
        return exit_stack

    async def start(self) -> None:
        token: str = self.settings.discord_token.get_secret_value()
        await self.discord_bot.start(token)

    async def close(self) -> None:
        await self._exit_stack.aclose()
