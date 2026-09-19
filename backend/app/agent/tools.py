"""
In-process Claude Agent SDK tools.

These run inside the FastAPI process (no extra IPC hop, no extra service) and
give the agent a way to *look before it leaps*: the retrieval tool is the only
way the agent can find out what the transcript knowledge base actually
contains. The agent is never allowed to answer a question itself here -- see
``app/agent/orchestrator.py`` for why the routing agent is intentionally kept
out of the answer-writing business.
"""

import logging

from claude_agent_sdk import create_sdk_mcp_server, tool

logger = logging.getLogger("lenny-assistant.agent")

# TranscriptRetriever is imported lazily inside build_retrieval_tool() rather
# than at module level. It pulls in sentence-transformers (a genuinely heavy,
# slow-to-import ML dependency), and this module otherwise only needs the
# lightweight claude_agent_sdk import -- keeping it lazy means code that only
# needs the rest of the agent layer (e.g. the heuristic router fallback, or
# unit tests for it) doesn't pay that import cost, and doesn't need
# sentence-transformers installed at all to be exercised.


def build_retrieval_tool(db):
    """Bind a retrieve_transcripts tool to a live DB session.

    A new tool instance is built per-request (per orchestrator call) because
    the SQLAlchemy session is request-scoped -- this avoids holding a DB
    session open across the lifetime of a long-lived MCP server.
    """

    @tool(
        "retrieve_transcripts",
        (
            "Search Lenny's Podcast transcript knowledge base for passages relevant "
            "to a product/growth question or topic. Returns the best-matching "
            "transcript excerpts with episode, guest, and a relevance score. "
            "ALWAYS call this before deciding whether a question is answerable "
            "from the knowledge base."
        ),
        {"query": str, "top_k": int},
    )
    async def retrieve_transcripts(args: dict) -> dict:
        from app.rag.retriever import TranscriptRetriever

        query = args.get("query", "")
        top_k = int(args.get("top_k") or 5)

        retriever = TranscriptRetriever(db)
        chunks = retriever.retrieve_relevant_chunks(query, top_k=top_k)

        if not chunks:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "No transcript chunks matched this query at all.",
                    }
                ]
            }

        lines = [f"Found {len(chunks)} matching transcript excerpt(s):"]
        for i, chunk in enumerate(chunks, start=1):
            lines.append(
                f"\n[{i}] episode={chunk.get('episode')!r} "
                f"guest={chunk.get('speaker')!r} score={chunk.get('score'):.3f}\n"
                f"{chunk.get('text', '')[:400]}"
            )
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    return create_sdk_mcp_server(name="lenny-transcripts", tools=[retrieve_transcripts])
