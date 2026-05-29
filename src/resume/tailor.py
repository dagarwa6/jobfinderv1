"""AI-powered resume tailoring.

Takes a job posting and the master resume YAML, sends both to Claude,
and returns a structured JSON specifying which bullets to use, how to
rewrite the summary, and how to order skills — all tailored to maximize
ATS match and recruiter relevance for the specific role.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

TAILOR_SYSTEM_PROMPT = """\
You are an expert resume tailor. Given a candidate's master resume (YAML) and a job posting, \
produce a tailored resume as strict JSON.

RULES:
1. The professional summary MUST be rewritten from scratch to mirror the job's language and \
emphasize the most relevant experience. Keep it 2-4 sentences. Include specific metrics.
2. For each role, select 2-4 bullets from the master list (by ID). You may lightly reword \
bullets to better echo the job posting's keywords, but do NOT fabricate experience.
3. Reorder skill categories so the most relevant category comes first. Within each category, \
put the most relevant skills first. Only include skills relevant to the role.
4. Decide whether to include: leadership section, honors, certifications, full project \
description vs short. Trade off space — a one-page resume is essential.
5. Pick the best education coursework variant (full or short) and graduation date variant.

OUTPUT FORMAT — strict JSON, no markdown fences:
{
  "summary": "<rewritten professional summary>",
  "experience": [
    {
      "company": "<company name>",
      "location": "<location>",
      "roles": [
        {
          "title": "<title>",
          "dates": "<dates>",
          "bullet_ids": ["id1", "id2", "id3"],
          "rewrites": {
            "id1": "<optional reworded text — omit key if no change needed>"
          }
        }
      ]
    }
  ],
  "project": {
    "name": "<full or short project name>",
    "bullet_ids": ["id1"],
    "rewrites": {}
  },
  "include_leadership": true/false,
  "include_honors": true/false,
  "include_certifications": true/false,
  "education_coursework": "full" or "short",
  "education_date_variant": "default" or "alt",
  "skills_order": ["analytics_bi", "technology", "strategy_product"],
  "skills_selected": {
    "analytics_bi": ["Power BI", "SQL", "Excel (advanced)"],
    "technology": ["Python", "SAP S/4 HANA"],
    "strategy_product": ["BPMN Process Mapping"]
  },
  "certifications_selected": ["AWS Cloud Foundations"],
  "skill_line_labels": {
    "analytics_bi": "Analytics & BI",
    "technology": "Technology",
    "strategy_product": "Strategy & Product",
    "certifications": "Certifications"
  }
}

