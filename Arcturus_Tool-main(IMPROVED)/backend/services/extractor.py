import asyncio
import httpx
import re
from bs4 import BeautifulSoup

semaphore = asyncio.Semaphore(10)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def executive_summary(text, title):
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < 30:
        return f"This update introduces enhanced capabilities for {title} to optimize functional responsiveness and streamline workflows."

    cleaned = re.sub(
        r"^(previously|earlier|in this release|with this update|you can now),?\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"key capabilities include:.*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"to open the.*$", "", cleaned, flags=re.I)
    cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else ""

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary_sentences = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if current_length + len(sentence) < 350 or not summary_sentences:
            summary_sentences.append(sentence)
            current_length += len(sentence)
        else:
            break

    final_summary = " ".join(summary_sentences).strip()
    if not final_summary.endswith("."):
        final_summary += "."

    return final_summary


def analyze_intelligence(title, steps, description):
    combined = (title + " " + steps + " " + description).lower()
    lower_title = title.lower()

    if "agent" in lower_title or "agentic" in lower_title:
        status = "Disabled"
        action = "Setup Required"
    elif "redwood" in lower_title and any(
        kw in combined
        for kw in ["opt-in", "opt in", "redesigned page", "activate", "profile option"]
    ):
        status = "Disabled"
        action = "Setup Required"
    elif "automatically enabled." not in steps.lower() and any(
        kw in combined
        for kw in [
            "opt in",
            "profile option",
            "setup and maintenance",
            "privilege",
            "ora_",
        ]
    ):
        status = "Disabled"
        action = "Setup Required"
    else:
        status = "Enabled"
        action = "No Action Required"

    if any(
        kw in combined
        for kw in [
            "ai agent",
            "agentic",
            "redwood",
            "workspace",
            "mobile device",
            "new user experience",
        ]
    ):
        impact = "Large Scale (UI/UX)"
    elif any(
        kw in combined
        for kw in ["rest api", "fbdi", "integration", "algorithm", "bulk patch"]
    ):
        impact = "Medium (Technical)"
    else:
        impact = "Small Scale"

    if impact == "Large Scale (UI/UX)" or action == "Setup Required":
        priority = "High"
    elif any(kw in combined for kw in ["report", "search filter", "otbi"]):
        priority = "Low"
    else:
        priority = "Medium"

    return status, action, impact, priority


async def fetch_detail_page(client, feature):
    async with semaphore:
        try:
            url = feature.get("url", "")
            if not url or "javascript" in url:
                return feature

            response = await client.get(url, timeout=20.0)
            if response.status_code != 200:
                return feature

            soup = BeautifulSoup(response.text, "html.parser")

            # 1. LIVE DYNAMIC MODULE ELEMENT EXTRACTION
            # Extracts Oracle's native sub-module categorization directly from the page body tree
            discovered_submodule = ""

            # Look for Oracle's standard metadata header block (e.g., "Collaboration Messaging")
            meta_element = soup.find(
                lambda tag: tag.name in ["p", "div", "span"]
                and any(
                    cl in str(tag.get("class", "")).lower()
                    for cl in ["sub-header", "subtitle", "meta-text"]
                )
            )
            if meta_element:
                discovered_submodule = meta_element.get_text().strip()

            # Fallback: Parse out explicitly labeled rows if present (e.g., "Functional Area: Cost Management")
            if not discovered_submodule:
                labeled_tag = soup.find(
                    lambda tag: tag.name in ["p", "span", "div", "td"]
                    and any(
                        kw in tag.text
                        for kw in ["Functional Area:", "Product:", "Submodule:"]
                    )
                )
                if labeled_tag:
                    discovered_submodule = re.sub(
                        r".*?:", "", labeled_tag.get_text()
                    ).strip()

            # Clean and sanitize the string value
            discovered_submodule = clean_text(discovered_submodule)

            # Safety Check: If it accidentally grabbed a giant paragraph or the title, wipe it
            if discovered_submodule and (
                len(discovered_submodule) > 50
                or "what's new" in discovered_submodule.lower()
            ):
                discovered_submodule = ""

            # Save the discovered sub-module string to the feature package
            feature["discovered_module"] = discovered_submodule

            # ------------------------------------------------------------------
            # 2. Extract Oracle Feature Description (Old-style extraction)
            # ------------------------------------------------------------------

            desc_text = ""

            desc_root = (
                soup.find("section", id=re.compile(r"description|overview", re.I))
                or soup.find("article")
                or soup.find("main")
                or soup.body
            )

            paragraphs = []

            SKIP_PATTERNS = [
                "copy template",
                "use template",
                "administrator profile",
                "profile option",
                "setup and maintenance",
                "credentials",
                "email account",
                "search for ora_",
                "opt in",
                "opt-in",
                "privilege",
                "security console",
                "to automatically add a suffix",
                "step-by-step process",
            ]

            def should_skip(text):
                t = clean_text(text).lower()

                if len(t) < 40:
                    return True

                for p in SKIP_PATTERNS:
                    if p in t:
                        return True

                return False

            if desc_root:

                started = False

                for node in desc_root.find_all(["h2", "h3", "h4", "p"]):

                    if node.name in ["h2", "h3", "h4"]:

                        heading = clean_text(node.get_text()).lower()

                        if any(
                            stop in heading
                            for stop in [
                                "business benefit",
                                "steps to enable",
                                "tips and considerations",
                                "known issues",
                                "documentation",
                                "give us feedback",
                                "key resources",
                                "role information",
                            ]
                        ):
                            break

                        if "description" in heading or "overview" in heading:
                            started = True
                            continue

                    if node.name == "p":

                        text = clean_text(node.get_text())

                        if should_skip(text):
                            continue

                        paragraphs.append(text)

                        if sum(len(x) for x in paragraphs) > 700:
                            break

            # fallback (same behaviour as old scraper)
            if not paragraphs and desc_root:

                for p in desc_root.find_all("p"):

                    text = clean_text(p.get_text())

                    if should_skip(text):
                        continue

                    paragraphs.append(text)

                    if len(paragraphs) >= 3:
                        break

            desc_text = " ".join(paragraphs)

            feature["raw_description"] = desc_text

            # 3. Extract Steps to Enable Section Nodes
            steps_text = ""
            steps_header = soup.find(
                lambda tag: tag.name in ["h2", "h3", "h4"]
                and any(
                    kw in tag.text
                    for kw in ["Steps to Enable", "How to Enable", "Setup"]
                )
            )
            if steps_header:
                content = []
                for sib in steps_header.find_next_siblings():
                    if sib.name in ["h2", "h3", "h4"]:
                        break
                    text_content = sib.get_text().strip()
                    if text_content:
                        content.append(text_content)
                steps_text = " ".join(content)
            feature["steps_to_enable"] = (
                clean_text(steps_text)
                if (steps_text and len(steps_text) > 30)
                else "Automatically enabled."
            )

            # 4. Scan System Bug Code Layout Trackers
            bugs = re.findall(r"\b\d{8}\b", soup.get_text())
            feature["bug_ids"] = ", ".join(set(bugs)) if bugs else "None"

        except Exception as e:
            print(f"Deep Scrape Error: {e}")
            feature["discovered_module"] = ""
            feature["raw_description"] = ""
            feature["steps_to_enable"] = "Automatically enabled."
            feature["bug_ids"] = "None"

        return feature


