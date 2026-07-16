"""baseline 13 tables

Revision ID: 45661e74932a
Revises: a824f766c793
Create Date: 2026-07-16 17:16:59.162187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '45661e74932a'
down_revision: Union[str, Sequence[str], None] = 'a824f766c793'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('projects',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('genre', sa.String(100), nullable=False, server_default=''),
        sa.Column('author_note', sa.String(2000), nullable=False, server_default=''),
        sa.Column('default_pov', sa.String(100), nullable=False, server_default=''),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('project_documents',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False, server_default=''),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'kind', name='uq_project_document_kind')
    )
    op.create_table('chapters',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(200), nullable=False, server_default=''),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('chapter_versions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('chapter_id', sa.String(36), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False, server_default='manual'),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('note', sa.String(500), nullable=False, server_default=''),
        sa.Column('generation_candidate_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('providers',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False, server_default='openai_compatible'),
        sa.Column('base_url', sa.String(500), nullable=False, server_default=''),
        sa.Column('encrypted_api_key', sa.Text(), nullable=True),
        sa.Column('extra_headers_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('provider_models',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('provider_id', sa.String(36), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False, server_default=''),
        sa.Column('is_manual', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('prompt_profiles',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.String(2000), nullable=False, server_default=''),
        sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('prompt_versions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('profile_id', sa.String(36), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('system_template', sa.Text(), nullable=False, server_default=''),
        sa.Column('user_template', sa.Text(), nullable=False, server_default=''),
        sa.Column('output_mode', sa.String(50), nullable=False, server_default='structured'),
        sa.Column('output_schema_name', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['prompt_profiles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', 'version_number', name='uq_prompt_version_number')
    )
    op.create_table('workflow_profiles',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.String(2000), nullable=False, server_default=''),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workflow_step_configs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('workflow_profile_id', sa.String(36), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('provider_id', sa.String(36), nullable=True),
        sa.Column('model_id', sa.String(200), nullable=True),
        sa.Column('prompt_version_id', sa.String(36), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=False, server_default='0.7'),
        sa.Column('top_p', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('max_output_tokens', sa.Integer(), nullable=False, server_default='4096'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='120'),
        sa.ForeignKeyConstraint(['prompt_version_id'], ['prompt_versions.id']),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id']),
        sa.ForeignKeyConstraint(['workflow_profile_id'], ['workflow_profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('generation_runs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('chapter_id', sa.String(36), nullable=True),
        sa.Column('workflow_profile_id', sa.String(36), nullable=True),
        sa.Column('scene_instruction', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['workflow_profile_id'], ['workflow_profiles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('generation_steps',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('selected_candidate_id', sa.String(36), nullable=True),
        sa.Column('selected_issue_ids_json', sa.Text(), nullable=True),
        sa.Column('input_snapshot_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['generation_runs.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('generation_candidates',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('step_id', sa.String(36), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('provider_id', sa.String(36), nullable=True),
        sa.Column('model_id', sa.String(200), nullable=True),
        sa.Column('prompt_version_id', sa.String(36), nullable=True),
        sa.Column('parameters_json', sa.Text(), nullable=True),
        sa.Column('run_override', sa.Text(), nullable=False, server_default=''),
        sa.Column('rendered_system_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('rendered_user_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('raw_response', sa.Text(), nullable=False, server_default=''),
        sa.Column('parsed_output_json', sa.Text(), nullable=True),
        sa.Column('text_output', sa.Text(), nullable=False, server_default=''),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('is_selected', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['step_id'], ['generation_steps.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('generation_candidates')
    op.drop_table('generation_steps')
    op.drop_table('generation_runs')
    op.drop_table('workflow_step_configs')
    op.drop_table('workflow_profiles')
    op.drop_table('prompt_versions')
    op.drop_table('prompt_profiles')
    op.drop_table('provider_models')
    op.drop_table('providers')
    op.drop_table('chapter_versions')
    op.drop_table('chapters')
    op.drop_table('project_documents')
    op.drop_table('projects')
