"""Optional OpenAI Responses API edge client for RackMarshal Investigator."""
import argparse, json, os, sys, urllib.error, urllib.request
from rackmarshal.agent.investigator import SYSTEM_INSTRUCTIONS
from rackmarshal.mcp.tools import TOOL_NAMES

DEFAULT_MODEL="gpt-6-luna"

def build_request(prompt,tunnel_id,model=DEFAULT_MODEL):
    return {
        "model":model,
        "instructions":SYSTEM_INSTRUCTIONS,
        "tools":[{
            "type":"mcp",
            "server_label":"rackmarshal",
            "server_description":"Read-only RackMarshal operational evidence and incident history.",
            "tunnel_id":tunnel_id,
            "require_approval":"never",
            "allowed_tools":list(TOOL_NAMES),
        }],
        "input":prompt,
    }

def extract_text(response):
    parts=[]
    for item in response.get("output",[]):
        if item.get("type")!="message": continue
        for content in item.get("content",[]):
            if content.get("type") in ("output_text","text") and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)

def run(prompt,api_key,tunnel_id,model=DEFAULT_MODEL,timeout=180):
    body=build_request(prompt,tunnel_id,model)
    req=urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode(),
        headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},
    )
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.load(response)

def main(argv=None):
    p=argparse.ArgumentParser(description="Run a read-only RackMarshal Investigator query through OpenAI.")
    p.add_argument("prompt",nargs="+")
    p.add_argument("--model",default=os.getenv("RACKMARSHAL_INVESTIGATOR_MODEL",DEFAULT_MODEL))
    p.add_argument("--tunnel-id",default=os.getenv("RACKMARSHAL_TUNNEL_ID"))
    args=p.parse_args(argv)
    key=os.getenv("OPENAI_API_KEY")
    if not key: p.error("OPENAI_API_KEY is required")
    if not args.tunnel_id: p.error("RACKMARSHAL_TUNNEL_ID or --tunnel-id is required")
    try:
        result=run(" ".join(args.prompt),key,args.tunnel_id,args.model)
    except urllib.error.HTTPError as exc:
        sys.stderr.write(exc.read().decode()+"\n"); return 1
    text=extract_text(result)
    if text: print(text)
    else: print(json.dumps(result,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
