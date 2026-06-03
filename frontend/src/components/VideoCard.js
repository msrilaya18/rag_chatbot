"use client";

import React from "react";

export default function VideoCard({ video, label }) {
  if (!video) return null;

  const formatNumber = (num) => {
    if (num === undefined || num === null) return "N/A";
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    }
    return num.toLocaleString();
  };

  const getEngagementClass = (rate) => {
    if (rate >= 5.0) return "engagement-high";
    if (rate >= 2.0) return "engagement-medium";
    return "engagement-low";
  };

  const platformClass = video.platform.toLowerCase();

  return (
    <div className={`video-card ${platformClass}-card`}>
      <div className="card-badge-header">
        <span className="card-label-badge">{label}</span>
        <span className={`platform-badge ${platformClass}`}>
          {video.platform}
        </span>
      </div>

      {video.thumbnail_url ? (
        <div className="video-thumbnail-container">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={video.thumbnail_url}
            alt={video.title}
            className="video-thumbnail"
            referrerPolicy="no-referrer"
            onError={(e) => {
              e.target.style.display = "none";
              // Insert a placeholder text if CDN blocked hotlinking
              const placeholder = document.createElement("div");
              placeholder.className = "video-thumbnail-placeholder";
              placeholder.innerHTML = "<span>Preview Blocked</span>";
              e.target.parentNode.appendChild(placeholder);
            }}
          />
        </div>
      ) : (
        <div className="video-thumbnail-placeholder">
          <span>No Thumbnail</span>
        </div>
      )}

      <div className="video-details">
        <h3 className="video-title" title={video.title}>
          {video.title}
        </h3>
        <p className="video-creator">
          by <strong>{video.creator}</strong>
          {video.follower_count && (
            <span className="follower-count">
              {" "}
              ({formatNumber(video.follower_count)} followers)
            </span>
          )}
        </p>

        <div className="stats-grid">
          <div className="stat-box">
            <span className="stat-label">Views</span>
            <span className="stat-value">{formatNumber(video.views)}</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Likes</span>
            <span className="stat-value">{formatNumber(video.likes)}</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Comments</span>
            <span className="stat-value">{formatNumber(video.comments)}</span>
          </div>
          <div className={`stat-box engagement-box ${getEngagementClass(video.engagement_rate)}`}>
            <span className="stat-label">Engagement</span>
            <span className="stat-value">{video.engagement_rate.toFixed(2)}%</span>
          </div>
        </div>

        <div className="metadata-meta">
          <div>
            <strong>Duration:</strong> {video.duration}
          </div>
          <div>
            <strong>Uploaded:</strong> {video.upload_date}
          </div>
        </div>

        {video.hashtags && video.hashtags.length > 0 && (
          <div className="video-hashtags">
            {video.hashtags.slice(0, 8).map((tag, idx) => (
              <span key={idx} className="hashtag-pill">
                {tag}
              </span>
            ))}
            {video.hashtags.length > 8 && (
              <span className="hashtag-pill-more">
                +{video.hashtags.length - 8} more
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
