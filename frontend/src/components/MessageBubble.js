"use client";

import React, { useState } from "react";

export default function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const [expandedCitation, setExpandedCitation] = useState(null);

  // Simple formatter for markdown bold (**text**) and newlines
  const formatMessageContent = (text) => {
    if (!text) return "";
    
    // Escape HTML first
    let formatted = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Replace bold syntax **word** with <strong>word</strong>
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    // Convert bullet points starting with - or * into actual lists
    const lines = formatted.split("\n");
    let inList = false;
    const processedLines = lines.map((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        const content = trimmed.substring(2);
        if (!inList) {
          inList = true;
          return `<ul><li>${content}</li>`;
        }
        return `<li>${content}</li>`;
      } else {
        if (inList) {
          inList = false;
          return `</ul>${line}<br />`;
        }
        return line + "<br />";
      }
    });

    if (inList) {
      processedLines.push("</ul>");
    }

    return processedLines.join("");
  };

  const toggleCitation = (idx) => {
    if (expandedCitation === idx) {
      setExpandedCitation(null);
    } else {
      setExpandedCitation(idx);
    }
  };

  return (
    <div className={`message-bubble-wrapper ${isUser ? "user-wrapper" : "assistant-wrapper"}`}>
      <div className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}>
        <div className="message-sender">{isUser ? "Creator" : "RAG Analyst"}</div>
        <div
          className="message-content"
          dangerouslySetInnerHTML={{
            __html: formatMessageContent(message.content),
          }}
        />

        {/* Citations section for Assistant */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="citations-container">
            <div className="citations-header">Source Citations:</div>
            <div className="citation-badges">
              {message.citations.map((citation, idx) => (
                <button
                  key={idx}
                  className={`citation-badge video-${citation.video_id}`}
                  onClick={() => toggleCitation(idx)}
                >
                  Video {citation.video_id} (Chunk {citation.chunk_index})
                </button>
              ))}
            </div>

            {expandedCitation !== null && message.citations[expandedCitation] && (
              <div className="citation-detail-drawer">
                <div className="drawer-header">
                  <strong>Transcript Clip [Video {message.citations[expandedCitation].video_id}, Chunk {message.citations[expandedCitation].chunk_index}]:</strong>
                  <button className="drawer-close" onClick={() => setExpandedCitation(null)}>×</button>
                </div>
                <div className="drawer-body">
                  &ldquo;{message.citations[expandedCitation].chunk_text}&rdquo;
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
