# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json


def _probe(url: str) -> str:
    try:
        response = gl.nondet.web.get(url)
        body = response.body
        text = body.decode("utf-8", errors="ignore") if body is not None else ""
        return json.dumps({"status": response.status, "length": len(text), "head": text[:600]})
    except Exception as e:
        return json.dumps({"error": str(e)})


class HfProbe(gl.Contract):
    last_result: str

    def __init__(self):
        self.last_result = ""

    @gl.public.write
    def probe(self, repo_id: str, revision: str) -> str:
        url = "https://huggingface.co/api/models/" + repo_id + "/revision/" + revision + "?blobs=true"
        result = gl.eq_principle.strict_eq(lambda: _probe(url))
        self.last_result = result
        return result

    @gl.public.view
    def get_last(self) -> str:
        return self.last_result
