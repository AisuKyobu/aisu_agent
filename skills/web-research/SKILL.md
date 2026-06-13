---
name: web-research
description: Conduct thorough web research by searching and fetching multiple sources
---

## What I do
- Search the web using web_search to find relevant information
- Fetch detailed content from promising pages using web_fetch
- Cross-reference information from multiple sources
- Synthesize findings into a clear, structured summary

## When to use me
Use this when the user asks about:
- Current events or recent news
- Facts that may be beyond your training data
- Comparing information from multiple sources
- Researching a topic in depth

## Workflow
1. First, call web_search with targeted keywords
2. Review results and pick the most relevant 2-3 links
3. Call web_fetch on each selected link
4. Combine and summarize the findings

## Rules
- 搜索任务：搜到 2-3 个有效结果就整理回答，不要继续搜更多
- 如果搜索结果不理想，报告已获取到的信息即可，不要反复换方式搜索
- 获取当前时间用: python -c "import datetime; print(datetime.datetime.now())"
- 最终回复要简洁，直接给出答案而非搜索过程
