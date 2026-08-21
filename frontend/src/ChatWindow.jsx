import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function FullScreenBoot({ onDone }) {
  const [phase, setPhase] = useState(0);
  const [lineIndex, setLineIndex] = useState(0);

  const bootLines = [
    'Booting agentic pipeline',
    'Spinning up orchestrator + sub-agents',
    'Establishing vector channel',
  ];

  useEffect(() => {
    if (lineIndex < bootLines.length - 1) {
      const t = setTimeout(
        () => setLineIndex((i) => i + 1),
        550
      );

      return () => clearTimeout(t);
    }

    const t = setTimeout(() => setPhase(1), 550);

    return () => clearTimeout(t);
  }, [lineIndex]);

  useEffect(() => {
    if (phase === 1) {
      const t = setTimeout(() => setPhase(2), 450);

      return () => clearTimeout(t);
    }

    if (phase === 2) {
      const t = setTimeout(onDone, 400);

      return () => clearTimeout(t);
    }
  }, [phase, onDone]);

  return (
    <div
      className={`boot-overlay ${
        phase === 1 ? 'flash' : ''
      } ${phase === 2 ? 'fade-out' : ''}`}
    >
      {phase < 1 ? (
        <>{bootLines[lineIndex]}...</>
      ) : (
        <>Agent ready</>
      )}
    </div>
  );
}

function ChatWindow({ onClose }) {
  const [stage, setStage] = useState('boot');

  const [sessionId] = useState(
    () => crypto.randomUUID()
  );

  const [collectionName, setCollectionName] = useState('');
  const [collectionInput, setCollectionInput] = useState('');

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');

  const [isSending, setIsSending] = useState(false);
  const [approvalPending, setApprovalPending] = useState(false);

  const [error, setError] = useState('');

  const bottomRef = useRef(null);

  /*
   * Scroll to latest message
   */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: 'smooth',
    });
  }, [messages, isSending, approvalPending]);

  /*
   * Poll approval status while waiting for human approval.
   */
  useEffect(() => {
    if (!approvalPending) {
      return;
    }

    const checkApprovalStatus = async () => {
      try {
        const response = await axios.get(
          'http://localhost:8001/approval-status',
          {
            params: {
              session_id: sessionId,
            },
          }
        );

        const status = response.data.status;

        /*
         * Still waiting for approval.
         */
        if (status === 'awaiting_approval') {
          return;
        }

        /*
         * Approval completed.
         */
        if (status === 'approved') {
          setApprovalPending(false);

          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content:
                response.data.output ||
                'Approval received, but no response was generated.',
            },
          ]);

          return;
        }

        /*
         * Approval denied.
         */
        if (status === 'denied') {
          setApprovalPending(false);

          setMessages((prev) => [
            ...prev,
            {
              role: 'assistant',
              content:
                response.data.output ||
                'The request was denied by the approver.',
            },
          ]);

          return;
        }
      } catch (err) {
        console.error(
          'Approval status check failed:',
          err
        );
      }
    };

    /*
     * Check immediately instead of waiting 2 seconds.
     */
    checkApprovalStatus();

    const interval = setInterval(
      checkApprovalStatus,
      2000
    );

    return () => clearInterval(interval);
  }, [approvalPending, sessionId]);

  /*
   * Start chat.
   */
  const startChat = () => {
    if (!collectionInput.trim()) {
      return;
    }

    setCollectionName(collectionInput.trim());
    setStage('chat');
  };

  /*
   * Send chat message.
   */
  const sendMessage = async () => {
    const text = input.trim();

    if (
      !text ||
      isSending ||
      approvalPending
    ) {
      return;
    }

    /*
     * Show user's message immediately.
     */
    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: text,
      },
    ]);

    setInput('');
    setIsSending(true);
    setError('');

    try {
      const response = await axios.post(
        'http://localhost:8001/chat',
        {
          session_id: sessionId,
          user_input: text,
          collection_name: collectionName,
        }
      );

      /*
       * TOKEN LIMIT EXCEEDED
       *
       * Backend paused the graph using interrupt().
       */
      if (
        response.data.status ===
        'awaiting_approval'
      ) {
        const interruptInfo =
          response.data.detail;

        setApprovalPending(true);

        setMessages((prev) => [
          ...prev,
          {
            role: 'approval',
            content:
              interruptInfo?.message ||
              'Token limit exceeded. Waiting for human approval.',
          },
        ]);

        return;
      }

      /*
       * NORMAL RESPONSE
       */
      if (response.data.output) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: response.data.output,
          },
        ]);
      }
    } catch (err) {
      const errorMsg =
        err.response?.data?.detail ||
        err.message;

      setError(`❌ ${errorMsg}`);
    } finally {
      setIsSending(false);
    }
  };

  /*
   * Enter key handling.
   */
  const handleKeyDown = (e) => {
    if (
      e.key === 'Enter' &&
      !e.shiftKey
    ) {
      e.preventDefault();

      if (stage === 'chat') {
        sendMessage();
      } else {
        startChat();
      }
    }
  };

  /*
   * Stage 1: Boot screen
   */
  if (stage === 'boot') {
    return (
      <FullScreenBoot
        onDone={() => setStage('setup')}
      />
    );
  }

  /*
   * Stage 2: Chat setup
   */
  if (stage === 'setup') {
    return (
      <div className="chat-card">
        <div className="chat-header">
          <div>
            <h2>Chat Setup</h2>
            <p>
              Start a Test Session
            </p>
          </div>

          <button
            className="chat-close-btn"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="chat-setup-body">
          <p>
            Enter the client / collection
            name to query
          </p>

          <input
            type="text"
            className="client-name-input"
            placeholder="e.g. gromonew"
            value={collectionInput}
            onChange={(e) =>
              setCollectionInput(
                e.target.value
              )
            }
            onKeyDown={handleKeyDown}
            autoFocus
          />

          <button
            className="upload-btn"
            onClick={startChat}
            disabled={
              !collectionInput.trim()
            }
          >
            Start Chat
          </button>
        </div>
      </div>
    );
  }

  /*
   * Stage 3: Actual chat
   */
  return (
    <div className="chat-card">
      <div className="chat-header">
        <div>
          <h2>AgenticRAG Chat</h2>
          <p>
            Collection: {collectionName}
          </p>
        </div>

        <button
          className="chat-close-btn"
          onClick={onClose}
        >
          ✕
        </button>
      </div>

      <div className="chat-messages">

        {messages.length === 0 && (
          <div className="chat-empty">
            Send a message to start the
            conversation.
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`chat-bubble-row ${msg.role}`}
          >
            <div
              className={`chat-bubble ${msg.role}`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {isSending && (
          <div className="chat-bubble-row assistant">
            <div className="chat-bubble assistant chat-typing">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        {approvalPending && (
          <div className="chat-bubble-row approval">
            <div className="chat-bubble approval">
              ⏳ Waiting for human approval...
              <br />
              <small>
                An approval request has been
                sent. The response will appear
                here automatically after approval.
              </small>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="status-banner error chat-error">
          {error}
        </div>
      )}

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          placeholder={
            approvalPending
              ? 'Waiting for approval...'
              : 'Type your message...'
          }
          value={input}
          onChange={(e) =>
            setInput(e.target.value)
          }
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={
            isSending ||
            approvalPending
          }
        />

        <button
          className="chat-send-btn"
          onClick={sendMessage}
          disabled={
            !input.trim() ||
            isSending ||
            approvalPending
          }
        >
          ➤
        </button>
      </div>
    </div>
  );
}

export default ChatWindow;