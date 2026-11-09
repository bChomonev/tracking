"""post.md → Substack ProseMirror draft body (D-034 publishing helper).

    uv run python -m corridor.scripts.substack_body <post.md> <images.json> <out.json>

``images.json`` maps each chart file name in the Markdown (lines.png, …) to the URL Substack
returned from ``POST /api/v1/image`` and its pixel size: ``{"lines.png": {"url": …,
"width": 1268, "height": 713}}``. The output holds ``title``, ``subtitle`` and ``body``
(the ProseMirror doc as an object; ``JSON.stringify`` it into ``draft_body``).

Node shapes copied from drafts the editor itself saved: ``heading`` carries
``{level, textAlign}``, a ``captionedImage`` holds an ``image2`` with width/height and a
``caption`` (not ``imageCaption`` — the API accepts that, the editor renders nothing). The
subscribe widget goes after the second paragraph; the footer line becomes italics with the
"How this works" link to the explainer post.
"""

import json
import re
import sys
from pathlib import Path

EXPLAINER = "https://chomanalysis.substack.com/p/why-i-built-red-lines-and-how-it"
AI_NOTE = " Drafted from data with an AI assistant and edited by me. New here? "


def inline(text: str) -> list[dict]:
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**"):
            out.append({"type": "text", "marks": [{"type": "strong"}], "text": part[2:-2]})
        elif part.startswith("*"):
            out.append({"type": "text", "marks": [{"type": "em"}], "text": part[1:-1]})
        else:
            out.append({"type": "text", "text": part})
    return out


def image_node(img: dict, alt: str, caption: str) -> dict:
    attrs = {
        "src": img["url"],
        "srcNoWatermark": None,
        "fullscreen": None,
        "imageSize": None,
        "height": img.get("height"),
        "width": img.get("width"),
        "resizeWidth": None,
        "bytes": None,
        "alt": alt,
        "title": None,
        "type": "image/png",
        "href": None,
        "belowTheFold": False,
        "topImage": False,
        "internalRedirect": None,
        "isProcessing": False,
        "align": None,
        "offset": False,
    }
    return {
        "type": "captionedImage",
        "content": [
            {"type": "image2", "attrs": attrs},
            {"type": "caption", "content": [{"type": "text", "text": caption}]},
        ],
    }


def convert(md: str, images: dict) -> dict:
    lines = md.split("\n")
    title = lines[0].lstrip("# ").strip()
    subtitle = lines[1].strip().strip("*")
    content: list[dict] = []
    paras = 0
    i = 2
    while i < len(lines):
        ln = lines[i].rstrip()
        i += 1
        if not ln:
            continue
        if ln.startswith("## "):
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": 2, "textAlign": None},
                    "content": [{"type": "text", "text": ln[3:]}],
                }
            )
        elif ln.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", ln)
            assert m, ln
            cap = ""
            if i < len(lines) and lines[i].startswith("*"):
                cap = lines[i].strip().strip("*")
                i += 1
            content.append(image_node(images[m.group(2)], m.group(1), cap))
        elif ln.startswith("Data: "):
            content.append(
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "marks": [{"type": "em"}], "text": ln + AI_NOTE},
                        {
                            "type": "text",
                            "marks": [
                                {"type": "em"},
                                {
                                    "type": "link",
                                    "attrs": {
                                        "href": EXPLAINER,
                                        "target": "_blank",
                                        "rel": "noopener noreferrer nofollow",
                                        "class": None,
                                    },
                                },
                            ],
                            "text": "How this works →",
                        },
                    ],
                }
            )
        else:
            content.append({"type": "paragraph", "content": inline(ln)})
            paras += 1
            if paras == 2:
                content.append(
                    {
                        "type": "subscribeWidget",
                        "attrs": {"url": "%%checkout_url%%", "text": "Subscribe", "language": "en"},
                        "content": [
                            {
                                "type": "ctaCaption",
                                "content": [
                                    {"type": "text", "text": "Free, after every United match."}
                                ],
                            }
                        ],
                    }
                )
    return {
        "title": title,
        "subtitle": subtitle,
        "body": {"type": "doc", "attrs": {"schemaVersion": "v1"}, "content": content},
    }


def main() -> None:
    md, images, out = (Path(a) for a in sys.argv[1:4])
    res = convert(md.read_text(), json.loads(images.read_text()))
    out.write_text(json.dumps(res, ensure_ascii=False))
    print(res["title"], "|", len(res["body"]["content"]), "nodes →", out)


if __name__ == "__main__":
    main()
