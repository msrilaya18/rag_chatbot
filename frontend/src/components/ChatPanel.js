"use client";

import React, { useState, useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

const SUGGESTED_QUESTIONS = [
  "Why did Video A get more engagement than Video B?",
  "What's the engagement rate of each?",
  "Compare the hooks in the first 5 seconds.",
  "Who's the creator of Video B and what's their follower count?",
  "Suggest improvements for B based on what worked in A.",
];

export default function ChatPanel({ sessionId, videoData }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState(null);
  
  const messagesEndRef = useRef(null);

  // Auto scroll to bottom when messages update (only if there are messages)
  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isStreaming]);

  // Load chat history if present in videoData (when recovering session)
  useEffect(() => {
    if (videoData && videoData.chat_history) {
      const history = videoData.chat_history.map((msg) => ({
        role: msg.role,
        content: msg.content,
        citations: msg.citations || [],
      }));
      setMessages(history);
    }
  }, [videoData]);

  const handleSend = async (textToSend) => {
    const messageText = textToSend || input;
    if (!messageText.trim() || isStreaming) return;

    if (!textToSend) setInput(""); // Clear typing input if sent from input box
    setStreamError(null);

    // 1. Append user message
    const userMessage = { role: "user", content: messageText };
    setMessages((prev) => [...prev, userMessage]);
    setIsStreaming(true);

    // 2. Append empty assistant message placeholder
    const assistantPlaceholder = { role: "assistant", content: "", citations: [] };
    setMessages((prev) => [...prev, assistantPlaceholder]);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: messageText,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `API error ${response.status}`);
      }

      if (!response.body) {
        throw new Error("No response body available for streaming.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // SSE messages are separated by double newlines (\r\n\r\n or \n\n)
        const blocks = buffer.split(/\r?\n\r?\n/);
        // Keep the last incomplete block in the buffer
        buffer = blocks.pop() || "";

        for (const block of blocks) {
          const trimmedBlock = block.trim();
          if (!trimmedBlock) continue;

          // Split block into individual lines to parse event and data tags separately
          const blockLines = trimmedBlock.split(/\r?\n/);
          for (const line of blockLines) {
            const trimmedLine = line.trim();
            if (trimmedLine.startsWith("data: ")) {
              const jsonStr = trimmedLine.substring(6);
              try {
                const chunk = JSON.parse(jsonStr);

                if (chunk.type === "token") {
                  setMessages((prev) => {
                    const updated = [...prev];
                    const lastIdx = updated.length - 1;
                    if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                      updated[lastIdx] = {
                        ...updated[lastIdx],
                        content: updated[lastIdx].content + chunk.content,
                      };
                    }
                    return updated;
                  });
                } else if (chunk.type === "clear") {
                  // Reset the assistant placeholder so retry starts clean (no double answer)
                  setMessages((prev) => {
                    const updated = [...prev];
                    const lastIdx = updated.length - 1;
                    if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                      updated[lastIdx] = {
                        ...updated[lastIdx],
                        content: "",
                        citations: [],
                      };
                    }
                    return updated;
                  });
                } else if (chunk.type === "citation") {
                  setMessages((prev) => {
                    const updated = [...prev];
                    const lastIdx = updated.length - 1;
                    if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                      updated[lastIdx] = {
                        ...updated[lastIdx],
                        citations: chunk.citations,
                      };
                    }
                    return updated;
                  });
                } else if (chunk.type === "error") {
                  // Make 429 rate-limit errors human-friendly
                  const is429 = chunk.content.includes("429") || chunk.content.toLowerCase().includes("quota") || chunk.content.toLowerCase().includes("rate");
                  const friendlyMsg = is429
                    ? "⚠️ Gemini API rate limit reached. Please wait 30–60 seconds and ask again. (Free-tier limit)"
                    : chunk.content;
                  setStreamError(friendlyMsg);
                  setMessages((prev) => {
                    const updated = [...prev];
                    const lastIdx = updated.length - 1;
                    if (lastIdx >= 0 && updated[lastIdx].role === "assistant") {
                      updated[lastIdx] = {
                        ...updated[lastIdx],
                        content: updated[lastIdx].content || `[${friendlyMsg}]`,
                      };
                    }
                    return updated;
                  });
                } else if (chunk.type === "done") {
                  // Streaming finished cleanly
                }
              } catch (err) {
                console.error("Error parsing JSON chunk:", err, "Raw line:", line);
              }
            }
          }
        }
      }
    } catch (error) {
      console.error("Streaming error:", error);
      setStreamError(error.message);
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (lastIdx >= 0 && updated[lastIdx].role === "assistant" && !updated[lastIdx].content) {
          updated[lastIdx] = {
            ...updated[lastIdx],
            content: `[Connection Error: ${error.message}]`,
          };
        }
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>AI Analysis Chat</h3>
        <span className="chat-status-indicator">
          {isStreaming ? (
            <span className="streaming-pulse">Analyzing transcripts...</span>
          ) : (
            "Connected"
          )}
        </span>
      </div>

      <div className="chat-messages-container">
        {messages.length === 0 ? (
          <div className="chat-placeholder">
            <p>Ready to analyze. Pick one of the questions below or write your own comparison query!</p>
            <div className="suggested-chips">
              {SUGGESTED_QUESTIONS.map((question, idx) => (
                <button
                  key={idx}
                  className="suggested-chip"
                  onClick={() => handleSend(question)}
                  disabled={isStreaming}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="messages-list">
              {messages.map((msg, idx) => (
                <MessageBubble key={idx} message={msg} />
              ))}
              {isStreaming &&
                messages[messages.length - 1]?.content === "" && (
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                )}
            </div>
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {streamError && (
        <div className="chat-error-banner">
          Error: {streamError}
        </div>
      )}

      {messages.length > 0 && (
        <div className="chat-suggested-row">
          <strong>Suggested queries:</strong>
          <div className="suggested-chips-scrollable">
            {SUGGESTED_QUESTIONS.map((question, idx) => (
              <button
                key={idx}
                className="suggested-chip-small"
                onClick={() => handleSend(question)}
                disabled={isStreaming}
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="chat-input-bar">
        <textarea
          rows={1}
          placeholder="Ask a comparison question... (e.g. Compare the hooks in the first 5 seconds)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
        />
        <button
          className="btn btn-primary send-btn"
          onClick={() => handleSend()}
          disabled={isStreaming || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
