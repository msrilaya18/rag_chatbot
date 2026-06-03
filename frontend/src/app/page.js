"use client";

import React, { useState, useEffect } from "react";
import InputForm from "../components/InputForm";
import VideoCard from "../components/VideoCard";
import ChatPanel from "../components/ChatPanel";

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [videoA, setVideoA] = useState(null);
  const [videoB, setVideoB] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState(null);
  const [isRecovering, setIsRecovering] = useState(false);

  // Recover session from localStorage on mount
  useEffect(() => {
    const savedSession = localStorage.getItem("rag_session");
    if (savedSession) {
      try {
        const { session_id, video_a, video_b } = JSON.parse(savedSession);
        if (session_id && video_a && video_b) {
          // Verify session still valid on backend
          setIsRecovering(true);
          fetch(`/api/session/${session_id}`)
            .then((res) => {
              if (res.ok) {
                setSessionId(session_id);
                setVideoA(video_a);
                setVideoB(video_b);
              } else {
                // Session expired — clean up
                localStorage.removeItem("rag_session");
              }
            })
            .catch(() => localStorage.removeItem("rag_session"))
            .finally(() => setIsRecovering(false));
        }
      } catch {
        localStorage.removeItem("rag_session");
      }
    }
  }, []);

  const handleAnalyze = async (urls) => {
    setIsAnalyzing(true);
    setError(null);

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(urls),
      });

      if (!response.ok) {
        let errorMsg = `Analysis failed (${response.status})`;
        try {
          const errDetail = await response.json();
          errorMsg = errDetail.detail || errDetail.message || errorMsg;
        } catch {
          try { errorMsg = await response.text() || errorMsg; } catch { /* ignore */ }
        }
        throw new Error(errorMsg);
      }

      const data = await response.json();
      setSessionId(data.session_id);
      setVideoA(data.video_a);
      setVideoB(data.video_b);
      // Persist session so page refresh doesn't lose state
      localStorage.setItem(
        "rag_session",
        JSON.stringify({
          session_id: data.session_id,
          video_a: data.video_a,
          video_b: data.video_b,
        })
      );
    } catch (err) {
      console.error("Error analyzing videos:", err);
      setError(err.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReset = async () => {
    if (sessionId) {
      // Best-effort delete session from backend
      try {
        await fetch(`/api/session/${sessionId}`, { method: "DELETE" });
      } catch (err) {
        console.error("Failed to delete session:", err);
      }
    }
    setSessionId("");
    setVideoA(null);
    setVideoB(null);
    setError(null);
    localStorage.removeItem("rag_session");
  };

  if (isRecovering) {
    return (
      <main className="app-main-container">
        <div className="recovery-loader">
          <div className="spinner"></div>
          <p>Recovering session...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="app-main-container">
      <header className="app-header">
        <div className="header-logo">
          <h1>Social RAG</h1>
          <span className="logo-badge">V1.0</span>
        </div>
        {sessionId && (
          <button className="btn btn-secondary reset-btn" onClick={handleReset}>
            New Comparison
          </button>
        )}
      </header>

      {error && (
        <div className="error-alert-banner">
          <div className="alert-content">
            <strong>Analysis Failed:</strong> {error}
          </div>
          <button className="alert-close" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      {!sessionId ? (
        <div className="welcome-section">
          <InputForm onAnalyze={handleAnalyze} isLoading={isAnalyzing} />
          
          <div className="features-preview-grid">
            <div className="feature-item">
              <span className="feature-icon">🔍</span>
              <h4>Deep Script Insights</h4>
              <p>Compare scripts, dialogue hooks, and CTA strategies inside transcripts.</p>
            </div>
            <div className="feature-item">
              <span className="feature-icon">📊</span>
              <h4>Engagement Metrics</h4>
              <p>Extract likes, comments, and views to calculate true engagement rates automatically.</p>
            </div>
            <div className="feature-item">
              <span className="feature-icon">💬</span>
              <h4>Multi-turn Chat</h4>
              <p>Ask follow-up questions with full conversational history and cited sources.</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="workspace-grid">
          <div className="workspace-sidebar">
            <div className="sidebar-section-title">Analyzed Content</div>
            <div className="video-cards-stack">
              <VideoCard video={videoA} label="Video A" />
              <VideoCard video={videoB} label="Video B" />
            </div>
          </div>
          <div className="workspace-content">
            <ChatPanel sessionId={sessionId} videoData={{ video_a: videoA, video_b: videoB }} />
          </div>
        </div>
      )}
    </main>
  );
}
