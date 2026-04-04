# AI Service

A modular AI service built with FastAPI, LangChain, and LangGraph.

## MCP Web Search Setup

The application uses MCP for web research tools. The default provider is the
official DDGS MCP server launched from the app environment via:

```bash
ddgs mcp
```

Notes:

- Install the DDGS MCP dependency into the same Python environment as the app:

```bash
pip install "ddgs[mcp]"
```

- If you bootstrap dependencies from the repo file, `requirements.txt` now
  includes `ddgs[mcp]`.
- DDGS supports proxy configuration through the inherited `DDGS_PROXY`
  environment variable.
- DDGS also supports an explicit proxy CLI flag in direct invocations:
  `ddgs mcp -pr socks5h://127.0.0.1:9150`
- The app-level research contract remains `search` and `fetch_content`; the
  MCP provider can change underneath that contract as long as runtime mapping
  preserves those tool semantics.

## Project Structure

```
ai_service_kiro/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config/                    # Configuration
│   ├── api/                       # API routes (AI + Business)
│   ├── agents/                    # LangChain Agents
│   ├── graphs/                    # LangGraph Workflows
│   ├── chains/                    # Simple LangChain Chains
│   ├── services/                  # Business logic layer
│   ├── infrastructure/            # External integrations (LLM, Vector DB, etc.)
│   ├── domain/                    # Domain models & schemas
│   ├── prompts/                   # Prompt templates
│   ├── workers/                   # Background jobs
│   └── common/                    # Shared utilities
├── tests/
├── scripts/
└── requirements.txt
```


## Example

