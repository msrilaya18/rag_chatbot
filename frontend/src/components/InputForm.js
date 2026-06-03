"use client";

import React, { useState } from "react";

function detectPlatform(url) {
  if (!url) return null;
  if (url.includes("youtube.com") || url.includes("youtu.be")) return "YouTube";
  if (url.includes("instagram.com")) return "Instagram";
  if (url.includes("tiktok.com")) return "TikTok";
  return "Unknown";
}

function PlatformBadge({ url }) {
  const platform = detectPlatform(url);
  if (!platform) return null;
  const colors = {
    YouTube: "#ef4444",
    Instagram: "#f43f5e",
    TikTok: "#06b6d4",
    Unknown: "#64748b",
  };
  return (
    <span
      style={{
        fontSize: "11px",
        fontWeight: 700,
        padding: "2px 7px",
        borderRadius: "4px",
        backgroundColor: colors[platform] + "22",
        color: colors[platform],
        marginLeft: "8px",
      }}
    >
      {platform}
    </span>
  );
}

export default function InputForm({ onAnalyze, isLoading }) {
  const [urlA, setUrlA] = useState("");
  const [urlB, setUrlB] = useState("");
  const [urlAError, setUrlAError] = useState("");
  const [urlBError, setUrlBError] = useState("");

  const validateUrl = (url) => {
    if (!url.trim()) return "URL is required.";
    try {
      new URL(url.trim());
    } catch {
      return "Please enter a valid URL (starting with https://).";
    }
    const supported =
      url.includes("youtube.com") ||
      url.includes("youtu.be") ||
      url.includes("instagram.com");
    if (!supported) {
      return "⚠️ This URL may not be supported. YouTube and Instagram Reels work best.";
    }
    return "";
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const errA = validateUrl(urlA);
    const errB = validateUrl(urlB);
    setUrlAError(errA);
    setUrlBError(errB);
    // Only block on hard errors, not warnings
    const isHardError = (err) => err && !err.startsWith("⚠️");
    if (isHardError(errA) || isHardError(errB)) return;

    onAnalyze({ video_a_url: urlA.trim(), video_b_url: urlB.trim() });
  };

  const loadExample = () => {
    setUrlA("https://youtube.com/shorts/QWgzrbCzCpE?si=ClubUUebLUKEjBBV");
    setUrlB("https://www.instagram.com/reel/DY77tyNSehB/?igsh=cG1oYXNjczZlZWVr");
    setUrlAError("");
    setUrlBError("");
  };

  return (
    <div className="input-form-container">
      <div className="input-form-header">
        <h2>RAG Social Video Analyzer</h2>
        <p>
          Compare performance, scripts, and hooks of any two videos.
          <br />
          <span style={{ color: "#64748b", fontSize: "12px" }}>
            Supports YouTube videos, Shorts, and Instagram Reels.
          </span>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="input-form">
        {/* Video A */}
        <div className="input-group">
          <label htmlFor="url-a">
            Video A
            <PlatformBadge url={urlA} />
          </label>
          <input
            id="url-a"
            type="url"
            placeholder="https://www.youtube.com/watch?v=... or https://youtube.com/shorts/..."
            value={urlA}
            onChange={(e) => {
              setUrlA(e.target.value);
              setUrlAError("");
            }}
            disabled={isLoading}
            required
          />
          {urlAError && (
            <div className={urlAError.startsWith("⚠️") ? "input-warning" : "input-warning"} style={{ color: urlAError.startsWith("⚠️") ? "var(--warning)" : "var(--danger)" }}>
              {urlAError}
            </div>
          )}
        </div>

        {/* Video B */}
        <div className="input-group">
          <label htmlFor="url-b">
            Video B
            <PlatformBadge url={urlB} />
          </label>
          <input
            id="url-b"
            type="url"
            placeholder="https://www.instagram.com/reel/... or another YouTube URL..."
            value={urlB}
            onChange={(e) => {
              setUrlB(e.target.value);
              setUrlBError("");
            }}
            disabled={isLoading}
            required
          />
          {urlBError && (
            <div style={{ color: urlBError.startsWith("⚠️") ? "var(--warning)" : "var(--danger)", fontSize: "11px", marginTop: "4px" }}>
              {urlBError}
            </div>
          )}
          <div className="platform-note">
            💡 Instagram Reels may show limited data if the reel is private or requires login. YouTube videos work best.
          </div>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadExample}
            disabled={isLoading}
            suppressHydrationWarning
          >
            Load Example
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading}
            suppressHydrationWarning
          >
            {isLoading ? (
              <span className="spinner-container">
                <span className="spinner" style={{ width: "16px", height: "16px", borderWidth: "2px" }}></span>
                Analyzing Videos...
              </span>
            ) : (
              "Analyze & Initialize Chat"
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
