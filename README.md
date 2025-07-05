# Open Agent Platform Supervisor

This project leverages the pre-built [LangGraph Supervisor](https://github.com/langchain-ai/langgraph-supervisor-py) agent to orchestrate specialist agents via a [RemoteGraph](https://langchain-ai.github.io/langgraph/reference/remote_graph/).

## Features

*   **Dynamic Agent Delegation:** The supervisor can decide whether to handle a user query itself or delegate it to a configured specialist agent.
*   **Configurable Agents:** Easily define and configure multiple child agents, selecting from the list of existing agents you have deployed and configured in [Open Agent Platform](https://github.com/langchain-ai/open-agent-platform) (OAP).
*   **Customizable System Prompt:** Tailor the supervisor's behavior and instructions using a configurable system prompt, with a sensible default provided.

## Deployments

### Local

To run the supervisor locally, 

1. Clone this repo

```bash
git clone https://github.com/langchain-ai/open-agent-supervisor.git
```

2. Copy the `.env.example` file into `.env`, and set your environment variables
     
   *We default to OpenAI to provide the underlying supervisor agent LLM*

```bash
cp .env.example .env
```

3. Create a new virtual environment, and activate it

```bash
uv venv
source .venv/bin/activate
```

4. Install the dependencies, and dev dependencies

```bash
uv sync
```

5. Run the LangGraph server locally

```bash
# The --no-browser will disable auto-opening LangGraph studio when the server starts
# optional, but recommended since the studio is not needed for this project
uv run langgraph dev --no-browser
```

For more info, see our [LangGraph CLI docs](https://langchain-ai.github.io/langgraph/cloud/reference/cli/#dev)

### Open Agent Platform

> [!IMPORTANT]
> **Prerequisites**: Have at least one supervisor deployed to your instance of LangGraph Platform (LGP) that matches or extends the base implementation provided in this repo

To add a supervisor agent to the platform: 
1. Navigate to the `Agents` tab in the left menu bar
2. Create and agent and select the graph deployed to your LGP instance described in the prerequisites above
3. Give your supervisor a name, description, an optional system prompt if you'd like to modify it and select the agents that it will orchestrate (note -  these agents will need to already be deployed in your LGP instance and configured in Open Agent Platform)

To update the OAP configuration, you can modify the `GraphConfigPydantic` class in the `agent.py` file. OAP will automatically register any changes to this class. You can modify a specific field's properties by editing the `x_oap_ui_config` metadata object. For more information, see the [Open Agent Platform documentation on graph configuration](https://github.com/langchain-ai/open-agent-platform/?tab=readme-ov-file#configuration).

## How it Works

The supervisor operates based on a system prompt that instructs it on how to manage incoming user messages. It can either:
1.  Answer the user directly.
2.  Delegate the query to a specialist agent by invoking a tool in the format `delegate_to_<agent_name>(user_query)`.

The user sees all messages and and optionally all tool calls, ensuring transparency in the conversation flow.

## Authentication

This project uses LangGraph custom auth to authenticate requests to the server. It's configured to use Supabase as the authentication provider, however it can be easily swapped for another service.

Requests must contain an `Authorization` header with a `Bearer` token. This token should be a valid JWT token from Supabase.

The auth handler then takes that token and verifies it with Supabase. If the token is valid, it returns the user's identity. If the token is invalid, it raises an exception. This means you must have a Supabase URL & key set in your environment variables to use this auth handler:

```bash
SUPABASE_URL=""
# Ensure this is your Supabase Service Role key
SUPABASE_KEY=""
```

The auth handler is then used as middleware for all requests to the server. It is configured to run on the following events:

* `threads.create`
* `threads.read`
* `threads.delete`
* `threads.update`
* `threads.search`
* `assistants.create`
* `assistants.read`
* `assistants.delete`
* `assistants.update`
* `assistants.search`
* `store`

For creation methods, it auto-injects the user's ID into the metadata. This is then uses in all read/update/delete/search methods to ensure that the user can only access their own threads and assistants.

By using custom authentication, we can call this LangGraph server directly from a frontend application, without having to worry about exposing API keys/secrets, since you only need a JWT token from Supabase to authenticate.

For more info, see our [LangGraph custom auth docs](https://langchain-ai.github.io/langgraph/tutorials/auth/getting_started/).

## Model API Keys
This agent is configured to accept model API keys set by a user in the OAP settings page. The default OAP implementation allows users to add their own OpenAI, Anthropic, and Google API keys, and these can easily be extended in OAP.

If a user sets their API keys in the OAP settings page, those keys will be passed to the agent through the config in an 'apiKeys' field and used by default. Otherwise, we will automatically fall back on the environment variables set in the agent deployed on LangGraph platform.