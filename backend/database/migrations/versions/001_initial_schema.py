"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-05-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Leads
    op.create_table(
        'leads',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('state', sa.String(length=2), nullable=True),
        sa.Column('country', sa.String(length=2), server_default='US', nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=True),
        sa.Column('phone_type', sa.String(length=20), nullable=True),
        sa.Column('has_consent', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False),
        sa.Column('call_attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_called_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('dnc_flagged', sa.Boolean(), server_default=sa.text('FALSE'), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='new', nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone')
    )
    op.create_index('idx_leads_phone', 'leads', ['phone'])
    op.create_index('idx_leads_status', 'leads', ['status'])

    # Calls
    op.create_table(
        'calls',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('vicidial_call_id', sa.String(length=100), nullable=True),
        sa.Column('asterisk_channel', sa.String(length=200), nullable=True),
        sa.Column('direction', sa.String(length=20), server_default='outbound', nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('answered_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('ended_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('recording_path', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_calls_lead_id', 'calls', ['lead_id'])
    op.create_index('idx_calls_status', 'calls', ['status'])

    # Transcripts
    op.create_table(
        'transcripts',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('speaker', sa.String(length=10), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('fsm_state', sa.String(length=50), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('spoken_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_transcripts_call_id', 'transcripts', ['call_id'])

    # Qualification Answers
    op.create_table(
        'qualification_answers',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('question_key', sa.String(length=100), nullable=False),
        sa.Column('answer_value', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # AI Summaries
    op.create_table(
        'ai_summaries',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('summary_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id')
    )

    # Agent Transfers
    op.create_table(
        'agent_transfers',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', sa.String(length=100), nullable=True),
        sa.Column('transfer_status', sa.String(length=50), nullable=False),
        sa.Column('transfer_reason', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Internal DNC
    op.create_table(
        'internal_dnc',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        sa.Column('added_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone')
    )
    op.create_index('idx_internal_dnc_phone', 'internal_dnc', ['phone'])

    # DNC Check Log
    op.create_table(
        'dnc_check_log',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('check_source', sa.String(length=50), nullable=False),
        sa.Column('is_blocked', sa.Boolean(), nullable=False),
        sa.Column('checked_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Consent Records
    op.create_table(
        'consent_records',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('lead_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('consent_type', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('url_source', sa.String(length=500), nullable=True),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=True),
        sa.Column('call_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_logs_call_id', 'audit_logs', ['call_id'])

    # Knowledge Documents
    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('knowledge_documents')
    op.drop_table('audit_logs')
    op.drop_table('consent_records')
    op.drop_table('dnc_check_log')
    op.drop_table('internal_dnc')
    op.drop_table('agent_transfers')
    op.drop_table('ai_summaries')
    op.drop_table('qualification_answers')
    op.drop_table('transcripts')
    op.drop_table('calls')
    op.drop_table('leads')
