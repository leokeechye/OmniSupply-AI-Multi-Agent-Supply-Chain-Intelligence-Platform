"""Streamlit GUI for the OmniSupply multi-agent supply-chain platform.

Calls SupervisorAgent.execute(query) — the supervisor routes to 1+ specialist
agents (data_analyst, risk, finance, meeting, email), aggregates their
AgentResult outputs, and returns a markdown executive report.

Designed to run against an empty PostgreSQL database — individual agents will
return success=False if they need data they don't have. The supervisor still
produces a report describing what was/wasn't possible.
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title="OmniSupply", page_icon="🚚", layout="wide")
st.title("OmniSupply — Multi-Agent Supply Chain Intelligence")
st.caption(
    "Ask a question. The supervisor routes it to specialist agents "
    "(data analyst, risk, finance, meeting, email), aggregates their outputs, "
    "and writes an executive report."
)


EXAMPLE_QUERIES = [
    "Generate a weekly executive report with top risks, financial KPIs, and recommended actions.",
    "What are the current supply chain risks and which stakeholders should be alerted?",
    "Show me the top 5 product categories by revenue this quarter.",
    "Identify shipments that are likely to be delayed and draft an email to the affected suppliers.",
    "Summarise finance health: P&L highlights, cash flow concerns, and three priority actions.",
]


@st.cache_resource(show_spinner="Initialising agents (one-time)…")
def build_platform() -> Dict[str, Any]:
    """Build database client, vector store, agent registry, and supervisor.

    Falls back gracefully when DATABASE_URL is unset or unreachable — agents
    are still constructed, they just return errors at query time.
    """
    from src.agents import (
        AgentRegistry,
        DataAnalystAgent,
        EmailAgent,
        FinanceAgent,
        MeetingAgent,
        RiskAgent,
    )
    from src.storage.vector.chromadb_client import OmniSupplyVectorStore
    from src.supervisor.orchestrator import SupervisorAgent

    db = None
    db_error: Optional[str] = None
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        try:
            from src.storage.sql.database import DatabaseClient
            db = DatabaseClient(database_url=database_url)
        except Exception as e:
            db_error = f"{type(e).__name__}: {e}"
            db = None
    else:
        db_error = "DATABASE_URL not set"

    vector_store = None
    vector_error: Optional[str] = None
    try:
        vector_store = OmniSupplyVectorStore()
    except Exception as e:
        vector_error = f"{type(e).__name__}: {e}"

    registry = AgentRegistry()
    registry.register(DataAnalystAgent(db_client=db, vector_store=vector_store))
    registry.register(RiskAgent(db_client=db, vector_store=vector_store))
    registry.register(FinanceAgent(db_client=db, vector_store=vector_store))
    registry.register(MeetingAgent(db_client=db, agent_registry=registry, vector_store=vector_store))
    registry.register(EmailAgent(db_client=db, vector_store=vector_store))

    supervisor = SupervisorAgent(agent_registry=registry)

    table_counts: Optional[Dict[str, int]] = None
    if db is not None:
        try:
            table_counts = db.get_table_counts()
        except Exception as e:
            db_error = f"Connected but query failed: {type(e).__name__}: {e}"

    return {
        "db": db,
        "db_error": db_error,
        "vector_store": vector_store,
        "vector_error": vector_error,
        "registry": registry,
        "supervisor": supervisor,
        "table_counts": table_counts,
    }


# --- Sidebar ----------------------------------------------------------------

with st.sidebar:
    st.header("Platform status")

    if not os.getenv("OPENAI_API_KEY"):
        st.error(
            "**OPENAI_API_KEY not set.** Set it in Railway's Variables tab "
            "(or locally in `.env`). The supervisor cannot run without it."
        )
        st.stop()
    st.success("OpenAI key detected")

    if not os.getenv("COMET_API_KEY"):
        st.caption("Opik tracing: off (no `COMET_API_KEY`). Agents still run.")
    else:
        st.caption("Opik tracing: on")

    platform = build_platform()
    counts = platform.get("table_counts")
    if counts is not None:
        total = sum(counts.values())
        if total == 0:
            st.warning(
                "Postgres connected but **empty** (0 records). "
                "Agents that need data will return errors or empty insights. "
                "Run `omnisupply_demo.py` to ingest, or load via SQL directly."
            )
        else:
            st.success(f"Postgres: {total:,} records loaded")
        with st.expander("Table counts", expanded=False):
            for table, count in counts.items():
                st.write(f"- **{table}**: {count:,}")
    elif platform.get("db_error"):
        st.error(f"Postgres: {platform['db_error']}")
    else:
        st.warning("Postgres: unknown state")

    if platform.get("vector_error"):
        st.warning(f"Vector store: {platform['vector_error']}")

    st.divider()
    st.subheader("Registered agents")
    registry = platform["registry"]
    for name in registry.list_agents():
        agent = registry.get_agent(name)
        if agent is None:
            continue
        with st.expander(name, expanded=False):
            for cap in agent.get_capabilities():
                st.write(f"- {cap}")

    st.divider()
    st.subheader("Example queries")
    for i, q in enumerate(EXAMPLE_QUERIES):
        if st.button(q, key=f"ex_{i}", use_container_width=True):
            st.session_state["query"] = q


# --- Main panel -------------------------------------------------------------

default_query = st.session_state.get("query", "")
query = st.text_area(
    "Your query",
    value=default_query,
    height=120,
    placeholder="e.g. Generate a weekly executive report with top risks and financial KPIs.",
)

run = st.button("Run supervisor", type="primary", disabled=not query.strip())

if not run:
    st.info("Enter a query (or click an example in the sidebar) and press **Run supervisor**.")
    st.stop()

if not os.getenv("OPENAI_API_KEY"):
    st.error("Cannot run without `OPENAI_API_KEY`.")
    st.stop()

with st.spinner("Supervisor orchestrating agents…"):
    try:
        result = platform["supervisor"].execute(query)
    except Exception as e:
        st.error(f"Supervisor crashed: {type(e).__name__}: {e}")
        st.exception(e)
        st.stop()

if result.get("error"):
    st.error(result["error"])

task_plan = result.get("task_plan")
if task_plan is not None:
    with st.expander("Task plan", expanded=False):
        st.write("**Steps**")
        for i, step in enumerate(task_plan.steps, 1):
            st.write(f"{i}. {step}")
        st.write(f"**Agents needed:** {', '.join(task_plan.agents_needed)}")
        st.write(f"**Expected output:** {task_plan.expected_output}")

selected = result.get("selected_agents", [])
if selected:
    st.caption(f"Agents invoked: **{', '.join(selected)}**")

agent_results = result.get("agent_results") or {}
if agent_results:
    st.subheader("Agent results")
    cols = st.columns(min(len(agent_results), 3) or 1)
    for i, (name, res) in enumerate(agent_results.items()):
        with cols[i % len(cols)]:
            ok = "✅" if res.success else "❌"
            st.markdown(f"**{ok} {name}**")
            if res.execution_time_ms:
                st.caption(f"{res.execution_time_ms:.0f} ms")
            if not res.success:
                st.error(res.error or "Unknown error")
                continue
            if res.insights:
                st.markdown("_Insights_")
                for ins in res.insights[:5]:
                    st.write(f"- {ins}")
            if res.recommendations:
                st.markdown("_Recommendations_")
                for rec in res.recommendations[:3]:
                    st.write(f"- {rec}")
            if res.metrics:
                with st.expander("Metrics"):
                    st.json(res.metrics, expanded=False)

exec_summary = result.get("executive_summary")
if exec_summary is not None:
    st.subheader("Executive summary")
    st.write(exec_summary.summary)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Key insights**")
        for ins in exec_summary.key_insights:
            st.write(f"- {ins}")
    with c2:
        st.markdown("**Recommendations**")
        for rec in exec_summary.recommendations:
            st.write(f"- {rec}")

    if exec_summary.kpis:
        st.markdown("**KPIs**")
        kpi_cols = st.columns(min(len(exec_summary.kpis), 4) or 1)
        for i, kpi in enumerate(exec_summary.kpis):
            with kpi_cols[i % len(kpi_cols)]:
                st.metric(kpi.name, kpi.value)

final_report = result.get("final_report")
if final_report:
    with st.expander("Full markdown report", expanded=False):
        st.markdown(final_report)
        st.download_button(
            "Download report (.md)",
            data=final_report,
            file_name="omnisupply_report.md",
            mime="text/markdown",
        )
