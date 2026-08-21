import React, { useState } from 'react';
import axios from 'axios';
import ChatWindow from './ChatWindow';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [clientName, setClientName] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [statusMessage, setStatusMessage] = useState({ text: '', type: '' });
  const [view, setView] = useState('upload'); // 'upload' | 'chat'

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setStatusMessage({ text: '', type: '' });
    }
  };

  const handleUpload = async () => {
    if (!file || !clientName.trim()) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("client_name", clientName.trim());

    setIsUploading(true);
    setStatusMessage({ text: "Uploading and initializing pipeline...", type: 'loading' });

    try {
      const response = await axios.post("http://localhost:8000/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setStatusMessage({ text: `✅ ${response.data.message}`, type: 'success' });
      setFile(null);
      // clientName intentionally left as-is (not cleared)
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message;
      setStatusMessage({ text: `❌ Error: ${errorMsg}`, type: 'error' });
    } finally {
      setIsUploading(false);
    }
  };

  if (view === 'chat') {
    return <ChatWindow onClose={() => setView('upload')} />;
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="eyebrow">Vector Ingestion Pipeline</span>
        <h1>AgenticRAG Hub</h1>
        <p>Seamlessly upload documents to the Qdrant Vector Database</p>
      </div>

      <input
        type="text"
        className="client-name-input"
        placeholder="Enter client name"
        value={clientName}
        onChange={(e) => setClientName(e.target.value)}
        disabled={isUploading}
      />

      <input
        id="file-upload"
        type="file"
        accept="application/pdf"
        onChange={handleFileChange}
        disabled={isUploading}
        className="hidden-input"
      />

      <label htmlFor="file-upload" className={`drop-zone ${file ? 'has-file' : ''}`}>
        <div className="icon-container">
          <svg className="upload-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>
        <span className="file-name">
          {file ? file.name : "Click to select your PDF file"}
        </span>
        {!file && <span className="file-hint">Supported file types: PDF</span>}
      </label>

      <button
        className={`upload-btn ${isUploading ? 'loading' : ''}`}
        onClick={handleUpload}
        disabled={!file || !clientName.trim() || isUploading}
      >
        {isUploading ? (
          <>
            <span className="spinner"></span>
            Processing...
          </>
        ) : 'Upload Document'}
      </button>

      {statusMessage.text && (
        <div className={`status-banner ${statusMessage.type}`}>
          {statusMessage.text}
        </div>
      )}

      <button
        className="test-chat-btn"
        onClick={() => setView('chat')}
      >
        💬 Test Chat
      </button>
    </div>
  );
}

export default App;