```
ai_service/
├── app/
│   ├── main.py                        # FastAPI entry point
│   ├── config/
│   │   ├── settings.py                # Pydantic settings
│   │   ├── logging.py
│   │   └── constants.py
│   │
│   │── api/                           # 🔹 API Layer (tất cả routes)
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Aggregate all routers
│   │   │   │
│   │   │   ├── ai/                    # AI-related endpoints
│   │   │   │   ├── chat.py            # /chat, /chat/stream
│   │   │   │   ├── agents.py          # /agents/{agent_id}/invoke
│   │   │   │   └── knowledge.py       # /knowledge/query, /index
│   │   │   │
│   │   │   └── business/              # Non-AI endpoints
│   │   │       ├── users.py
│   │   │       ├── projects.py
│   │   │       └── analytics.py
│   │   │
│   │   ├── deps.py                    # Shared dependencies
│   │   └── middleware.py
│   │
│   ├── agents/                        # 🤖 AI Agents Module
│   │   ├── __init__.py
│   │   ├── registry.py                # Agent registry/factory
│   │   │
│   │   ├── base/
│   │   │   ├── base_agent.py          # Abstract base agent
│   │   │   └── types.py               # Agent types, enums
│   │   │
│   │   ├── implementations/           # Concrete agents
│   │   │   ├── research_agent/
│   │   │   │   ├── agent.py
│   │   │   │   ├── prompts.py
│   │   │   │   └── tools.py
│   │   │   │
│   │   │   ├── coding_agent/
│   │   │   │   ├── agent.py
│   │   │   │   ├── prompts.py
│   │   │   │   └── tools.py
│   │   │   │
│   │   │   └── support_agent/
│   │   │       ├── agent.py
│   │   │       ├── prompts.py
│   │   │       └── tools.py
│   │   │
│   │   └── tools/                     # Shared tools across agents
│   │       ├── search.py
│   │       ├── database.py
│   │       └── api_caller.py
│   │
│   ├── graphs/                        # 📊 LangGraph Workflows
│   │   ├── __init__.py
│   │   ├── registry.py                # Graph registry/factory
│   │   │
│   │   ├── base/
│   │   │   ├── base_graph.py          # Abstract base graph
│   │   │   ├── state.py               # Shared state definitions
│   │   │   └── types.py
│   │   │
│   │   ├── workflows/                 # Concrete graphs
│   │   │   ├── chat_workflow/
│   │   │   │   ├── graph.py           # Graph definition
│   │   │   │   ├── state.py           # Workflow-specific state
│   │   │   │   └── nodes/
│   │   │   │       ├── classifier.py
│   │   │   │       ├── retriever.py
│   │   │   │       └── responder.py
│   │   │   │
│   │   │   ├── rag_workflow/
│   │   │   │   ├── graph.py
│   │   │   │   ├── state.py
│   │   │   │   └── nodes/
│   │   │   │       ├── query_rewriter.py
│   │   │   │       ├── retriever.py
│   │   │   │       ├── grader.py
│   │   │   │       └── generator.py
│   │   │   │
│   │   │   └── multi_agent_workflow/
│   │   │       ├── graph.py
│   │   │       ├── state.py
│   │   │       └── nodes/
│   │   │           ├── supervisor.py
│   │   │           ├── router.py
│   │   │           └── aggregator.py
│   │   │
│   │   └── nodes/                     # Shared/reusable nodes
│   │       ├── common_retriever.py
│   │       └── common_formatter.py
│   │
│   ├── chains/                        # 🔗 LangChain Chains (simple flows)
│   │   ├── __init__.py
│   │   ├── summarization.py
│   │   ├── translation.py
│   │   └── extraction.py
│   │
│   ├── services/                      # 💼 Business Services
│   │   ├── __init__.py
│   │   │
│   │   ├── ai/                        # AI-related services
│   │   │   ├── chat_service.py
│   │   │   ├── agent_service.py       # Orchestrates agents
│   │   │   ├── graph_service.py       # Orchestrates graphs
│   │   │   └── knowledge_service.py
│   │   │
│   │   └── business/                  # Non-AI services
│   │       ├── user_service.py
│   │       ├── project_service.py
│   │       └── analytics_service.py
│   │
│   ├── infrastructure/                # 🏗️ External Integrations
│   │   ├── __init__.py
│   │   │
│   │   ├── llm/                       # LLM Providers
│   │   │   ├── __init__.py
│   │   │   ├── factory.py             # LLM factory
│   │   │   ├── openai_client.py
│   │   │   ├── anthropic_client.py
│   │   │   └── local_client.py        # Ollama, vLLM
│   │   │
│   │   ├── vector_store/              # Vector DBs
│   │   │   ├── __init__.py
│   │   │   ├── factory.py
│   │   │   ├── qdrant.py
│   │   │   ├── pinecone.py
│   │   │   └── chroma.py
│   │   │
│   │   ├── embeddings/
│   │   │   ├── factory.py
│   │   │   ├── openai_embeddings.py
│   │   │   └── local_embeddings.py
│   │   │
│   │   ├── database/                  # Traditional DBs
│   │   │   ├── mongodb.py
│   │   │   └── postgres.py
│   │   │
│   │   ├── cache/
│   │   │   └── redis.py
│   │   │
│   │   └── messaging/                 # Queues
│   │       ├── redis_queue.py
│   │       └── kafka.py
│   │
│   ├── domain/                        # 📦 Domain Models
│   │   ├── models/
│   │   │   ├── conversation.py
│   │   │   ├── message.py
│   │   │   ├── agent_config.py
│   │   │   └── user.py
│   │   │
│   │   └── schemas/                   # Pydantic schemas
│   │       ├── chat.py
│   │       ├── agent.py
│   │       └── common.py
│   │
│   ├── prompts/                       # 📝 Prompt Templates
│   │   ├── __init__.py
│   │   ├── system/
│   │   │   ├── assistant.py
│   │   │   └── researcher.py
│   │   ├── templates/
│   │   │   ├── rag_template.py
│   │   │   └── summary_template.py
│   │   └── loader.py                  # Load from files/DB
│   │
│   ├── workers/                       # 🔄 Background Jobs
│   │   ├── __init__.py
│   │   ├── embedding_worker.py
│   │   ├── indexing_worker.py
│   │   └── cleanup_worker.py
│   │
│   └── common/                        # 🔧 Shared Utilities
│       ├── exceptions.py
│       ├── streaming.py               # SSE/WebSocket helpers
│       ├── callbacks.py               # LangChain callbacks
│       ├── parsers.py
│       └── validators.py
│
├── tests/
│   ├── unit/
│   │   ├── agents/
│   │   ├── graphs/
│   │   └── services/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│   ├── seed_data.py
│   └── migrate.py
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md

```
