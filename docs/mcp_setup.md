# MCP Server Setup

This project uses MCP (Model Context Protocol) servers from two providers:

- **Alibaba Cloud (DashScope)**: https://bailian.console.aliyun.com/#/mcp-market
- **ModelScope**: https://modelscope.cn/mcp

## Available MCP Servers

The following MCP servers are configured:

### DashScope MCP Servers

| Server | Description | Transport |
|--------|-------------|-----------|
| **amap** | AMap Maps - Location and navigation services | SSE |
| **stockstar** | Stock Star - Securities and financial data | SSE |

### ModelScope MCP Servers

| Server | Description | Transport |
|--------|-------------|-----------|
| **gitHub** | GitHub Integration | HTTP |
| **jina** | Jina AI - Web content extraction | HTTP |
| **arXiv** | arXiv - Academic paper search | HTTP |

## Setup Instructions

1. Navigate to the MCP marketplace pages listed above
2. Deploy the desired MCP servers according to the provided instructions
3. Configure the required environment variables:
   - `DASHSCOPE_API_KEY`: Your Alibaba Cloud DashScope API key (for amap, stockstar)
   - `MODELSCOPE_API_KEY`: Your ModelScope API key (for gitHub, jina, arXiv)
4. Ensure the environment variables are set before using these MCP servers