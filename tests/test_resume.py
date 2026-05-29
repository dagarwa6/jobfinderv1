"""Tests for resume tailoring and PDF generation."""
import json
from pathlib import Path

import pytest

from src.resume.tailor import TailoredResume, load_master_resume, _build_bullet_index
from src.resume.pdf_gen import generate_resume_pdf

CONFIG_DIR = Path(__file__).parent.parent / "config"
MASTER_PATH = CONFIG_DIR / "master_resume.yml"


class TestMasterResume:
    def test_load_master(self):
        master = load_master_resume(MASTER_PATH)
        assert master["contact"]["full_name"] == "Devansh Agarwal"
        assert len(master["experience"]) >= 2
        assert len(master["education"]) == 2

    def test_bullet_index(self):
        master = load_master_resume(MASTER_PATH)
        index = _build_bullet_index(master)
        assert "gsu_llm_platform" in index
        assert "genpact_am_dashboard" in index
        assert "project_langgraph" in index
        assert len(index) > 15

    def test_summary_variants_exist(self):
        master = load_master_resume(MASTER_PATH)
        variants = master["summary_variants"]
        assert "strategy_ops" in variants
        assert "analytics_default" in variants
        assert "cybersecurity" in variants
        assert "data_analyst" in variants


class TestTailoredResume:
    def test_from_ai_response(self):
        data = {
            "summary": "Test summary",
            "experience": [
                {
                    "company": "Genpact LLC",
                    "location": "Chicago, IL",
                    "roles": [
                        {
                            "title": "Assistant Manager",
                            "dates": "March 2023-July 2024",
                            "bullet_ids": ["genpact_am_dashboard", "genpact_am_governance"],
                            "rewrites": {},
                        }
                    ],
                }
            ],
            "project": {
                "name": "AI-Driven Risk Platform",
                "bullet_ids": ["project_langgraph_short"],
                "rewrites": {},
            },
            "include_leadership": False,
            "include_honors": True,
            "include_certifications": True,
            "education_coursework": "short",
            "education_date_variant": "default",
            "skills_order": ["analytics_bi", "technology"],
            "skills_selected": {
                "analytics_bi": ["Power BI", "SQL"],
                "technology": ["Python", "SAP S/4 HANA"],
            },
            "certifications_selected": ["AWS Cloud Foundations"],
            "skill_line_labels": {
                "analytics_bi": "Analytics & BI",
                "technology": "Technology",
                "certifications": "Certifications",
            },
        }
        tailored = TailoredResume.from_ai_response(data, job_id=42, company_name="Google", job_title="BA")
        assert tailored.summary == "Test summary"
        assert tailored.job_id == 42
        assert len(tailored.experience) == 1
        assert tailored.include_certifications is True


class TestPDFGeneration:
    def test_generates_pdf(self, tmp_path):
        master = load_master_resume(MASTER_PATH)
        tailored = TailoredResume(
            summary=(
                "Strategy and analytics professional with 2+ years of consulting "
                "experience driving measurable business outcomes. Combines Power BI, "
                "SQL, and Python expertise with management consulting at Genpact."
            ),
            experience=[
                {
                    "company": "Georgia State University & Massachusetts Institute of Technology",
                    "location": "Atlanta, GA",
                    "roles": [
                        {
                            "title": "Graduate Research Assistant",
                            "dates": "August 2025-Present",
                            "bullet_ids": ["gsu_llm_platform", "gsu_eval_frameworks"],
                            "rewrites": {},
                            "resolved_bullets": [
                                "Co-developed an LLM-based Python tutoring platform in collaboration with MIT",
                                "Built evaluation frameworks to measure platform effectiveness",
                            ],
                        }
                    ],
                },
                {
                    "company": "Genpact LLC",
                    "location": "Chicago, IL",
                    "roles": [
                        {
                            "title": "Assistant Manager, Operations Strategy & Analytics",
                            "dates": "March 2023-July 2024",
                            "bullet_ids": ["genpact_am_dashboard", "genpact_am_governance"],
                            "rewrites": {},
                            "resolved_bullets": [
                                "Designed and owned a weekly executive dashboard in Power BI, reducing cost per order by 15%",
                                "Established a cross-functional governance structure with finance and operations stakeholders",
                            ],
                        },
                        {
                            "title": "Senior Associate, Process Strategy & Transformation",
                            "dates": "June 2022-March 2023",
                            "bullet_ids": ["genpact_sa_iops", "genpact_sa_headcount"],
                            "rewrites": {},
                            "resolved_bullets": [
                                "Led the operating model design for the iOps digital transformation program",
                                "Built automated statistical headcount forecasting models for 1,000+ employees",
                            ],
                        },
                        {
                            "title": "Consulting Intern, Strategy & Operations",
                            "dates": "June 2021-August 2021",
                            "bullet_ids": ["genpact_intern_highradius", "genpact_intern_financial"],
                            "rewrites": {},
                            "resolved_bullets": [
                                "Evaluated HighRadius OTC module integration within SAP ERP",
                                "Conducted financial analysis using 10-K statements",
                            ],
                        },
                    ],
                },
            ],
            project={
                "name": "AI-Driven Risk Quantification Platform",
                "bullet_ids": ["project_langgraph_short"],
                "rewrites": {},
                "resolved_bullets": [
                    "Architected a 5-agent LangGraph pipeline that ingests organizational documents and produces board-ready risk assessments"
                ],
            },
            include_leadership=False,
            include_honors=True,
            include_certifications=True,
            education_coursework="short",
            education_date_variant="default",
            skills_order=["analytics_bi", "technology", "strategy_product"],
            skills_selected={
                "analytics_bi": ["Power BI", "Tableau", "SQL", "Excel (advanced)", "Visio", "Executive Dashboarding"],
                "technology": ["SAP S/4 HANA", "Python", "LangChain/LangGraph", "GenAI/LLM", "HTML/CSS", "MySQL"],
                "strategy_product": ["BPMN Process Mapping", "JIRA", "Stakeholder Management"],
            },
            certifications_selected=["Google Generative AI", "Google LLMs", "AWS Cloud Foundations", "AWS Cloud Security"],
            skill_line_labels={
                "analytics_bi": "Analytics & BI",
                "technology": "Technology",
                "strategy_product": "Strategy & Product",
                "certifications": "Certifications",
            },
            job_id=42,
            company_name="TestCo",
            job_title="Business Analyst",
        )

        pdf_path = generate_resume_pdf(tailored, master, tmp_path)
        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        assert pdf_path.stat().st_size > 2000  # Non-trivial PDF
        assert "Agarwal_Devansh_Resume_TestCo" in pdf_path.name
