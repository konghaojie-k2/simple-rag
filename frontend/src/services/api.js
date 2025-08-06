import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const uploadDocument = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  
  return response.data;
};

export const getProgress = async (taskId) => {
  const response = await api.get(`/progress/${taskId}`);
  return response.data;
};

export const askQuestion = async (question) => {
  const response = await api.post('/ask', { question });
  return response.data;
};

export const getDocuments = async () => {
  const response = await api.get('/documents');
  return response.data;
};

export const deleteDocuments = async () => {
  const response = await api.delete('/documents');
  return response.data;
};

// 添加获取配置的API
export const getConfig = async () => {
  const response = await api.get('/config');
  return response.data;
};

// 添加更新配置的API
export const updateConfig = async (config) => {
  const response = await api.post('/config', config);
  return response.data;
};

// 添加健康检查API
export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

export default api;