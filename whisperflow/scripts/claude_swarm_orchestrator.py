import os
import sys
import re
import argparse
from anthropic import Anthropic

def parse_swarm_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        sys.exit(1)
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    agents = []
    
    # Regex to find sub-agents
    pattern = r"###\s+(A\d+.*?)\n(.*?)(?=\n###|\n##|\Z)"
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for match in matches:
        title = match.group(1).strip()
        body = match.group(2).strip()
        if "PM" in title or "Orchestrator" in title:
            continue
            
        system_prompt = f"You are {title}.\n\nYour instructions:\n{body}\n\n"
        system_prompt += "Follow the global rules and ensure you output structured evidence."
        
        agents.append({
            "name": title.split("—")[0].strip() if "—" in title else title,
            "system": system_prompt
        })
        
    # Find PM/Orchestrator
    pm_pattern = r"###\s+((?:PM|Orchestrator).*?)\n(.*?)(?=\n###|\n##|\Z)"
    pm_match = re.search(pm_pattern, content, re.DOTALL)
    pm_system = "You are the Orchestrator.\n"
    if pm_match:
        pm_system += pm_match.group(2).strip()
        
    return agents, pm_system

def main():
    parser = argparse.ArgumentParser(description="Run Claude Swarm Orchestrator")
    parser.add_argument("--swarm", type=str, required=True, help="Path to the SWARM.md file")
    parser.add_argument("--env-id", type=str, required=False, help="Environment ID (optional)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is missing.")
        sys.exit(1)

    client = Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": "managed-agents-2026-04-01"}
    )

    print(f"Parsing {args.swarm}...")
    sub_agents, pm_system = parse_swarm_file(args.swarm)
    
    if not sub_agents:
        print("Error: No sub-agents found in the markdown file.")
        sys.exit(1)
        
    print(f"Found {len(sub_agents)} sub-agents. Registering them with Claude...")
    
    roster = []
    for agent_data in sub_agents:
        try:
            # We'll use claude-3-5-sonnet-20241022 as a default model
            agent = client.beta.agents.create(
                name=agent_data["name"][:64],
                model="claude-3-5-sonnet-20241022",
                system=agent_data["system"],
            )
            roster.append({"type": "agent", "id": agent.id})
            print(f"Registered {agent_data['name']} (ID: {agent.id})")
        except Exception as e:
            print(f"Failed to create agent {agent_data['name']}: {e}")
            sys.exit(1)
            
    print("\nRegistering Coordinator (PM)...")
    try:
        coordinator = client.beta.agents.create(
            name="Orchestrator",
            model="claude-3-5-sonnet-20241022",
            system=pm_system,
            tools=[{"type": "agent_toolset_20260401"}],
            multiagent={
                "type": "coordinator",
                "agents": roster
            }
        )
        print(f"Registered Coordinator (ID: {coordinator.id})")
    except Exception as e:
        print(f"Failed to create coordinator: {e}")
        sys.exit(1)
        
    print("\nStarting session...")
    
    session_args = {"agent": coordinator.id}
    if args.env_id:
        session_args["environment_id"] = args.env_id
        
    try:
        session = client.beta.sessions.create(**session_args)
        print(f"Session started! ID: {session.id}")
        print("\nNote: Event streaming is not yet fully implemented in this script.")
        print(f"To list threads: ant beta:sessions:threads list --session-id {session.id}")
    except Exception as e:
        print(f"Failed to create session: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
