-- Supabase数据库初始化脚本
-- 为知识管理系统创建必要的表和扩展

-- 启用必要的扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建原始文件存储表
CREATE TABLE IF NOT EXISTS document_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,
    file_hash VARCHAR(64), -- SHA-256哈希，用于去重
    file_content BYTEA, -- 存储原始文件二进制内容
    storage_path TEXT, -- 如果使用Supabase Storage，存储文件路径
    collection_name VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 创建文档元数据表
CREATE TABLE IF NOT EXISTS document_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID REFERENCES document_files(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) DEFAULT 'text',
    size BIGINT DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    processed_content TEXT, -- 提取的文本内容
    collection_name VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 创建文件存储表索引
CREATE INDEX IF NOT EXISTS idx_document_files_filename ON document_files(filename);
CREATE INDEX IF NOT EXISTS idx_document_files_hash ON document_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_document_files_collection ON document_files(collection_name);
CREATE INDEX IF NOT EXISTS idx_document_files_created_at ON document_files(created_at);
CREATE INDEX IF NOT EXISTS idx_document_files_content_type ON document_files(content_type);

-- 创建文档元数据表索引
CREATE INDEX IF NOT EXISTS idx_document_metadata_file_id ON document_metadata(file_id);
CREATE INDEX IF NOT EXISTS idx_document_metadata_collection ON document_metadata(collection_name);
CREATE INDEX IF NOT EXISTS idx_document_metadata_filename ON document_metadata(filename);
CREATE INDEX IF NOT EXISTS idx_document_metadata_created_at ON document_metadata(created_at);

-- 创建知识库表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- 插入默认知识库
INSERT INTO knowledge_bases (name, description) 
VALUES ('default', '默认知识库') 
ON CONFLICT (name) DO NOTHING;

-- 创建任务状态表
CREATE TABLE IF NOT EXISTS task_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    progress FLOAT DEFAULT 0.0,
    message TEXT,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_task_status_task_id ON task_status(task_id);
CREATE INDEX IF NOT EXISTS idx_task_status_status ON task_status(status);
CREATE INDEX IF NOT EXISTS idx_task_status_created_at ON task_status(created_at);

-- 创建触发器函数来自动更新updated_at字段
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为相关表创建触发器
DROP TRIGGER IF EXISTS update_document_metadata_updated_at ON document_metadata;
CREATE TRIGGER update_document_metadata_updated_at
    BEFORE UPDATE ON document_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_knowledge_bases_updated_at ON knowledge_bases;
CREATE TRIGGER update_knowledge_bases_updated_at
    BEFORE UPDATE ON knowledge_bases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_task_status_updated_at ON task_status;
CREATE TRIGGER update_task_status_updated_at
    BEFORE UPDATE ON task_status
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 创建RLS (Row Level Security) 策略（可选，用于多租户支持）
-- ALTER TABLE document_metadata ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE knowledge_bases ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE task_status ENABLE ROW LEVEL SECURITY;

-- 创建视图来方便查询统计信息
CREATE OR REPLACE VIEW knowledge_base_stats AS
SELECT 
    kb.id,
    kb.name,
    kb.description,
    COUNT(DISTINCT dm.id) as document_count,
    COALESCE(SUM(dm.chunk_count), 0) as chunk_count,
    COALESCE(SUM(df.file_size), 0) as total_file_size,
    COALESCE(SUM(dm.size), 0) as total_processed_size,
    kb.created_at,
    kb.updated_at
FROM knowledge_bases kb
LEFT JOIN document_metadata dm ON dm.collection_name = kb.name
LEFT JOIN document_files df ON df.id = dm.file_id
GROUP BY kb.id, kb.name, kb.description, kb.created_at, kb.updated_at;

-- 创建文档详细信息视图
CREATE OR REPLACE VIEW document_details AS
SELECT 
    dm.id as metadata_id,
    df.id as file_id,
    df.original_filename,
    df.filename as stored_filename,
    df.content_type,
    df.file_size,
    df.file_hash,
    df.storage_path,
    dm.chunk_count,
    dm.processed_content,
    dm.collection_name,
    dm.created_at,
    dm.updated_at,
    dm.metadata
FROM document_metadata dm
JOIN document_files df ON df.id = dm.file_id;

-- 授予必要的权限（根据实际情况调整）
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- 创建一些有用的函数

-- 获取知识库统计信息的函数
CREATE OR REPLACE FUNCTION get_knowledge_base_stats(kb_name TEXT DEFAULT 'default')
RETURNS TABLE(
    document_count BIGINT,
    chunk_count BIGINT,
    total_file_size BIGINT,
    total_processed_size BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT dm.id)::BIGINT as document_count,
        COALESCE(SUM(dm.chunk_count), 0)::BIGINT as chunk_count,
        COALESCE(SUM(df.file_size), 0)::BIGINT as total_file_size,
        COALESCE(SUM(dm.size), 0)::BIGINT as total_processed_size
    FROM document_metadata dm
    LEFT JOIN document_files df ON df.id = dm.file_id
    WHERE dm.collection_name = kb_name;
END;
$$ LANGUAGE plpgsql;

