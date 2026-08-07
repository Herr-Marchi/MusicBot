from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

playlist_access = postgresql.ENUM(
    "PRIVATE",
    "PUBLIC",
    name="playlistaccess",
    create_type=False,
)


def upgrade() -> None:
    playlist_access.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "discord_users",
        sa.Column("discord_user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("discord_user_id", name="pk_discord_users"),
    )

    op.create_table(
        "tracks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tracks"),
        sa.UniqueConstraint("url", name="uq_tracks_url"),
    )

    op.create_table(
        "playlists",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("access", playlist_access, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["discord_users.discord_user_id"],
            name="fk_playlists_owner_id_discord_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playlists"),
        sa.UniqueConstraint("owner_id", "title", name="uq_playlists_owner_id_title"),
    )

    op.create_table(
        "playlist_tracks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("playlist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["playlist_id"],
            ["playlists.id"],
            name="fk_playlist_tracks_playlist_id_playlists",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["tracks.id"],
            name="fk_playlist_tracks_track_id_tracks",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playlist_tracks"),
        sa.UniqueConstraint(
            "playlist_id",
            "position",
            name="uq_playlist_tracks_playlist_id_position",
        ),
    )
    op.create_index(
        "ix_playlist_tracks_track_id",
        "playlist_tracks",
        ["track_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("playlist_tracks")
    op.drop_table("playlists")
    op.drop_table("tracks")
    op.drop_table("discord_users")

    playlist_access.drop(op.get_bind(), checkfirst=True)