IMPORTANT:
- Output ONLY valid JSON. No explanation, no markdown fences.
- Every bullet_id must exist in the master resume YAML.
- Keep the resume to ONE PAGE worth of content (~500-600 words max).
- Prioritize metrics and impact language that mirrors the job posting.
- MUST include ALL companies from the master resume in the experience array. \
You choose which bullets per role, but do NOT drop entire companies. For the \
intern role, 1-2 bullets is fine.
- Experience order MUST match the master resume YAML order (do NOT rearrange).
- Do NOT put "certifications" in skills_order — certifications are rendered \
separately via certifications_selected. skills_order should only contain \
skill category keys like "analytics_bi", "technology", "strategy_product", etc.
- Do NOT duplicate any category in skills_order.
"""


@dataclass
class TailoredResume:
    """Structured output from the AI tailor."""
    summary: str
    experience: list[dict]
    project: dict
    include_leadership: bool
    include_honors: bool
    include_certifications: bool
    education_coursework: str  # "full" or "short"
    education_date_variant: str  # "default" or "alt"
    skills_order: list[str]
    skills_selected: dict[str, list[str]]
    certifications_selected: list[str]
    skill_line_labels: dict[str, str]
    job_id: int = 0
    company_name: str = ""
    job_title: str = ""

    @classmethod
    def from_ai_response(cls, data: dict, job_id: int = 0,
                         company_name: str = "", job_title: str = "") -> TailoredResume:
        return cls(
            summary=data["summary"],
            experience=data["experience"],
            project=data.get("project", {}),
            include_leadership=data.get("include_leadership", False),
            include_honors=data.get("include_honors", True),
            include_certifications=data.get("include_certifications", True),
            education_coursework=data.get("education_coursework", "short"),
            education_date_variant=data.get("education_date_variant", "default"),
            skills_order=data.get("skills_order", ["analytics_bi", "technology", "strategy_product"]),
            skills_selected=data.get("skills_selected", {}),
            certifications_selected=data.get("certifications_selected", []),
            skill_line_labels=data.get("skill_line_labels", {}),
            job_id=job_id,
            company_name=company_name,
            job_title=job_title,
        )


def load_master_resume(path: Path | str) -> dict:
    """Load the master resume YAML."""
    with open(path) as f:
        return yaml.safe_load(f)


def _build_bullet_index(master: dict) -> dict[str, str]:
    """Build a flat id→text map of all bullets for quick lookup."""
    index = {}
    for exp in master.get("experience", []):
        for role in exp.get("roles", []):
            for bullet in role.get("bullets", []):
                index[bullet["id"]] = bullet["text"]
    for proj in master.get("projects", []):
        for bullet in proj.get("bullets", []):
            index[bullet["id"]] = bullet["text"]
    if master.get("leadership"):
        for item in master["leadership"]:
            for bullet in item.get("bullets", []):
                index[bullet["id"]] = bullet["text"]
    return index


class ResumeTailor:
    """AI-powered resume tailor using Claude."""

    def __init__(self, master_path: Path | str, model: str = "claude-haiku-4-5-20251001"):
        self.master = load_master_resume(master_path)
        self.master_path = Path(master_path)
        self.bullet_index = _build_bullet_index(self.master)
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def tailor(self, job: dict) -> TailoredResume:
        """Tailor the resume for a specific job posting.

        Args:
            job: Dict with at least 'id', 'company_name', 'title',
                 'description_text', 'matched_lane'.

        Returns:
            TailoredResume with AI-selected content.
        """
        master_yaml = self.master_path.read_text()

        job_text = (
            f"Company: {job.get('company_name', 'Unknown')}\n"
            f"Title: {job.get('title', 'Unknown')}\n"
            f"Lane: {job.get('matched_lane', '')}\n"
            f"Location: {job.get('location_parsed', '')}\n"
            f"Description:\n{job.get('description_text', '')[:4000]}"
        )

        user_prompt = (
            f"MASTER RESUME YAML:\n```yaml\n{master_yaml}\n```\n\n"
            f"JOB POSTING:\n{job_text}\n\n"
            "Produce the tailored resume JSON."
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=TAILOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tailor response: {e}\nRaw: {raw[:500]}")
            raise ValueError(f"AI returned invalid JSON: {e}")

        tailored = TailoredResume.from_ai_response(
            data,
            job_id=job.get("id", 0),
            company_name=job.get("company_name", ""),
            job_title=job.get("title", ""),
        )

        # Enforce master resume experience ordering (most recent first)
        self._enforce_experience_order(tailored)
        # Resolve bullet IDs to text, applying rewrites
        self._resolve_bullets(tailored)
        return tailored

    def _enforce_experience_order(self, tailored: TailoredResume):
        """Reorder experience blocks to match master resume order (most recent first).

        The AI sometimes reorders experience blocks. We preserve the master
        YAML ordering which is chronological (most recent first).
        """
        master_order = {
            exp["company"]: i for i, exp in enumerate(self.master.get("experience", []))
        }
        tailored.experience.sort(
            key=lambda e: master_order.get(e.get("company", ""), 999)
        )

    def _resolve_bullets(self, tailored: TailoredResume):
        """Replace bullet IDs with actual text, applying AI rewrites."""
        for exp in tailored.experience:
            for role in exp.get("roles", []):
                rewrites = role.get("rewrites", {})
                resolved = []
                for bid in role.get("bullet_ids", []):
                    if bid in rewrites:
                        resolved.append(rewrites[bid])
                    elif bid in self.bullet_index:
                        resolved.append(self.bullet_index[bid])
                    else:
                        logger.warning(f"Unknown bullet ID: {bid}")
                role["resolved_bullets"] = resolved

        if tailored.project:
            rewrites = tailored.project.get("rewrites", {})
            resolved = []
            for bid in tailored.project.get("bullet_ids", []):
                if bid in rewrites:
                    resolved.append(rewrites[bid])
                elif bid in self.bullet_index:
                    resolved.append(self.bullet_index[bid])
                else:
                    logger.warning(f"Unknown project bullet ID: {bid}")
            tailored.project["resolved_bullets"] = resolved
