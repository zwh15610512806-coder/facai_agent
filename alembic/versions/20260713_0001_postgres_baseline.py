"""postgres baseline and integration control

Revision ID: 20260713_0001
Revises:
Create Date: 2026-07-13 18:47:05.068214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260713_0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ai_interface_settings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('interface_key', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('max_tokens', sa.Integer(), nullable=False),
    sa.Column('api_key_secret', sa.Text(), nullable=True),
    sa.Column('base_url_override', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_interface_settings_interface_key'), 'ai_interface_settings', ['interface_key'], unique=True)
    op.create_table('ai_usage_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('interface_key', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('total_tokens', sa.Integer(), nullable=False),
    sa.Column('usage_source', sa.String(length=20), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('actor_name', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_usage_records_actor_name'), 'ai_usage_records', ['actor_name'], unique=False)
    op.create_index(op.f('ix_ai_usage_records_created_at'), 'ai_usage_records', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_usage_records_interface_key'), 'ai_usage_records', ['interface_key'], unique=False)
    op.create_index(op.f('ix_ai_usage_records_provider'), 'ai_usage_records', ['provider'], unique=False)
    op.create_index(op.f('ix_ai_usage_records_status'), 'ai_usage_records', ['status'], unique=False)
    op.create_table('audit_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('actor_name', sa.String(length=100), nullable=False),
    sa.Column('actor_role', sa.String(length=30), nullable=False),
    sa.Column('auth_source', sa.String(length=30), nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('path', sa.String(length=500), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('client_ip', sa.String(length=100), nullable=True),
    sa.Column('request_id', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_actor_name'), 'audit_events', ['actor_name'], unique=False)
    op.create_index(op.f('ix_audit_events_actor_role'), 'audit_events', ['actor_role'], unique=False)
    op.create_index(op.f('ix_audit_events_created_at'), 'audit_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_events_path'), 'audit_events', ['path'], unique=False)
    op.create_index(op.f('ix_audit_events_request_id'), 'audit_events', ['request_id'], unique=False)
    op.create_table('durable_tasks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('task_type', sa.String(length=100), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
    sa.Column('lease_until', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_durable_tasks_created_at'), 'durable_tasks', ['created_at'], unique=False)
    op.create_index(op.f('ix_durable_tasks_lease_until'), 'durable_tasks', ['lease_until'], unique=False)
    op.create_index(op.f('ix_durable_tasks_next_attempt_at'), 'durable_tasks', ['next_attempt_at'], unique=False)
    op.create_index(op.f('ix_durable_tasks_status'), 'durable_tasks', ['status'], unique=False)
    op.create_index(op.f('ix_durable_tasks_task_type'), 'durable_tasks', ['task_type'], unique=False)
    op.create_table('bd_members',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name='ck_bd_members_name_nonblank'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_bd_members_active'), 'bd_members', ['active'], unique=False)
    op.create_table('creator_import_batches',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('source_type', sa.String(length=50), nullable=False),
    sa.Column('filename', sa.String(length=500), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('mapping', sa.JSON(), nullable=False),
    sa.Column('errors', sa.JSON(), nullable=False),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('imported_count', sa.Integer(), nullable=False),
    sa.Column('updated_count', sa.Integer(), nullable=False),
    sa.Column('skipped_count', sa.Integer(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('committed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index('ix_creator_import_batch_file_lookup', 'creator_import_batches', ['kind', 'file_sha256', 'status'], unique=False)
    op.create_index('uq_creator_import_committed_file', 'creator_import_batches', ['kind', 'file_sha256'], unique=True, sqlite_where=sa.text("status = 'committed'"), postgresql_where=sa.text("status = 'committed'"))
    op.create_table('integration_app_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('provider', sa.Enum('qianchuan', 'doudian', 'taobao', 'pdd', name='ck_integration_app_configs_provider', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('app_id', sa.String(length=255), nullable=False),
    sa.Column('app_secret_ciphertext', sa.Text(), nullable=True),
    sa.Column('app_secret_tail', sa.String(length=4), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', name='uq_integration_app_configs_provider')
    )
    op.create_index('ix_integration_app_configs_status', 'integration_app_configs', ['status'], unique=False)
    op.create_table('integration_authorizations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('provider', sa.Enum('qianchuan', 'doudian', 'taobao', 'pdd', name='ck_integration_authorizations_provider', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('external_subject_id', sa.String(length=255), nullable=False),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('access_token_ciphertext', sa.Text(), nullable=False),
    sa.Column('access_token_tail', sa.String(length=4), nullable=False),
    sa.Column('refresh_token_ciphertext', sa.Text(), nullable=True),
    sa.Column('refresh_token_tail', sa.String(length=4), nullable=True),
    sa.Column('access_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refresh_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('refresh_lease_owner', sa.String(length=255), nullable=True),
    sa.Column('refresh_lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('active', 'reauthorization_required', 'revoked', 'disabled', name='ck_integration_authorizations_status', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('last_authorized_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_refreshed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'provider', name='uq_integration_authorizations_id_provider'),
    sa.UniqueConstraint('provider', 'external_subject_id', name='uq_integration_authorizations_provider_external_subject_id')
    )
    op.create_index('ix_integration_authorizations_refresh_lease_expires_at', 'integration_authorizations', ['refresh_lease_expires_at'], unique=False)
    op.create_index('ix_integration_authorizations_status', 'integration_authorizations', ['status'], unique=False)
    op.create_table('integration_login_throttles',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source_digest', sa.String(length=64), nullable=False),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_digest', name='uq_integration_login_throttles_source_digest')
    )
    op.create_index('ix_integration_login_throttles_locked_until', 'integration_login_throttles', ['locked_until'], unique=False)
    op.create_table('integration_oauth_states',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('state_hash', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.Enum('qianchuan', 'doudian', 'taobao', 'pdd', name='ck_integration_oauth_states_provider', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('initiating_session_digest', sa.String(length=64), nullable=False),
    sa.Column('return_path', sa.String(length=2048), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(return_path = '/app/api-connections' OR return_path LIKE '/app/api-connections/_%') AND return_path NOT LIKE '%?%' AND return_path NOT LIKE '%#%' AND return_path NOT LIKE '%//%' AND return_path NOT LIKE '%/../%' AND return_path NOT LIKE '%/..' AND return_path NOT LIKE '%/./%' AND return_path NOT LIKE '%/.' AND replace(return_path, '\\', '') = return_path AND replace(return_path, '%', '') = return_path", name='ck_integration_oauth_states_return_path'),
    sa.CheckConstraint('length(state_hash) = 64', name='ck_integration_oauth_states_state_hash_length'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('state_hash', name='uq_integration_oauth_states_state_hash')
    )
    op.create_index('ix_integration_oauth_states_expires_at', 'integration_oauth_states', ['expires_at'], unique=False)
    op.create_table('integration_security_audit',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('outcome', sa.String(length=32), nullable=False),
    sa.Column('source_digest', sa.String(length=64), nullable=True),
    sa.Column('session_digest', sa.String(length=64), nullable=True),
    sa.Column('provider', sa.Enum('qianchuan', 'doudian', 'taobao', 'pdd', name='ck_integration_security_audit_provider', native_enum=False, create_constraint=True), nullable=True),
    sa.Column('target_type', sa.String(length=100), nullable=True),
    sa.Column('target_id', sa.String(length=255), nullable=True),
    sa.Column('summary_code', sa.String(length=100), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_integration_security_audit_created_at', 'integration_security_audit', ['created_at'], unique=False)
    op.create_index('ix_integration_security_audit_provider_event_type', 'integration_security_audit', ['provider', 'event_type'], unique=False)
    op.create_table('job_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('job_type', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('progress_current', sa.Integer(), nullable=False),
    sa.Column('progress_total', sa.Integer(), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_runs_job_type'), 'job_runs', ['job_type'], unique=False)
    op.create_index(op.f('ix_job_runs_status'), 'job_runs', ['status'], unique=False)
    op.create_table('product_rag_query_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('scope', sa.String(length=30), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('policy', sa.JSON(), nullable=True),
    sa.Column('retrieval_mode', sa.String(length=120), nullable=False),
    sa.Column('hit_chunks', sa.JSON(), nullable=True),
    sa.Column('final_product_ids', sa.JSON(), nullable=True),
    sa.Column('excluded_product_ids', sa.JSON(), nullable=True),
    sa.Column('degraded_reason', sa.Text(), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('pipeline_version', sa.String(length=50), nullable=False),
    sa.Column('index_version', sa.String(length=100), nullable=False),
    sa.Column('query_plan', sa.JSON(), nullable=True),
    sa.Column('candidate_trace', sa.JSON(), nullable=True),
    sa.Column('selected_evidence', sa.JSON(), nullable=True),
    sa.Column('rerank_status', sa.String(length=30), nullable=False),
    sa.Column('answer_mode', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_product_rag_query_logs_created_at'), 'product_rag_query_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_product_rag_query_logs_product_id'), 'product_rag_query_logs', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_rag_query_logs_scope'), 'product_rag_query_logs', ['scope'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False, comment='产品名称'),
    sa.Column('category', sa.String(length=100), nullable=False, comment='品类'),
    sa.Column('price', sa.Float(), nullable=False, comment='售价'),
    sa.Column('original_price', sa.Float(), nullable=True, comment='原价'),
    sa.Column('commission_rate', sa.Float(), nullable=True, comment='佣金比例(%)'),
    sa.Column('brand', sa.String(length=100), nullable=True, comment='品牌'),
    sa.Column('description', sa.Text(), nullable=True, comment='产品描述'),
    sa.Column('image_url', sa.String(length=500), nullable=True, comment='产品图片URL'),
    sa.Column('info_file', sa.String(length=500), nullable=True, comment='产品资料文件路径'),
    sa.Column('status', sa.String(length=20), nullable=True, comment='状态: active/inactive'),
    sa.Column('pending_fields', sa.JSON(), nullable=True, comment='pending product fields'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_products_category'), 'products', ['category'], unique=False)
    op.create_table('qianchuan_import_batches',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('filename', sa.String(length=500), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('imported_count', sa.Integer(), nullable=True),
    sa.Column('skipped_count', sa.Integer(), nullable=True),
    sa.Column('amount_field', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_qianchuan_import_batches_file_sha256'), 'qianchuan_import_batches', ['file_sha256'], unique=True)
    op.create_table('reference_scripts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True, comment='标题'),
    sa.Column('video_url', sa.String(length=500), nullable=True, comment='视频链接'),
    sa.Column('script_content', sa.Text(), nullable=False, comment='脚本内容'),
    sa.Column('video_type', sa.String(length=100), nullable=True, comment='视频类型'),
    sa.Column('tags', sa.String(length=200), nullable=True, comment='标签'),
    sa.Column('notes', sa.Text(), nullable=True, comment='备注/亮点'),
    sa.Column('is_high_conversion', sa.Integer(), nullable=True, comment='高成交标记'),
    sa.Column('embedding_id', sa.String(length=200), nullable=True, comment='ChromaDB向量ID'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('script_templates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False, comment='模板名称'),
    sa.Column('video_type', sa.String(length=100), nullable=False, comment='视频类型'),
    sa.Column('structure', sa.JSON(), nullable=False, comment='脚本结构定义'),
    sa.Column('hook_templates', sa.JSON(), nullable=True, comment='黄金开头模板列表'),
    sa.Column('cta_templates', sa.JSON(), nullable=True, comment='转化话术模板列表'),
    sa.Column('duration_range', sa.String(length=50), nullable=True, comment='建议时长'),
    sa.Column('description', sa.Text(), nullable=True, comment='模板描述'),
    sa.Column('example_script', sa.Text(), nullable=True, comment='示例脚本'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_script_templates_video_type'), 'script_templates', ['video_type'], unique=False)
    op.create_table('vector_index_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('collection_name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('embedding_model', sa.String(length=200), nullable=True),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('activated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('collection_name')
    )
    op.create_index(op.f('ix_vector_index_versions_entity_type'), 'vector_index_versions', ['entity_type'], unique=False)
    op.create_index(op.f('ix_vector_index_versions_status'), 'vector_index_versions', ['status'], unique=False)
    op.create_table('vector_sync_jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('operation', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vector_sync_jobs_entity_id'), 'vector_sync_jobs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_vector_sync_jobs_entity_type'), 'vector_sync_jobs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_vector_sync_jobs_next_attempt_at'), 'vector_sync_jobs', ['next_attempt_at'], unique=False)
    op.create_index(op.f('ix_vector_sync_jobs_status'), 'vector_sync_jobs', ['status'], unique=False)
    op.create_table('viral_scripts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True, comment='品类'),
    sa.Column('video_type', sa.String(length=100), nullable=True, comment='视频类型'),
    sa.Column('title', sa.String(length=300), nullable=False, comment='脚本标题'),
    sa.Column('script_content', sa.Text(), nullable=False, comment='完整脚本内容'),
    sa.Column('performance_data', sa.JSON(), nullable=True, comment='跑量数据'),
    sa.Column('tags', sa.String(length=500), nullable=True, comment='标签(逗号分隔)'),
    sa.Column('embedding_id', sa.String(length=200), nullable=True, comment='ChromaDB向量ID'),
    sa.Column('is_high_conversion', sa.Integer(), nullable=True, comment='是否高成交：1=是 0=否'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_viral_scripts_category'), 'viral_scripts', ['category'], unique=False)
    op.create_index(op.f('ix_viral_scripts_video_type'), 'viral_scripts', ['video_type'], unique=False)
    op.create_table('creators',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('platform', sa.String(length=30), nullable=False),
    sa.Column('platform_uid', sa.String(length=200), nullable=True),
    sa.Column('platform_uid_normalized', sa.String(length=200), nullable=True),
    sa.Column('douyin_handle', sa.String(length=200), nullable=True),
    sa.Column('douyin_handle_normalized', sa.String(length=200), nullable=True),
    sa.Column('nickname', sa.String(length=200), nullable=False),
    sa.Column('homepage_url', sa.String(length=1000), nullable=True),
    sa.Column('avatar_url', sa.String(length=1000), nullable=True),
    sa.Column('mcn_name', sa.String(length=200), nullable=True),
    sa.Column('contact_name', sa.String(length=100), nullable=True),
    sa.Column('contact_phone', sa.String(length=50), nullable=True),
    sa.Column('wechat_id', sa.String(length=100), nullable=True),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('stage', sa.String(length=30), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("stage IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')", name='ck_creators_stage'),
    sa.CheckConstraint('(platform_uid_normalized IS NOT NULL AND length(trim(platform_uid_normalized)) > 0) OR (douyin_handle_normalized IS NOT NULL AND length(trim(douyin_handle_normalized)) > 0)', name='ck_creators_identity_present'),
    sa.ForeignKeyConstraint(['owner_id'], ['bd_members.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_creators_archived_at'), 'creators', ['archived_at'], unique=False)
    op.create_index(op.f('ix_creators_nickname'), 'creators', ['nickname'], unique=False)
    op.create_index(op.f('ix_creators_owner_id'), 'creators', ['owner_id'], unique=False)
    op.create_index(op.f('ix_creators_stage'), 'creators', ['stage'], unique=False)
    op.create_index('ix_creators_stage_owner_archived', 'creators', ['stage', 'owner_id', 'archived_at'], unique=False)
    op.create_index('uq_creators_douyin_handle', 'creators', ['platform', 'douyin_handle_normalized'], unique=True, sqlite_where=sa.text('douyin_handle_normalized IS NOT NULL'), postgresql_where=sa.text('douyin_handle_normalized IS NOT NULL'))
    op.create_index('uq_creators_platform_uid', 'creators', ['platform', 'platform_uid_normalized'], unique=True, sqlite_where=sa.text('platform_uid_normalized IS NOT NULL'), postgresql_where=sa.text('platform_uid_normalized IS NOT NULL'))
    op.create_table('generated_scripts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('template_id', sa.Integer(), nullable=True),
    sa.Column('source_script_id', sa.Integer(), nullable=True, comment='具体参考脚本ID'),
    sa.Column('source_script_source', sa.String(length=20), nullable=True, comment='具体参考脚本来源：facai/other'),
    sa.Column('source_script_title', sa.String(length=300), nullable=True, comment='具体参考脚本标题快照'),
    sa.Column('source_script_content', sa.Text(), nullable=True, comment='具体参考脚本内容快照'),
    sa.Column('script_content', sa.Text(), nullable=False, comment='生成的脚本内容'),
    sa.Column('video_type', sa.String(length=100), nullable=True, comment='视频类型'),
    sa.Column('ai_model', sa.String(length=100), nullable=True, comment='使用的AI模型'),
    sa.Column('is_high_conversion', sa.Integer(), nullable=True, comment='是否高成交：1=是 0=否'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['template_id'], ['script_templates.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('integration_connections',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('authorization_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.Enum('qianchuan', 'doudian', 'taobao', 'pdd', name='ck_integration_connections_provider', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('connection_type', sa.Enum('shop', 'ad_account', name='ck_integration_connections_connection_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('external_account_id', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('status', sa.Enum('setup_required', 'authorizing', 'active', 'permission_limited', 'syncing', 'degraded', 'reauthorization_required', 'disabled', name='ck_integration_connections_status', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('capability_report', sa.JSON(), nullable=False),
    sa.Column('earliest_available_date', sa.Date(), nullable=True),
    sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['authorization_id', 'provider'], ['integration_authorizations.id', 'integration_authorizations.provider'], name='fk_integration_connections_authorization_provider', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'connection_type', 'external_account_id', name='uq_integration_connections_provider_type_external_account')
    )
    op.create_index('ix_integration_connections_authorization_id', 'integration_connections', ['authorization_id'], unique=False)
    op.create_index('ix_integration_connections_provider_status', 'integration_connections', ['provider', 'status'], unique=False)
    op.create_table('product_rag_feedbacks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('query_log_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.String(length=10), nullable=False),
    sa.Column('reason', sa.String(length=30), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['query_log_id'], ['product_rag_query_logs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('query_log_id', name='uq_product_rag_feedback_query')
    )
    op.create_index(op.f('ix_product_rag_feedbacks_query_log_id'), 'product_rag_feedbacks', ['query_log_id'], unique=False)
    op.create_table('qianchuan_material_performance',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('batch_id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.String(length=100), nullable=False),
    sa.Column('material_name', sa.String(length=500), nullable=False),
    sa.Column('material_evaluation', sa.String(length=200), nullable=True),
    sa.Column('material_duration', sa.String(length=50), nullable=True),
    sa.Column('material_created_time', sa.String(length=50), nullable=True),
    sa.Column('material_source', sa.String(length=100), nullable=True),
    sa.Column('tags', sa.String(length=500), nullable=True),
    sa.Column('amount_field', sa.String(length=100), nullable=True),
    sa.Column('transaction_amount', sa.Float(), nullable=True),
    sa.Column('order_count', sa.Integer(), nullable=True),
    sa.Column('user_pay_amount', sa.Float(), nullable=True),
    sa.Column('roi', sa.Float(), nullable=True),
    sa.Column('impressions', sa.Integer(), nullable=True),
    sa.Column('ctr', sa.Float(), nullable=True),
    sa.Column('spend', sa.Float(), nullable=True),
    sa.Column('clicks', sa.Integer(), nullable=True),
    sa.Column('cvr', sa.Float(), nullable=True),
    sa.Column('play_3s_rate', sa.Float(), nullable=True),
    sa.Column('play_10s_rate', sa.Float(), nullable=True),
    sa.Column('avg_watch_seconds', sa.Float(), nullable=True),
    sa.Column('completion_rate', sa.Float(), nullable=True),
    sa.Column('plan_count', sa.Integer(), nullable=True),
    sa.Column('product_count', sa.Integer(), nullable=True),
    sa.Column('raw_data', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['batch_id'], ['qianchuan_import_batches.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('batch_id', 'material_id', name='uq_qianchuan_batch_material')
    )
    op.create_index(op.f('ix_qianchuan_material_performance_batch_id'), 'qianchuan_material_performance', ['batch_id'], unique=False)
    op.create_index(op.f('ix_qianchuan_material_performance_material_id'), 'qianchuan_material_performance', ['material_id'], unique=False)
    op.create_index(op.f('ix_qianchuan_material_performance_material_name'), 'qianchuan_material_performance', ['material_name'], unique=False)
    op.create_table('qianchuan_script_bindings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('script_id', sa.Integer(), nullable=False),
    sa.Column('material_id', sa.String(length=100), nullable=False),
    sa.Column('material_name', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['script_id'], ['viral_scripts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('script_id', 'material_id', name='uq_qianchuan_script_material')
    )
    op.create_index(op.f('ix_qianchuan_script_bindings_material_id'), 'qianchuan_script_bindings', ['material_id'], unique=False)
    op.create_index(op.f('ix_qianchuan_script_bindings_script_id'), 'qianchuan_script_bindings', ['script_id'], unique=False)
    op.create_table('selling_points',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('point_type', sa.String(length=50), nullable=False, comment='卖点类型'),
    sa.Column('content', sa.Text(), nullable=False, comment='话术内容'),
    sa.Column('priority', sa.Integer(), nullable=True, comment='优先级'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('creator_addresses',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('recipient_name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=50), nullable=False),
    sa.Column('province', sa.String(length=100), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('district', sa.String(length=100), nullable=True),
    sa.Column('detail', sa.String(length=1000), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['creator_id'], ['creators.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_creator_addresses_creator_default', 'creator_addresses', ['creator_id', 'is_default'], unique=False)
    op.create_table('creator_collaborations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('source_type', sa.String(length=50), nullable=False),
    sa.Column('external_record_id', sa.String(length=200), nullable=True),
    sa.Column('internal_code', sa.String(length=100), nullable=False),
    sa.Column('collaboration_type', sa.String(length=30), nullable=False),
    sa.Column('collaboration_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('actual_paid_cents', sa.Integer(), nullable=False),
    sa.Column('amount_status', sa.String(length=30), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("amount_status IN ('pending','confirmed')", name='ck_creator_collaborations_amount_status'),
    sa.CheckConstraint("collaboration_type IN ('short_video','live','graphic','other')", name='ck_creator_collaborations_type'),
    sa.CheckConstraint("status IN ('planned','in_progress','completed','cancelled')", name='ck_creator_collaborations_status'),
    sa.CheckConstraint('actual_paid_cents >= 0', name='ck_creator_collaborations_paid_nonnegative'),
    sa.CheckConstraint('length(trim(internal_code)) > 0', name='ck_creator_collaborations_internal_code_nonblank'),
    sa.ForeignKeyConstraint(['creator_id'], ['creators.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['bd_members.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('internal_code')
    )
    op.create_index('ix_creator_collaborations_creator_date_status', 'creator_collaborations', ['creator_id', 'collaboration_date', 'status', 'amount_status'], unique=False)
    op.create_index('uq_creator_collaboration_external', 'creator_collaborations', ['source_type', 'external_record_id'], unique=True, sqlite_where=sa.text('external_record_id IS NOT NULL'), postgresql_where=sa.text('external_record_id IS NOT NULL'))
    op.create_table('creator_followups',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('followed_up_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('method', sa.String(length=30), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('next_followup_at', sa.DateTime(), nullable=True),
    sa.Column('stage_after', sa.String(length=30), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("method IN ('douyin','wechat','phone','offline','other')", name='ck_creator_followups_method'),
    sa.CheckConstraint("stage_after IS NULL OR stage_after IN ('lead','contacted','negotiating','sampled','scheduled','cooperating','completed','paused')", name='ck_creator_followups_stage_after'),
    sa.ForeignKeyConstraint(['creator_id'], ['creators.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['bd_members.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_creator_followups_creator_time', 'creator_followups', ['creator_id', 'followed_up_at'], unique=False)
    op.create_table('creator_portraits',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('primary_categories', sa.JSON(), nullable=False),
    sa.Column('content_formats', sa.JSON(), nullable=False),
    sa.Column('follower_count', sa.Integer(), nullable=True),
    sa.Column('audience_profile', sa.JSON(), nullable=False),
    sa.Column('regions', sa.JSON(), nullable=False),
    sa.Column('style_tags', sa.JSON(), nullable=False),
    sa.Column('cooperation_preferences', sa.JSON(), nullable=False),
    sa.Column('price_range', sa.String(length=200), nullable=True),
    sa.Column('fit_score', sa.Integer(), nullable=True),
    sa.Column('risk_notes', sa.Text(), nullable=True),
    sa.Column('assessed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('fit_score IS NULL OR (fit_score >= 1 AND fit_score <= 5)', name='ck_creator_portraits_fit'),
    sa.CheckConstraint('follower_count IS NULL OR follower_count >= 0', name='ck_creator_portraits_followers'),
    sa.ForeignKeyConstraint(['creator_id'], ['creators.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('creator_id')
    )
    op.create_table('creator_collaboration_products',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('collaboration_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('product_name_snapshot', sa.String(length=200), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['collaboration_id'], ['creator_collaborations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('collaboration_id', 'product_id', name='uq_creator_collaboration_product')
    )
    op.create_table('creator_sample_orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('address_id', sa.Integer(), nullable=True),
    sa.Column('collaboration_id', sa.Integer(), nullable=True),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('recipient_name_snapshot', sa.String(length=100), nullable=False),
    sa.Column('phone_snapshot', sa.String(length=50), nullable=False),
    sa.Column('province_snapshot', sa.String(length=100), nullable=False),
    sa.Column('city_snapshot', sa.String(length=100), nullable=False),
    sa.Column('district_snapshot', sa.String(length=100), nullable=True),
    sa.Column('address_detail_snapshot', sa.String(length=1000), nullable=False),
    sa.Column('shipping_company', sa.String(length=100), nullable=True),
    sa.Column('tracking_number', sa.String(length=200), nullable=True),
    sa.Column('shipped_at', sa.DateTime(), nullable=True),
    sa.Column('received_at', sa.DateTime(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending_shipment','shipped','received','cancelled')", name='ck_creator_sample_orders_status'),
    sa.ForeignKeyConstraint(['address_id'], ['creator_addresses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['collaboration_id'], ['creator_collaborations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['creator_id'], ['creators.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index('ix_creator_sample_orders_creator_status', 'creator_sample_orders', ['creator_id', 'status'], unique=False)
    op.create_table('creator_sample_order_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('sample_order_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('product_name_snapshot', sa.String(length=200), nullable=False),
    sa.Column('specification', sa.String(length=300), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint('quantity > 0', name='ck_creator_sample_items_quantity_positive'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sample_order_id'], ['creator_sample_orders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('creator_sample_order_items')
    op.drop_index('ix_creator_sample_orders_creator_status', table_name='creator_sample_orders')
    op.drop_table('creator_sample_orders')
    op.drop_table('creator_collaboration_products')
    op.drop_table('creator_portraits')
    op.drop_index('ix_creator_followups_creator_time', table_name='creator_followups')
    op.drop_table('creator_followups')
    op.drop_index('uq_creator_collaboration_external', table_name='creator_collaborations', sqlite_where=sa.text('external_record_id IS NOT NULL'), postgresql_where=sa.text('external_record_id IS NOT NULL'))
    op.drop_index('ix_creator_collaborations_creator_date_status', table_name='creator_collaborations')
    op.drop_table('creator_collaborations')
    op.drop_index('ix_creator_addresses_creator_default', table_name='creator_addresses')
    op.drop_table('creator_addresses')
    op.drop_table('selling_points')
    op.drop_index(op.f('ix_qianchuan_script_bindings_script_id'), table_name='qianchuan_script_bindings')
    op.drop_index(op.f('ix_qianchuan_script_bindings_material_id'), table_name='qianchuan_script_bindings')
    op.drop_table('qianchuan_script_bindings')
    op.drop_index(op.f('ix_qianchuan_material_performance_material_name'), table_name='qianchuan_material_performance')
    op.drop_index(op.f('ix_qianchuan_material_performance_material_id'), table_name='qianchuan_material_performance')
    op.drop_index(op.f('ix_qianchuan_material_performance_batch_id'), table_name='qianchuan_material_performance')
    op.drop_table('qianchuan_material_performance')
    op.drop_index(op.f('ix_product_rag_feedbacks_query_log_id'), table_name='product_rag_feedbacks')
    op.drop_table('product_rag_feedbacks')
    op.drop_index('ix_integration_connections_provider_status', table_name='integration_connections')
    op.drop_index('ix_integration_connections_authorization_id', table_name='integration_connections')
    op.drop_table('integration_connections')
    op.drop_table('generated_scripts')
    op.drop_index('uq_creators_platform_uid', table_name='creators', sqlite_where=sa.text('platform_uid_normalized IS NOT NULL'), postgresql_where=sa.text('platform_uid_normalized IS NOT NULL'))
    op.drop_index('uq_creators_douyin_handle', table_name='creators', sqlite_where=sa.text('douyin_handle_normalized IS NOT NULL'), postgresql_where=sa.text('douyin_handle_normalized IS NOT NULL'))
    op.drop_index('ix_creators_stage_owner_archived', table_name='creators')
    op.drop_index(op.f('ix_creators_stage'), table_name='creators')
    op.drop_index(op.f('ix_creators_owner_id'), table_name='creators')
    op.drop_index(op.f('ix_creators_nickname'), table_name='creators')
    op.drop_index(op.f('ix_creators_archived_at'), table_name='creators')
    op.drop_table('creators')
    op.drop_index(op.f('ix_viral_scripts_video_type'), table_name='viral_scripts')
    op.drop_index(op.f('ix_viral_scripts_category'), table_name='viral_scripts')
    op.drop_table('viral_scripts')
    op.drop_index(op.f('ix_vector_sync_jobs_status'), table_name='vector_sync_jobs')
    op.drop_index(op.f('ix_vector_sync_jobs_next_attempt_at'), table_name='vector_sync_jobs')
    op.drop_index(op.f('ix_vector_sync_jobs_entity_type'), table_name='vector_sync_jobs')
    op.drop_index(op.f('ix_vector_sync_jobs_entity_id'), table_name='vector_sync_jobs')
    op.drop_table('vector_sync_jobs')
    op.drop_index(op.f('ix_vector_index_versions_status'), table_name='vector_index_versions')
    op.drop_index(op.f('ix_vector_index_versions_entity_type'), table_name='vector_index_versions')
    op.drop_table('vector_index_versions')
    op.drop_index(op.f('ix_script_templates_video_type'), table_name='script_templates')
    op.drop_table('script_templates')
    op.drop_table('reference_scripts')
    op.drop_index(op.f('ix_qianchuan_import_batches_file_sha256'), table_name='qianchuan_import_batches')
    op.drop_table('qianchuan_import_batches')
    op.drop_index(op.f('ix_products_category'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_product_rag_query_logs_scope'), table_name='product_rag_query_logs')
    op.drop_index(op.f('ix_product_rag_query_logs_product_id'), table_name='product_rag_query_logs')
    op.drop_index(op.f('ix_product_rag_query_logs_created_at'), table_name='product_rag_query_logs')
    op.drop_table('product_rag_query_logs')
    op.drop_index(op.f('ix_job_runs_status'), table_name='job_runs')
    op.drop_index(op.f('ix_job_runs_job_type'), table_name='job_runs')
    op.drop_table('job_runs')
    op.drop_index('ix_integration_security_audit_provider_event_type', table_name='integration_security_audit')
    op.drop_index('ix_integration_security_audit_created_at', table_name='integration_security_audit')
    op.drop_table('integration_security_audit')
    op.drop_index('ix_integration_oauth_states_expires_at', table_name='integration_oauth_states')
    op.drop_table('integration_oauth_states')
    op.drop_index('ix_integration_login_throttles_locked_until', table_name='integration_login_throttles')
    op.drop_table('integration_login_throttles')
    op.drop_index('ix_integration_authorizations_status', table_name='integration_authorizations')
    op.drop_index('ix_integration_authorizations_refresh_lease_expires_at', table_name='integration_authorizations')
    op.drop_table('integration_authorizations')
    op.drop_index('ix_integration_app_configs_status', table_name='integration_app_configs')
    op.drop_table('integration_app_configs')
    op.drop_index('uq_creator_import_committed_file', table_name='creator_import_batches', sqlite_where=sa.text("status = 'committed'"), postgresql_where=sa.text("status = 'committed'"))
    op.drop_index('ix_creator_import_batch_file_lookup', table_name='creator_import_batches')
    op.drop_table('creator_import_batches')
    op.drop_index(op.f('ix_bd_members_active'), table_name='bd_members')
    op.drop_table('bd_members')
    op.drop_index(op.f('ix_durable_tasks_task_type'), table_name='durable_tasks')
    op.drop_index(op.f('ix_durable_tasks_status'), table_name='durable_tasks')
    op.drop_index(op.f('ix_durable_tasks_next_attempt_at'), table_name='durable_tasks')
    op.drop_index(op.f('ix_durable_tasks_lease_until'), table_name='durable_tasks')
    op.drop_index(op.f('ix_durable_tasks_created_at'), table_name='durable_tasks')
    op.drop_table('durable_tasks')
    op.drop_index(op.f('ix_audit_events_request_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_path'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_created_at'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_role'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_name'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index(op.f('ix_ai_usage_records_status'), table_name='ai_usage_records')
    op.drop_index(op.f('ix_ai_usage_records_provider'), table_name='ai_usage_records')
    op.drop_index(op.f('ix_ai_usage_records_interface_key'), table_name='ai_usage_records')
    op.drop_index(op.f('ix_ai_usage_records_created_at'), table_name='ai_usage_records')
    op.drop_index(op.f('ix_ai_usage_records_actor_name'), table_name='ai_usage_records')
    op.drop_table('ai_usage_records')
    op.drop_index(op.f('ix_ai_interface_settings_interface_key'), table_name='ai_interface_settings')
    op.drop_table('ai_interface_settings')