-- 检查文件是否已存在的函数（基于哈希去重）
CREATE OR REPLACE FUNCTION check_file_exists(file_hash_input VARCHAR(64))
RETURNS TABLE(
    file_id UUID,
    filename VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        df.id,
        df.filename,
        df.created_at
    FROM document_files df
    WHERE df.file_hash = file_hash_input;
END;
$$ LANGUAGE plpgsql;

-- 获取文件内容的函数
CREATE OR REPLACE FUNCTION get_file_content(file_id_input UUID)
RETURNS TABLE(
    filename VARCHAR(255),
    content_type VARCHAR(100),
    file_content BYTEA
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        df.filename,
        df.content_type,
        df.file_content
    FROM document_files df
    WHERE df.id = file_id_input;
END;
$$ LANGUAGE plpgsql;

-- 清理孤立文件的函数（没有关联文档元数据的文件）
CREATE OR REPLACE FUNCTION cleanup_orphaned_files()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM document_files df
    WHERE NOT EXISTS (
        SELECT 1 FROM document_metadata dm 
        WHERE dm.file_id = df.id
    );
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 清理过期任务的函数
CREATE OR REPLACE FUNCTION cleanup_old_tasks(days_old INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM task_status 
    WHERE created_at < NOW() - INTERVAL '1 day' * days_old;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 创建定期清理任务的函数（可以通过cron扩展调用）
-- SELECT cron.schedule('cleanup-old-tasks', '0 2 * * *', 'SELECT cleanup_old_tasks(7);');

COMMENT ON TABLE document_files IS '原始文件存储表，存储上传文件的二进制内容和元信息';
COMMENT ON TABLE document_metadata IS '文档元数据表，存储文档处理后的信息和分块统计';
COMMENT ON TABLE knowledge_bases IS '知识库表，支持多个知识库管理';
COMMENT ON TABLE task_status IS '任务状态表，跟踪异步任务的执行状态';
COMMENT ON VIEW knowledge_base_stats IS '知识库统计信息视图，包含文件大小和处理统计';
COMMENT ON VIEW document_details IS '文档详细信息视图，关联原始文件和处理信息';
COMMENT ON FUNCTION get_knowledge_base_stats IS '获取指定知识库的统计信息';
COMMENT ON FUNCTION check_file_exists IS '检查文件是否已存在（基于哈希去重）';
COMMENT ON FUNCTION get_file_content IS '获取指定文件的原始内容';
COMMENT ON FUNCTION cleanup_orphaned_files IS '清理没有关联文档元数据的孤立文件';
COMMENT ON FUNCTION cleanup_old_tasks IS '清理指定天数之前的旧任务记录';

-- =====================================
-- 向量数据库相关代码（独立部分）
-- =====================================

-- 创建向量文档表（用于存储文档分块和向量嵌入）
-- 基于Supabase官方推荐的结构
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL, -- 对应 Document.pageContent
    metadata JSONB DEFAULT '{}', -- 对应 Document.metadata
    embedding vector(1536) -- 1536适用于OpenAI embeddings，根据模型调整
);

-- 创建文档相似度搜索函数（删除现有函数以避免冲突）
DROP FUNCTION IF EXISTS match_documents(vector, jsonb, float, int);
DROP FUNCTION IF EXISTS match_documents(vector, jsonb);
DROP FUNCTION IF EXISTS match_documents;

CREATE FUNCTION match_documents (
    query_embedding vector(1536),
    filter jsonb default '{}',
    match_threshold float default 0.78,
    match_count int default 10
) RETURNS TABLE (
    id uuid,
    content text,
    metadata jsonb,
    similarity float
) LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT
        documents.id,
        documents.content,
        documents.metadata,
        1 - (documents.embedding <=> query_embedding) AS similarity
    FROM documents
    WHERE documents.metadata @> filter
        AND 1 - (documents.embedding <=> query_embedding) > match_threshold
    ORDER BY documents.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 创建向量表的基础索引
CREATE INDEX IF NOT EXISTS idx_documents_metadata_collection 
ON documents USING BTREE ((metadata->>'collection_name'));

CREATE INDEX IF NOT EXISTS idx_documents_metadata_source 
ON documents USING BTREE ((metadata->>'source'));

CREATE INDEX IF NOT EXISTS idx_documents_metadata_doc_id 
ON documents USING BTREE ((metadata->>'doc_id'));

-- 为JSONB元数据创建GIN索引（支持复杂查询）
CREATE INDEX IF NOT EXISTS idx_documents_metadata_gin 
ON documents USING GIN (metadata);

-- 创建向量索引（提高向量搜索性能）
-- 注意：ivfflat索引需要表中有一些向量数据才能成功创建
DO $$
BEGIN
    -- 尝试创建向量索引，如果失败则跳过
    BEGIN
        CREATE INDEX IF NOT EXISTS idx_documents_embedding 
        ON documents USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100);
        
        RAISE NOTICE '✅ 向量索引创建成功';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE '⚠️ 向量索引创建跳过（需要先添加向量数据）: %', SQLERRM;
    END;
END $$;

-- 向量表注释
COMMENT ON TABLE documents IS '向量文档表，存储文档分块内容和向量嵌入（基于Supabase官方推荐结构）';
COMMENT ON FUNCTION match_documents IS '文档相似度搜索函数，基于向量嵌入查找相似文档';

-- =====================================
-- 向量数据库代码结束
-- =====================================
