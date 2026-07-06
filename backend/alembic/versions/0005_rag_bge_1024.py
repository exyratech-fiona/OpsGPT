"""RAG embeddings: doc_chunks vector 768 -> 1024 (nomic -> BGE-large-en-v1.5)

Existing 768-dim vectors are incompatible with the 1024-dim model, so they are
dropped to NULL here; the chunk TEXT is preserved and re-embedded with BGE right
after this migration by a one-off re-embed step.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_doc_chunks_embedding")
    # the column is NOT NULL; allow NULL so we can clear the incompatible 768-dim
    # vectors (chunk text is kept and re-embedded to 1024-dim right after).
    op.execute("ALTER TABLE doc_chunks ALTER COLUMN embedding DROP NOT NULL")
    op.execute("ALTER TABLE doc_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.execute(
        "CREATE INDEX ix_doc_chunks_embedding ON doc_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_doc_chunks_embedding")
    op.execute("ALTER TABLE doc_chunks ALTER COLUMN embedding TYPE vector(768) USING NULL")
    op.execute(
        "CREATE INDEX ix_doc_chunks_embedding ON doc_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
