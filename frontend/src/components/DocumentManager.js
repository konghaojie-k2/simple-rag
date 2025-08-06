import { useState, useEffect } from 'react';
import { getDocuments, deleteDocuments } from '../services/api';

export default function DocumentManager() {
  const [documentStats, setDocumentStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      setLoading(true);
      const data = await getDocuments();
      setDocumentStats(data);
    } catch (error) {
      console.error('加载文档统计失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm('确定要清空所有文档吗？此操作不可恢复！')) {
      return;
    }

    try {
      setDeleting(true);
      await deleteDocuments();
      await loadDocuments(); // 重新加载文档统计
      alert('文档已清空');
    } catch (error) {
      console.error('清空文档失败:', error);
      alert('清空文档失败: ' + error.message);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <div className="loading">加载文档统计中...</div>;
  }

  return (
    <div className="document-manager">
      <h3>知识库状态</h3>
      {documentStats ? (
        <div className="document-stats">
          <div className="stat-item">
            <h4>文档块数量</h4>
            <p className="stat-value">{documentStats.document_count}</p>
          </div>
          {documentStats.message && (
            <div className="stat-item">
              <p className="stat-message">{documentStats.message}</p>
            </div>
          )}
          <div className="document-actions">
            {documentStats.document_count > 0 && (
              <button
                className="delete-all-button"
                onClick={handleDeleteAll}
                disabled={deleting}
              >
                {deleting ? '清空中...' : '清空知识库'}
              </button>
            )}
            <button className="refresh-button" onClick={loadDocuments}>
              刷新状态
            </button>
          </div>
        </div>
      ) : (
        <p>无法获取文档统计信息</p>
      )}
    </div>
  );
}