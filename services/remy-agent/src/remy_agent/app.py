import streamlit as st
import os
import uuid
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from remy_agent.graph import get_workflow

# Page config
st.set_page_config(page_title="Remy - AI Grocery Agent", layout="wide")

# Persistent Thread ID for LangGraph
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# Workflow definition (uncompiled)
workflow = get_workflow()
DB_PATH = "data/checkpoints.sqlite"

st.title("👨‍🍳 Remy: Your Personal Grocery Agent")

# Two-column layout
col1, col2 = st.columns([2, 1])

# Helper to run the graph asynchronously
async def run_agent(input_state=None, command="invoke"):
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        app = workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=["execute_order"]
        )
        config = {"configurable": {"thread_id": st.session_state.thread_id}}
        
        if command == "invoke":
            return await app.ainvoke(input_state, config=config)
        elif command == "get_state":
            return await app.aget_state(config)
        elif command == "update_state":
            return await app.aupdate_state(config, input_state)

with col1:
    st.subheader("Chat")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message("user" if isinstance(msg, HumanMessage) else "assistant"):
            st.markdown(msg.content)

    if prompt := st.chat_input("What would you like to cook?"):
        st.session_state.messages.append(HumanMessage(content=prompt))
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Remy is thinking..."):
                input_state = {"messages": st.session_state.messages}
                
                # Execute graph
                result = asyncio.run(run_agent(input_state, "invoke"))
                
                new_messages = result.get("messages", [])
                if len(new_messages) > len(st.session_state.messages):
                    for i in range(len(st.session_state.messages), len(new_messages)):
                        msg = new_messages[i]
                        if isinstance(msg, AIMessage):
                            st.markdown(msg.content)
                            st.session_state.messages.append(msg)
                else:
                    st.info("Waiting for your approval on the right...")

with col2:
    st.subheader("🛒 Cart & Approval")
    
    # Get current state asynchronously
    state = asyncio.run(run_agent(command="get_state"))
    
    if state and state.values:
        pending_cart = state.values.get("pending_cart", [])
        pantry_items = state.values.get("pantry_items", [])
        
        if pantry_items:
            with st.expander("✅ Found in Pantry (Bypassed)"):
                for item in pantry_items:
                    st.write(f"- {item['original']}")
        
        if pending_cart:
            st.write("Review items to add to Kroger cart:")
            
            approved_items = []
            for i, item in enumerate(pending_cart):
                checked = st.checkbox(item['original'], value=True, key=f"item_{i}")
                if checked:
                    approved_items.append(item)
            
            if st.button("🚀 Approve & Order"):
                # Update state and resume
                asyncio.run(run_agent({"approved_cart": approved_items}, "update_state"))
                
                with st.spinner("Placing order..."):
                    asyncio.run(run_agent(None, "invoke"))
                    st.success("Order request sent to Kroger!")
                    st.rerun()
        
        order_result = state.values.get("order_result")
        if order_result:
            st.subheader("Order Summary")
            for item in order_result.get("items", []):
                icon = "✅" if item['status'] == "added" else "❌"
                st.write(f"{icon} {item['item']} - {item.get('product', item['status'])}")
    else:
        st.write("Start a conversation to see items here.")
