import os
from langgraph.pregel.remote import RemoteGraph
from langgraph_supervisor import create_supervisor
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_core.runnables import RunnableConfig
from langchain.chat_models import init_chat_model

# This system prompt is ALWAYS included at the bottom of the message.
UNEDITABLE_SYSTEM_PROMPT = """\nYou can invoke sub-agents by calling tools in this format:
`delegate_to_<name>(user_query)`--replacing <name> with the agent's name--
to hand off control. Otherwise, answer the user yourself.

The user will see all messages and tool calls produced in the conversation, 
along with all returned from the sub-agents. With this in mind, ensure you 
never repeat any information already presented to the user.
"""

DEFAULT_SUPERVISOR_PROMPT = """You are a supervisor AI overseeing a team of specialist agents. 
For each incoming user message, decide if it should be handled by one of your agents. 
"""


class AgentsConfig(BaseModel):
    deployment_url: str
    """The URL of the LangGraph deployment"""
    agent_id: str
    """The ID of the agent to use"""
    name: str
    """The name of the agent"""


class GraphConfigPydantic(BaseModel):
    agents: List[AgentsConfig] = Field(
        default=[],
        metadata={"x_oap_ui_config": {"type": "agents"}},
    )
    system_prompt: Optional[str] = Field(
        default=DEFAULT_SUPERVISOR_PROMPT,
        metadata={
            "x_oap_ui_config": {
                "type": "textarea",
                "placeholder": "Enter a system prompt...",
                "description": f"The system prompt to use in all generations. The following prompt will always be included at the end of the system prompt:\n---{UNEDITABLE_SYSTEM_PROMPT}---",
                "default": DEFAULT_SUPERVISOR_PROMPT,
            }
        },
    )
    supervisor_model: str = Field(
        default="openai:gpt-4.1",
        metadata={"x_oap_ui_config": {"type": "text", "placeholder": "Enter the model to use for the supervisor."}},
    )


class OAPRemoteGraph(RemoteGraph):
    def _sanitize_config(self, config: RunnableConfig) -> RunnableConfig:
        """Sanitize the config to remove non-serializable fields."""
        sanitized = super()._sanitize_config(config)

        # Filter out keys that are already defined in GraphConfigPydantic
        # to avoid the child graph inheriting config from the supervisor
        # (e.g. system_prompt)
        graph_config_fields = set(GraphConfigPydantic.model_fields.keys())

        if "configurable" in sanitized:
            sanitized["configurable"] = {
                k: v
                for k, v in sanitized["configurable"].items()
                if k not in graph_config_fields
            }

        if "metadata" in sanitized:
            sanitized["metadata"] = {
                k: v
                for k, v in sanitized["metadata"].items()
                if k not in graph_config_fields
            }

        return sanitized


def make_child_graphs(cfg: GraphConfigPydantic, access_token: Optional[str] = None):
    """
    Instantiate a list of RemoteGraph nodes based on the configuration.

    Args:
        cfg: The configuration for the graph
        access_token: The Supabase access token for authentication, can be None

    Returns:
        A list of RemoteGraph instances
    """
    import re

    def sanitize_name(name):
        # Replace spaces with underscores
        sanitized = name.replace(" ", "_")
        # Remove any other disallowed characters (<, >, |, \, /)
        sanitized = re.sub(r"[<|\\/>]", "", sanitized)
        return sanitized

    # If no agents in config, return empty list
    if not cfg.agents:
        return []

    # If access_token is None, create headers without token
    headers = {}
    if access_token:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "x-supabase-access-token": access_token,
        }

    def create_remote_graph_wrapper(agent: AgentsConfig):
        return OAPRemoteGraph(
            agent.agent_id,
            url=agent.deployment_url,
            name=sanitize_name(agent.name),
            headers=headers,
        )

    return [create_remote_graph_wrapper(a) for a in cfg.agents]


def get_api_key_for_model(model_name: str, config: RunnableConfig):
    model_name = model_name.lower()
    model_to_key = {
        "openai:": "OPENAI_API_KEY",
        "anthropic:": "ANTHROPIC_API_KEY", 
        "google": "GOOGLE_API_KEY"
    }
    key_name = next((key for prefix, key in model_to_key.items() 
                    if model_name.startswith(prefix)), None)
    if not key_name:
        return None
    api_keys = config.get("configurable", {}).get("apiKeys", {})
    if api_keys and api_keys.get(key_name) and len(api_keys[key_name]) > 0:
        return api_keys[key_name]
    # Fallback to environment variable
    return os.getenv(key_name)


def make_model(cfg: GraphConfigPydantic, model_api_key: str):
    """Instantiate the LLM for the supervisor based on the config."""
    return init_chat_model(
        model=cfg.supervisor_model,
        api_key=model_api_key
    )


def make_prompt(cfg: GraphConfigPydantic):
    """Build the system prompt, falling back to a sensible default."""
    return cfg.system_prompt + UNEDITABLE_SYSTEM_PROMPT


def graph(config: RunnableConfig):
    cfg = GraphConfigPydantic(**config.get("configurable", {}))
    supabase_access_token = config.get("configurable", {}).get(
        "x-supabase-access-token"
    )

    # Pass the token to make_child_graphs, which now handles None values
    child_graphs = make_child_graphs(cfg, supabase_access_token)

    # Get the API key from the RunnableConfig or from the environment variable
    model_api_key = get_api_key_for_model(cfg.supervisor_model, config) or "No token found"

    return create_supervisor(
        child_graphs,
        model=make_model(cfg, model_api_key),
        prompt=make_prompt(cfg),
        config_schema=GraphConfigPydantic,
        handoff_tool_prefix="delegate_to_",
        output_mode="full_history",
    )
