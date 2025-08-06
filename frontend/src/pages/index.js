import { useState, useEffect } from 'react';
import { uploadDocument, getProgress, askQuestion } from '../services/api';
import DocumentManager from '../components/DocumentManager';

export default function Home() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [sources, setSources] = useState([]);
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(null);

  // 轮询进度
  useEffect(() => {
    let interval;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const progressData = await getProgress(taskId);
          setProgress(progressData);
          
          if (progressData.status === 'completed' || progressData.status === 'failed') {
            clearInterval(interval);
            setTaskId(null);
            
            if (progressData.status === 'completed') {
              setUploadStatus(progressData.message);
            } else {
              setUploadStatus(`处理失败: ${progressData.error || progressData.message}`);
            }
          }
        } catch (error) {
          console.error('获取进度失败:', error);
          clearInterval(interval);
          setTaskId(null);
        }
      }, 1000); // 每秒查询一次进度
    }
    
    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [taskId]);

  const handleAsk = async () => {
    if (!question.trim()) return;
    
    setLoading(true);
    setAnswer('');
    setSources([]);
    
    try {
      const response = await askQuestion(question);
      setAnswer(response.answer);
      setSources(response.source_documents || []);
    } catch (error) {
      console.error('Error:', error);
      setAnswer('Error occurred while fetching answer.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;
    
    try {
      setUploadStatus('开始上传文档...');
      setProgress(null);
      
      const response = await uploadDocument(file);
      setTaskId(response.task_id);
      setUploadStatus('文档上传完成，开始处理...');
    } catch (error) {
      console.error('Upload error:', error);
      setUploadStatus('Error occurred while uploading file: ' + error.message);
    }
  };

  return (
    <div className="container">
      <div className="header">
        <h1>Simple RAG 知识库问答系统</h1>
        <p>上传文档并基于文档内容进行问答</p>
      </div>
      
      <div className="card">
        <h2>上传文档</h2>
        <div className="form-group">
          <label htmlFor="file">选择文档 (支持 TXT, PDF, DOCX):</label>
          <input 
            type="file" 
            id="file" 
            onChange={handleFileChange} 
            accept=".txt,.pdf,.docx" 
          />
        </div>
        <button 
          className="button" 
          onClick={handleUpload}
          disabled={!file || !!taskId}
        >
          {taskId ? '处理中...' : '上传文档'}
        </button>
        
        {uploadStatus && (
          <div className="result">
            <p>{uploadStatus}</p>
          </div>
        )}
        
        {progress && (
          <div className="progress">
            <div className="progress-info">
              <span>{progress.message}</span>
              <span>{Math.round(progress.progress * 100)}%</span>
            </div>
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{ width: `${progress.progress * 100}%` }}
              ></div>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <DocumentManager />
      </div>
      
      <div className="card">
        <h2>提问</h2>
        <div className="form-group">
          <label htmlFor="question">输入你的问题:</label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="请输入你的问题..."
            rows={4}
          />
        </div>
        <button 
          className="button" 
          onClick={handleAsk}
          disabled={loading || !question.trim()}
        >
          {loading ? '处理中...' : '提问'}
        </button>
        
        {answer && (
          <div className="result">
            <h3>答案:</h3>
            <p>{answer}</p>
          </div>
        )}
        
        {sources.length > 0 && (
          <div className="sources">
            <h3>参考文档:</h3>
            {sources.map((source, index) => (
              <div key={index} className="source-item">
                <p><strong>来源:</strong> {source.metadata?.source || 'Unknown'}</p>
                <p>{source.page_content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}