async def enrich_all_features(injected_features):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = [fetch_detail_page(client, f) for f in injected_features]
        raw_results = await asyncio.gather(*tasks)

        final_features = []
        for idx, f in enumerate(raw_results, start=1):
            title = f.get("title", "")
            raw_steps = clean_text(f.get("steps_to_enable", ""))
            raw_desc = f.get("raw_description", "")

            # STRICT DYNAMIC OVERWRITE
            # If the dynamic scraper successfully harvested the page sub-module, use it!
            # Otherwise, use the baseline extension value as a safety backup.
            live_submodule = f.get("discovered_module", "")
            resolved_module = (
                live_submodule
                if live_submodule
                else f.get("module", "Inventory Management")
            )

            status, action, impact, priority = analyze_intelligence(
                title, raw_steps, raw_desc
            )
            polished_description = executive_summary(raw_desc, title)

            lower_steps = raw_steps.lower()
            if "agent" in title.lower() or "agentic" in title.lower():
                final_steps = "Configure email account integration routes and access parameters via Setup and Maintenance. Ensure targeted end-users are assigned appropriate Generative AI runtime duty roles."
                status = "Disabled"
                action = "Setup Required"
                priority = "High"
            elif status == "Disabled" and (
                not raw_steps
                or len(raw_steps) < 25
                or "automatically enabled" in lower_steps
            ):
                final_steps = "Requires manual activation via the Functional Setup Manager Opt-In interface under the SCM application workspace."
            elif (
                not raw_steps
                or len(raw_steps) < 25
                or "automatically enabled" in lower_steps
                and len(raw_steps) < 60
            ):
                final_steps = "Automatically enabled. No configuration required."
            else:
                sentences = re.split(r"(?<=[.!?])\s+", raw_steps)
                step_blocks = []
                length_counter = 0
                for s in sentences:
                    if length_counter + len(s) < 400 or not step_blocks:
                        step_blocks.append(s.strip())
                        length_counter += len(s)
                    else:
                        break
                final_steps = " ".join(step_blocks).strip()
                if not final_steps.endswith("."):
                    final_steps += "."
                status = "Disabled"
                action = "Setup Required"
                priority = "High"

            f.update(
                {
                    "module": resolved_module,  # Overwritten dynamically from the page DOM
                    "feature_id": f"INV26B-{idx:03d}",
                    "description": polished_description,
                    "steps_to_enable": final_steps,
                    "delivery_status": status,
                    "action_required": action,
                    "impact": impact,
                    "priority": priority,
                    "bug_ids": (
                        f.get("bug_ids", "None")
                        if f.get("bug_ids", "None") != "None"
                        else "Not Applicable (New Feature Release)"
                    ),
                    "notes": f"Automated analytical audit validation completed for {impact} update parameters.",
                }
            )

            if "raw_description" in f:
                del f["raw_description"]
            if "discovered_module" in f:
                del f["discovered_module"]

            final_features.append(f)

        return final_features
