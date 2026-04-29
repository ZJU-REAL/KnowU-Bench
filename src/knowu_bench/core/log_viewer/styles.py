"""CSS styles for the log viewer."""

DARK_THEME_CSS = """
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --text-primary: #c9d1d9;
    --text-secondary: #8b949e;
    --accent-color: #58a6ff;
    --accent-hover: #79c0ff;
    --border-color: #30363d;
    --success-color: #238636;
    --success-bg: rgba(35, 134, 54, 0.15);
    --success-text: #3fb950;
    --warning-color: #d29922;
    --warning-bg: rgba(210, 153, 34, 0.15);
    --warning-text: #e3b341;
    --danger-color: #da3633;
    --danger-bg: rgba(218, 54, 51, 0.15);
    --danger-text: #f85149;
    --font-mono: ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
    --radius-sm: 6px;
    --radius-md: 8px;
    --shadow-sm: 0 1px 0 rgba(27,31,35,0.04);
    --shadow-md: 0 3px 6px rgba(0,0,0,0.4);
    --header-height: 60px;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
}

/* Typography */
h1, h2, h3, h4, h5, h6 {
    color: var(--text-primary);
    margin-bottom: 1rem;
    font-weight: 600;
    line-height: 1.25;
}

h1 { font-size: 24px; }
h2 { font-size: 20px; }
h3 { font-size: 16px; }

a {
    color: var(--accent-color);
    text-decoration: none;
    transition: color 0.2s ease;
}

a:hover {
    color: var(--accent-hover);
    text-decoration: underline;
}

code, pre, .font-mono {
    font-family: var(--font-mono);
    font-size: 13px;
}

/* Layout */
.container {
    max-width: 1600px !important;
    margin: 0 auto;
    padding: 30px !important;
    width: 100%;
}

/* Header */
.app-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 20px;
    margin-bottom: 30px;
    border-bottom: 1px solid var(--border-color);
}

.app-title h1 {
    margin: 0;
    font-size: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-primary);
}

.last-update {
    color: var(--text-secondary);
    font-size: 12px;
    font-family: var(--font-mono);
}

/* Controls & Filters */
.controls-section {
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: 24px;
    margin-bottom: 30px;
    box-shadow: var(--shadow-sm);
}

.input-group {
    margin-bottom: 20px;
}

.input-group:last-child {
    margin-bottom: 0;
}

.input-row {
    display: flex;
    gap: 16px;
    margin-bottom: 20px;
}

.input-group-item {
    flex: 1;
}

.input-group-item.input-group-wide {
    flex: 2;
}

.input-group-item label {
    display: block;
    color: var(--text-secondary);
    font-size: 12px;
    margin-bottom: 8px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

@media (max-width: 768px) {
    .input-row {
        flex-direction: column;
    }
    .input-group-item.input-group-wide {
        flex: 1;
    }
}

input[type="text"], select {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    padding: 10px 14px;
    font-family: var(--font-mono);
    font-size: 13px;
    border-radius: var(--radius-sm);
    transition: all 0.2s ease;
    width: 100%;
}

input[type="text"]:focus, select:focus {
    outline: none;
    border-color: var(--accent-color);
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1);
}

.filters-row {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    align-items: flex-end;
}

.filter-item {
    flex: 1;
    min-width: 200px;
}

.filter-item label {
    display: block;
    color: var(--text-secondary);
    font-size: 12px;
    margin-bottom: 8px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

.checkbox-wrapper {
    display: flex;
    align-items: center;
    height: 42px; /* Match input height */
    background-color: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    padding: 0 12px;
}

.checkbox-label {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    user-select: none;
    color: var(--text-primary);
    font-size: 13px;
    width: 100%;
}

input[type="checkbox"] {
    accent-color: var(--accent-color);
    width: 16px;
    height: 16px;
}

/* Stats Cards */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s ease, border-color 0.2s ease;
}

.stat-card:hover {
    transform: translateY(-4px);
    border-color: var(--accent-color);
    box-shadow: var(--shadow-md);
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 8px;
}

.stat-label {
    font-size: 11px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}

.stat-value.success { color: var(--success-text); }
.stat-value.warning { color: var(--warning-text); }
.stat-value.danger { color: var(--danger-text); }

.stat-card-wide {
    min-width: 200px;
}

.stats-grid-rates {
    margin-top: 16px;
    grid-template-columns: repeat(4, 1fr);
}

@media (max-width: 1200px) {
    .stats-grid-rates {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 600px) {
    .stats-grid-rates {
        grid-template-columns: 1fr;
    }
}

/* Table Styles */
.table-container {
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow-x: auto;
    box-shadow: var(--shadow-sm);
}

.task-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    white-space: nowrap;
    table-layout: fixed; /* Important for column widths */
}

.task-table th {
    background-color: var(--bg-tertiary);
    color: var(--text-primary);
    font-weight: 600;
    text-align: left;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    position: sticky;
    top: 0;
    z-index: 10;
}

.task-table td {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    vertical-align: top;
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
}

.task-table tr:last-child td {
    border-bottom: none;
}

.task-table tr:hover td {
    background-color: rgba(255,255,255,0.02);
    color: var(--text-primary);
}

.task-name-col { font-weight: 600; font-size: 14px; width: 200px; white-space: normal; word-break: break-word; }
.task-name-col a { display: block; }

/* Column Specifics */
.col-screenshot { width: 160px; }
.col-goal { width: 250px; white-space: normal; word-break: break-word; }
.col-tags { width: 150px; white-space: normal; }
.col-status { width: 100px; }
.col-score { width: 80px; }
.col-reason { width: 200px; white-space: normal; word-break: break-word; }
.col-step { width: 70px; }
.col-action { width: 120px; white-space: normal; word-break: break-word; }
.col-prediction { width: 250px; white-space: normal; word-break: break-word; }


/* Status Badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid transparent;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.badge.finished { background-color: var(--success-bg); color: var(--success-text); border-color: rgba(63, 185, 80, 0.3); }
.badge.running { background-color: var(--warning-bg); color: var(--warning-text); border-color: rgba(210, 153, 34, 0.3); }
.badge.stale { background-color: var(--danger-bg); color: var(--danger-text); border-color: rgba(248, 81, 73, 0.3); }
.badge.neutral { background-color: rgba(110, 118, 129, 0.2); color: var(--text-secondary); border-color: rgba(110, 118, 129, 0.3); }

/* ===========================================
   Task Detail Page - Waterfall Layout
   =========================================== */
.detail-page {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}

.detail-header {
    background-color: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
    padding: 16px 24px;
    flex-shrink: 0;
}

.detail-header h1 {
    font-size: 18px;
    margin-bottom: 12px;
}

.detail-meta-grid {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}

.meta-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 12px;
    background-color: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    min-width: 120px;
}

.meta-label {
    font-size: 10px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
}

.meta-value {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-primary);
    word-break: break-word;
}

/* Two-column layout: gallery left, details right */
.detail-main {
    display: grid;
    grid-template-columns: 1fr 480px;
    gap: 0;
    flex: 1;
    min-height: 0;
}

@media (max-width: 1200px) {
    .detail-main {
        grid-template-columns: 1fr 380px;
    }
}

@media (max-width: 900px) {
    .detail-main {
        grid-template-columns: 1fr;
    }
    .detail-panel {
        position: relative !important;
        top: auto !important;
        max-height: none !important;
    }
}

/* Waterfall gallery on left */
.steps-gallery {
    padding: 24px;
    overflow-y: auto;
    background-color: var(--bg-primary);
}

.gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 16px;
}

.gallery-item {
    background-color: var(--bg-secondary);
    border: 2px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow: hidden;
    cursor: pointer;
    transition: all 0.2s ease;
}

.gallery-item:hover {
    border-color: var(--accent-color);
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
}

.gallery-item.selected {
    border-color: var(--accent-color);
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.3);
}

.gallery-thumb {
    width: 100%;
    height: auto;
    display: block;
    background-color: #010409;
}

.gallery-item-info {
    padding: 10px 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: var(--bg-tertiary);
    border-top: 1px solid var(--border-color);
}

.gallery-step-num {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
}

.gallery-action-type {
    font-size: 11px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Sticky detail panel on right */
.detail-panel {
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    background-color: var(--bg-secondary);
    border-left: 1px solid var(--border-color);
}

.detail-panel-header {
    background-color: var(--bg-tertiary);
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 10;
}

.detail-panel-title {
    font-weight: 600;
    color: var(--text-primary);
    font-size: 16px;
}

.detail-panel-content {
    padding: 20px;
}

.detail-panel-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: var(--text-secondary);
    font-size: 14px;
}

.detail-image-container {
    background-color: #010409;
    border-radius: var(--radius-md);
    padding: 16px;
    margin-bottom: 20px;
    border: 1px solid var(--border-color);
}

.detail-image {
    width: 100%;
    height: auto;
    border-radius: var(--radius-sm);
    display: block;
}

.detail-group {
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 16px;
    margin-bottom: 16px;
}

.detail-group:last-child {
    border-bottom: none;
    padding-bottom: 0;
    margin-bottom: 0;
}

.detail-group label {
    display: block;
    color: var(--text-secondary);
    font-size: 11px;
    text-transform: uppercase;
    margin-bottom: 8px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

.prediction-box {
    background-color: var(--bg-primary);
    padding: 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text-primary);
}

/* Navigation buttons for detail panel */
.detail-nav {
    display: flex;
    gap: 8px;
}

.nav-btn {
    background-color: var(--bg-secondary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    padding: 6px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 4px;
    transition: all 0.2s;
}

.nav-btn:hover:not(:disabled) {
    background-color: var(--accent-color);
    color: #fff;
    border-color: var(--accent-color);
}

.nav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* Thumbnails */
.thumb {
    width: 140px;
    height: auto;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
    transition: transform 0.2s;
}

.thumb:hover {
    transform: scale(1.5);
    z-index: 100;
    position: relative;
    border-color: var(--accent-color);
    box-shadow: var(--shadow-md);
}

/* Utilities */
.empty-state {
    text-align: center;
    padding: 80px 20px;
    color: var(--text-secondary);
}

.btn-floating {
    position: fixed;
    bottom: 40px;
    right: 40px;
    width: 64px;
    height: 64px;
    border-radius: 50%;
    background-color: var(--accent-color);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    border: none;
    box-shadow: 0 6px 16px rgba(88, 166, 255, 0.3);
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 100;
}

.btn-floating:hover {
    background-color: var(--accent-hover);
    transform: translateY(-4px) scale(1.05);
    box-shadow: 0 8px 24px rgba(88, 166, 255, 0.4);
}

.back-nav {
    margin-bottom: 8px;
}

.back-nav a {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
    padding: 4px 0;
}

.back-nav a:hover {
    color: var(--accent-color);
    text-decoration: none;
}

/* Show More/Less Links */
.show-more-link {
    color: var(--accent-color);
    font-size: 12px;
    margin-left: 4px;
    cursor: pointer;
    white-space: nowrap;
}

.show-more-link:hover {
    color: var(--accent-hover);
    text-decoration: underline;
}

/* Pagination */
.pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    margin-top: 24px;
    padding: 16px;
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
}

.page-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 36px;
    height: 36px;
    padding: 0 12px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
    background-color: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    transition: all 0.2s ease;
    text-decoration: none;
}

.page-link:hover {
    background-color: var(--accent-color);
    color: #fff;
    border-color: var(--accent-color);
    text-decoration: none;
}

.page-link.current {
    background-color: var(--accent-color);
    color: #fff;
    border-color: var(--accent-color);
    cursor: default;
}

.page-link.disabled {
    opacity: 0.4;
    cursor: not-allowed;
    pointer-events: none;
}

.page-ellipsis {
    color: var(--text-secondary);
    padding: 0 8px;
    font-size: 14px;
}

/* Modal */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(4px);
}

.modal-content {
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    max-width: 800px;
    width: 90%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    background-color: var(--bg-tertiary);
    border-radius: var(--radius-md) var(--radius-md) 0 0;
}

.modal-title {
    font-weight: 600;
    font-size: 16px;
    color: var(--text-primary);
}

.modal-close {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 24px;
    cursor: pointer;
    padding: 0 8px;
    line-height: 1;
    transition: color 0.2s;
}

.modal-close:hover {
    color: var(--text-primary);
}

.modal-body {
    padding: 20px;
    overflow-y: auto;
    flex: 1;
}

/* Tools display in modal */
.tools-link {
    cursor: pointer;
    text-decoration: underline;
}

.tools-link:hover {
    color: var(--accent-hover);
}

.tool-item {
    background-color: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    margin-bottom: 12px;
    overflow: hidden;
}

.tool-item:last-child {
    margin-bottom: 0;
}

.tool-header {
    background-color: var(--bg-tertiary);
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-color);
}

.tool-name {
    font-family: var(--font-mono);
    font-weight: 600;
    font-size: 13px;
    color: var(--accent-color);
}

.tool-description {
    padding: 12px 14px;
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
}

.tool-schema-container {
    border-top: 1px solid var(--border-color);
}

.tool-schema {
    margin: 0;
    padding: 12px 14px;
    font-size: 11px;
    color: var(--text-secondary);
    background-color: transparent;
    overflow-x: auto;
    white-space: pre;
}

/* Token Usage Modal */
.modal-content-small {
    max-width: 400px;
}

.token-usage-body {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.token-usage-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background-color: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
}

.token-usage-label {
    font-size: 13px;
    color: var(--text-secondary);
    font-weight: 500;
}

.token-usage-value {
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 600;
    color: var(--accent-color);
}
"""

HTML_BODY_CSS = """
/* Additional body styles for detail page */
"""
