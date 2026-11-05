"""Record public model metadata and hashes without downloading/executing weights."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

REPOS = ["divergentlabs/masker-mini", "kalyan-ks/ettin-32m-nemotron-pii",
         "ConwayResearch/pii-30M-mlx-4bit-v1.0", "ConwayResearch/pii-30M-coreml-ane-v1.0",
         "knowledgator/gliner-stream-pii-v1.0", "safetype/blackbar-nano"]


def fetch(url):
    with urlopen(url, timeout=45) as response:
        return response.read()


def inspect(repo):
    metadata_url = "https://huggingface.co/api/models/" + repo + "?blobs=true"
    raw = fetch(metadata_url)
    metadata = json.loads(raw)
    revision = metadata["sha"]
    card = metadata.get("cardData") or {}
    result = {"repo_id": repo, "revision": revision, "gated": metadata.get("gated"),
        "created_at": metadata.get("createdAt"), "last_modified": metadata.get("lastModified"),
        "metadata_license": card.get("license"), "pipeline_tag": metadata.get("pipeline_tag"),
        "parameters": (metadata.get("safetensors") or {}).get("total"),
        "api": {"url": metadata_url, "sha256": hashlib.sha256(raw).hexdigest()},
        "files": metadata.get("siblings", []), "text_artifacts": {}, "config": {}}
    names = {f["rfilename"] for f in metadata.get("siblings", [])}
    selected = names & {"README.md", "config.json", "tokenizer_config.json", "LICENSE",
                        "LICENSE.txt", "LICENSE-APACHE", "NOTICE", "pii.py"}
    for name in sorted(selected):
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{quote(name)}"
        try:
            body = fetch(url)
        except HTTPError as error:
            result["text_artifacts"][name] = {"url": url, "http_status": error.code}
            continue
        result["text_artifacts"][name] = {"url": url, "bytes": len(body),
                                          "sha256": hashlib.sha256(body).hexdigest()}
        if name.endswith(".json"):
            config = json.loads(body)
            keys = ("model_type", "architectures", "auto_map", "id2label", "hidden_size",
                    "num_hidden_layers", "max_position_embeddings", "model_max_length", "tokenizer_class")
            result["config"][name] = {k: config[k] for k in keys if k in config}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = {"cutoff": "2026-11-05", "review_date": datetime.now(timezone.utc).isoformat(),
        "scope": "targeted public artifact inspection; metadata is not measured model quality",
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "models": list(ThreadPoolExecutor(max_workers=6).map(inspect, REPOS))}
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("Inspected", len(payload["models"]), "models:", destination)


if __name__ == "__main__":
    main()
